from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

RunStatus = Literal["queued", "running", "completed", "replayed", "failed"]
Difficulty = Literal["easy", "medium", "hard"]
Modality = Literal["audio", "multimodal"]
DatasetAccessMode = Literal["direct", "request", "streaming"]
DatasetAvailabilityStatus = Literal["remote", "downloaded"]
Trend = Literal["stable", "watch", "risk"]
RegressionSeverity = Literal["low", "medium", "high"]
Environment = Literal["dev", "staging", "prod"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AppModel(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


class BenchmarkScenario(AppModel):
    name: str
    difficulty: Difficulty = "medium"
    modality: Modality = "audio"
    category: str = "acoustics"
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    weight: float = 1.0


class DatasetAvailability(AppModel):
    status: DatasetAvailabilityStatus = "remote"
    local_path: str | None = None
    manifest_path: str | None = None
    downloaded_at: datetime | None = None
    audio_file_count: int = 0
    sample_files: list[str] = Field(default_factory=list)


class PublicDataset(AppModel):
    dataset_id: str
    name: str
    domain: str
    provider: str
    description: str
    source_url: str
    download_url: str
    license_name: str
    access_mode: DatasetAccessMode = "direct"
    download_size: str
    tasks: list[str] = Field(default_factory=list)
    recommended_benchmarks: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    availability: DatasetAvailability = Field(default_factory=DatasetAvailability)


class WorkspaceCreate(AppModel):
    name: str
    description: str
    owner: str = "RE-AMP Team"
    tenant_name: str = "Arthur Labs"
    tenant_slug: str = "arthur-labs"
    project_name: str = "Audio Red Team"
    project_slug: str = "audio-redteam"
    focus_areas: list[str] = Field(default_factory=list)
    default_benchmark: str = ""
    default_model: str = ""
    dataset_preferences: list[str] = Field(default_factory=list)
    default_prompt_schema: str = "prompt-schema-2026-04"
    default_judge_configuration: str = "aurora-judge-v4"


class WorkspaceRecord(AppModel):
    workspace_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    name: str
    description: str
    owner: str = "RE-AMP Team"
    tenant_name: str = "Arthur Labs"
    tenant_slug: str = "arthur-labs"
    project_name: str = "Audio Red Team"
    project_slug: str = "audio-redteam"
    focus_areas: list[str] = Field(default_factory=list)
    default_benchmark: str = ""
    default_model: str = ""
    dataset_preferences: list[str] = Field(default_factory=list)
    default_prompt_schema: str = "prompt-schema-2026-04"
    default_judge_configuration: str = "aurora-judge-v4"
    created_at: datetime = Field(default_factory=utc_now)
    last_run_at: datetime | None = None
    run_count: int = 0


class RunCreate(AppModel):
    benchmark_name: str
    model_name: str
    dataset_name: str = ""
    seed: int = 7
    notes: str = ""
    workspace_id: str | None = None
    public_dataset_id: str | None = None
    baseline_run_id: str | None = None
    prompt_schema_revision: str | None = None
    tokenizer_revision: str | None = None
    judge_configuration: str | None = None
    scenarios: list[BenchmarkScenario] = Field(default_factory=list)


class ScenarioResult(AppModel):
    scenario_name: str
    category: str
    difficulty: Difficulty
    robustness_score: float
    failure_rate: float
    latency_ms: float
    similarity_score: float
    artifact_rate: float
    judge_confidence: float
    notes: list[str] = Field(default_factory=list)


class SliceScore(AppModel):
    slice_name: str
    score: float
    failure_rate: float
    trend: Trend


class RunLineage(AppModel):
    dataset_revision: str
    dataset_manifest: str
    prompt_schema_revision: str
    tokenizer_revision: str
    model_artifact: str
    judge_configuration: str
    scoring_revision: str
    execution_fingerprint: str
    lineage_tags: list[str] = Field(default_factory=list)


class ArtifactCacheStatus(AppModel):
    cache_namespace: str
    cache_key: str
    hit_ratio: float
    restored_artifacts: int
    reused_judge_calls: int
    estimated_gpu_seconds_saved: float


class RegressionAlert(AppModel):
    slice_name: str
    previous_score: float
    current_score: float
    delta: float
    severity: RegressionSeverity
    note: str


class ArtifactRecord(AppModel):
    label: str
    artifact_type: Literal[
        "report",
        "spectrogram",
        "waveform",
        "audio_preview",
        "logs",
        "manifest",
        "lineage",
        "regression",
        "diff",
        "cache",
    ]
    path: str
    download_url: str = ""
    size_kb: float
    description: str


class RunSummary(AppModel):
    aggregate_score: float
    average_failure_rate: float
    average_latency_ms: float
    average_similarity_score: float
    average_artifact_rate: float
    strongest_scenario: str
    weakest_scenario: str
    headline: str
    regression_alert_count: int = 0
    cache_hit_ratio: float = 0.0


class BenchmarkRun(AppModel):
    run_id: str = Field(default_factory=lambda: uuid4().hex)
    benchmark_name: str
    model_name: str
    dataset_name: str
    seed: int
    notes: str = ""
    workspace_id: str = "core-audio-lab"
    workspace_name: str = "Core Audio Lab"
    tenant_slug: str = "arthur-labs"
    tenant_name: str = "Arthur Labs"
    project_slug: str = "audio-redteam"
    project_name: str = "Audio Red Team"
    environment: Environment = "staging"
    public_dataset_id: str | None = None
    dataset_source_url: str | None = None
    baseline_run_id: str | None = None
    scenarios: list[BenchmarkScenario] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    source_run_id: str | None = None
    status: RunStatus = "queued"
    progress: int = 0
    error_message: str | None = None
    results: list[ScenarioResult] = Field(default_factory=list)
    summary: RunSummary | None = None
    artifacts: list[ArtifactRecord] = Field(default_factory=list)
    slices: list[SliceScore] = Field(default_factory=list)
    lineage: RunLineage | None = None
    cache_status: ArtifactCacheStatus | None = None
    regressions: list[RegressionAlert] = Field(default_factory=list)


class BenchmarkTemplate(AppModel):
    benchmark_name: str
    dataset_name: str
    description: str
    default_scenarios: list[str]
    target_metrics: list[str]


class ModelCard(AppModel):
    name: str
    family: str
    provider: str
    description: str
    strengths: list[str] = Field(default_factory=list)


class CatalogResponse(AppModel):
    benchmark_templates: list[BenchmarkTemplate]
    models: list[ModelCard]
    scenario_library: list[BenchmarkScenario]
    public_datasets: list[PublicDataset] = Field(default_factory=list)


class RecentRunEntry(AppModel):
    run_id: str
    benchmark_name: str
    model_name: str
    workspace_name: str
    status: RunStatus
    aggregate_score: float | None = None
    created_at: datetime


class LeaderboardEntry(AppModel):
    model_name: str
    benchmark_count: int
    average_score: float
    average_latency_ms: float


class OverviewResponse(AppModel):
    total_runs: int
    active_runs: int
    replay_runs: int
    average_score: float
    average_latency_ms: float
    best_model_name: str
    best_score: float
    workspace_count: int = 0
    public_dataset_count: int = 0
    leaderboard: list[LeaderboardEntry] = Field(default_factory=list)
    recent_runs: list[RecentRunEntry] = Field(default_factory=list)


class CompareRequest(AppModel):
    left_run_id: str
    right_run_id: str


class ScenarioDelta(AppModel):
    scenario_name: str
    left_score: float
    right_score: float
    delta: float
    trend: Literal["improved", "regressed", "flat"]


class SliceDelta(AppModel):
    slice_name: str
    left_score: float
    right_score: float
    delta: float
    trend: Literal["improved", "regressed", "flat"]


class CompareResponse(AppModel):
    left_run_id: str
    right_run_id: str
    left_label: str
    right_label: str
    score_delta: float
    verdict: str
    headline: str
    scenario_deltas: list[ScenarioDelta] = Field(default_factory=list)
    slice_deltas: list[SliceDelta] = Field(default_factory=list)
    regression_alerts: list[RegressionAlert] = Field(default_factory=list)
    lineage_summary: str = ""


class SystemStatus(AppModel):
    app_version: str
    storage_backend: Literal["json", "database"]
    database_enabled: bool
    database_url_hint: str | None = None
    inline_worker_enabled: bool
    worker_count: int
    multi_tenant_enabled: bool = True
    cache_enabled: bool = True
    artifact_root: str
    dataset_root: str
