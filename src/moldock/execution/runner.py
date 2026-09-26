from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from threading import Event, Lock
from typing import AbstractSet, Protocol

from moldock.domain import (
    DomainValidationError,
    ExecutionFailure,
    FailureKind,
    TaskAttempt,
    TaskStatus,
)
from moldock.repositories import TaskRepository

from .executor import TaskExecutor
from .heartbeat import LeaseHeartbeat


class HeartbeatController(Protocol):
    @property
    def error(self) -> Exception | None: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...


HeartbeatFactory = Callable[..., HeartbeatController]


def _failure(error: Exception, default_kind: FailureKind) -> ExecutionFailure:
    if isinstance(error, ExecutionFailure):
        return error
    return ExecutionFailure(
        default_kind,
        f"{type(error).__name__}: {error}",
    )


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
        if lease_duration <= timedelta(0):
            raise DomainValidationError("lease_duration must be > 0")
        if heartbeat_interval <= timedelta(0):
            raise DomainValidationError("heartbeat interval must be > 0")
        if heartbeat_interval >= lease_duration:
            raise DomainValidationError(
                "heartbeat interval must be shorter than lease duration"
            )

        self._lease_duration = lease_duration
        self._heartbeat_interval = heartbeat_interval
        self._heartbeat_factory = heartbeat_factory
        self._stopped = Event()
        self._claim_lock = Lock()

    @property
    def stopped(self) -> bool:
        return self._stopped.is_set()

    def stop(self) -> None:
        with self._claim_lock:
            self._stopped.set()

    def run_once(
        self,
        experiment_id: str,
        run_id: str,
        worker_id: str,
        *,
        allowed_task_ids: AbstractSet[str] | None = None,
    ) -> TaskAttempt | None:
        with self._claim_lock:
            if self.stopped:
                return None
            attempt = self._tasks.claim_next(
                experiment_id=experiment_id,
                run_id=run_id,
                worker_id=worker_id,
                at=self._clock(),
                lease_duration=self._lease_duration,
                allowed_task_ids=allowed_task_ids,
            )
        if attempt is None:
            return None

        execution_error: Exception | None = None
        heartbeat = None
        heartbeat_started = False
        try:
            heartbeat = self._heartbeat_factory(
                repository=self._tasks,
                attempt=attempt,
                worker_id=worker_id,
                clock=self._clock,
                lease_duration=self._lease_duration,
                interval=self._heartbeat_interval,
            )
            heartbeat.start()
            heartbeat_started = True
            self._executor.execute(attempt)
        except Exception as exc:
            execution_error = exc
        finally:
            if heartbeat is not None:
                try:
                    heartbeat.stop()
                except Exception as stop_error:
                    if execution_error is None:
                        execution_error = stop_error

        if not heartbeat_started and execution_error is not None:
            failure = _failure(execution_error, FailureKind.LEASE)
            return self._fail_attempt(attempt, failure)

        current = self._current_attempt(attempt)
        if current.status is not TaskStatus.RUNNING:
            return current

        heartbeat_error = heartbeat.error if heartbeat is not None else None
        if heartbeat_error is not None:
            return self._fail_attempt(
                attempt,
                _failure(heartbeat_error, FailureKind.LEASE),
            )

        if execution_error is not None:
            return self._fail_attempt(
                attempt,
                _failure(
                    execution_error,
                    FailureKind.INFRASTRUCTURE,
                ),
            )

        return self._finalize_attempt(
            attempt,
            lambda: self._tasks.succeed(
                attempt.attempt_id,
                self._clock(),
            ),
        )

    def _fail_attempt(
        self,
        attempt: TaskAttempt,
        failure: ExecutionFailure,
    ) -> TaskAttempt:
        return self._finalize_attempt(
            attempt,
            lambda: self._tasks.fail(
                attempt.attempt_id,
                self._clock(),
                str(failure),
                failure.kind,
            ),
        )

    def _current_attempt(self, attempt: TaskAttempt) -> TaskAttempt:
        history = self._tasks.attempts_for(
            attempt.task_id,
            attempt.run_id,
        )
        current = next(
            (
                item
                for item in history
                if item.attempt_id == attempt.attempt_id
            ),
            None,
        )
        if current is None:
            raise RuntimeError(
                f"claimed attempt disappeared: {attempt.attempt_id}"
            )
        return current

    def _finalize_attempt(
        self,
        attempt: TaskAttempt,
        finalize: Callable[[], TaskAttempt],
    ) -> TaskAttempt:
        try:
            return finalize()
        except DomainValidationError:
            current = self._current_attempt(attempt)
            if current.status is not TaskStatus.RUNNING:
                return current
            raise
