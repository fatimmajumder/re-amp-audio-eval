from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path

from .schemas import BenchmarkRun


class RunRepository:
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._runs: dict[str, BenchmarkRun] = {}
        self._load()

    def _load(self) -> None:
        if not self.storage_path.exists():
            return

        raw = json.loads(self.storage_path.read_text())
        self._runs = {
            item["run_id"]: BenchmarkRun.model_validate(item)
            for item in raw
        }

    def _persist(self) -> None:
        ordered = sorted(
            self._runs.values(),
            key=lambda run: run.created_at,
            reverse=True,
        )
        payload = [run.model_dump(mode="json") for run in ordered]
        self.storage_path.write_text(json.dumps(payload, indent=2))

    def list_runs(self) -> list[BenchmarkRun]:
        with self._lock:
            return [
                deepcopy(run)
                for run in sorted(
                    self._runs.values(),
                    key=lambda item: item.created_at,
                    reverse=True,
                )
            ]

    def get_run(self, run_id: str) -> BenchmarkRun | None:
        with self._lock:
            run = self._runs.get(run_id)
            return deepcopy(run) if run else None

    def save_run(self, run: BenchmarkRun) -> BenchmarkRun:
        with self._lock:
            self._runs[run.run_id] = run.model_copy(deep=True)
            self._persist()
            return deepcopy(self._runs[run.run_id])
