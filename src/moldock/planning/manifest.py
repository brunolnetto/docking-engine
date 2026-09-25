from __future__ import annotations

from dataclasses import dataclass
from typing import AbstractSet, Iterable

from moldock.domain import DockingTask, DomainValidationError, content_id


@dataclass(frozen=True, slots=True)
class TaskManifest:
    experiment_id: str
    tasks: tuple[DockingTask, ...]

    def __init__(
        self,
        experiment_id: str,
        tasks: Iterable[DockingTask],
    ) -> None:
        if not experiment_id.strip():
            raise DomainValidationError("experiment_id must not be blank")

        ordered = tuple(sorted(tasks, key=lambda task: task.task_id))
        task_ids = [task.task_id for task in ordered]

        if any(task.experiment_id != experiment_id for task in ordered):
            raise DomainValidationError(
                "all manifest tasks must belong to the manifest experiment"
            )

        if len(task_ids) != len(set(task_ids)):
            raise DomainValidationError("manifest cannot contain duplicate task IDs")

        object.__setattr__(self, "experiment_id", experiment_id)
        object.__setattr__(self, "tasks", ordered)

    @property
    def manifest_id(self) -> str:
        return content_id(
            "manifest",
            {
                "experiment_id": self.experiment_id,
                "task_ids": [task.task_id for task in self.tasks],
            },
        )

    @property
    def task_count(self) -> int:
        return len(self.tasks)

    def pending_tasks(
        self,
        completed_task_ids: AbstractSet[str],
    ) -> tuple[DockingTask, ...]:
        return tuple(
            task for task in self.tasks if task.task_id not in completed_task_ids
        )
