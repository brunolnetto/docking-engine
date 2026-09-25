from datetime import datetime, timedelta, timezone

import pytest

from moldock.domain import DomainValidationError, TaskAttempt, TaskStatus


T0 = datetime(2026, 9, 25, 14, 0, tzinfo=timezone.utc)


def make_running(**overrides):
    values = dict(
        attempt_id="attempt_1",
        task_id="task_1",
        run_id="run_1",
        attempt_number=1,
        worker_id="worker_1",
        started_at=T0,
        heartbeat_at=T0,
        lease_expires_at=T0 + timedelta(minutes=5),
        status=TaskStatus.RUNNING,
    )
    values.update(overrides)
    return TaskAttempt(**values)


def test_running_attempt_requires_lease_timestamps():
    with pytest.raises(DomainValidationError):
        make_running(heartbeat_at=None)

    with pytest.raises(DomainValidationError):
        make_running(lease_expires_at=None)


def test_lease_must_not_precede_heartbeat():
    with pytest.raises(DomainValidationError):
        make_running(
            heartbeat_at=T0 + timedelta(minutes=2),
            lease_expires_at=T0 + timedelta(minutes=1),
        )


def test_heartbeat_extends_lease():
    attempt = make_running()

    updated = attempt.heartbeat(
        at=T0 + timedelta(minutes=2),
        lease_duration=timedelta(minutes=10),
    )

    assert updated.heartbeat_at == T0 + timedelta(minutes=2)
    assert updated.lease_expires_at == T0 + timedelta(minutes=12)


def test_heartbeat_must_be_monotonic():
    attempt = make_running()

    with pytest.raises(DomainValidationError):
        attempt.heartbeat(
            at=T0 - timedelta(seconds=1),
            lease_duration=timedelta(minutes=5),
        )


def test_terminal_attempts_clear_lease_state():
    attempt = make_running()

    succeeded = attempt.succeed(T0 + timedelta(minutes=1))
    failed = attempt.fail(T0 + timedelta(minutes=1), "boom")

    assert succeeded.heartbeat_at is None
    assert succeeded.lease_expires_at is None
    assert failed.heartbeat_at is None
    assert failed.lease_expires_at is None
