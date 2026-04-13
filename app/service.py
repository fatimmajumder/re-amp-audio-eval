from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean

from .artifacts import get_artifact_path, write_run_artifacts
from .demo_data import (
    build_catalog,
    build_seed_payloads,
    build_seed_workspaces,
    resolve_dataset_name,
    resolve_scenarios,
)
from .evaluation import evaluate_payload
from .public_datasets import build_public_datasets, get_public_dataset
from .repository import RunRepository, WorkspaceRepository
from .schemas import (
    ArtifactCacheStatus,
    BenchmarkRun,
    CompareResponse,
    LeaderboardEntry,
    OverviewResponse,
    RecentRunEntry,
    RegressionAlert,
    RunCreate,
    RunLineage,
    ScenarioDelta,
    SliceDelta,
    SystemStatus,
    WorkspaceCreate,
    WorkspaceRecord,
)
from .settings import AppSettings


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RunService:
    def __init__(
        self,
        repository: RunRepository,
        workspace_repository: WorkspaceRepository,
        artifacts_root: Path,
        datasets_root: Path,
        settings: AppSettings,
    ):
        self.repository = repository
        self.workspace_repository = workspace_repository
        self.artifacts_root = artifacts_root
        self.datasets_root = datasets_root
        self.settings = settings
        self.artifacts_root.mkdir(parents=True, exist_ok=True)
        self.datasets_root.mkdir(parents=True, exist_ok=True)

    def ensure_seed_workspaces(self) -> None:
        if self.workspace_repository.list_workspaces():
            self._refresh_all_workspace_stats()
            return

        for workspace in build_seed_workspaces():
            self.workspace_repository.save_workspace(workspace)
        self._refresh_all_workspace_stats()

    def ensure_seed_data(self) -> None:
        self.ensure_seed_workspaces()
        if self.repository.list_runs():
            self._refresh_all_workspace_stats()
            return

        for payload in build_seed_payloads():
            run = self.create_run(payload)
            self.execute_run(run.run_id)

    def get_catalog(self):
        return build_catalog(public_datasets=self.list_public_datasets())

    def list_public_datasets(self):
        return build_public_datasets(self.datasets_root)

    def list_workspaces(self) -> list[WorkspaceRecord]:
        return self.workspace_repository.list_workspaces()

    def create_workspace(self, payload: WorkspaceCreate) -> WorkspaceRecord:
        slug = _slugify(payload.name)
        base_slug = slug
        index = 2
        while self.workspace_repository.get_workspace(slug):
            slug = f"{base_slug}-{index}"
            index += 1

        workspace = WorkspaceRecord(
            workspace_id=slug,
            name=payload.name,
            description=payload.description,
            owner=payload.owner,
            tenant_name=payload.tenant_name,
            tenant_slug=payload.tenant_slug,
            project_name=payload.project_name,
            project_slug=payload.project_slug,
            focus_areas=payload.focus_areas,
            default_benchmark=payload.default_benchmark,
            default_model=payload.default_model,
            dataset_preferences=payload.dataset_preferences,
            default_prompt_schema=payload.default_prompt_schema,
            default_judge_configuration=payload.default_judge_configuration,
        )
        return self.workspace_repository.save_workspace(workspace)

    def list_runs(self) -> list[BenchmarkRun]:
        return self.repository.list_runs()

    def get_run(self, run_id: str) -> BenchmarkRun | None:
        return self.repository.get_run(run_id)

    def get_system_status(self) -> SystemStatus:
        return SystemStatus(
            app_version=self.settings.app_version,
            storage_backend=self.settings.storage_backend,  # type: ignore[arg-type]
            database_enabled=self.settings.database_enabled,
            database_url_hint=self.settings.database_url_hint,
            inline_worker_enabled=self.settings.inline_worker_enabled,
            worker_count=self.settings.worker_count,
            multi_tenant_enabled=self.settings.multi_tenant_enabled,
            cache_enabled=self.settings.cache_enabled,
            artifact_root=str(self.artifacts_root),
            dataset_root=str(self.datasets_root),
        )

    def create_run(self, payload: RunCreate, *, source_run_id: str | None = None) -> BenchmarkRun:
        resolved_payload = payload.model_copy(
            update={
                "scenarios": resolve_scenarios(payload),
                "dataset_name": resolve_dataset_name(payload),
            }
        )
        if not resolved_payload.scenarios:
            raise ValueError("at least one scenario is required to create a run")

        workspace = self._resolve_workspace(resolved_payload.workspace_id)
        public_dataset = None
        dataset_name = resolved_payload.dataset_name
        dataset_source_url = None
        if resolved_payload.public_dataset_id:
            public_dataset = get_public_dataset(self.datasets_root, resolved_payload.public_dataset_id)
            if not public_dataset:
                raise ValueError(f"unknown public dataset: {resolved_payload.public_dataset_id}")
            dataset_name = public_dataset.name
            dataset_source_url = public_dataset.source_url

        lineage = _build_lineage(
            payload=resolved_payload,
            workspace=workspace,
            dataset_name=dataset_name,
            public_dataset=public_dataset,
        )
        baseline_run = (
            self.require_completed_run(resolved_payload.baseline_run_id)
            if resolved_payload.baseline_run_id
            else self._find_comparable_baseline(
                benchmark_name=resolved_payload.benchmark_name,
                workspace_id=workspace.workspace_id,
                dataset_name=dataset_name,
                public_dataset_id=resolved_payload.public_dataset_id,
            )
        )
        cache_status = _seed_cache_status(
            lineage=lineage,
            namespace=f"{workspace.tenant_slug}/{workspace.project_slug}",
            scenario_count=len(resolved_payload.scenarios),
            baseline_run=baseline_run,
        )

        run = BenchmarkRun(
            benchmark_name=resolved_payload.benchmark_name,
            model_name=resolved_payload.model_name,
            dataset_name=dataset_name,
            seed=resolved_payload.seed,
            notes=resolved_payload.notes,
            workspace_id=workspace.workspace_id,
            workspace_name=workspace.name,
            tenant_slug=workspace.tenant_slug,
            tenant_name=workspace.tenant_name,
            project_slug=workspace.project_slug,
            project_name=workspace.project_name,
            public_dataset_id=resolved_payload.public_dataset_id,
            dataset_source_url=dataset_source_url,
            baseline_run_id=baseline_run.run_id if baseline_run else None,
            scenarios=[scenario.model_copy(deep=True) for scenario in resolved_payload.scenarios],
            source_run_id=source_run_id,
            status="queued",
            progress=5,
            lineage=lineage,
            cache_status=cache_status,
        )
        self.repository.save_run(run)
        self._refresh_workspace_stats(workspace.workspace_id)
        return run

    def execute_run(self, run_id: str) -> BenchmarkRun:
        existing = self.require_run(run_id)
        payload = RunCreate(
            benchmark_name=existing.benchmark_name,
            model_name=existing.model_name,
            dataset_name=existing.dataset_name,
            seed=existing.seed,
            notes=existing.notes,
            workspace_id=existing.workspace_id,
            public_dataset_id=existing.public_dataset_id,
            baseline_run_id=existing.baseline_run_id,
            prompt_schema_revision=existing.lineage.prompt_schema_revision if existing.lineage else None,
            tokenizer_revision=existing.lineage.tokenizer_revision if existing.lineage else None,
            judge_configuration=existing.lineage.judge_configuration if existing.lineage else None,
            scenarios=[scenario.model_copy(deep=True) for scenario in existing.scenarios],
        )

        running = existing.model_copy(
            update={
                "status": "running",
                "progress": 38,
                "started_at": utc_now(),
            },
            deep=True,
        )
        self.repository.save_run(running)

        try:
            bundle = evaluate_payload(payload, run_id)
            baseline = (
                self.require_completed_run(existing.baseline_run_id)
                if existing.baseline_run_id
                else self._find_comparable_baseline(
                    benchmark_name=existing.benchmark_name,
                    workspace_id=existing.workspace_id,
                    dataset_name=existing.dataset_name,
                    public_dataset_id=existing.public_dataset_id,
                    exclude_run_id=existing.run_id,
                )
            )
            regressions = _build_regression_alerts(bundle.slices, baseline)
            cache_status = _refresh_cache_status(
                cache_status=existing.cache_status,
                lineage=existing.lineage,
                baseline_run=baseline,
                result_count=len(bundle.results),
            )
            summary = bundle.summary.model_copy(
                update={
                    "headline": _build_headline(bundle.summary.headline, regressions, cache_status),
                    "regression_alert_count": len(regressions),
                    "cache_hit_ratio": cache_status.hit_ratio if cache_status else 0.0,
                },
                deep=True,
            )
            public_dataset = (
                get_public_dataset(self.datasets_root, existing.public_dataset_id)
                if existing.public_dataset_id
                else None
            )
            artifacts = write_run_artifacts(
                self.artifacts_root,
                running,
                summary,
                bundle.results,
                bundle.slices,
                public_dataset=public_dataset,
                lineage=existing.lineage,
                cache_status=cache_status,
                regressions=regressions,
                baseline_run=baseline,
            )
            final_status = "replayed" if existing.source_run_id else "completed"
            completed = running.model_copy(
                update={
                    "status": final_status,
                    "progress": 100,
                    "completed_at": utc_now(),
                    "baseline_run_id": baseline.run_id if baseline else existing.baseline_run_id,
                    "results": bundle.results,
                    "summary": summary,
                    "artifacts": artifacts,
                    "slices": bundle.slices,
                    "lineage": existing.lineage,
                    "cache_status": cache_status,
                    "regressions": regressions,
                    "error_message": None,
                },
                deep=True,
            )
            self.repository.save_run(completed)
            self._refresh_workspace_stats(completed.workspace_id)
            return completed
        except Exception as exc:
            failed = running.model_copy(
                update={
                    "status": "failed",
                    "progress": 100,
                    "completed_at": utc_now(),
                    "error_message": str(exc),
                },
                deep=True,
            )
            self.repository.save_run(failed)
            self._refresh_workspace_stats(failed.workspace_id)
            raise

    def execute_next_queued_run(self) -> BenchmarkRun | None:
        queued = sorted(
            (run for run in self.repository.list_runs() if run.status == "queued"),
            key=lambda item: item.created_at,
        )
        if not queued:
            return None
        return self.execute_run(queued[0].run_id)

    def replay_run(self, run_id: str) -> BenchmarkRun:
        source = self.require_run(run_id)
        payload = RunCreate(
            benchmark_name=source.benchmark_name,
            model_name=source.model_name,
            dataset_name=source.dataset_name,
            seed=source.seed,
            notes=f"Replay of {source.run_id}",
            workspace_id=source.workspace_id,
            public_dataset_id=source.public_dataset_id,
            baseline_run_id=source.run_id,
            prompt_schema_revision=source.lineage.prompt_schema_revision if source.lineage else None,
            tokenizer_revision=source.lineage.tokenizer_revision if source.lineage else None,
            judge_configuration=source.lineage.judge_configuration if source.lineage else None,
            scenarios=[scenario.model_copy(deep=True) for scenario in source.scenarios],
        )
        replay = self.create_run(payload, source_run_id=source.run_id)
        return replay

    def compare_runs(self, left_run_id: str, right_run_id: str) -> CompareResponse:
        left = self.require_completed_run(left_run_id)
        right = self.require_completed_run(right_run_id)

        left_scores = {item.scenario_name: item for item in left.results}
        right_scores = {item.scenario_name: item for item in right.results}
        shared_names = sorted(set(left_scores) & set(right_scores))

        scenario_deltas: list[ScenarioDelta] = []
        for name in shared_names:
            left_item = left_scores[name]
            right_item = right_scores[name]
            delta = round(right_item.robustness_score - left_item.robustness_score, 4)
            scenario_deltas.append(
                ScenarioDelta(
                    scenario_name=name,
                    left_score=left_item.robustness_score,
                    right_score=right_item.robustness_score,
                    delta=delta,
                    trend=_delta_trend(delta),
                )
            )

        left_slices = {item.slice_name: item for item in left.slices}
        right_slices = {item.slice_name: item for item in right.slices}
        shared_slice_names = sorted(set(left_slices) & set(right_slices))
        slice_deltas: list[SliceDelta] = []
        regression_alerts: list[RegressionAlert] = []
        for name in shared_slice_names:
            left_item = left_slices[name]
            right_item = right_slices[name]
            delta = round(right_item.score - left_item.score, 4)
            slice_deltas.append(
                SliceDelta(
                    slice_name=name,
                    left_score=left_item.score,
                    right_score=right_item.score,
                    delta=delta,
                    trend=_delta_trend(delta),
                )
            )
            if delta < -0.03:
                regression_alerts.append(
                    RegressionAlert(
                        slice_name=name,
                        previous_score=left_item.score,
                        current_score=right_item.score,
                        delta=delta,
                        severity=_severity_for_delta(delta),
                        note=f"{name} regressed when moving from {left.model_name} to {right.model_name}.",
                    )
                )

        score_delta = round(
            (right.summary.aggregate_score if right.summary else 0.0)
            - (left.summary.aggregate_score if left.summary else 0.0),
            4,
        )
        if score_delta > 0.03:
            verdict = "right run materially improves robustness"
        elif score_delta < -0.03:
            verdict = "right run regresses against the baseline"
        else:
            verdict = "runs are effectively tied"

        biggest_swing = max(scenario_deltas, key=lambda item: abs(item.delta), default=None)
        headline = (
            f"Largest movement appears in {biggest_swing.scenario_name}."
            if biggest_swing
            else "No overlapping scenarios were available to compare."
        )

        return CompareResponse(
            left_run_id=left.run_id,
            right_run_id=right.run_id,
            left_label=f"{left.model_name} · {left.benchmark_name}",
            right_label=f"{right.model_name} · {right.benchmark_name}",
            score_delta=score_delta,
            verdict=verdict,
            headline=headline,
            scenario_deltas=scenario_deltas,
            slice_deltas=slice_deltas,
            regression_alerts=regression_alerts,
            lineage_summary=_summarize_lineage_delta(left.lineage, right.lineage),
        )

    def get_overview(self) -> OverviewResponse:
        runs = self.repository.list_runs()
        terminal_runs = [run for run in runs if run.summary is not None]
        replay_runs = [run for run in runs if run.source_run_id]
        active_runs = [run for run in runs if run.status in {"queued", "running"}]

        if terminal_runs:
            average_score = round(fmean(run.summary.aggregate_score for run in terminal_runs if run.summary), 4)
            average_latency_ms = round(
                fmean(run.summary.average_latency_ms for run in terminal_runs if run.summary),
                1,
            )
        else:
            average_score = 0.0
            average_latency_ms = 0.0

        model_groups: dict[str, list[BenchmarkRun]] = {}
        for run in terminal_runs:
            model_groups.setdefault(run.model_name, []).append(run)

        leaderboard: list[LeaderboardEntry] = []
        for model_name, model_runs in model_groups.items():
            leaderboard.append(
                LeaderboardEntry(
                    model_name=model_name,
                    benchmark_count=len(model_runs),
                    average_score=round(
                        fmean(run.summary.aggregate_score for run in model_runs if run.summary),
                        4,
                    ),
                    average_latency_ms=round(
                        fmean(run.summary.average_latency_ms for run in model_runs if run.summary),
                        1,
                    ),
                )
            )
        leaderboard.sort(key=lambda item: item.average_score, reverse=True)

        best_model_name = leaderboard[0].model_name if leaderboard else "n/a"
        best_score = leaderboard[0].average_score if leaderboard else 0.0

        recent_runs = [
            RecentRunEntry(
                run_id=run.run_id,
                benchmark_name=run.benchmark_name,
                model_name=run.model_name,
                workspace_name=run.workspace_name,
                status=run.status,
                aggregate_score=run.summary.aggregate_score if run.summary else None,
                created_at=run.created_at,
            )
            for run in runs[:6]
        ]

        return OverviewResponse(
            total_runs=len(runs),
            active_runs=len(active_runs),
            replay_runs=len(replay_runs),
            average_score=average_score,
            average_latency_ms=average_latency_ms,
            best_model_name=best_model_name,
            best_score=best_score,
            workspace_count=len(self.workspace_repository.list_workspaces()),
            public_dataset_count=len(self.list_public_datasets()),
            leaderboard=leaderboard,
            recent_runs=recent_runs,
        )

    def get_artifact_path(self, run_id: str, filename: str) -> Path:
        self.require_run(run_id)
        return get_artifact_path(self.artifacts_root, run_id, filename)

    def require_run(self, run_id: str) -> BenchmarkRun:
        run = self.repository.get_run(run_id)
        if not run:
            raise KeyError(run_id)
        return run

    def require_completed_run(self, run_id: str | None) -> BenchmarkRun:
        if not run_id:
            raise ValueError("run_id is required")
        run = self.require_run(run_id)
        if not run.summary or run.status not in {"completed", "replayed"}:
            raise ValueError(run_id)
        return run

    def _resolve_workspace(self, workspace_id: str | None) -> WorkspaceRecord:
        self.ensure_seed_workspaces()
        if workspace_id:
            workspace = self.workspace_repository.get_workspace(workspace_id)
            if not workspace:
                raise ValueError(f"unknown workspace: {workspace_id}")
            return workspace

        available = self.workspace_repository.list_workspaces()
        if not available:
            raise ValueError("no workspaces available")
        return available[0]

    def _find_comparable_baseline(
        self,
        *,
        benchmark_name: str,
        workspace_id: str,
        dataset_name: str,
        public_dataset_id: str | None,
        exclude_run_id: str | None = None,
    ) -> BenchmarkRun | None:
        for run in self.repository.list_runs():
            if run.run_id == exclude_run_id:
                continue
            if run.status not in {"completed", "replayed"} or not run.summary:
                continue
            if run.workspace_id != workspace_id or run.benchmark_name != benchmark_name:
                continue
            if public_dataset_id and run.public_dataset_id != public_dataset_id:
                continue
            if not public_dataset_id and run.dataset_name != dataset_name:
                continue
            return run
        return None

    def _refresh_all_workspace_stats(self) -> None:
        for workspace in self.workspace_repository.list_workspaces():
            self._refresh_workspace_stats(workspace.workspace_id)

    def _refresh_workspace_stats(self, workspace_id: str) -> None:
        workspace = self.workspace_repository.get_workspace(workspace_id)
        if not workspace:
            return

        runs = [run for run in self.repository.list_runs() if run.workspace_id == workspace_id]
        last_run_at = max((run.created_at for run in runs), default=None)
        updated = workspace.model_copy(
            update={
                "run_count": len(runs),
                "last_run_at": last_run_at,
            },
            deep=True,
        )
        self.workspace_repository.save_workspace(updated)


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or "workspace"


