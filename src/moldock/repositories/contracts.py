from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable

from moldock.domain import ArtifactMetadata, DockingTask, TaskAttempt


@runtime_checkable
class TaskRepository(Protocol):
    def register(self, task: DockingTask) -> None: ...

    def get(self, task_id: str) -> DockingTask | None: ...

    def list_for_experiment(self, experiment_id: str) -> tuple[DockingTask, ...]: ...

    def claim_next(
        self,
        experiment_id: str,
        run_id: str,
        worker_id: str,
        at: datetime,
        *,
        lease_duration: timedelta | None = None,
    ) -> TaskAttempt | None: ...

    def heartbeat(
        self,
        attempt_id: str,
        *,
        worker_id: str,
        at: datetime,
        lease_duration: timedelta | None = None,
    ) -> TaskAttempt: ...

    def succeed(self, attempt_id: str, at: datetime) -> TaskAttempt: ...

    def fail(self, attempt_id: str, at: datetime, error: str) -> TaskAttempt: ...

    def attempts_for(
        self,
        task_id: str,
        run_id: str,
    ) -> tuple[TaskAttempt, ...]: ...


@runtime_checkable
class ArtifactRepository(Protocol):
    def register(self, artifact: ArtifactMetadata) -> None: ...

    def get(self, artifact_id: str) -> ArtifactMetadata | None: ...

    def list_for_attempt(
        self,
        attempt_id: str,
    ) -> tuple[ArtifactMetadata, ...]: ...
