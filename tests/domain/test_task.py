from datetime import datetime, timedelta, timezone

import pytest

from moldock.domain import (
    DockingTask,
    DomainValidationError,
    ExperimentRun,
    FailureKind,
    TaskAttempt,
    TaskStatus,
)


UTC = timezone.utc
T0 = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
LEASE = timedelta(minutes=5)


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


def make_run(**overrides):
    values = dict(
        run_id="run_1",
        experiment_id="exp_1",
        runtime_version="0.1.0",
        started_at=T0,
    )
    values.update(overrides)
    return ExperimentRun(**values)


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


def running_attempt(**overrides):
    values = dict(
        status=TaskStatus.RUNNING,
        started_at=T0,
        heartbeat_at=T0,
        lease_expires_at=T0 + LEASE,
    )
    values.update(overrides)
    return make_attempt(**values)


def test_task_identity_depends_on_prepared_inputs_and_experiment():
    a = make_task()
    b = make_task()
    c = make_task(prepared_ligand_id="lprep_2")

    assert a.task_id == b.task_id
    assert a.task_id != c.task_id


@pytest.mark.parametrize(
    "field",
    [
        "experiment_id",
        "receptor_id",
        "ligand_id",
        "prepared_receptor_id",
        "prepared_ligand_id",
        "search_space_id",
    ],
)
def test_task_rejects_blank_required_identifiers(field):
    with pytest.raises(DomainValidationError):
        make_task(**{field: " "})


def test_run_can_remain_open_or_finish_after_it_starts():
    open_run = make_run()
    finished_run = make_run(finished_at=T0 + timedelta(seconds=1))

    assert open_run.finished_at is None
    assert finished_run.finished_at == T0 + timedelta(seconds=1)


@pytest.mark.parametrize("field", ["run_id", "experiment_id", "runtime_version"])
def test_run_rejects_blank_required_metadata(field):
    with pytest.raises(DomainValidationError):
        make_run(**{field: " "})


def test_run_can_finish_only_after_it_starts():
    with pytest.raises(DomainValidationError):
        make_run(finished_at=T0 - timedelta(seconds=1))


def test_attempt_happy_path_pending_running_succeeded():
    pending = make_attempt()

    running = pending.start(T0, lease_duration=LEASE)
    succeeded = running.succeed(T0 + timedelta(seconds=5))

    assert pending.status is TaskStatus.PENDING
    assert running.status is TaskStatus.RUNNING
    assert running.heartbeat_at == T0
    assert running.lease_expires_at == T0 + LEASE
    assert succeeded.status is TaskStatus.SUCCEEDED
    assert succeeded.started_at == T0
    assert succeeded.finished_at == T0 + timedelta(seconds=5)
    assert succeeded.error is None


def test_attempt_can_fail_with_error():
    failed = (
        make_attempt()
        .start(T0, lease_duration=LEASE)
        .fail(T0 + timedelta(seconds=2), "vina process exited with code 1", FailureKind.BACKEND)
    )

    assert failed.status is TaskStatus.FAILED
    assert failed.error == "vina process exited with code 1"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("attempt_number", 0),
        ("attempt_id", " "),
        ("task_id", " "),
        ("run_id", " "),
        ("worker_id", " "),
    ],
)
def test_attempt_rejects_invalid_identity_metadata(field, value):
    with pytest.raises(DomainValidationError):
        make_attempt(**{field: value})


