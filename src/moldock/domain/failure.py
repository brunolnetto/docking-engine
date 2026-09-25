from __future__ import annotations

from enum import Enum

from .common import DomainValidationError


class FailureKind(str, Enum):
    INPUT = "INPUT"
    BACKEND = "BACKEND"
    TIMEOUT = "TIMEOUT"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    ARTIFACT = "ARTIFACT"
    INTERPRETATION = "INTERPRETATION"
    LEASE = "LEASE"


class ExecutionFailure(RuntimeError):
    def __init__(self, kind: FailureKind, message: str) -> None:
        if not isinstance(kind, FailureKind):
            raise DomainValidationError("kind must be a FailureKind")
        if not message.strip():
            raise DomainValidationError("failure message must not be blank")
        self.kind = kind
        super().__init__(message)
