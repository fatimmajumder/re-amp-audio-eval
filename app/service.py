from __future__ import annotations

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
    BenchmarkRun,
    CompareResponse,
    LeaderboardEntry,
    OverviewResponse,
    RecentRunEntry,
    RunCreate,
    ScenarioDelta,
    WorkspaceCreate,
    WorkspaceRecord,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RunService:
    def __init__(
        self,
        repository: RunRepository,
        workspace_repository: WorkspaceRepository,
        artifacts_root: Path,
        datasets_root: Path,
    ):
        self.repository = repository
        self.workspace_repository = workspace_repository
        self.artifacts_root = artifacts_root
        self.datasets_root = datasets_root
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
            focus_areas=payload.focus_areas,
            default_benchmark=payload.default_benchmark,
            default_model=payload.default_model,
            dataset_preferences=payload.dataset_preferences,
        )
        return self.workspace_repository.save_workspace(workspace)

    def list_runs(self) -> list[BenchmarkRun]:
        return self.repository.list_runs()

    def get_run(self, run_id: str) -> BenchmarkRun | None:
        return self.repository.get_run(run_id)

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

        run = BenchmarkRun(
            benchmark_name=resolved_payload.benchmark_name,
            model_name=resolved_payload.model_name,
            dataset_name=dataset_name,
            seed=resolved_payload.seed,
            notes=resolved_payload.notes,
            workspace_id=workspace.workspace_id,
            workspace_name=workspace.name,
            public_dataset_id=resolved_payload.public_dataset_id,
            dataset_source_url=dataset_source_url,
            scenarios=[scenario.model_copy(deep=True) for scenario in resolved_payload.scenarios],
            source_run_id=source_run_id,
            status="queued",
            progress=5,
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
            public_dataset = (
                get_public_dataset(self.datasets_root, existing.public_dataset_id)
                if existing.public_dataset_id
                else None
            )
            artifacts = write_run_artifacts(
                self.artifacts_root,
                running,
                bundle.summary,
                bundle.results,
                bundle.slices,
                public_dataset=public_dataset,
            )
            final_status = "replayed" if existing.source_run_id else "completed"
            completed = running.model_copy(
                update={
                    "status": final_status,
                    "progress": 100,
                    "completed_at": utc_now(),
                    "results": bundle.results,
                    "summary": bundle.summary,
                    "artifacts": artifacts,
                    "slices": bundle.slices,
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

        deltas: list[ScenarioDelta] = []
        for name in shared_names:
            left_item = left_scores[name]
            right_item = right_scores[name]
            delta = round(right_item.robustness_score - left_item.robustness_score, 4)
            trend = "flat"
            if delta > 0.02:
                trend = "improved"
            elif delta < -0.02:
                trend = "regressed"

            deltas.append(
                ScenarioDelta(
                    scenario_name=name,
                    left_score=left_item.robustness_score,
                    right_score=right_item.robustness_score,
                    delta=delta,
                    trend=trend,
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

        biggest_swing = max(deltas, key=lambda item: abs(item.delta), default=None)
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
            scenario_deltas=deltas,
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

    def require_completed_run(self, run_id: str) -> BenchmarkRun:
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
