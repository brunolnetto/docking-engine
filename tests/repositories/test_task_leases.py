from datetime import datetime, timedelta, timezone

import pytest

from moldock.domain import DockingTask, DomainValidationError, RetryPolicy, TaskStatus
from moldock.repositories import InMemoryTaskRepository


T0 = datetime(2026, 9, 25, 14, 0, tzinfo=timezone.utc)


def make_task():
    return DockingTask(
        experiment_id="exp_1",
        receptor_id="rec_1",
        ligand_id="lig_1",
        prepared_receptor_id="prepared_rec_1",
        prepared_ligand_id="prepared_lig_1",
        search_space_id="space_1",
    )


def test_repository_rejects_non_positive_default_lease():
    with pytest.raises(DomainValidationError):
        InMemoryTaskRepository(default_lease_duration=timedelta(0))


def test_claim_rejects_blank_run_and_worker_ids():
    repo = InMemoryTaskRepository()
    repo.register(make_task())

    with pytest.raises(DomainValidationError):
        repo.claim_next("exp_1", " ", "worker_1", T0)

    with pytest.raises(DomainValidationError):
        repo.claim_next("exp_1", "run_1", " ", T0)


def test_claim_rejects_explicit_zero_duration():
    repo = InMemoryTaskRepository()
    repo.register(make_task())

    with pytest.raises(DomainValidationError):
        repo.claim_next(
            "exp_1",
            "run_1",
            "worker_1",
            T0,
            lease_duration=timedelta(0),
        )


def test_claim_assigns_lease():
    repo = InMemoryTaskRepository()
    task = make_task()
    repo.register(task)

    attempt = repo.claim_next(
        "exp_1",
        "run_1",
        "worker_1",
        T0,
        lease_duration=timedelta(minutes=5),
    )

    assert attempt is not None
    assert attempt.heartbeat_at == T0
    assert attempt.lease_expires_at == T0 + timedelta(minutes=5)


def test_active_lease_blocks_reclaim():
    repo = InMemoryTaskRepository()
    task = make_task()
    repo.register(task)
    repo.claim_next(
        "exp_1",
        "run_1",
        "worker_1",
        T0,
        lease_duration=timedelta(minutes=5),
    )

    assert repo.claim_next(
        "exp_1",
        "run_1",
        "worker_2",
        T0 + timedelta(minutes=4),
        lease_duration=timedelta(minutes=5),
    ) is None


def test_expired_lease_is_failed_and_reclaimed():
    repo = InMemoryTaskRepository()
    task = make_task()
    repo.register(task)
    first = repo.claim_next(
        "exp_1",
        "run_1",
        "worker_1",
        T0,
        lease_duration=timedelta(minutes=5),
    )
    assert first is not None

    second = repo.claim_next(
        "exp_1",
        "run_1",
        "worker_2",
        T0 + timedelta(minutes=6),
        lease_duration=timedelta(minutes=5),
    )

    assert second is not None
    assert second.attempt_number == 2
    history = repo.attempts_for(task.task_id, "run_1")
    assert history[0].status is TaskStatus.FAILED
    assert history[0].error == "lease expired"
    assert history[1].status is TaskStatus.RUNNING


def test_heartbeat_extends_repository_lease():
    repo = InMemoryTaskRepository()
    repo.register(make_task())
    attempt = repo.claim_next(
        "exp_1",
        "run_1",
        "worker_1",
        T0,
        lease_duration=timedelta(minutes=5),
    )
    assert attempt is not None

    updated = repo.heartbeat(
        attempt.attempt_id,
        worker_id="worker_1",
        at=T0 + timedelta(minutes=4),
        lease_duration=timedelta(minutes=5),
    )

    assert updated.lease_expires_at == T0 + timedelta(minutes=9)
    assert repo.claim_next(
        "exp_1",
        "run_1",
        "worker_2",
        T0 + timedelta(minutes=6),
        lease_duration=timedelta(minutes=5),
    ) is None


def test_heartbeat_rejects_explicit_zero_duration():
    repo = InMemoryTaskRepository()
    repo.register(make_task())
    attempt = repo.claim_next("exp_1", "run_1", "worker_1", T0)
    assert attempt is not None

    with pytest.raises(DomainValidationError):
        repo.heartbeat(
            attempt.attempt_id,
            worker_id="worker_1",
            at=T0 + timedelta(seconds=1),
            lease_duration=timedelta(0),
        )


def test_heartbeat_rejects_wrong_worker():
    repo = InMemoryTaskRepository()
    repo.register(make_task())
    attempt = repo.claim_next(
        "exp_1",
        "run_1",
        "worker_1",
        T0,
        lease_duration=timedelta(minutes=5),
    )
    assert attempt is not None

    with pytest.raises(DomainValidationError, match="worker"):
        repo.heartbeat(
            attempt.attempt_id,
            worker_id="worker_2",
            at=T0 + timedelta(minutes=1),
            lease_duration=timedelta(minutes=5),
        )


def test_expired_heartbeat_marks_attempt_failed():
    repo = InMemoryTaskRepository()
    repo.register(make_task())
    attempt = repo.claim_next(
        "exp_1",
        "run_1",
        "worker_1",
        T0,
        lease_duration=timedelta(minutes=1),
    )
    assert attempt is not None

    with pytest.raises(DomainValidationError, match="expired"):
        repo.heartbeat(
            attempt.attempt_id,
            worker_id="worker_1",
            at=T0 + timedelta(minutes=2),
        )

    history = repo.attempts_for(attempt.task_id, "run_1")
    assert history[-1].status is TaskStatus.FAILED
    assert history[-1].error == "lease expired"


def test_succeed_rejects_expired_lease_and_marks_failed():
    repo = InMemoryTaskRepository()
    repo.register(make_task())
    attempt = repo.claim_next(
        "exp_1",
        "run_1",
        "worker_1",
        T0,
        lease_duration=timedelta(minutes=1),
    )
    assert attempt is not None

    with pytest.raises(DomainValidationError, match="expired"):
        repo.succeed(attempt.attempt_id, T0 + timedelta(minutes=2))

    history = repo.attempts_for(attempt.task_id, "run_1")
    assert history[-1].status is TaskStatus.FAILED


def test_retry_policy_stops_after_max_attempts():
    repo = InMemoryTaskRepository(retry_policy=RetryPolicy(max_attempts=2))
    repo.register(make_task())

    first = repo.claim_next(
        "exp_1", "run_1", "worker_1", T0,
        lease_duration=timedelta(minutes=1),
    )
    assert first is not None
    repo.fail(first.attempt_id, T0 + timedelta(seconds=10), "boom")

    second = repo.claim_next(
        "exp_1", "run_1", "worker_2", T0 + timedelta(seconds=20),
        lease_duration=timedelta(minutes=1),
    )
    assert second is not None
    repo.fail(second.attempt_id, T0 + timedelta(seconds=30), "boom again")

    assert repo.claim_next(
        "exp_1", "run_1", "worker_3", T0 + timedelta(seconds=40),
        lease_duration=timedelta(minutes=1),
    ) is None
