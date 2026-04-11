from __future__ import annotations

import json
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from sqlalchemy import JSON, DateTime, String, create_engine, select, update
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .schemas import BenchmarkRun, WorkspaceRecord
from .settings import Settings


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RunStore(Protocol):
    def list_runs(self) -> list[BenchmarkRun]: ...

    def get_run(self, run_id: str) -> BenchmarkRun | None: ...

    def save_run(self, run: BenchmarkRun) -> BenchmarkRun: ...

    def claim_next_run(self) -> BenchmarkRun | None: ...

    def recover_incomplete_runs(self) -> int: ...


class WorkspaceStore(Protocol):
    def list_workspaces(self) -> list[WorkspaceRecord]: ...

    def get_workspace(self, workspace_id: str) -> WorkspaceRecord | None: ...

    def save_workspace(self, workspace: WorkspaceRecord) -> WorkspaceRecord: ...


class JsonRunRepository:
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
        self._runs = {item["run_id"]: BenchmarkRun.model_validate(item) for item in raw}

    def _persist(self) -> None:
        ordered = sorted(self._runs.values(), key=lambda run: run.created_at, reverse=True)
        payload = [run.model_dump(mode="json") for run in ordered]
        self.storage_path.write_text(json.dumps(payload, indent=2))

    def list_runs(self) -> list[BenchmarkRun]:
        with self._lock:
            return [
                deepcopy(run)
                for run in sorted(self._runs.values(), key=lambda item: item.created_at, reverse=True)
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

    def claim_next_run(self) -> BenchmarkRun | None:
        with self._lock:
            queued = sorted(
                (run for run in self._runs.values() if run.status == "queued"),
                key=lambda item: item.created_at,
            )
            if not queued:
                return None

            run = queued[0]
            claimed = run.model_copy(
                update={
                    "status": "running",
                    "progress": max(run.progress, 38),
                    "started_at": run.started_at or utc_now(),
                    "error_message": None,
                },
                deep=True,
            )
            self._runs[run.run_id] = claimed
            self._persist()
            return deepcopy(claimed)

    def recover_incomplete_runs(self) -> int:
        recovered = 0
        with self._lock:
            for run_id, run in list(self._runs.items()):
                if run.status != "running":
                    continue
                self._runs[run_id] = run.model_copy(
                    update={
                        "status": "queued",
                        "progress": 5,
                        "started_at": None,
                        "error_message": "Recovered after worker restart.",
                    },
                    deep=True,
                )
                recovered += 1
            if recovered:
                self._persist()
        return recovered


class JsonWorkspaceRepository:
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._workspaces: dict[str, WorkspaceRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self.storage_path.exists():
            return

        raw = json.loads(self.storage_path.read_text())
        self._workspaces = {
            item["workspace_id"]: WorkspaceRecord.model_validate(item)
            for item in raw
        }

    def _persist(self) -> None:
        ordered = sorted(self._workspaces.values(), key=lambda workspace: workspace.created_at)
        payload = [workspace.model_dump(mode="json") for workspace in ordered]
        self.storage_path.write_text(json.dumps(payload, indent=2))

    def list_workspaces(self) -> list[WorkspaceRecord]:
        with self._lock:
            return [
                deepcopy(workspace)
                for workspace in sorted(self._workspaces.values(), key=lambda item: item.name.lower())
            ]

    def get_workspace(self, workspace_id: str) -> WorkspaceRecord | None:
        with self._lock:
            workspace = self._workspaces.get(workspace_id)
            return deepcopy(workspace) if workspace else None

    def save_workspace(self, workspace: WorkspaceRecord) -> WorkspaceRecord:
        with self._lock:
            self._workspaces[workspace.workspace_id] = workspace.model_copy(deep=True)
            self._persist()
            return deepcopy(self._workspaces[workspace.workspace_id])


class Base(DeclarativeBase):
    pass


class RunRow(Base):
    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    benchmark_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class WorkspaceRow(Base):
    __tablename__ = "workspaces"

    workspace_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


def _engine_kwargs(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_pre_ping": True}


class DatabaseRunRepository:
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url, future=True, **_engine_kwargs(database_url))
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

    def list_runs(self) -> list[BenchmarkRun]:
        with self.session_factory() as session:
            rows = session.execute(select(RunRow).order_by(RunRow.created_at.desc())).scalars().all()
            return [BenchmarkRun.model_validate(row.payload) for row in rows]

    def get_run(self, run_id: str) -> BenchmarkRun | None:
        with self.session_factory() as session:
            row = session.get(RunRow, run_id)
            return BenchmarkRun.model_validate(row.payload) if row else None

    def save_run(self, run: BenchmarkRun) -> BenchmarkRun:
        payload = run.model_dump(mode="json")
        with self.session_factory.begin() as session:
            row = session.get(RunRow, run.run_id)
            if row is None:
                row = RunRow(
                    run_id=run.run_id,
                    benchmark_name=run.benchmark_name,
                    model_name=run.model_name,
                    workspace_id=run.workspace_id,
                    status=run.status,
                    created_at=run.created_at,
                    payload=payload,
                )
                session.add(row)
            else:
                row.benchmark_name = run.benchmark_name
                row.model_name = run.model_name
                row.workspace_id = run.workspace_id
                row.status = run.status
                row.created_at = run.created_at
                row.payload = payload
        return run.model_copy(deep=True)

    def claim_next_run(self) -> BenchmarkRun | None:
        while True:
            with self.session_factory.begin() as session:
                row = session.execute(
                    select(RunRow).where(RunRow.status == "queued").order_by(RunRow.created_at.asc()).limit(1)
                ).scalar_one_or_none()
                if row is None:
                    return None

                run = BenchmarkRun.model_validate(row.payload)
                claimed = run.model_copy(
                    update={
                        "status": "running",
                        "progress": max(run.progress, 38),
                        "started_at": run.started_at or utc_now(),
                        "error_message": None,
                    },
                    deep=True,
                )
                result = session.execute(
                    update(RunRow)
                    .where(RunRow.run_id == row.run_id, RunRow.status == "queued")
                    .values(status="running", payload=claimed.model_dump(mode="json"))
                )
                if result.rowcount == 1:
                    return claimed

    def recover_incomplete_runs(self) -> int:
        recovered = 0
        with self.session_factory.begin() as session:
            rows = session.execute(select(RunRow).where(RunRow.status == "running")).scalars().all()
            for row in rows:
                run = BenchmarkRun.model_validate(row.payload).model_copy(
                    update={
                        "status": "queued",
                        "progress": 5,
                        "started_at": None,
                        "error_message": "Recovered after worker restart.",
                    },
                    deep=True,
                )
                row.status = "queued"
                row.payload = run.model_dump(mode="json")
                recovered += 1
        return recovered


class DatabaseWorkspaceRepository:
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url, future=True, **_engine_kwargs(database_url))
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

    def list_workspaces(self) -> list[WorkspaceRecord]:
        with self.session_factory() as session:
            rows = session.execute(select(WorkspaceRow).order_by(WorkspaceRow.name.asc())).scalars().all()
            return [WorkspaceRecord.model_validate(row.payload) for row in rows]

    def get_workspace(self, workspace_id: str) -> WorkspaceRecord | None:
        with self.session_factory() as session:
            row = session.get(WorkspaceRow, workspace_id)
            return WorkspaceRecord.model_validate(row.payload) if row else None

    def save_workspace(self, workspace: WorkspaceRecord) -> WorkspaceRecord:
        payload = workspace.model_dump(mode="json")
        with self.session_factory.begin() as session:
            row = session.get(WorkspaceRow, workspace.workspace_id)
            if row is None:
                row = WorkspaceRow(
                    workspace_id=workspace.workspace_id,
                    name=workspace.name,
                    created_at=workspace.created_at,
                    payload=payload,
                )
                session.add(row)
            else:
                row.name = workspace.name
                row.created_at = workspace.created_at
                row.payload = payload
        return workspace.model_copy(deep=True)


def build_repositories(settings: Settings) -> tuple[RunStore, WorkspaceStore]:
    if settings.database_enabled and settings.database_url:
        return (
            DatabaseRunRepository(settings.database_url),
            DatabaseWorkspaceRepository(settings.database_url),
        )

    return (
        JsonRunRepository(settings.runs_storage_path),
        JsonWorkspaceRepository(settings.workspaces_storage_path),
    )
