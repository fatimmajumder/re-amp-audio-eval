from __future__ import annotations

import logging
import threading
import time

from .service import RunService

logger = logging.getLogger(__name__)


class RunWorkerPool:
    def __init__(
        self,
        service: RunService,
        *,
        worker_count: int = 1,
        poll_interval_seconds: float = 1.0,
    ):
        self.service = service
        self.worker_count = max(worker_count, 1)
        self.poll_interval_seconds = max(poll_interval_seconds, 0.1)
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        if self._threads:
            return

        for index in range(self.worker_count):
            thread = threading.Thread(
                target=self._run_loop,
                name=f"reamp-worker-{index + 1}",
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        self._stop_event.set()
        for thread in self._threads:
            thread.join(timeout=1.5)
        self._threads.clear()

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            claimed_run = None
            try:
                claimed_run = self.service.claim_next_run()
                if not claimed_run:
                    self._stop_event.wait(self.poll_interval_seconds)
                    continue
                self.service.execute_run(claimed_run.run_id)
            except Exception:
                logger.exception(
                    "Worker loop failed while processing run %s",
                    claimed_run.run_id if claimed_run else "n/a",
                )
                self._stop_event.wait(min(self.poll_interval_seconds, 1.0))


def run_worker_forever(
    service: RunService,
    *,
    worker_count: int = 1,
    poll_interval_seconds: float = 1.0,
) -> None:
    pool = RunWorkerPool(
        service,
        worker_count=worker_count,
        poll_interval_seconds=poll_interval_seconds,
    )
    pool.start()
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        pool.stop()
