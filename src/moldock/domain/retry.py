from __future__ import annotations

from dataclasses import dataclass, field

from .common import DomainValidationError
from .failure import FailureKind


_DEFAULT_RETRYABLE_KINDS = frozenset(
    {
        FailureKind.BACKEND,
        FailureKind.TIMEOUT,
        FailureKind.INFRASTRUCTURE,
        FailureKind.ARTIFACT,
        FailureKind.LEASE,
    }
)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    retryable_kinds: frozenset[FailureKind] = field(
        default_factory=lambda: _DEFAULT_RETRYABLE_KINDS
    )

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_attempts, bool)
            or not isinstance(self.max_attempts, int)
            or self.max_attempts < 1
        ):
            raise DomainValidationError("max_attempts must be a positive integer")
        if any(
            not isinstance(kind, FailureKind)
            for kind in self.retryable_kinds
        ):
            raise DomainValidationError(
                "retryable_kinds must contain only FailureKind values"
            )
        object.__setattr__(
            self,
            "retryable_kinds",
            frozenset(self.retryable_kinds),
        )

    def can_attempt(
        self,
        attempt_number: int,
        previous_failure_kind: FailureKind | None = None,
    ) -> bool:
        if attempt_number > self.max_attempts:
            return False
        if attempt_number == 1:
            return True
        return previous_failure_kind in self.retryable_kinds
