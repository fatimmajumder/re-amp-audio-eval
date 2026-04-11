from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _coerce_bool(value: str | bool | None, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def normalize_database_url(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    if value.startswith("postgresql://") and "+psycopg" not in value:
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


@dataclass(frozen=True)
class Settings:
    base_dir: Path
    data_dir: Path
    runs_storage_path: Path
    workspaces_storage_path: Path
    artifacts_dir: Path
    public_datasets_dir: Path
    database_url: str | None
    storage_backend: str
    inline_worker_enabled: bool
    worker_count: int
    worker_poll_interval_seconds: float

    @property
    def database_enabled(self) -> bool:
        return self.storage_backend == "database" and bool(self.database_url)

    @classmethod
    def from_env(
        cls,
        base_dir: Path,
        *,
        storage_path: Path | None = None,
        database_url: str | None = None,
        inline_worker_enabled: bool | None = None,
    ) -> Settings:
        data_dir = storage_path.parent if storage_path else (base_dir / "data")
        runs_storage_path = storage_path or (data_dir / "runs.json")
        workspaces_storage_path = data_dir / "workspaces.json"
        artifacts_dir = data_dir / "artifacts"
        public_datasets_dir = data_dir / "public_datasets"

        normalized_database_url = normalize_database_url(database_url or os.getenv("DATABASE_URL"))
        storage_backend = os.getenv("REAMP_STORAGE_BACKEND", "database" if normalized_database_url else "json")
        if storage_backend not in {"json", "database"}:
            storage_backend = "json"
        if storage_backend == "database" and not normalized_database_url:
            storage_backend = "json"

        resolved_inline_worker = _coerce_bool(
            inline_worker_enabled,
            _coerce_bool(os.getenv("REAMP_INLINE_WORKERS"), True),
        )

        worker_count = max(int(os.getenv("REAMP_WORKER_COUNT", "2")), 1)
        worker_poll_interval_seconds = max(float(os.getenv("REAMP_WORKER_POLL_INTERVAL", "1.0")), 0.1)

        return cls(
            base_dir=base_dir,
            data_dir=data_dir,
            runs_storage_path=runs_storage_path,
            workspaces_storage_path=workspaces_storage_path,
            artifacts_dir=artifacts_dir,
            public_datasets_dir=public_datasets_dir,
            database_url=normalized_database_url,
            storage_backend=storage_backend,
            inline_worker_enabled=resolved_inline_worker,
            worker_count=worker_count,
            worker_poll_interval_seconds=worker_poll_interval_seconds,
        )