def _digest(*parts: str) -> str:
    return hashlib.sha256("::".join(parts).encode("utf-8")).hexdigest()


def _build_lineage(
    *,
    payload: RunCreate,
    workspace: WorkspaceRecord,
    dataset_name: str,
    public_dataset,
) -> RunLineage:
    dataset_manifest = (
        public_dataset.availability.manifest_path
        if public_dataset and public_dataset.availability.manifest_path
        else f"registry://{public_dataset.dataset_id}/latest"
        if public_dataset
        else f"label://{_slugify(dataset_name)}"
    )
    dataset_revision = _digest(dataset_name, public_dataset.dataset_id if public_dataset else "custom")[:12]
    prompt_schema_revision = payload.prompt_schema_revision or workspace.default_prompt_schema
    tokenizer_revision = payload.tokenizer_revision or "audio-bpe-v3"
    judge_configuration = payload.judge_configuration or workspace.default_judge_configuration
    model_artifact = f"{payload.model_name}:{_digest(payload.model_name, prompt_schema_revision)[:10]}"
    scoring_revision = "scorecard-v2.3"
    lineage_tags = sorted(
        {
            workspace.tenant_slug,
            workspace.project_slug,
            *(scenario.category for scenario in payload.scenarios),
            *(scenario.name for scenario in payload.scenarios[:3]),
        }
    )
    execution_fingerprint = _digest(
        workspace.workspace_id,
        payload.benchmark_name,
        payload.model_name,
        dataset_revision,
        prompt_schema_revision,
        tokenizer_revision,
        judge_configuration,
        ",".join(sorted(scenario.name for scenario in payload.scenarios)),
        str(payload.seed),
    )
    return RunLineage(
        dataset_revision=dataset_revision,
        dataset_manifest=dataset_manifest,
        prompt_schema_revision=prompt_schema_revision,
        tokenizer_revision=tokenizer_revision,
        model_artifact=model_artifact,
        judge_configuration=judge_configuration,
        scoring_revision=scoring_revision,
        execution_fingerprint=execution_fingerprint,
        lineage_tags=lineage_tags,
    )


