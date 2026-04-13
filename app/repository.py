from __future__ import annotations

import json
import sqlite3
import threading
from copy import deepcopy
from pathlib import Path

from .schemas import BenchmarkRun, WorkspaceRecord


class RunRepository:
    def __init__(self, storage_path: Path, database_url: str | None = None):
        self.storage_path = storage_path
        self.database_url = database_url
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._runs: dict[str, BenchmarkRun] = {}

        self._conn: sqlite3.Connection | None = None
        if database_url:
            self._init_database(database_url)
        else:
            self._load_json()

    def _init_database(self, database_url: str) -> None:
        if not database_url.startswith("sqlite:///"):
            raise ValueError("This public portfolio build supports sqlite database URLs only.")
        db_path = Path(database_url.removeprefix("sqlite:///"))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def _load_json(self) -> None:
        if not self.storage_path.exists():
            return
        raw = json.loads(self.storage_path.read_text())
        self._runs = {item["run_id"]: BenchmarkRun.model_validate(item) for item in raw}

    def _persist_json(self) -> None:
        ordered = sorted(self._runs.values(), key=lambda run: run.created_at, reverse=True)
        payload = [run.model_dump(mode="json") for run in ordered]
        self.storage_path.write_text(json.dumps(payload, indent=2))

    def list_runs(self) -> list[BenchmarkRun]:
        with self._lock:
            if self._conn:
                rows = self._conn.execute(
                    "SELECT payload FROM runs ORDER BY created_at DESC"
                ).fetchall()
                return [BenchmarkRun.model_validate(json.loads(row[0])) for row in rows]
            return [
                deepcopy(run)
                for run in sorted(self._runs.values(), key=lambda item: item.created_at, reverse=True)
            ]

    def get_run(self, run_id: str) -> BenchmarkRun | None:
        with self._lock:
            if self._conn:
                row = self._conn.execute(
                    "SELECT payload FROM runs WHERE run_id = ?",
                    (run_id,),
                ).fetchone()
                return BenchmarkRun.model_validate(json.loads(row[0])) if row else None
            run = self._runs.get(run_id)
            return deepcopy(run) if run else None

    def save_run(self, run: BenchmarkRun) -> BenchmarkRun:
        with self._lock:
            payload = json.dumps(run.model_dump(mode="json"))
            if self._conn:
                self._conn.execute(
                    """
                    INSERT INTO runs(run_id, created_at, payload)
                    VALUES (?, ?, ?)
                    ON CONFLICT(run_id) DO UPDATE SET
                        created_at = excluded.created_at,
                        payload = excluded.payload
                    """,
                    (run.run_id, run.created_at.isoformat(), payload),
                )
                self._conn.commit()
                return BenchmarkRun.model_validate(json.loads(payload))

            self._runs[run.run_id] = run.model_copy(deep=True)
            self._persist_json()
            return deepcopy(self._runs[run.run_id])


class WorkspaceRepository:
    def __init__(self, storage_path: Path, database_url: str | None = None):
        self.storage_path = storage_path
        self.database_url = database_url
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._workspaces: dict[str, WorkspaceRecord] = {}

        self._conn: sqlite3.Connection | None = None
        if database_url:
            self._init_database(database_url)
        else:
            self._load_json()

    def _init_database(self, database_url: str) -> None:
        if not database_url.startswith("sqlite:///"):
            raise ValueError("This public portfolio build supports sqlite database URLs only.")
        db_path = Path(database_url.removeprefix("sqlite:///"))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workspaces (
                workspace_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def _load_json(self) -> None:
        if not self.storage_path.exists():
            return
        raw = json.loads(self.storage_path.read_text())
        self._workspaces = {
            item["workspace_id"]: WorkspaceRecord.model_validate(item)
            for item in raw
        }

    def _persist_json(self) -> None:
        ordered = sorted(self._workspaces.values(), key=lambda workspace: workspace.created_at)
        payload = [workspace.model_dump(mode="json") for workspace in ordered]
        self.storage_path.write_text(json.dumps(payload, indent=2))

    def list_workspaces(self) -> list[WorkspaceRecord]:
        with self._lock:
            if self._conn:
                rows = self._conn.execute(
                    "SELECT payload FROM workspaces ORDER BY created_at ASC"
                ).fetchall()
                workspaces = [WorkspaceRecord.model_validate(json.loads(row[0])) for row in rows]
                return sorted(workspaces, key=lambda item: item.name.lower())
            return [
                deepcopy(workspace)
                for workspace in sorted(self._workspaces.values(), key=lambda item: item.name.lower())
            ]

    def get_workspace(self, workspace_id: str) -> WorkspaceRecord | None:
        with self._lock:
            if self._conn:
                row = self._conn.execute(
                    "SELECT payload FROM workspaces WHERE workspace_id = ?",
                    (workspace_id,),
                ).fetchone()
                return WorkspaceRecord.model_validate(json.loads(row[0])) if row else None
            workspace = self._workspaces.get(workspace_id)
            return deepcopy(workspace) if workspace else None

    def save_workspace(self, workspace: WorkspaceRecord) -> WorkspaceRecord:
        with self._lock:
            payload = json.dumps(workspace.model_dump(mode="json"))
            if self._conn:
                self._conn.execute(
                    """
                    INSERT INTO workspaces(workspace_id, created_at, payload)
                    VALUES (?, ?, ?)
                    ON CONFLICT(workspace_id) DO UPDATE SET
                        created_at = excluded.created_at,
                        payload = excluded.payload
                    """,
                    (workspace.workspace_id, workspace.created_at.isoformat(), payload),
                )
                self._conn.commit()
                return WorkspaceRecord.model_validate(json.loads(payload))

            self._workspaces[workspace.workspace_id] = workspace.model_copy(deep=True)
            self._persist_json()
            return deepcopy(self._workspaces[workspace.workspace_id])
