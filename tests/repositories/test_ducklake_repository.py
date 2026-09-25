from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier, Lock

import duckdb

import pytest

from moldock.domain import DockingTask, DomainValidationError, FailureKind, TaskStatus
from moldock.repositories import DuckLakeTaskRepository, TaskRepository


T0 = datetime(2026, 9, 25, 19, 0, tzinfo=timezone.utc)


def make_task() -> DockingTask:
    return DockingTask(
        experiment_id="exp_1",
        receptor_id="rec_1",
        ligand_id="lig_1",
        prepared_receptor_id="prepared_rec_1",
        prepared_ligand_id="prepared_lig_1",
        search_space_id="space_1",
    )


def make_repo(tmp_path, *, before_claim_write=None):
    return DuckLakeTaskRepository(
        catalog_path=tmp_path / "catalog.sqlite",
        data_path=tmp_path / "data",
        default_lease_duration=timedelta(minutes=5),
        max_transaction_retries=8,
        before_claim_write=before_claim_write,
    )


def test_ducklake_repository_satisfies_task_repository_contract(tmp_path):
    repo = make_repo(tmp_path)

    assert isinstance(repo, TaskRepository)


def test_ducklake_repository_round_trips_task_and_attempt_lifecycle(tmp_path):
    repo = make_repo(tmp_path)
    task = make_task()
    repo.register(task)

    assert repo.get(task.task_id) == task
    assert repo.list_for_experiment("exp_1") == (task,)

    attempt = repo.claim_next(
        "exp_1",
        "run_1",
        "worker_1",
        T0,
        lease_duration=timedelta(minutes=5),
    )
    assert attempt is not None
    assert attempt.status is TaskStatus.RUNNING

    heartbeat = repo.heartbeat(
        attempt.attempt_id,
        worker_id="worker_1",
        at=T0 + timedelta(minutes=1),
        lease_duration=timedelta(minutes=5),
    )
    assert heartbeat.lease_expires_at == T0 + timedelta(minutes=6)

    completed = repo.succeed(
        attempt.attempt_id,
        T0 + timedelta(minutes=2),
    )
    assert completed.status is TaskStatus.SUCCEEDED
    assert repo.attempts_for(task.task_id, "run_1") == (completed,)


def test_two_independent_ducklake_clients_cannot_claim_same_task(tmp_path):
    task = make_task()
    barrier = Barrier(2)
    calls = 0
    calls_lock = Lock()

    def synchronize_first_candidate():
        nonlocal calls
        with calls_lock:
            calls += 1
            should_wait = calls <= 2
        if should_wait:
            barrier.wait(timeout=5)

    repo1 = make_repo(tmp_path, before_claim_write=synchronize_first_candidate)
    repo1.register(task)
    repo2 = make_repo(tmp_path, before_claim_write=synchronize_first_candidate)

    def claim(repo, worker_id):
        return repo.claim_next(
            "exp_1",
            "run_1",
            worker_id,
            T0,
            lease_duration=timedelta(minutes=5),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda args: claim(*args),
                ((repo1, "worker_1"), (repo2, "worker_2")),
            )
        )

    claimed = [attempt for attempt in results if attempt is not None]
    assert len(claimed) == 1
    assert claimed[0].status is TaskStatus.RUNNING

    history = repo1.attempts_for(task.task_id, "run_1")
    assert len(history) == 1
    assert history[0].attempt_id == claimed[0].attempt_id


def test_expired_ducklake_lease_is_failed_and_reclaimed(tmp_path):
    repo1 = make_repo(tmp_path)
    task = make_task()
    repo1.register(task)

    first = repo1.claim_next(
        "exp_1",
        "run_1",
        "worker_1",
        T0,
        lease_duration=timedelta(minutes=1),
    )
    assert first is not None

    repo2 = make_repo(tmp_path)
    second = repo2.claim_next(
        "exp_1",
        "run_1",
        "worker_2",
        T0 + timedelta(minutes=2),
        lease_duration=timedelta(minutes=5),
    )

    assert second is not None
    assert second.attempt_number == 2
    history = repo1.attempts_for(task.task_id, "run_1")
    assert history[0].status is TaskStatus.FAILED
    assert history[0].error == "lease expired"
    assert history[1].status is TaskStatus.RUNNING