def _seed_cache_status(
    *,
    lineage: RunLineage,
    namespace: str,
    scenario_count: int,
    baseline_run: BenchmarkRun | None,
) -> ArtifactCacheStatus:
    base = 0.54 if baseline_run else 0.16
    signal = int(_digest(lineage.execution_fingerprint, namespace)[:6], 16) / 0xFFFFFF
    hit_ratio = round(min(0.94, base + signal * (0.22 if baseline_run else 0.18)), 4)
    restored_artifacts = max(1, round(scenario_count * 2 * hit_ratio))
    reused_judge_calls = max(2, round(scenario_count * 18 * hit_ratio))
    return ArtifactCacheStatus(
        cache_namespace=namespace,
        cache_key=lineage.execution_fingerprint[:18],
        hit_ratio=hit_ratio,
        restored_artifacts=restored_artifacts,
        reused_judge_calls=reused_judge_calls,
        estimated_gpu_seconds_saved=round(reused_judge_calls * 0.41, 1),
    )


def _refresh_cache_status(
    *,
    cache_status: ArtifactCacheStatus | None,
    lineage: RunLineage | None,
    baseline_run: BenchmarkRun | None,
    result_count: int,
) -> ArtifactCacheStatus | None:
    if not cache_status or not lineage:
        return cache_status
    if baseline_run and baseline_run.lineage:
        shared_fingerprint = sum(
            1
            for left, right in zip(lineage.execution_fingerprint, baseline_run.lineage.execution_fingerprint)
            if left == right
        )
        overlap = shared_fingerprint / len(lineage.execution_fingerprint)
        hit_ratio = round(min(0.97, max(cache_status.hit_ratio, 0.44 + overlap * 0.46)), 4)
    else:
        hit_ratio = cache_status.hit_ratio

    restored_artifacts = max(cache_status.restored_artifacts, round(result_count * 2.4 * hit_ratio))
    reused_judge_calls = max(cache_status.reused_judge_calls, round(result_count * 24 * hit_ratio))
    return cache_status.model_copy(
        update={
            "hit_ratio": hit_ratio,
            "restored_artifacts": restored_artifacts,
            "reused_judge_calls": reused_judge_calls,
            "estimated_gpu_seconds_saved": round(reused_judge_calls * 0.46, 1),
        },
        deep=True,
    )


