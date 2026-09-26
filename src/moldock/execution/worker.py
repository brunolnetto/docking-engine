from __future__ import annotations

from collections.abc import Callable
from typing import AbstractSet
from datetime import datetime, timedelta

from moldock.backends import DockingBackend
from moldock.domain import TaskAttempt
from moldock.repositories import ArtifactRepository, TaskRepository
from moldock.results import ScientificResultInterpreter
from moldock.storage import ArtifactStore

from .executor import TaskExecutor
from .resolver import DockingInputResolver
from .runner import LeasedWorkerRunner


class Worker:
    """Compatibility facade for one leased task execution."""

    def __init__(
        self,
        *,
        task_repository: TaskRepository,
        artifact_repository: ArtifactRepository,
        artifact_store: ArtifactStore,
        input_resolver: DockingInputResolver,
        backend: DockingBackend,
        clock: Callable[[], datetime],
        result_interpreter: ScientificResultInterpreter | None = None,
        lease_duration: timedelta = timedelta(minutes=5),
        heartbeat_interval: timedelta = timedelta(minutes=1),
    ) -> None:
        executor = TaskExecutor(
            task_repository=task_repository,
            artifact_repository=artifact_repository,
            artifact_store=artifact_store,
            input_resolver=input_resolver,
            backend=backend,
            result_interpreter=result_interpreter,
        )
        self._runner = LeasedWorkerRunner(
            task_repository=task_repository,
            executor=executor,
            clock=clock,
            lease_duration=lease_duration,
            heartbeat_interval=heartbeat_interval,
        )

    @property
    def stopped(self) -> bool:
        return self._runner.stopped

    def stop(self) -> None:
        self._runner.stop()

    def run_once(
        self,
        experiment_id: str,
        run_id: str,
        worker_id: str,
        *,
        allowed_task_ids: AbstractSet[str] | None = None,
    ) -> TaskAttempt | None:
        return self._runner.run_once(
            experiment_id,
            run_id,
            worker_id,
            allowed_task_ids=allowed_task_ids,
        )
