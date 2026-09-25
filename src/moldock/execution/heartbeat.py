from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from threading import Event, Thread

from moldock.domain import DomainValidationError, TaskAttempt
from moldock.repositories import TaskRepository


Waiter = Callable[[Event, float], bool]


def _default_waiter(stop_event: Event, interval_seconds: float) -> bool:
    return stop_event.wait(interval_seconds)


class LeaseHeartbeat:
    """Renew an attempt lease until stopped or renewal fails."""

    def __init__(
        self,
        *,
        repository: TaskRepository,
        attempt: TaskAttempt,
        worker_id: str,
        clock: Callable[[], datetime],
        lease_duration: timedelta = timedelta(minutes=5),
        interval: timedelta = timedelta(minutes=1),
        waiter: Waiter | None = None,
    ) -> None:
        if lease_duration <= timedelta(0):
            raise DomainValidationError("lease_duration must be > 0")
        if interval <= timedelta(0):
            raise DomainValidationError("heartbeat interval must be > 0")
        if interval >= lease_duration:
            raise DomainValidationError(
                "heartbeat interval must be shorter than lease duration"
            )

        self._repository = repository
        self._attempt = attempt
        self._worker_id = worker_id
        self._clock = clock
        self._lease_duration = lease_duration
        self._interval = interval
        self._waiter = waiter or _default_waiter
        self._stop_event = Event()
        self._heartbeat_event = Event()
        self._thread: Thread | None = None
        self._error: Exception | None = None

    @property
    def error(self) -> Exception | None:
        return self._error

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("heartbeat already started")
        self._thread = Thread(
            target=self._run,
            name=f"lease-heartbeat-{self._attempt.attempt_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()

    def wait_for_heartbeat(self, timeout: float | None = None) -> bool:
        return self._heartbeat_event.wait(timeout)

    def _run(self) -> None:
        while not self._waiter(
            self._stop_event,
            self._interval.total_seconds(),
        ):
            try:
                self._repository.heartbeat(
                    self._attempt.attempt_id,
                    worker_id=self._worker_id,
                    at=self._clock(),
                    lease_duration=self._lease_duration,
                )
            except Exception as exc:
                self._error = exc
                self._heartbeat_event.set()
                return
            self._heartbeat_event.set()
