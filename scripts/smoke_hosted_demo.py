from __future__ import annotations

import argparse
import sys
import time
from urllib.parse import urljoin

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke-test a hosted RE-AMP deployment by exercising health, catalog, and a real benchmark run."
    )
    parser.add_argument("base_url", help="Base URL for the hosted RE-AMP app, for example https://re-amp-demo.onrender.com")
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Maximum seconds to wait for the queued run to finish.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=1.5,
        help="Polling interval in seconds while waiting for the run to finish.",
    )
    parser.add_argument(
        "--skip-run",
        action="store_true",
        help="Only verify health and read-only routes without queueing a benchmark run.",
    )
    return parser.parse_args()


def build_url(base_url: str, path: str) -> str:
    return urljoin(f"{base_url.rstrip('/')}/", path.lstrip("/"))


def request_json(client: httpx.Client, method: str, url: str, **kwargs) -> object:
    response = client.request(method, url, **kwargs)
    response.raise_for_status()
    return response.json()


def wait_for_terminal_run(
    client: httpx.Client,
    base_url: str,
    run_id: str,
    *,
    timeout: float,
    poll_interval: float,
) -> dict:
    deadline = time.monotonic() + timeout
    last_payload: dict | None = None
    while time.monotonic() < deadline:
        payload = request_json(client, "GET", build_url(base_url, f"/api/runs/{run_id}"))
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected run payload shape.")
        last_payload = payload
        if payload["status"] in {"completed", "replayed", "failed"}:
            return payload
        time.sleep(poll_interval)

    raise TimeoutError(f"Run {run_id} did not finish within {timeout:.1f}s: {last_payload}")


def choose_smoke_payload(workspaces: list[dict], catalog: dict) -> dict:
    workspace_lookup = {workspace["workspace_id"]: workspace for workspace in workspaces}
    workspace = workspace_lookup.get("speech-red-team") or workspaces[0]
    preferred_dataset_id = (workspace.get("dataset_preferences") or [None])[0]

    benchmark_name = workspace.get("default_benchmark") or catalog["benchmark_templates"][0]["benchmark_name"]
    model_name = workspace.get("default_model") or catalog["models"][0]["name"]
    dataset_id = preferred_dataset_id or (catalog["public_datasets"][0]["dataset_id"] if catalog["public_datasets"] else None)

    dataset_name = ""
    for dataset in catalog["public_datasets"]:
        if dataset["dataset_id"] == dataset_id:
            dataset_name = dataset["name"]
            break

    return {
        "benchmark_name": benchmark_name,
        "model_name": model_name,
        "workspace_id": workspace["workspace_id"],
        "public_dataset_id": dataset_id,
        "dataset_name": dataset_name or "Hosted smoke dataset",
        "seed": 31,
        "notes": "Hosted deployment smoke test run.",
        "scenarios": [],
    }


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")

    with httpx.Client(follow_redirects=True, timeout=30.0) as client:
        health = request_json(client, "GET", build_url(base_url, "/health"))
        system = request_json(client, "GET", build_url(base_url, "/api/system"))
        overview = request_json(client, "GET", build_url(base_url, "/api/overview"))
        catalog = request_json(client, "GET", build_url(base_url, "/api/catalog"))
        workspaces = request_json(client, "GET", build_url(base_url, "/api/workspaces"))

        if not isinstance(health, dict) or health.get("status") != "ok":
            raise RuntimeError(f"Unexpected health payload: {health}")
        if not isinstance(system, dict) or not isinstance(overview, dict):
            raise RuntimeError("Unexpected system or overview payload.")
        if not isinstance(catalog, dict) or not isinstance(workspaces, list):
            raise RuntimeError("Unexpected catalog or workspace payload.")

        print(f"[ok] health: {health['status']}")
        print(
            f"[ok] runtime: backend={system['storage_backend']} inline_workers={system['inline_worker_enabled']} worker_count={system['worker_count']}"
        )
        print(
            f"[ok] overview: total_runs={overview['total_runs']} active_runs={overview['active_runs']} public_datasets={overview['public_dataset_count']}"
        )
        print(
            f"[ok] catalog: benchmarks={len(catalog['benchmark_templates'])} models={len(catalog['models'])} datasets={len(catalog['public_datasets'])}"
        )
        print(f"[ok] workspaces: {len(workspaces)} available")

        if args.skip_run:
            print("[ok] smoke test completed without queueing a benchmark run")
            return 0

        payload = choose_smoke_payload(workspaces, catalog)
        queued_run = request_json(client, "POST", build_url(base_url, "/api/runs"), json=payload)
        if not isinstance(queued_run, dict):
            raise RuntimeError("Unexpected queued run payload.")

        run_id = queued_run["run_id"]
        print(f"[ok] queued run: {run_id}")
        completed_run = wait_for_terminal_run(
            client,
            base_url,
            run_id,
            timeout=args.timeout,
            poll_interval=args.poll_interval,
        )
        print(f"[ok] terminal status: {completed_run['status']}")

        if completed_run["status"] not in {"completed", "replayed"}:
            raise RuntimeError(f"Hosted run failed: {completed_run.get('error_message')}")

        report_artifact = next(
            (artifact for artifact in completed_run["artifacts"] if artifact["artifact_type"] == "report"),
            None,
        )
        if not report_artifact:
            raise RuntimeError("No report artifact was generated.")

        report_url = build_url(base_url, report_artifact["download_url"])
        report = request_json(client, "GET", report_url)
        if not isinstance(report, dict) or report.get("run_id") != run_id:
            raise RuntimeError("Report artifact payload did not match the queued run.")

        print(
            f"[ok] report artifact: aggregate_score={report['summary']['aggregate_score']:.3f} latency_ms={report['summary']['average_latency_ms']:.1f}"
        )
        print("[ok] hosted smoke test completed successfully")
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - CLI should surface a concise failure message.
        print(f"[error] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc