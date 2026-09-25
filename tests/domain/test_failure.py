import pytest

from moldock.domain import (
    DomainValidationError,
    ExecutionFailure,
    FailureKind,
)


def test_execution_failure_carries_typed_kind_and_message():
    failure = ExecutionFailure(
        FailureKind.BACKEND,
        "vina failed",
    )

    assert failure.kind is FailureKind.BACKEND
    assert str(failure) == "vina failed"


def test_execution_failure_rejects_invalid_kind_and_blank_message():
    with pytest.raises(DomainValidationError):
        ExecutionFailure("backend", "boom")

    with pytest.raises(DomainValidationError):
        ExecutionFailure(FailureKind.BACKEND, " ")
