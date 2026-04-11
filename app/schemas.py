from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

RunStatus = Literal["queued", "running", "completed", "replayed", "failed"]
Difficulty = Literal["easy", "medium", "hard"]
Modality = Literal["audio", "multimodal"]


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


class RunCreate(AppModel):
    benchmark_name: str
    model_name: str
    dataset_name: str = "synthetic-acoustic-suite"
    seed: int = 7
    notes: str = ""
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
    trend: Literal["stable", "watch", "risk"]


class ArtifactRecord(AppModel):
    label: str
    artifact_type: Literal["report", "spectrogram", "logs", "manifest"]
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


class BenchmarkRun(AppModel):
    run_id: str = Field(default_factory=lambda: uuid4().hex)
    benchmark_name: str
    model_name: str
    dataset_name: str
    seed: int
    notes: str = ""
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


class RecentRunEntry(AppModel):
    run_id: str
    benchmark_name: str
    model_name: str
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


class CompareResponse(AppModel):
    left_run_id: str
    right_run_id: str
    left_label: str
    right_label: str
    score_delta: float
    verdict: str
    headline: str
    scenario_deltas: list[ScenarioDelta] = Field(default_factory=list)
