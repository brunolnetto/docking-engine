from datetime import datetime, timedelta, timezone

from moldock.domain import DockingTask, FailureKind, RetryPolicy
from moldock.repositories import InMemoryTaskRepository


T0 = datetime(2026, 9, 25, 15, 0, tzinfo=timezone.utc)


def make_task():
    return DockingTask(
        experiment_id="exp_1",
        receptor_id="rec_1",
        ligand_id="lig_1",
        prepared_receptor_id="prepared_rec_1",
        prepared_ligand_id="prepared_lig_1",
        search_space_id="space_1",
    )


def claim(repo, worker, at):
    return repo.claim_next(
        "exp_1",
        "run_1",
        worker,
        at,
        lease_duration=timedelta(minutes=5),
    )


def test_non_retryable_input_failure_stops_future_claims():
    repo = InMemoryTaskRepository(retry_policy=RetryPolicy(max_attempts=3))
    repo.register(make_task())
    first = claim(repo, "worker_1", T0)
    assert first is not None

    repo.fail(
        first.attempt_id,
        T0 + timedelta(seconds=1),
        "invalid ligand",
        FailureKind.INPUT,
    )

    assert claim(repo, "worker_2", T0 + timedelta(seconds=2)) is None


def test_retryable_backend_failure_allows_next_attempt():
    repo = InMemoryTaskRepository(retry_policy=RetryPolicy(max_attempts=3))
    repo.register(make_task())
    first = claim(repo, "worker_1", T0)
    assert first is not None

    repo.fail(
        first.attempt_id,
        T0 + timedelta(seconds=1),
        "vina crashed",
        FailureKind.BACKEND,
    )

    second = claim(repo, "worker_2", T0 + timedelta(seconds=2))

    assert second is not None
    assert second.attempt_number == 2
