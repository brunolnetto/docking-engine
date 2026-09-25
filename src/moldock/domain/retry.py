from __future__ import annotations

from dataclasses import dataclass

from .common import DomainValidationError


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_attempts, bool)
            or not isinstance(self.max_attempts, int)
            or self.max_attempts < 1
        ):
            raise DomainValidationError("max_attempts must be a positive integer")

    def can_attempt(self, attempt_number: int) -> bool:
        return attempt_number <= self.max_attempts
