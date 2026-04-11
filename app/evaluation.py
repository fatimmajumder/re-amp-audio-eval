from __future__ import annotations

import hashlib
from copy import deepcopy

from .schemas import BenchmarkRun, CompareResponse, RunCreate, ScenarioResult


def _stable_float(*parts: str) -> float:
    digest = hashlib.sha256("::".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def materialize_run(payload: RunCreate) -> BenchmarkRun:
    run = BenchmarkRun(
        benchmark_name=payload.benchmark_name,
        model_name=payload.model_name,
        seed=payload.seed,
        status="completed",
    )

    scenario_results: list[ScenarioResult] = []
    for scenario in payload.scenarios:
        base = _stable_float(payload.model_name, scenario.name, str(payload.seed))
        difficulty_penalty = {"easy": 0.06, "medium": 0.12, "hard": 0.2}[scenario.difficulty]
        robustness_score = max(0.0, min(1.0, 0.62 + base * 0.32 - difficulty_penalty))
        failure_rate = round(1.0 - robustness_score, 4)
        scenario_results.append(
            ScenarioResult(
                scenario_name=scenario.name,
                robustness_score=round(robustness_score, 4),
                failure_rate=failure_rate,
            )
        )

    run.results = scenario_results
    if scenario_results:
        run.aggregate_score = round(
            sum(item.robustness_score for item in scenario_results) / len(scenario_results),
            4,
        )

    return run


def replay_run(existing: BenchmarkRun) -> BenchmarkRun:
    replay = deepcopy(existing)
    replay.run_id = f"{existing.run_id}-replay"
    replay.status = "replayed"
    return replay


def compare_runs(left: BenchmarkRun, right: BenchmarkRun) -> CompareResponse:
    delta = round(right.aggregate_score - left.aggregate_score, 4)
    if delta > 0.03:
        verdict = "right run materially improves robustness"
    elif delta < -0.03:
        verdict = "right run regresses against the baseline"
    else:
        verdict = "runs are effectively tied"

    return CompareResponse(
        left_run_id=left.run_id,
        right_run_id=right.run_id,
        score_delta=delta,
        verdict=verdict,
    )