def _build_regression_alerts(
    current_slices,
    baseline_run: BenchmarkRun | None,
) -> list[RegressionAlert]:
    if not baseline_run or not baseline_run.slices:
        return []

    baseline_lookup = {item.slice_name: item for item in baseline_run.slices}
    alerts: list[RegressionAlert] = []
    for slice_score in current_slices:
        baseline = baseline_lookup.get(slice_score.slice_name)
        if not baseline:
            continue
        delta = round(slice_score.score - baseline.score, 4)
        failure_delta = round(slice_score.failure_rate - baseline.failure_rate, 4)
        if delta >= -0.02 and failure_delta <= 0.015:
            continue
        alerts.append(
            RegressionAlert(
                slice_name=slice_score.slice_name,
                previous_score=baseline.score,
                current_score=slice_score.score,
                delta=delta,
                severity=_severity_for_delta(delta),
                note=(
                    f"{slice_score.slice_name} dropped by {abs(delta):.3f} with failure-rate change "
                    f"{failure_delta:+.3f} versus baseline {baseline_run.run_id[:8]}."
                ),
            )
        )
    return alerts


def _build_headline(
    base_headline: str,
    regressions: list[RegressionAlert],
    cache_status: ArtifactCacheStatus | None,
) -> str:
    if regressions:
        suffix = f" {len(regressions)} slice regression alerts were flagged."
    else:
        suffix = " No slice regression alerts were flagged."
    if cache_status:
        suffix += f" Cache reuse landed at {cache_status.hit_ratio:.0%}."
    return f"{base_headline}{suffix}"


