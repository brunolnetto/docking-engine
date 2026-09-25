from datetime import datetime, timedelta, timezone

import pytest

from moldock.domain import (
    DockingTask,
    DomainValidationError,
    ExperimentRun,
    TaskAttempt,
    TaskStatus,
)


UTC = timezone.utc
T0 = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)


def make_task(**overrides):
    values = dict(
        experiment_id="exp_1",
        receptor_id="rec_1",
        ligand_id="lig_1",
        prepared_receptor_id="rprep_1",
        prepared_ligand_id="lprep_1",
        search_space_id="space_1",
    )
    values.update(overrides)
    return DockingTask(**values)


def make_attempt(**overrides):
    values = dict(
        attempt_id="attempt_1",
        task_id="task_1",
        run_id="run_1",
        attempt_number=1,
        worker_id="worker_1",
    )
    values.update(overrides)
    return TaskAttempt(**values)


def test_task_identity_depends_on_prepared_inputs_and_experiment():
    a = make_task()
    b = make_task()
    c = make_task(prepared_ligand_id="lprep_2")

    assert a.task_id == b.task_id
    assert a.task_id != c.task_id


def test_run_can_finish_only_after_it_starts():
    with pytest.raises(DomainValidationError):
        ExperimentRun(
            run_id="run_1",
            experiment_id="exp_1",
            runtime_version="0.1.0",
            started_at=T0,
            finished_at=T0 - timedelta(seconds=1),
        )


def test_attempt_happy_path_pending_running_succeeded():
    pending = make_attempt()

    running = pending.start(T0)
    succeeded = running.succeed(T0 + timedelta(seconds=5))

    assert pending.status is TaskStatus.PENDING
    assert running.status is TaskStatus.RUNNING
    assert succeeded.status is TaskStatus.SUCCEEDED
    assert succeeded.started_at == T0
    assert succeeded.finished_at == T0 + timedelta(seconds=5)
    assert succeeded.error is None


def test_attempt_can_fail_with_error():
    failed = (
        make_attempt()
        .start(T0)
        .fail(T0 + timedelta(seconds=2), "vina process exited with code 1")
    )

    assert failed.status is TaskStatus.FAILED
    assert failed.error == "vina process exited with code 1"


def test_pending_attempt_cannot_succeed_without_starting():
    with pytest.raises(DomainValidationError):
        make_attempt().succeed(T0)


def test_failed_attempt_requires_non_blank_error():
    running = make_attempt().start(T0)

    with pytest.raises(DomainValidationError):
        running.fail(T0 + timedelta(seconds=1), " ")
