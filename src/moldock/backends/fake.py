from __future__ import annotations

from moldock.domain import DockingOutputArtifact, DockingResult, DockingTask

from .base import DockingBackendError


class FakeDockingBackend:
    def __init__(self, fail_task_ids: set[str] | None = None) -> None:
        self._fail_task_ids = set(fail_task_ids or ())
        self._calls: list[str] = []

    @property
    def calls(self) -> tuple[str, ...]:
        return tuple(self._calls)

    def execute(self, task: DockingTask) -> DockingResult:
        self._calls.append(task.task_id)

        if task.task_id in self._fail_task_ids:
            raise DockingBackendError(f"fake backend failed task {task.task_id}")

        content = f"FAKE_PDBQT\nREMARK task_id={task.task_id}\n".encode()
        return DockingResult(
            artifacts=(
                DockingOutputArtifact(
                    kind="docking_pose",
                    media_type="chemical/x-pdbqt",
                    content=content,
                ),
            ),
            stdout=f"executed {task.task_id}",
            stderr="",
        )
