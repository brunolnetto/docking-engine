from __future__ import annotations

from typing import Protocol, runtime_checkable

from moldock.domain import DockingResult, DockingTask


class DockingBackendError(RuntimeError):
    pass


@runtime_checkable
class DockingBackend(Protocol):
    def execute(self, task: DockingTask) -> DockingResult: ...
