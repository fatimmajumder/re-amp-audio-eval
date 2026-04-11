from __future__ import annotations

import hashlib
from dataclasses import dataclass
from statistics import fmean

from .schemas import (
    BenchmarkScenario,
    RunCreate,
    RunSummary,
    ScenarioResult,
    SliceScore,
)

DIFFICULTY_PENALTY = {"easy": 0.05, "medium": 0.11, "hard": 0.19}
DIFFICULTY_LATENCY = {"easy": 0.95, "medium": 1.0, "hard": 1.12}


def _stable_float(*parts: str) -> float:
    digest = hashlib.sha256("::".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class EvaluationBundle:
    results: list[ScenarioResult]
    summary: RunSummary
    slices: list[SliceScore]


def evaluate_payload(payload: RunCreate, run_id: str) -> EvaluationBundle:
    results = [_score_scenario(payload, scenario) for scenario in payload.scenarios]
    summary = _build_summary(payload.model_name, results)
    slices = _build_slice_scores(results)
    return EvaluationBundle(results=results, summary=summary, slices=slices)


def _score_scenario(payload: RunCreate, scenario: BenchmarkScenario) -> ScenarioResult:
    difficulty_penalty = DIFFICULTY_PENALTY[scenario.difficulty]
    base_signal = _stable_float(payload.model_name, scenario.name, scenario.category, str(payload.seed))
    latency_signal = _stable_float("latency", payload.model_name, scenario.name, str(payload.seed))
    similarity_signal = _stable_float("similarity", payload.model_name, scenario.name)
    artifact_signal = _stable_float("artifact", payload.model_name, scenario.name)
    confidence_signal = _stable_float("judge", payload.model_name, scenario.name, payload.benchmark_name)

    robustness_score = _clamp(0.61 + base_signal * 0.33 - difficulty_penalty, 0.28, 0.97)
    failure_rate = _clamp(1.0 - robustness_score, 0.02, 0.72)
    latency_ms = round((135 + latency_signal * 180) * DIFFICULTY_LATENCY[scenario.difficulty], 1)
    similarity_score = round(
        _clamp(0.48 + similarity_signal * 0.42 - difficulty_penalty * 0.35, 0.31, 0.99),
        4,
    )
    artifact_rate = round(
        _clamp(failure_rate * 0.78 + artifact_signal * 0.12, 0.03, 0.59),
        4,
    )
    judge_confidence = round(_clamp(0.66 + confidence_signal * 0.27, 0.58, 0.99), 4)

    notes: list[str] = []
    if robustness_score < 0.55:
        notes.append("regression-risk")
    if latency_ms > 255:
        notes.append("latency-spike")
    if artifact_rate > 0.24:
        notes.append("artifact-heavy")
    if not notes:
        notes.append("stable")

    return ScenarioResult(
        scenario_name=scenario.name,
        category=scenario.category,
        difficulty=scenario.difficulty,
        robustness_score=round(robustness_score, 4),
        failure_rate=round(failure_rate, 4),
        latency_ms=latency_ms,
        similarity_score=similarity_score,
        artifact_rate=artifact_rate,
        judge_confidence=judge_confidence,
        notes=notes,
    )


def _build_summary(model_name: str, results: list[ScenarioResult]) -> RunSummary:
    strongest = max(results, key=lambda item: item.robustness_score)
    weakest = min(results, key=lambda item: item.robustness_score)
    aggregate_score = round(fmean(item.robustness_score for item in results), 4)
    average_failure_rate = round(fmean(item.failure_rate for item in results), 4)
    average_latency_ms = round(fmean(item.latency_ms for item in results), 1)
    average_similarity_score = round(fmean(item.similarity_score for item in results), 4)
    average_artifact_rate = round(fmean(item.artifact_rate for item in results), 4)

    headline = (
        f"{model_name} is strongest on {strongest.scenario_name} and most vulnerable on "
        f"{weakest.scenario_name}."
    )

    return RunSummary(
        aggregate_score=aggregate_score,
        average_failure_rate=average_failure_rate,
        average_latency_ms=average_latency_ms,
        average_similarity_score=average_similarity_score,
        average_artifact_rate=average_artifact_rate,
        strongest_scenario=strongest.scenario_name,
        weakest_scenario=weakest.scenario_name,
        headline=headline,
    )

def _build_slice_scores(results: list[ScenarioResult]) -> list[SliceScore]:
    buckets: dict[str, list[ScenarioResult]] = {}
    for item in results:
        buckets.setdefault(item.category, []).append(item)

    slice_scores: list[SliceScore] = []
    for category, members in sorted(buckets.items()):
        score = round(fmean(member.robustness_score for member in members), 4)
        failure_rate = round(fmean(member.failure_rate for member in members), 4)
        trend = "stable"
        if score < 0.56 or failure_rate > 0.28:
            trend = "risk"
        elif score < 0.66 or failure_rate > 0.2:
            trend = "watch"

        slice_scores.append(
            SliceScore(
                slice_name=category,
                score=score,
                failure_rate=failure_rate,
                trend=trend,
            )
        )

    return slice_scores
