from __future__ import annotations

from app.main import create_app
from app.worker import QueueWorker


def main() -> int:
    app = create_app(seed_demo_data=False)
    worker = QueueWorker(app.state.run_service, poll_interval=1.0)
    worker.run_forever()


if __name__ == "__main__":
    raise SystemExit(main())
