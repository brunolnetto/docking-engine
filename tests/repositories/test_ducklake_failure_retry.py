from datetime import datetime, timedelta, timezone

from moldock.domain import DockingTask, FailureKind, RetryPolicy
from moldock.repositories import DuckLakeTaskRepository


T0 = datetime(2026, 9, 25, 19, 0, tzinfo=timezone.utc)


def make_repo(tmp_path):
    return DuckLakeTaskRepository(
        catalog_path=tmp_path / "catalog.sqlite",
        data_path=tmp_path / "data",
        retry_policy=RetryPolicy(max_attempts=3),
        retry_delay_seconds=0,
    )


def make_task():
    return DockingTask(
        experiment_id="exp_1",
        receptor_id="rec_1",
        ligand_id="lig_1",
        prepared_receptor_id="prepared_rec_1",
        prepared_ligand_id="prepared_lig_1",
        search_space_id="space_1",
    )


def test_ducklake_persists_failure_kind_and_blocks_non_retryable_failure(tmp_path):
    repo = make_repo(tmp_path)
    task = make_task()
    repo.register(task)

    first = repo.claim_next("exp_1", "run_1", "worker_1", T0)
    assert first is not None
    failed = repo.fail(
        first.attempt_id,
        T0 + timedelta(seconds=1),
        "invalid ligand",
        FailureKind.INPUT,
    )

    history = repo.attempts_for(task.task_id, "run_1")
    assert history[-1].failure_kind is FailureKind.INPUT
    assert failed.failure_kind is FailureKind.INPUT
    assert repo.claim_next(
        "exp_1",
        "run_1",
        "worker_2",
        T0 + timedelta(seconds=2),
    ) is None