def test_ducklake_registration_is_idempotent_across_clients(tmp_path):
    task = make_task()
    repo1 = make_repo(tmp_path)
    repo2 = make_repo(tmp_path)

    repo1.register(task)
    repo2.register(task)

    assert repo1.list_for_experiment("exp_1") == (task,)


def test_concurrent_repository_bootstrap_creates_one_coordination_row(tmp_path):
    barrier = Barrier(2)

    class SynchronizedBootstrapRepository(DuckLakeTaskRepository):
        def _initialize_schema(self):
            barrier.wait(timeout=5)
            super()._initialize_schema()

    def construct():
        return SynchronizedBootstrapRepository(
            catalog_path=tmp_path / "catalog.sqlite",
            data_path=tmp_path / "data",
            default_lease_duration=timedelta(minutes=5),
            max_transaction_retries=8,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        repos = list(pool.map(lambda _: construct(), range(2)))

    try:
        rows = repos[0]._connection.execute(
            """
            SELECT coordination_key, epoch
            FROM moldock.claim_coordination
            WHERE coordination_key = 'task_repository'
            """
        ).fetchall()
        assert len(rows) == 1
    finally:
        for repo in repos:
            repo.close()


@pytest.mark.parametrize("method", ["claim", "heartbeat", "succeed", "fail"])
def test_ducklake_repository_rejects_naive_timestamps(tmp_path, method):
    repo = make_repo(tmp_path)
    task = make_task()
    repo.register(task)
    naive = T0.replace(tzinfo=None)

    if method == "claim":
        with pytest.raises(DomainValidationError, match="timezone-aware"):
            repo.claim_next("exp_1", "run_1", "worker_1", naive)
        return

    attempt = repo.claim_next("exp_1", "run_1", "worker_1", T0)
    assert attempt is not None

    if method == "heartbeat":
        action = lambda: repo.heartbeat(
            attempt.attempt_id,
            worker_id="worker_1",
            at=naive,
        )
    elif method == "succeed":
        action = lambda: repo.succeed(attempt.attempt_id, naive)
    else:
        action = lambda: repo.fail(attempt.attempt_id, naive, "boom", FailureKind.BACKEND)

    with pytest.raises(DomainValidationError, match="timezone-aware"):
        action()


def test_deferred_expiry_commit_conflict_is_retried_before_domain_error(tmp_path):
    repo = DuckLakeTaskRepository(
        catalog_path=tmp_path / "catalog.sqlite",
        data_path=tmp_path / "data",
        default_lease_duration=timedelta(minutes=1),
        max_transaction_retries=3,
        retry_delay_seconds=0,
    )
    task = make_task()
    repo.register(task)
    attempt = repo.claim_next(
        "exp_1",
        "run_1",
        "worker_1",
        T0,
        lease_duration=timedelta(minutes=1),
    )
    assert attempt is not None

    inner = repo._connection

    class CommitConflictOnceConnection:
        def __init__(self):
            self.conflicts = 0

        def execute(self, query, parameters=None):
            if query.strip().upper() == "COMMIT" and self.conflicts == 0:
                self.conflicts += 1
                raise duckdb.TransactionException(
                    "transaction conflict injected by test"
                )
            if parameters is None:
                return inner.execute(query)
            return inner.execute(query, parameters)

        def __getattr__(self, name):
            return getattr(inner, name)

    wrapped = CommitConflictOnceConnection()
    repo._connection = wrapped

    with pytest.raises(DomainValidationError, match="lease has expired"):
        repo.succeed(
            attempt.attempt_id,
            T0 + timedelta(minutes=2),
        )

    assert wrapped.conflicts == 1
    history = repo.attempts_for(task.task_id, "run_1")
    assert history[-1].status is TaskStatus.FAILED
    assert history[-1].error == "lease expired"
