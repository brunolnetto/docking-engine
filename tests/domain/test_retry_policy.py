import pytest

from moldock.domain import DomainValidationError, FailureKind, RetryPolicy


@pytest.mark.parametrize("max_attempts", [0, -1, 1.5, True])
def test_retry_policy_requires_positive_integer(max_attempts):
    with pytest.raises(DomainValidationError):
        RetryPolicy(max_attempts=max_attempts)


def test_first_attempt_is_allowed_within_limit():
    policy = RetryPolicy(max_attempts=3)

    assert policy.can_attempt(1)
    assert not policy.can_attempt(4)


def test_retry_requires_retryable_previous_failure():
    policy = RetryPolicy(max_attempts=3)

    assert policy.can_attempt(2, FailureKind.BACKEND)
    assert policy.can_attempt(2, FailureKind.LEASE)
    assert not policy.can_attempt(2, FailureKind.INPUT)
    assert not policy.can_attempt(2, FailureKind.INTERPRETATION)


def test_retryable_failure_still_respects_attempt_limit():
    policy = RetryPolicy(max_attempts=2)

    assert not policy.can_attempt(3, FailureKind.INFRASTRUCTURE)


def test_retry_policy_validates_retryable_kinds():
    with pytest.raises(DomainValidationError):
        RetryPolicy(retryable_kinds=frozenset({"backend"}))
