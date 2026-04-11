from __future__ import annotations

from fastapi import FastAPI, HTTPException

from .evaluation import compare_runs, materialize_run, replay_run
from .schemas import BenchmarkRun, CompareRequest, RunCreate

app = FastAPI(title="RE-AMP", version="0.1.0")
RUNS: dict[str, BenchmarkRun] = {}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/runs", response_model=BenchmarkRun)
def create_run(payload: RunCreate) -> BenchmarkRun:
    run = materialize_run(payload)
    RUNS[run.run_id] = run
    return run


@app.get("/runs/{run_id}", response_model=BenchmarkRun)
def get_run(run_id: str) -> BenchmarkRun:
    run = RUNS.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@app.post("/runs/{run_id}/replay", response_model=BenchmarkRun)
def replay_existing_run(run_id: str) -> BenchmarkRun:
    existing = RUNS.get(run_id)
    if not existing:
        raise HTTPException(status_code=404, detail="run not found")

    replay = replay_run(existing)
    RUNS[replay.run_id] = replay
    return replay


@app.post("/compare")
def compare(payload: CompareRequest):
    left = RUNS.get(payload.left_run_id)
    right = RUNS.get(payload.right_run_id)

    if not left or not right:
        raise HTTPException(status_code=404, detail="one or both runs were not found")

    return compare_runs(left, right)
