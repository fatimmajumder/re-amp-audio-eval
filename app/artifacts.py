from __future__ import annotations

import json
from pathlib import Path

from .schemas import ArtifactRecord, RunCreate, RunSummary, ScenarioResult, SliceScore


def write_run_artifacts(
    root: Path,
    run_id: str,
    payload: RunCreate,
    summary: RunSummary,
    results: list[ScenarioResult],
    slices: list[SliceScore],
) -> list[ArtifactRecord]:
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    report_path = run_dir / "report.json"
    spectrogram_path = run_dir / "spectrogram.svg"
    logs_path = run_dir / "worker.log"
    manifest_path = run_dir / "manifest.json"

    report_payload = {
        "run_id": run_id,
        "benchmark_name": payload.benchmark_name,
        "model_name": payload.model_name,
        "dataset_name": payload.dataset_name,
        "seed": payload.seed,
        "notes": payload.notes,
        "summary": summary.model_dump(mode="json"),
        "results": [result.model_dump(mode="json") for result in results],
        "slices": [slice_score.model_dump(mode="json") for slice_score in slices],
    }
    report_path.write_text(json.dumps(report_payload, indent=2))

    spectrogram_path.write_text(_build_spectrogram_svg(payload.model_name, results))

    logs_path.write_text(_build_worker_log(run_id, payload, summary, results))

    manifest_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "files": [
                    report_path.name,
                    spectrogram_path.name,
                    logs_path.name,
                    manifest_path.name,
                ],
                "result_count": len(results),
                "slice_count": len(slices),
            },
            indent=2,
        )
    )

    return [
        _artifact_record(
            run_id=run_id,
            label="Run report",
            artifact_type="report",
            path=report_path,
            description=f"Serialized evaluation summary for {payload.benchmark_name}.",
        ),
        _artifact_record(
            run_id=run_id,
            label="Spectrogram board",
            artifact_type="spectrogram",
            path=spectrogram_path,
            description=f"SVG overview of scenario-level robustness for {payload.model_name}.",
        ),
        _artifact_record(
            run_id=run_id,
            label="Inference logs",
            artifact_type="logs",
            path=logs_path,
            description="Queue timing, status transitions, and judge-style scoring traces.",
        ),
        _artifact_record(
            run_id=run_id,
            label="Artifact manifest",
            artifact_type="manifest",
            path=manifest_path,
            description="Index of generated files for downstream reporting and QA flows.",
        ),
    ]


def get_artifact_path(root: Path, run_id: str, filename: str) -> Path:
    candidate = (root / run_id / filename).resolve()
    root_resolved = root.resolve()
    if root_resolved not in candidate.parents or not candidate.exists():
        raise FileNotFoundError(filename)
    return candidate


def _artifact_record(
    *,
    run_id: str,
    label: str,
    artifact_type: str,
    path: Path,
    description: str,
) -> ArtifactRecord:
    return ArtifactRecord(
        label=label,
        artifact_type=artifact_type,  # type: ignore[arg-type]
        path=str(path),
        download_url=f"/api/runs/{run_id}/artifacts/{path.name}",
        size_kb=round(path.stat().st_size / 1024, 1),
        description=description,
    )


def _build_spectrogram_svg(model_name: str, results: list[ScenarioResult]) -> str:
    width = 760
    height = 320
    padding = 36
    chart_width = width - padding * 2
    baseline = height - 64
    max_bar_width = chart_width / max(len(results), 1) - 14

    bars: list[str] = []
    labels: list[str] = []
    for index, result in enumerate(results):
        x = padding + index * ((chart_width / max(len(results), 1)))
        bar_height = max(22, int(result.robustness_score * 180))
        y = baseline - bar_height
        color = "#71f0d1" if result.robustness_score >= 0.7 else "#ff9b71"
        bars.append(
            f'<rect x="{x:.1f}" y="{y}" width="{max_bar_width:.1f}" '
            f'height="{bar_height}" rx="10" fill="{color}" opacity="0.88" />'
        )
        labels.append(
            f'<text x="{x + max_bar_width / 2:.1f}" y="{baseline + 24}" '
            f'font-size="11" text-anchor="middle" fill="#b8c4e4">{result.scenario_name}</text>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none">
  <rect width="{width}" height="{height}" rx="24" fill="#0B1020"/>
  <rect x="14" y="14" width="{width - 28}" height="{height - 28}" rx="18" fill="#111831" stroke="rgba(125,181,255,0.18)"/>
  <text x="{padding}" y="46" fill="#EEF3FF" font-size="22" font-family="IBM Plex Mono, monospace">RE-AMP spectrogram board</text>
  <text x="{padding}" y="72" fill="#B8C4E4" font-size="13" font-family="IBM Plex Mono, monospace">{model_name}</text>
  <line x1="{padding}" y1="{baseline}" x2="{width - padding}" y2="{baseline}" stroke="#324164" stroke-width="1" />
  {''.join(bars)}
  {''.join(labels)}
</svg>
"""


def _build_worker_log(
    run_id: str,
    payload: RunCreate,
    summary: RunSummary,
    results: list[ScenarioResult],
) -> str:
    lines = [
        f"[queue] accepted run={run_id} benchmark={payload.benchmark_name} model={payload.model_name}",
        f"[config] dataset={payload.dataset_name} seed={payload.seed} scenarios={len(payload.scenarios)}",
        f"[summary] aggregate_score={summary.aggregate_score} average_latency_ms={summary.average_latency_ms}",
    ]
    for result in results:
        lines.append(
            "[scenario] "
            f"name={result.scenario_name} "
            f"robustness={result.robustness_score} "
            f"latency_ms={result.latency_ms} "
            f"artifact_rate={result.artifact_rate}"
        )
    lines.append("[queue] completed successfully")
    return "\n".join(lines) + "\n"
