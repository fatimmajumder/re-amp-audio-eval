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
        "workspace_id": "core-audio-lab",
        "public_dataset_id": "mini_speech_commands",
        "dataset_name": "Mini Speech Commands",
        "seed": 17,
        "notes": "Integration test run",
        "scenarios": [
            {"name": "speaker_overlap", "difficulty": "hard"},
            {"name": "pitch_drift", "difficulty": "medium"},
        ],
    }


def test_catalog_and_workspaces_include_public_audio_sources(tmp_path: Path) -> None:
    client = create_client(tmp_path)

    catalog = client.get("/api/catalog")
    assert catalog.status_code == 200
    catalog_payload = catalog.json()
    dataset_ids = {dataset["dataset_id"] for dataset in catalog_payload["public_datasets"]}
    assert "mini_speech_commands" in dataset_ids
    assert "librispeech_test_clean" in dataset_ids

    workspaces = client.get("/api/workspaces")
    assert workspaces.status_code == 200
    workspace_ids = {workspace["workspace_id"] for workspace in workspaces.json()}
    assert {"core-audio-lab", "music-evaluation", "speech-red-team"} <= workspace_ids


def test_create_workspace_and_run_materializes_rich_artifacts(tmp_path: Path) -> None:
    client = create_client(tmp_path)

    workspace_response = client.post(
        "/api/workspaces",
        json={
            "name": "Speech QA Sprint",
            "description": "Short-turn lane for noisy speech and overlap regressions.",
            "owner": "Fatim Majumder",
            "focus_areas": ["speaker overlap", "noise"],
        },
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["workspace_id"]

    payload = build_payload()
    payload["workspace_id"] = workspace_id
    response = client.post("/api/runs", json=payload)
    assert response.status_code == 200

    run_id = response.json()["run_id"]
    run_response = client.get(f"/api/runs/{run_id}")
    assert run_response.status_code == 200

    run = run_response.json()
    assert run["status"] == "completed"
    assert run["workspace_id"] == workspace_id
    assert run["public_dataset_id"] == "mini_speech_commands"
    artifact_types = {artifact["artifact_type"] for artifact in run["artifacts"]}
    assert artifact_types == {
        "report",
        "spectrogram",
        "waveform",
        "audio_preview",
        "logs",
        "manifest",
    }

    report_url = next(
        artifact["download_url"]
        for artifact in run["artifacts"]
        if artifact["artifact_type"] == "report"
    )
    report_response = client.get(report_url)
    assert report_response.status_code == 200
    assert report_response.json()["run_id"] == run_id
    assert report_response.json()["public_dataset"]["dataset_id"] == "mini_speech_commands"


def test_replay_keeps_original_scenario_mix_and_workspace(tmp_path: Path) -> None:
    client = create_client(tmp_path)

    source = client.post("/api/runs", json=build_payload()).json()
    replay_response = client.post(f"/api/runs/{source['run_id']}/replay")
    assert replay_response.status_code == 200

    replay = replay_response.json()
    assert replay["source_run_id"] == source["run_id"]
    assert replay["workspace_id"] == source["workspace_id"]
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
