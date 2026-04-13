from __future__ import annotations

import time

from .service import RunService


class QueueWorker:
    def __init__(self, service: RunService, poll_interval: float = 1.0):
        self.service = service
        self.poll_interval = poll_interval

    def run_forever(self) -> None:
        while True:
            run = self.service.execute_next_queued_run()
            if run is None:
                time.sleep(self.poll_interval)
                continue
            print(f"[worker] completed {run.run_id} ({run.status})")