def test_attempt_rejects_completion_before_start_on_direct_construction():
    with pytest.raises(DomainValidationError):
        make_attempt(
            status=TaskStatus.SUCCEEDED,
            started_at=T0,
            finished_at=T0 - timedelta(seconds=1),
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": TaskStatus.PENDING, "started_at": T0},
        {"status": TaskStatus.PENDING, "heartbeat_at": T0},
        {"status": TaskStatus.PENDING, "error": "unexpected"},
        {
            "status": TaskStatus.PENDING,
            "started_at": T0,
            "finished_at": T0 + timedelta(seconds=1),
        },
        {"status": TaskStatus.RUNNING},
        {"status": TaskStatus.RUNNING, "started_at": T0},
        {
            "status": TaskStatus.RUNNING,
            "started_at": T0,
            "heartbeat_at": T0,
        },
        {
            "status": TaskStatus.RUNNING,
            "started_at": T0,
            "heartbeat_at": T0,
            "lease_expires_at": T0 + LEASE,
            "finished_at": T0 + timedelta(seconds=1),
        },
        {
            "status": TaskStatus.RUNNING,
            "started_at": T0,
            "heartbeat_at": T0,
            "lease_expires_at": T0 + LEASE,
            "error": "premature",
        },
        {"status": TaskStatus.SUCCEEDED},
        {"status": TaskStatus.SUCCEEDED, "started_at": T0},
        {
            "status": TaskStatus.SUCCEEDED,
            "started_at": T0,
            "finished_at": T0 + timedelta(seconds=1),
            "heartbeat_at": T0,
        },
        {
            "status": TaskStatus.SUCCEEDED,
            "started_at": T0,
            "finished_at": T0 + timedelta(seconds=1),
            "error": "should not exist",
        },
        {"status": TaskStatus.FAILED, "started_at": T0, "error": "failure"},
        {
            "status": TaskStatus.FAILED,
            "started_at": T0,
            "finished_at": T0 + timedelta(seconds=1),
            "error": " ",
        },
        {
            "status": TaskStatus.FAILED,
            "started_at": T0,
            "finished_at": T0 + timedelta(seconds=1),
            "error": "boom",
            "failure_kind": FailureKind.BACKEND,
            "lease_expires_at": T0 + LEASE,
        },
    ],
)
def test_attempt_constructor_rejects_state_timestamp_mismatches(overrides):
    with pytest.raises(DomainValidationError):
        make_attempt(**overrides)


def test_attempt_constructor_rejects_unsupported_status():
    with pytest.raises(DomainValidationError):
        make_attempt(status="CANCELLED")


def test_attempt_constructor_accepts_valid_running_state():
    attempt = running_attempt()

    assert attempt.status is TaskStatus.RUNNING


def test_attempt_constructor_accepts_valid_succeeded_state():
    attempt = make_attempt(
        status=TaskStatus.SUCCEEDED,
        started_at=T0,
        finished_at=T0 + timedelta(seconds=1),
    )

    assert attempt.status is TaskStatus.SUCCEEDED


def test_attempt_constructor_accepts_valid_failed_state():
    attempt = make_attempt(
        status=TaskStatus.FAILED,
        started_at=T0,
        finished_at=T0 + timedelta(seconds=1),
        error="worker lost",
        failure_kind=FailureKind.INFRASTRUCTURE,
    )

    assert attempt.status is TaskStatus.FAILED


def test_only_pending_attempt_can_start():
    running = running_attempt()

    with pytest.raises(DomainValidationError):
        running.start(T0 + timedelta(seconds=1), lease_duration=LEASE)


def test_start_rejects_non_positive_lease():
    with pytest.raises(DomainValidationError):
        make_attempt().start(T0, lease_duration=timedelta(0))


def test_pending_attempt_cannot_succeed_without_starting():
    with pytest.raises(DomainValidationError):
        make_attempt().succeed(T0)


def test_attempt_cannot_succeed_before_it_started():
    running = make_attempt().start(T0, lease_duration=LEASE)

    with pytest.raises(DomainValidationError):
        running.succeed(T0 - timedelta(seconds=1))


def test_only_running_attempt_can_fail():
    with pytest.raises(DomainValidationError):
        make_attempt().fail(T0, "failure", FailureKind.BACKEND)


def test_failed_attempt_requires_non_blank_error():
    running = make_attempt().start(T0, lease_duration=LEASE)

    with pytest.raises(DomainValidationError):
        running.fail(T0 + timedelta(seconds=1), " ", FailureKind.BACKEND)


def test_attempt_cannot_fail_before_it_started():
    running = make_attempt().start(T0, lease_duration=LEASE)

    with pytest.raises(DomainValidationError):
        running.fail(T0 - timedelta(seconds=1), "clock skew", FailureKind.BACKEND)



def test_fail_rejects_non_failure_kind_value():
    running = make_attempt().start(T0, lease_duration=LEASE)

    with pytest.raises(DomainValidationError, match="failure_kind"):
        running.fail(T0 + timedelta(seconds=1), "boom", "BACKEND")
