from __future__ import annotations

import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.repository import build_repositories
from app.service import RunService
from app.settings import Settings
from app.worker import run_worker_forever


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    settings = Settings.from_env(ROOT, inline_worker_enabled=False)
    repository, workspace_repository = build_repositories(settings)
    service = RunService(
        repository,
        workspace_repository,
        settings.artifacts_dir,
        settings.public_datasets_dir,
        settings,
    )
    service.ensure_seed_workspaces()
    service.recover_incomplete_runs()
    run_worker_forever(
        service,
        worker_count=settings.worker_count,
        poll_interval_seconds=settings.worker_poll_interval_seconds,
    )


if __name__ == "__main__":
    main()
