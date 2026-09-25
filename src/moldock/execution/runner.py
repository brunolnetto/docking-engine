from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from threading import Event
from typing import Protocol

from moldock.domain import TaskAttempt, TaskStatus
from moldock.repositories import TaskRepository

from .executor import TaskExecutor
from .heartbeat import LeaseHeartbeat


class HeartbeatController(Protocol):
    @property
    def error(self) -> Exception | None: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...


HeartbeatFactory = Callable[..., HeartbeatController]


class LeasedWorkerRunner:
    """Own task claim, lease lifecycle, and attempt finalization."""

    def __init__(
        self,
        *,
        task_repository: TaskRepository,
        executor: TaskExecutor,
        clock: Callable[[], datetime],
        lease_duration: timedelta = timedelta(minutes=5),
        heartbeat_interval: timedelta = timedelta(minutes=1),
        heartbeat_factory: HeartbeatFactory = LeaseHeartbeat,
    ) -> None:
        self._tasks = task_repository
        self._executor = executor
        self._clock = clock
        self._lease_duration = lease_duration
        self._heartbeat_interval = heartbeat_interval
        self._heartbeat_factory = heartbeat_factory
        self._stopped = Event()

    @property
    def stopped(self) -> bool:
        return self._stopped.is_set()

    def stop(self) -> None:
        """Prevent future claims without cancelling the active attempt."""
        self._stopped.set()

    def run_once(
        self,
        experiment_id: str,
        run_id: str,
        worker_id: str,
    ) -> TaskAttempt | None:
        if self.stopped:
            return None

        attempt = self._tasks.claim_next(
            experiment_id=experiment_id,
            run_id=run_id,
            worker_id=worker_id,
            at=self._clock(),
            lease_duration=self._lease_duration,
        )
        if attempt is None:
            return None

        heartbeat = self._heartbeat_factory(
            repository=self._tasks,
            attempt=attempt,
            worker_id=worker_id,
            clock=self._clock,
            lease_duration=self._lease_duration,
            interval=self._heartbeat_interval,
        )

        execution_error: Exception | None = None
        heartbeat.start()
        try:
            self._executor.execute(attempt)
        except Exception as exc:
            execution_error = exc
        finally:
            heartbeat.stop()

        latest = self._latest_attempt(attempt)
        if latest.status is not TaskStatus.RUNNING:
            return latest

        error = heartbeat.error or execution_error
        if error is not None:
            return self._tasks.fail(
                latest.attempt_id,
                self._clock(),
                f"{type(error).__name__}: {error}",
            )

        return self._tasks.succeed(latest.attempt_id, self._clock())

    def _latest_attempt(self, attempt: TaskAttempt) -> TaskAttempt:
        history = self._tasks.attempts_for(
            attempt.task_id,
            attempt.run_id,
        )
        if not history:
            raise RuntimeError(
                f"claimed attempt history disappeared: {attempt.attempt_id}"
            )
        return history[-1]