def _delta_trend(delta: float) -> str:
    if delta > 0.02:
        return "improved"
    if delta < -0.02:
        return "regressed"
    return "flat"


def _severity_for_delta(delta: float) -> str:
    if delta <= -0.08:
        return "high"
    if delta <= -0.05:
        return "medium"
    return "low"


def _summarize_lineage_delta(left: RunLineage | None, right: RunLineage | None) -> str:
    if not left or not right:
        return "Lineage metadata is not available for one or both runs."

    differences: list[str] = []
    if left.prompt_schema_revision != right.prompt_schema_revision:
        differences.append(
            f"prompt schema {left.prompt_schema_revision} -> {right.prompt_schema_revision}"
        )
    if left.tokenizer_revision != right.tokenizer_revision:
        differences.append(f"tokenizer {left.tokenizer_revision} -> {right.tokenizer_revision}")
    if left.judge_configuration != right.judge_configuration:
        differences.append(
            f"judge config {left.judge_configuration} -> {right.judge_configuration}"
        )
    if left.dataset_revision != right.dataset_revision:
        differences.append(f"dataset revision {left.dataset_revision} -> {right.dataset_revision}")

    if not differences:
        return "Lineage is aligned across dataset revision, prompt schema, tokenizer, and judge configuration."
    return "Lineage differences: " + "; ".join(differences) + "."
