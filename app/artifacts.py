from __future__ import annotations

import json
import math
import struct
import wave
from pathlib import Path

from .schemas import (
    ArtifactCacheStatus,
    ArtifactRecord,
    BenchmarkRun,
    PublicDataset,
    RegressionAlert,
    RunLineage,
    RunSummary,
    ScenarioResult,
    SliceScore,
)

SAMPLE_RATE = 16_000
PREVIEW_DURATION_SECONDS = 2.6
TARGET_FREQUENCIES = [110, 165, 220, 330, 440, 550, 660, 880, 1100, 1320, 1760, 2200]


def write_run_artifacts(
    root: Path,
    run: BenchmarkRun,
    summary: RunSummary,
    results: list[ScenarioResult],
    slices: list[SliceScore],
    *,
    public_dataset: PublicDataset | None = None,
    lineage: RunLineage | None = None,
    cache_status: ArtifactCacheStatus | None = None,
    regressions: list[RegressionAlert] | None = None,
    baseline_run: BenchmarkRun | None = None,
) -> list[ArtifactRecord]:
    run_dir = root / run.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    report_path = run_dir / "report.json"
    spectrogram_path = run_dir / "spectrogram.svg"
    waveform_path = run_dir / "waveform.svg"
    audio_preview_path = run_dir / "audio_preview.wav"
    logs_path = run_dir / "worker.log"
    manifest_path = run_dir / "manifest.json"
    lineage_path = run_dir / "lineage.json"
    regression_path = run_dir / "slice_regressions.json"
    diff_path = run_dir / "run_diff.json"
    cache_path = run_dir / "cache_trace.json"

    regressions = regressions or []
    signal = _build_preview_signal(run, results)

    report_payload = {
        "run_id": run.run_id,
        "workspace": {
            "workspace_id": run.workspace_id,
            "workspace_name": run.workspace_name,
            "tenant_slug": run.tenant_slug,
            "tenant_name": run.tenant_name,
            "project_slug": run.project_slug,
            "project_name": run.project_name,
        },
        "benchmark_name": run.benchmark_name,
        "model_name": run.model_name,
        "dataset_name": run.dataset_name,
        "public_dataset_id": run.public_dataset_id,
        "dataset_source_url": run.dataset_source_url,
        "seed": run.seed,
        "notes": run.notes,
        "summary": summary.model_dump(mode="json"),
        "results": [result.model_dump(mode="json") for result in results],
        "slices": [slice_score.model_dump(mode="json") for slice_score in slices],
        "lineage": lineage.model_dump(mode="json") if lineage else None,
        "cache_status": cache_status.model_dump(mode="json") if cache_status else None,
        "regressions": [item.model_dump(mode="json") for item in regressions],
        "public_dataset": public_dataset.model_dump(mode="json") if public_dataset else None,
    }
    report_path.write_text(json.dumps(report_payload, indent=2))

    spectrogram_path.write_text(_build_spectrogram_svg(run, signal, results))
    waveform_path.write_text(_build_waveform_svg(run, signal, summary))
    _write_preview_audio(audio_preview_path, signal)
    logs_path.write_text(_build_worker_log(run, summary, results, public_dataset, cache_status))
    lineage_path.write_text(
        json.dumps(
            {
                "run_id": run.run_id,
                "baseline_run_id": baseline_run.run_id if baseline_run else None,
                "lineage": lineage.model_dump(mode="json") if lineage else None,
            },
            indent=2,
        )
    )
    regression_path.write_text(
        json.dumps(
            {
                "run_id": run.run_id,
                "baseline_run_id": baseline_run.run_id if baseline_run else None,
                "alert_count": len(regressions),
                "alerts": [item.model_dump(mode="json") for item in regressions],
            },
            indent=2,
        )
    )
    diff_path.write_text(
        json.dumps(
            {
                "run_id": run.run_id,
                "baseline_run_id": baseline_run.run_id if baseline_run else None,
                "baseline_model_name": baseline_run.model_name if baseline_run else None,
                "baseline_summary": baseline_run.summary.model_dump(mode="json") if baseline_run and baseline_run.summary else None,
                "current_summary": summary.model_dump(mode="json"),
                "slice_count": len(slices),
                "scenario_count": len(results),
            },
            indent=2,
        )
    )
    cache_path.write_text(
        json.dumps(
            {
                "run_id": run.run_id,
                "cache_status": cache_status.model_dump(mode="json") if cache_status else None,
                "lineage_fingerprint": lineage.execution_fingerprint if lineage else None,
            },
            indent=2,
        )
    )

    manifest_path.write_text(
        json.dumps(
            {
                "run_id": run.run_id,
                "workspace_id": run.workspace_id,
                "dataset_name": run.dataset_name,
                "public_dataset_id": run.public_dataset_id,
                "files": [
                    report_path.name,
                    spectrogram_path.name,
                    waveform_path.name,
                    audio_preview_path.name,
                    logs_path.name,
                    manifest_path.name,
                    lineage_path.name,
                    regression_path.name,
                    diff_path.name,
                    cache_path.name,
                ],
                "result_count": len(results),
                "slice_count": len(slices),
                "sample_rate": SAMPLE_RATE,
                "duration_seconds": PREVIEW_DURATION_SECONDS,
            },
            indent=2,
        )
    )

    return [
        _artifact_record(
            run_id=run.run_id,
            label="Run report",
            artifact_type="report",
            path=report_path,
            description=f"Serialized evaluation summary for {run.benchmark_name}.",
        ),
        _artifact_record(
            run_id=run.run_id,
            label="Spectrogram board",
            artifact_type="spectrogram",
            path=spectrogram_path,
            description=f"Frequency-band stability heatmap for {run.model_name}.",
        ),
        _artifact_record(
            run_id=run.run_id,
            label="Waveform board",
            artifact_type="waveform",
            path=waveform_path,
            description="Amplitude envelope preview generated from the scored scenario mix.",
        ),
        _artifact_record(
            run_id=run.run_id,
            label="Audio preview",
            artifact_type="audio_preview",
            path=audio_preview_path,
            description="Synthetic WAV preview used for product demos and regression walkthroughs.",
        ),
        _artifact_record(
            run_id=run.run_id,
            label="Inference logs",
            artifact_type="logs",
            path=logs_path,
            description="Queue timing, status transitions, and judge-style scoring traces.",
        ),
        _artifact_record(
            run_id=run.run_id,
            label="Artifact manifest",
            artifact_type="manifest",
            path=manifest_path,
            description="Index of generated files for downstream reporting and QA flows.",
        ),
        _artifact_record(
            run_id=run.run_id,
            label="Lineage record",
            artifact_type="lineage",
            path=lineage_path,
            description="Dataset, prompt schema, tokenizer, and judge configuration for exact replay.",
        ),
        _artifact_record(
            run_id=run.run_id,
            label="Slice regression report",
            artifact_type="regression",
            path=regression_path,
            description="Slice-level regressions relative to the chosen baseline run.",
        ),
        _artifact_record(
            run_id=run.run_id,
            label="Run diff summary",
            artifact_type="diff",
            path=diff_path,
            description="Compact before/after summary for baseline-aware comparison flows.",
        ),
        _artifact_record(
            run_id=run.run_id,
            label="Cache trace",
            artifact_type="cache",
            path=cache_path,
            description="Artifact and judge-call reuse metadata for repeat experiments.",
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


def _build_preview_signal(run: BenchmarkRun, results: list[ScenarioResult]) -> list[float]:
    total_samples = int(SAMPLE_RATE * PREVIEW_DURATION_SECONDS)
    segment_length = max(total_samples // max(len(results), 1), 1)
    signal = [0.0 for _ in range(total_samples)]

    for index, result in enumerate(results):
        start = index * segment_length
        end = total_samples if index == len(results) - 1 else min(total_samples, start + segment_length)
        base_frequency = 110 + ((sum(ord(char) for char in result.scenario_name) % 12) * 35)
        shimmer_frequency = base_frequency * (1.5 + result.similarity_score * 0.6)
        amplitude = 0.18 + result.robustness_score * 0.22
        tremolo_depth = 0.05 + result.artifact_rate * 0.08
        for sample_index in range(start, end):
            t = sample_index / SAMPLE_RATE
            envelope = 0.65 + 0.35 * math.sin(math.pi * (sample_index - start) / max(end - start, 1))
            tone = math.sin(2 * math.pi * base_frequency * t)
            shimmer = 0.55 * math.sin(2 * math.pi * shimmer_frequency * t)
            tremolo = 1.0 - tremolo_depth * math.sin(2 * math.pi * (3.0 + result.failure_rate * 7.0) * t)
            signal[sample_index] += amplitude * envelope * tremolo * (tone + shimmer)

    peak = max((abs(value) for value in signal), default=1.0)
    normalization = 0.92 / peak if peak else 1.0
    return [value * normalization for value in signal]


def _write_preview_audio(path: Path, signal: list[float]) -> None:
    pcm = bytearray()
    for value in signal:
        clipped = max(-1.0, min(1.0, value))
        pcm.extend(struct.pack("<h", int(clipped * 32767)))

    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(bytes(pcm))


def _build_waveform_svg(run: BenchmarkRun, signal: list[float], summary: RunSummary) -> str:
    width = 920
    height = 280
    center_y = height / 2
    padding_x = 28
    usable_width = width - padding_x * 2
    stride = max(len(signal) // 240, 1)
    points: list[str] = []
    for index, sample_index in enumerate(range(0, len(signal), stride)):
        x = padding_x + (index / max((len(signal) // stride) - 1, 1)) * usable_width
        y = center_y - signal[sample_index] * 82
        points.append(f"{x:.1f},{y:.1f}")

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
    <linearGradient id="waveGradient" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#71f0d1" />
      <stop offset="100%" stop-color="#7db5ff" />
    </linearGradient>
  </defs>
  <rect width="{width}" height="{height}" rx="24" fill="#0b1020"/>
  <rect x="12" y="12" width="{width - 24}" height="{height - 24}" rx="18" fill="#111831" stroke="rgba(125,181,255,0.18)"/>
  <text x="28" y="42" fill="#eef3ff" font-size="22" font-family="IBM Plex Mono, monospace">Waveform preview</text>
  <text x="28" y="68" fill="#b8c4e4" font-size="13" font-family="IBM Plex Mono, monospace">{run.model_name} · {run.dataset_name}</text>
  <text x="{width - 28}" y="42" fill="#71f0d1" font-size="16" text-anchor="end" font-family="IBM Plex Mono, monospace">score {summary.aggregate_score:.3f}</text>
  <line x1="28" y1="{center_y:.1f}" x2="{width - 28}" y2="{center_y:.1f}" stroke="rgba(255,255,255,0.08)"/>
  <polyline fill="none" stroke="url(#waveGradient)" stroke-width="3" points="{' '.join(points)}"/>
</svg>
"""


def _build_spectrogram_svg(run: BenchmarkRun, signal: list[float], results: list[ScenarioResult]) -> str:
    width = 920
    height = 360
    padding_x = 34
    padding_y = 52
    frame_size = 320
    hop = 160
    frames = [signal[index : index + frame_size] for index in range(0, max(len(signal) - frame_size, 1), hop)]
    if not frames:
        frames = [signal]

    band_grid = [_goertzel_grid(frame) for frame in frames[:42]]
    max_value = max((value for column in band_grid for value in column), default=1.0)
    chart_width = width - padding_x * 2
    chart_height = height - padding_y * 2
    cell_width = chart_width / max(len(band_grid), 1)
    cell_height = chart_height / max(len(TARGET_FREQUENCIES), 1)

    cells: list[str] = []
    for column_index, column in enumerate(band_grid):
        for band_index, magnitude in enumerate(column):
            intensity = magnitude / max_value if max_value else 0.0
            hue = 182 - int(90 * intensity)
            lightness = 18 + intensity * 48
            x = padding_x + column_index * cell_width
            y = padding_y + (len(TARGET_FREQUENCIES) - band_index - 1) * cell_height
            cells.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell_width + 0.4:.1f}" height="{cell_height + 0.4:.1f}" '
                f'fill="hsl({hue}, 86%, {lightness:.1f}%)" opacity="{0.32 + intensity * 0.68:.3f}" />'
            )

    scenario_labels = ", ".join(result.scenario_name for result in results)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="{width}" height="{height}" rx="24" fill="#0b1020"/>
  <rect x="12" y="12" width="{width - 24}" height="{height - 24}" rx="18" fill="#111831" stroke="rgba(125,181,255,0.18)"/>
  <text x="{padding_x}" y="36" fill="#eef3ff" font-size="22" font-family="IBM Plex Mono, monospace">Spectrogram board</text>
  <text x="{padding_x}" y="62" fill="#b8c4e4" font-size="13" font-family="IBM Plex Mono, monospace">{run.workspace_name}</text>
  <text x="{padding_x}" y="{height - 24}" fill="#b8c4e4" font-size="11" font-family="IBM Plex Mono, monospace">{scenario_labels}</text>
  {''.join(cells)}
</svg>
"""


def _goertzel_grid(frame: list[float]) -> list[float]:
    magnitudes: list[float] = []
    frame_length = len(frame)
    for frequency in TARGET_FREQUENCIES:
        omega = (2.0 * math.pi * frequency) / SAMPLE_RATE
        coefficient = 2.0 * math.cos(omega)
        previous = 0.0
        previous2 = 0.0
        for sample in frame:
            current = sample + coefficient * previous - previous2
            previous2 = previous
            previous = current
        power = previous2**2 + previous**2 - coefficient * previous * previous2
        magnitudes.append(math.sqrt(max(power, 0.0) / max(frame_length, 1)))
    return magnitudes


def _build_worker_log(
    run: BenchmarkRun,
    summary: RunSummary,
    results: list[ScenarioResult],
    public_dataset: PublicDataset | None,
    cache_status: ArtifactCacheStatus | None,
) -> str:
    lines = [
        f"[queue] accepted run={run.run_id} tenant={run.tenant_slug} project={run.project_slug} workspace={run.workspace_id}",
        f"[config] benchmark={run.benchmark_name} model={run.model_name} dataset={run.dataset_name} seed={run.seed} scenarios={len(run.scenarios)}",
    ]
    if public_dataset:
        lines.append(
            f"[dataset] source={public_dataset.source_url} access_mode={public_dataset.access_mode} "
            f"local_status={public_dataset.availability.status}"
        )
    if run.lineage:
        lines.append(
            f"[lineage] prompt_schema={run.lineage.prompt_schema_revision} tokenizer={run.lineage.tokenizer_revision} "
            f"judge={run.lineage.judge_configuration} fingerprint={run.lineage.execution_fingerprint[:12]}"
        )
    if cache_status:
        lines.append(
            f"[cache] namespace={cache_status.cache_namespace} key={cache_status.cache_key} "
            f"hit_ratio={cache_status.hit_ratio} reused_judge_calls={cache_status.reused_judge_calls}"
        )
    lines.append(
        f"[summary] aggregate_score={summary.aggregate_score} average_latency_ms={summary.average_latency_ms}"
    )
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
