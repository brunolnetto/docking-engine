from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum

from .common import DomainValidationError, content_id
from .failure import FailureKind


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class DockingTask:
    experiment_id: str
    receptor_id: str
    ligand_id: str
    prepared_receptor_id: str
    prepared_ligand_id: str
    search_space_id: str

    def __post_init__(self) -> None:
        for name in (
            "experiment_id",
            "receptor_id",
            "ligand_id",
            "prepared_receptor_id",
            "prepared_ligand_id",
            "search_space_id",
        ):
            if not getattr(self, name).strip():
                raise DomainValidationError(f"{name} must not be blank")

    @property
    def task_id(self) -> str:
        return content_id(
            "task",
            {
                "experiment_id": self.experiment_id,
                "prepared_receptor_id": self.prepared_receptor_id,
                "prepared_ligand_id": self.prepared_ligand_id,
                "search_space_id": self.search_space_id,
            },
        )


@dataclass(frozen=True, slots=True)
class ExperimentRun:
    run_id: str
    experiment_id: str
    runtime_version: str
    started_at: datetime
    finished_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise DomainValidationError("run_id must not be blank")
        if not self.experiment_id.strip():
            raise DomainValidationError("experiment_id must not be blank")
        if not self.runtime_version.strip():
            raise DomainValidationError("runtime_version must not be blank")
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise DomainValidationError("finished_at cannot be before started_at")


@dataclass(frozen=True, slots=True)
class TaskAttempt:
    attempt_id: str
    task_id: str
    run_id: str
    attempt_number: int
    worker_id: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    heartbeat_at: datetime | None = None
    lease_expires_at: datetime | None = None
    status: TaskStatus = TaskStatus.PENDING
    error: str | None = None
    failure_kind: FailureKind | None = None

    def __post_init__(self) -> None:
        if self.attempt_number < 1:
            raise DomainValidationError("attempt_number must be >= 1")
        if not self.attempt_id.strip():
            raise DomainValidationError("attempt_id must not be blank")
        if not self.task_id.strip():
            raise DomainValidationError("task_id must not be blank")
        if not self.run_id.strip():
            raise DomainValidationError("run_id must not be blank")
        if not self.worker_id.strip():
            raise DomainValidationError("worker_id must not be blank")

        if (
            self.started_at is not None
            and self.finished_at is not None
            and self.finished_at < self.started_at
        ):
            raise DomainValidationError("finished_at cannot be before started_at")

        if self.status is TaskStatus.PENDING:
            if any(
                value is not None
                for value in (
                    self.started_at,
                    self.finished_at,
                    self.heartbeat_at,
                    self.lease_expires_at,
                    self.error,
                    self.failure_kind,
                )
            ):
                raise DomainValidationError(
                    "pending attempt cannot have timestamps, lease state, or failure"
                )
            return

        if self.status is TaskStatus.RUNNING:
            if self.started_at is None:
                raise DomainValidationError("running attempt must have started_at")
            if self.finished_at is not None:
                raise DomainValidationError("running attempt cannot have finished_at")
            if self.error is not None or self.failure_kind is not None:
                raise DomainValidationError(
                    "running attempt cannot have failure metadata"
                )
            if self.heartbeat_at is None:
                raise DomainValidationError("running attempt must have heartbeat_at")
            if self.lease_expires_at is None:
                raise DomainValidationError("running attempt must have lease_expires_at")
            if self.heartbeat_at < self.started_at:
                raise DomainValidationError("heartbeat_at cannot precede started_at")
            if self.lease_expires_at < self.heartbeat_at:
                raise DomainValidationError(
                    "lease_expires_at cannot precede heartbeat_at"
                )
            return

        if self.status is TaskStatus.SUCCEEDED:
            if self.started_at is None or self.finished_at is None:
                raise DomainValidationError(
                    "successful attempt must have started_at and finished_at"
                )
            if self.error is not None or self.failure_kind is not None:
                raise DomainValidationError(
                    "successful attempt cannot include failure metadata"
                )
            if self.heartbeat_at is not None or self.lease_expires_at is not None:
                raise DomainValidationError(
                    "successful attempt cannot retain lease state"
                )
            return

        if self.status is TaskStatus.FAILED:
            if self.started_at is None or self.finished_at is None:
                raise DomainValidationError(
                    "failed attempt must have started_at and finished_at"
                )
            if not self.error or not self.error.strip():
                raise DomainValidationError("failed attempt must include an error")
            if not isinstance(self.failure_kind, FailureKind):
                raise DomainValidationError(
                    "failed attempt must include a FailureKind"
                )
            if self.heartbeat_at is not None or self.lease_expires_at is not None:
                raise DomainValidationError(
                    "failed attempt cannot retain lease state"
                )
            return

        raise DomainValidationError(f"unsupported attempt status: {self.status!r}")

    def start(
        self,
        at: datetime,
        *,
        lease_duration: timedelta,
    ) -> "TaskAttempt":
        if self.status is not TaskStatus.PENDING:
            raise DomainValidationError("only pending attempts can be started")
        if lease_duration <= timedelta(0):
            raise DomainValidationError("lease_duration must be > 0")
        return replace(
            self,
            status=TaskStatus.RUNNING,
            started_at=at,
            heartbeat_at=at,
            lease_expires_at=at + lease_duration,
        )

    def heartbeat(
        self,
        *,
        at: datetime,
        lease_duration: timedelta,
    ) -> "TaskAttempt":
        if self.status is not TaskStatus.RUNNING:
            raise DomainValidationError("only running attempts can heartbeat")
        if at < self.heartbeat_at:
            raise DomainValidationError("heartbeat cannot move backwards")
        if lease_duration <= timedelta(0):
            raise DomainValidationError("lease_duration must be > 0")
        return replace(
            self,
            heartbeat_at=at,
            lease_expires_at=at + lease_duration,
        )

    def lease_expired(self, at: datetime) -> bool:
        return (
            self.status is TaskStatus.RUNNING
            and self.lease_expires_at is not None
            and at >= self.lease_expires_at
        )

    def succeed(self, at: datetime) -> "TaskAttempt":
        if self.status is not TaskStatus.RUNNING or self.started_at is None:
            raise DomainValidationError("only running attempts can succeed")
        if at < self.started_at:
            raise DomainValidationError("completion cannot precede start")
        return replace(
            self,
            status=TaskStatus.SUCCEEDED,
            finished_at=at,
            heartbeat_at=None,
            lease_expires_at=None,
            error=None,
            failure_kind=None,
        )

    def fail(
        self,
        at: datetime,
        error: str,
        failure_kind: FailureKind,
    ) -> "TaskAttempt":
        if self.status is not TaskStatus.RUNNING or self.started_at is None:
            raise DomainValidationError("only running attempts can fail")
        if not error.strip():
            raise DomainValidationError("failure must include an error")
        if not isinstance(failure_kind, FailureKind):
            raise DomainValidationError("failure_kind must be a FailureKind")
        if at < self.started_at:
            raise DomainValidationError("completion cannot precede start")
        return replace(
            self,
            status=TaskStatus.FAILED,
            finished_at=at,
            heartbeat_at=None,
            lease_expires_at=None,
            error=error,
            failure_kind=failure_kind,
        )
