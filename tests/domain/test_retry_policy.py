import pytest

from moldock.domain import DomainValidationError, RetryPolicy


@pytest.mark.parametrize("max_attempts", [0, -1, 1.5, True])
def test_retry_policy_requires_positive_integer(max_attempts):
    with pytest.raises(DomainValidationError):
        RetryPolicy(max_attempts=max_attempts)


def test_retry_policy_allows_attempts_up_to_limit():
    policy = RetryPolicy(max_attempts=3)

    assert policy.can_attempt(1)
    assert policy.can_attempt(2)
    assert policy.can_attempt(3)
    assert not policy.can_attempt(4)
