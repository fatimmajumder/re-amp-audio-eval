from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class BenchmarkScenario(BaseModel):
    name: str
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    modality: Literal["audio", "text", "multimodal"] = "audio"


class RunCreate(BaseModel):
    benchmark_name: str
    model_name: str
    seed: int = 7
    scenarios: list[BenchmarkScenario] = Field(default_factory=list)


class ScenarioResult(BaseModel):
    scenario_name: str
    robustness_score: float
    failure_rate: float


class BenchmarkRun(BaseModel):
    run_id: str = Field(default_factory=lambda: uuid4().hex)
    benchmark_name: str
    model_name: str
    seed: int
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: Literal["queued", "completed", "replayed"] = "queued"
    results: list[ScenarioResult] = Field(default_factory=list)
    aggregate_score: float = 0.0


class CompareRequest(BaseModel):
    left_run_id: str
    right_run_id: str


class CompareResponse(BaseModel):
    left_run_id: str
    right_run_id: str
    score_delta: float
    verdict: str
