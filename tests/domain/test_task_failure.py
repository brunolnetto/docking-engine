from datetime import datetime, timedelta, timezone

import pytest

from moldock.domain import (
    DomainValidationError,
    FailureKind,
    TaskAttempt,
    TaskStatus,
)


T0 = datetime(2026, 9, 25, 15, 0, tzinfo=timezone.utc)


def make_running():
    return TaskAttempt(
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


def test_failed_attempt_requires_typed_failure_kind():
    failed = make_running().fail(
        T0 + timedelta(seconds=1),
        "backend exploded",
        FailureKind.BACKEND,
    )

    assert failed.status is TaskStatus.FAILED
    assert failed.failure_kind is FailureKind.BACKEND


def test_non_failed_attempt_cannot_carry_failure_kind():
    with pytest.raises(DomainValidationError):
        TaskAttempt(
            attempt_id="attempt_1",
            task_id="task_1",
            run_id="run_1",
            attempt_number=1,
            worker_id="worker_1",
            failure_kind=FailureKind.BACKEND,
        )


def test_failed_attempt_rejects_missing_or_untyped_failure_kind():
    with pytest.raises(DomainValidationError):
        TaskAttempt(
            attempt_id="attempt_1",
            task_id="task_1",
            run_id="run_1",
            attempt_number=1,
            worker_id="worker_1",
            started_at=T0,
            finished_at=T0 + timedelta(seconds=1),
            status=TaskStatus.FAILED,
            error="boom",
        )

    with pytest.raises(DomainValidationError):
        make_running().fail(
            T0 + timedelta(seconds=1),
            "boom",
            "backend",
        )
