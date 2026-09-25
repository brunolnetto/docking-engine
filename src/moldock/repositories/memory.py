from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from threading import RLock

from moldock.domain import (
    ArtifactMetadata,
    DockingTask,
    DomainValidationError,
    FailureKind,
    RetryPolicy,
    TaskAttempt,
    TaskStatus,
    content_id,
)


class InMemoryTaskRepository:
    def __init__(
        self,
        *,
        retry_policy: RetryPolicy | None = None,
        default_lease_duration: timedelta = timedelta(minutes=5),
    ) -> None:
        if default_lease_duration <= timedelta(0):
            raise DomainValidationError("default_lease_duration must be > 0")
        self._tasks: dict[str, DockingTask] = {}
        self._attempts: dict[str, TaskAttempt] = {}
        self._attempt_ids_by_task_run: dict[tuple[str, str], list[str]] = defaultdict(list)
        self._lock = RLock()
        self._retry_policy = retry_policy or RetryPolicy()
        self._default_lease_duration = default_lease_duration

    def register(self, task: DockingTask) -> None:
        with self._lock:
            existing = self._tasks.get(task.task_id)
            if existing is None:
                self._tasks[task.task_id] = task
                return
            if existing != task:
                raise DomainValidationError(
                    "task identity already exists with conflicting provenance"
                )

    def get(self, task_id: str) -> DockingTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list_for_experiment(self, experiment_id: str) -> tuple[DockingTask, ...]:
        with self._lock:
            return tuple(
                sorted(
                    (
                        task
                        for task in self._tasks.values()
                        if task.experiment_id == experiment_id
                    ),
                    key=lambda task: task.task_id,
                )
            )

    def claim_next(
        self,
        experiment_id: str,
        run_id: str,
        worker_id: str,
        at: datetime,
        *,
        lease_duration: timedelta | None = None,
    ) -> TaskAttempt | None:
        if not run_id.strip():
            raise DomainValidationError("run_id must not be blank")
        if not worker_id.strip():
            raise DomainValidationError("worker_id must not be blank")
        duration = (
            self._default_lease_duration
            if lease_duration is None
            else lease_duration
        )
        if duration <= timedelta(0):
            raise DomainValidationError("lease_duration must be > 0")

        with self._lock:
            for task in self.list_for_experiment(experiment_id):
                history = self.attempts_for(task.task_id, run_id)

                if history and history[-1].status is TaskStatus.RUNNING:
                    latest = history[-1]
                    if not latest.lease_expired(at):
                        continue
                    expired = latest.fail(at, "lease expired", FailureKind.LEASE)
                    self._attempts[latest.attempt_id] = expired
                    history = self.attempts_for(task.task_id, run_id)

                if history and history[-1].status is TaskStatus.SUCCEEDED:
                    continue

                attempt_number = len(history) + 1
                previous_failure_kind = (
                    history[-1].failure_kind
                    if history and history[-1].status is TaskStatus.FAILED
                    else None
                )
                if not self._retry_policy.can_attempt(
                    attempt_number,
                    previous_failure_kind,
                ):
                    continue

                attempt = TaskAttempt(
                    attempt_id=content_id(
                        "attempt",
                        {
                            "task_id": task.task_id,
                            "run_id": run_id,
                            "attempt_number": attempt_number,
                        },
                    ),
                    task_id=task.task_id,
                    run_id=run_id,
                    attempt_number=attempt_number,
                    worker_id=worker_id,
                    started_at=at,
                    heartbeat_at=at,
                    lease_expires_at=at + duration,
                    status=TaskStatus.RUNNING,
                )
                self._attempts[attempt.attempt_id] = attempt
                self._attempt_ids_by_task_run[(task.task_id, run_id)].append(
                    attempt.attempt_id
                )
                return attempt

            return None

    def heartbeat(
        self,
        attempt_id: str,
        *,
        worker_id: str,
        at: datetime,
        lease_duration: timedelta | None = None,
    ) -> TaskAttempt:
        duration = (
            self._default_lease_duration
            if lease_duration is None
            else lease_duration
        )
        if duration <= timedelta(0):
            raise DomainValidationError("lease_duration must be > 0")

        with self._lock:
            attempt = self._require_attempt(attempt_id)
            if attempt.worker_id != worker_id:
                raise DomainValidationError(
                    "worker does not own this attempt"
                )
            if attempt.lease_expired(at):
                expired = attempt.fail(at, "lease expired", FailureKind.LEASE)
                self._attempts[attempt_id] = expired
                raise DomainValidationError("attempt lease has expired")

            updated = attempt.heartbeat(
                at=at,
                lease_duration=duration,
            )
            self._attempts[attempt_id] = updated
            return updated

    def succeed(self, attempt_id: str, at: datetime) -> TaskAttempt:
        with self._lock:
            attempt = self._require_attempt(attempt_id)
            if attempt.lease_expired(at):
                expired = attempt.fail(at, "lease expired")
                self._attempts[attempt_id] = expired
                raise DomainValidationError("attempt lease has expired")
            updated = attempt.succeed(at)
            self._attempts[attempt_id] = updated
            return updated

    def fail(
        self,
        attempt_id: str,
        at: datetime,
        error: str,
        failure_kind: FailureKind,
    ) -> TaskAttempt:
        with self._lock:
            attempt = self._require_attempt(attempt_id)
            updated = attempt.fail(at, error, failure_kind)
            self._attempts[attempt_id] = updated
            return updated

    def attempts_for(
        self,
        task_id: str,
        run_id: str,
    ) -> tuple[TaskAttempt, ...]:
        with self._lock:
            ids = self._attempt_ids_by_task_run.get((task_id, run_id), ())
            return tuple(self._attempts[attempt_id] for attempt_id in ids)

    def _require_attempt(self, attempt_id: str) -> TaskAttempt:
        attempt = self._attempts.get(attempt_id)
        if attempt is None:
            raise DomainValidationError(f"unknown attempt: {attempt_id}")
        return attempt


class InMemoryArtifactRepository:
    def __init__(self) -> None:
        self._artifacts: dict[str, ArtifactMetadata] = {}

    def register(self, artifact: ArtifactMetadata) -> None:
        existing = self._artifacts.get(artifact.artifact_id)
        if existing is None:
            self._artifacts[artifact.artifact_id] = artifact
            return
        if existing != artifact:
            raise DomainValidationError(
                "artifact ID already exists with conflicting metadata"
            )

    def get(self, artifact_id: str) -> ArtifactMetadata | None:
        return self._artifacts.get(artifact_id)

    def list_for_attempt(
        self,
        attempt_id: str,
    ) -> tuple[ArtifactMetadata, ...]:
        return tuple(
            sorted(
                (
                    artifact
                    for artifact in self._artifacts.values()
                    if artifact.producer_attempt_id == attempt_id
                ),
                key=lambda artifact: artifact.artifact_id,
            )
        )
