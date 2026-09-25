from __future__ import annotations

from typing import Protocol, runtime_checkable

from moldock.domain import DockingExecutionRequest, DockingResult


class DockingBackendError(RuntimeError):
    pass


class DockingBackendTimeoutError(DockingBackendError):
    pass


@runtime_checkable
class DockingBackend(Protocol):
    def execute(self, request: DockingExecutionRequest) -> DockingResult: ...
