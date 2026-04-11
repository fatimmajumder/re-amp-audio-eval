from __future__ import annotations

from pathlib import Path
import time

from fastapi.testclient import TestClient

from app.main import create_app


def create_client(
    tmp_path: Path,
    *,
    database_url: str | None = None,
    inline_worker_enabled: bool = True,
) -> TestClient:
    app = create_app(
        storage_path=tmp_path / "runs.json",
        seed_demo_data=False,
        database_url=database_url,
        inline_worker_enabled=inline_worker_enabled,
    )
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


def wait_for_terminal_run(client: TestClient, run_id: str, timeout_seconds: float = 6.0) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last_payload = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        last_payload = response.json()
        if last_payload["status"] in {"completed", "replayed", "failed"}:
            return last_payload
        time.sleep(0.1)

    raise AssertionError(f"run {run_id} did not reach a terminal state: {last_payload}")


def test_catalog_and_workspaces_include_public_audio_sources(tmp_path: Path) -> None:
    with create_client(tmp_path) as client:
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
    with create_client(tmp_path) as client:
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
        run = wait_for_terminal_run(client, run_id)
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
    with create_client(tmp_path) as client:
        source = client.post("/api/runs", json=build_payload()).json()
        wait_for_terminal_run(client, source["run_id"])

        replay_response = client.post(f"/api/runs/{source['run_id']}/replay")
        assert replay_response.status_code == 200

        replay = replay_response.json()
        assert replay["source_run_id"] == source["run_id"]
        assert replay["workspace_id"] == source["workspace_id"]
        assert [scenario["name"] for scenario in replay["scenarios"]] == [
            scenario["name"] for scenario in source["scenarios"]
        ]
        assert replay["status"] == "queued"

        completed_replay = wait_for_terminal_run(client, replay["run_id"])
        assert completed_replay["status"] == "replayed"


def test_compare_returns_scenario_level_deltas(tmp_path: Path) -> None:
    with create_client(tmp_path) as client:
        left = client.post("/api/runs", json=build_payload("reamp-studio-alpha")).json()
        right = client.post("/api/runs", json=build_payload("reamp-studio-beta")).json()
        wait_for_terminal_run(client, left["run_id"])
        wait_for_terminal_run(client, right["run_id"])

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


def test_system_status_reports_database_runtime_with_sqlite_backend(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'reamp.db'}"
    with create_client(tmp_path, database_url=database_url) as client:
        response = client.get("/api/system")
        assert response.status_code == 200
        payload = response.json()
        assert payload["storage_backend"] == "database"
        assert payload["database_enabled"] is True
        assert payload["worker_count"] >= 1


def test_database_backend_executes_queued_run(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'reamp-jobs.db'}"
    with create_client(tmp_path, database_url=database_url) as client:
        response = client.post("/api/runs", json=build_payload("reamp-studio-beta"))
        assert response.status_code == 200
        run = wait_for_terminal_run(client, response.json()["run_id"])
        assert run["status"] == "completed"
        assert run["summary"]["headline"]
