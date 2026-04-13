from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _read_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class AppSettings:
    database_url: str | None
    inline_worker_enabled: bool
    worker_count: int
    multi_tenant_enabled: bool = True
    cache_enabled: bool = True
    app_version: str = "2.3.0"

    @property
    def database_enabled(self) -> bool:
        return bool(self.database_url)

    @property
    def storage_backend(self) -> str:
        return "database" if self.database_enabled else "json"

    @property
    def database_url_hint(self) -> str | None:
        if not self.database_url:
            return None
        if self.database_url.startswith("sqlite:///"):
            return Path(self.database_url.removeprefix("sqlite:///")).name
        return "configured"

    @classmethod
    def from_inputs(
        cls,
        *,
        database_url: str | None = None,
        inline_worker_enabled: bool | None = None,
        worker_count: int | None = None,
    ) -> "AppSettings":
        resolved_database_url = database_url if database_url is not None else os.getenv("DATABASE_URL")
        resolved_inline = (
            inline_worker_enabled
            if inline_worker_enabled is not None
            else _read_bool("REAMP_INLINE_WORKERS", True)
        )
        resolved_workers = worker_count if worker_count is not None else int(os.getenv("REAMP_WORKER_COUNT", "1"))
        return cls(
            database_url=resolved_database_url,
            inline_worker_enabled=resolved_inline,
            worker_count=max(1, resolved_workers),
        )
