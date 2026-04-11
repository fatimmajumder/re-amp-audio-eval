from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def create_client(tmp_path: Path) -> TestClient:
    app = create_app(storage_path=tmp_path / "runs.json", seed_demo_data=False)
    return TestClient(app)


def build_payload(model_name: str = "reamp-studio-alpha") -> dict:
    return {
        "benchmark_name": "audio_robustness_suite",
        "model_name": model_name,
        "dataset_name": "synthetic-acoustic-suite",
        "seed": 17,
        "notes": "Integration test run",
        "scenarios": [
            {"name": "speaker_overlap", "difficulty": "hard"},
            {"name": "pitch_drift", "difficulty": "medium"},
        ],
    }


def test_create_run_materializes_results_and_artifacts(tmp_path: Path) -> None:
    client = create_client(tmp_path)

    response = client.post("/api/runs", json=build_payload())
    assert response.status_code == 200

    run_id = response.json()["run_id"]
    run_response = client.get(f"/api/runs/{run_id}")
    assert run_response.status_code == 200

    run = run_response.json()
    assert run["status"] == "completed"
    assert run["summary"]["aggregate_score"] > 0
    assert len(run["artifacts"]) == 4

    report_url = next(
        artifact["download_url"]
        for artifact in run["artifacts"]
        if artifact["artifact_type"] == "report"
    )
    report_response = client.get(report_url)
    assert report_response.status_code == 200
    assert report_response.json()["run_id"] == run_id


def test_replay_keeps_original_scenario_mix(tmp_path: Path) -> None:
    client = create_client(tmp_path)

    source = client.post("/api/runs", json=build_payload()).json()
    replay_response = client.post(f"/api/runs/{source['run_id']}/replay")
    assert replay_response.status_code == 200

    replay = replay_response.json()
    assert replay["source_run_id"] == source["run_id"]
    assert [scenario["name"] for scenario in replay["scenarios"]] == [
        scenario["name"] for scenario in source["scenarios"]
    ]
    assert replay["status"] == "queued"

    completed_replay = client.get(f"/api/runs/{replay['run_id']}").json()
    assert completed_replay["status"] == "replayed"


def test_compare_returns_scenario_level_deltas(tmp_path: Path) -> None:
    client = create_client(tmp_path)

    left = client.post("/api/runs", json=build_payload("reamp-studio-alpha")).json()
    right = client.post("/api/runs", json=build_payload("reamp-studio-beta")).json()

    response = client.post(
        "/api/compare",
        json={"left_run_id": left["run_id"], "right_run_id": right["run_id"]},
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["left_run_id"] == left["run_id"]
    assert payload["right_run_id"] == right["run_id"]
    assert len(payload["scenario_deltas"]) == 2
    assert payload["headline"]
