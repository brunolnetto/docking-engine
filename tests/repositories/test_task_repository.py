from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
import time

import pytest

from moldock.domain import DockingTask, DomainValidationError, FailureKind, TaskStatus
from moldock.repositories import InMemoryTaskRepository
import moldock.repositories.memory as memory_module


UTC = timezone.utc
T0 = datetime(2026, 9, 25, 14, 0, tzinfo=UTC)


def make_task(
    ligand_id: str = "lig_1",
    prepared_ligand_id: str = "prepared_lig_1",
) -> DockingTask:
    return DockingTask(
        experiment_id="exp_1",
        receptor_id="rec_1",
        ligand_id=ligand_id,
        prepared_receptor_id="prepared_rec_1",
        prepared_ligand_id=prepared_ligand_id,
        search_space_id="space_1",
    )


def test_register_is_idempotent_for_identical_task():
    repo = InMemoryTaskRepository()
    task = make_task()

    repo.register(task)
    repo.register(task)

    assert repo.get(task.task_id) == task
    assert repo.list_for_experiment("exp_1") == (task,)


def test_register_rejects_same_task_identity_with_conflicting_provenance():
    repo = InMemoryTaskRepository()
    first = make_task("source_a", "same_prepared")
    conflicting = make_task("source_b", "same_prepared")

    assert first.task_id == conflicting.task_id

    repo.register(first)

    with pytest.raises(DomainValidationError):
        repo.register(conflicting)


def test_claim_creates_running_attempt():
    repo = InMemoryTaskRepository()
    task = make_task()
    repo.register(task)

    attempt = repo.claim_next(
        experiment_id="exp_1",
        run_id="run_1",
        worker_id="worker_1",
        at=T0,
    )

    assert attempt is not None
    assert attempt.task_id == task.task_id
    assert attempt.run_id == "run_1"
    assert attempt.attempt_number == 1
    assert attempt.status is TaskStatus.RUNNING
    assert attempt.started_at == T0


def test_running_task_cannot_be_claimed_twice_in_same_run():
    repo = InMemoryTaskRepository()
    repo.register(make_task())

    first = repo.claim_next("exp_1", "run_1", "worker_1", T0)
    second = repo.claim_next(
        "exp_1",
        "run_1",
        "worker_2",
        T0 + timedelta(seconds=1),
    )

    assert first is not None
    assert second is None


def test_claim_next_is_atomic_across_threads(monkeypatch):
    repo = InMemoryTaskRepository()
    task = make_task()
    repo.register(task)

    start = Barrier(2)
    real_content_id = memory_module.content_id

    def slow_content_id(prefix, value):
        if prefix == "attempt":
            time.sleep(0.05)
        return real_content_id(prefix, value)

    monkeypatch.setattr(memory_module, "content_id", slow_content_id)

    def claim(worker_id):
        start.wait()
        return repo.claim_next("exp_1", "run_1", worker_id, T0)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ("worker_1", "worker_2")))

    claimed = [result for result in results if result is not None]

    assert len(claimed) == 1
    assert len(repo.attempts_for(task.task_id, "run_1")) == 1


def test_failed_task_can_be_retried_with_incremented_attempt_number():
    repo = InMemoryTaskRepository()
    repo.register(make_task())

    first = repo.claim_next("exp_1", "run_1", "worker_1", T0)
    assert first is not None
    failed = repo.fail(
        first.attempt_id,
        T0 + timedelta(seconds=1),
        "backend exited 1",
        FailureKind.BACKEND,
    )

    retry = repo.claim_next(
        "exp_1",
        "run_1",
        "worker_2",
        T0 + timedelta(seconds=2),
    )

    assert failed.status is TaskStatus.FAILED
    assert retry is not None
    assert retry.attempt_number == 2
    assert retry.attempt_id != first.attempt_id


def test_succeeded_task_is_terminal_for_that_run():
    repo = InMemoryTaskRepository()
    repo.register(make_task())

    attempt = repo.claim_next("exp_1", "run_1", "worker_1", T0)
    assert attempt is not None
    succeeded = repo.succeed(attempt.attempt_id, T0 + timedelta(seconds=1))

    assert succeeded.status is TaskStatus.SUCCEEDED
    assert repo.claim_next(
        "exp_1",
        "run_1",
        "worker_2",
        T0 + timedelta(seconds=2),
    ) is None


def test_success_in_one_run_does_not_prevent_intentional_new_run():
    repo = InMemoryTaskRepository()
    repo.register(make_task())

    first = repo.claim_next("exp_1", "run_1", "worker_1", T0)
    assert first is not None
    repo.succeed(first.attempt_id, T0 + timedelta(seconds=1))

    second = repo.claim_next(
        "exp_1",
        "run_2",
        "worker_2",
        T0 + timedelta(seconds=2),
    )

    assert second is not None
    assert second.run_id == "run_2"
    assert second.attempt_number == 1


def test_claim_order_is_deterministic_by_task_id():
    repo = InMemoryTaskRepository()
    a = make_task("lig_a", "prepared_a")
    b = make_task("lig_b", "prepared_b")
    repo.register(b)
    repo.register(a)

    claimed = repo.claim_next("exp_1", "run_1", "worker_1", T0)

    assert claimed is not None
    assert claimed.task_id == min(a.task_id, b.task_id)


def test_unknown_attempt_cannot_be_completed():
    repo = InMemoryTaskRepository()

    with pytest.raises(DomainValidationError):
        repo.succeed("missing", T0)


def test_only_running_attempt_can_be_completed():
    repo = InMemoryTaskRepository()
    repo.register(make_task())
    attempt = repo.claim_next("exp_1", "run_1", "worker_1", T0)
    assert attempt is not None
    repo.fail(attempt.attempt_id, T0 + timedelta(seconds=1), "boom", FailureKind.BACKEND)

    with pytest.raises(DomainValidationError):
        repo.succeed(attempt.attempt_id, T0 + timedelta(seconds=2))


def test_attempt_history_is_preserved():
    repo = InMemoryTaskRepository()
    task = make_task()
    repo.register(task)

    first = repo.claim_next("exp_1", "run_1", "worker_1", T0)
    assert first is not None
    repo.fail(first.attempt_id, T0 + timedelta(seconds=1), "boom", FailureKind.BACKEND)
    second = repo.claim_next(
        "exp_1",
        "run_1",
        "worker_2",
        T0 + timedelta(seconds=2),
    )
    assert second is not None

    history = repo.attempts_for(task.task_id, "run_1")

    assert [attempt.attempt_number for attempt in history] == [1, 2]
    assert history[0].status is TaskStatus.FAILED
    assert history[1].status is TaskStatus.RUNNING


def test_claim_next_can_be_restricted_to_allowed_task_ids():
    repo = InMemoryTaskRepository()
    first = make_task("lig_a", "prepared_a")
    second = make_task("lig_b", "prepared_b")
    repo.register(first)
    repo.register(second)

    claimed = repo.claim_next(
        "exp_1",
        "run_1",
        "worker_1",
        T0,
        allowed_task_ids={second.task_id},
    )

    assert claimed is not None
    assert claimed.task_id == second.task_id
    assert repo.attempts_for(first.task_id, "run_1") == ()


def test_claim_next_with_empty_allowed_task_ids_claims_nothing():
    repo = InMemoryTaskRepository()
    repo.register(make_task())

    assert (
        repo.claim_next(
            "exp_1",
            "run_1",
            "worker_1",
            T0,
            allowed_task_ids=set(),
        )
        is None
    )
