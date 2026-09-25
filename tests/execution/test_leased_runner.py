from datetime import datetime, timedelta, timezone
from threading import Event, Thread

import pytest

from moldock.domain import DockingTask, DomainValidationError, TaskStatus
from moldock.execution import LeasedWorkerRunner
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


class RecordingExecutor:
    def __init__(self, error=None, on_execute=None):
        self.calls = []
        self.error = error
        self.on_execute = on_execute

    def execute(self, attempt):
        self.calls.append(attempt.attempt_id)
        if self.on_execute is not None:
            self.on_execute()
        if self.error is not None:
            raise self.error


class RecordingHeartbeat:
    def __init__(self, error=None):
        self.started = False
        self.stopped = False
        self.error = error

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


class HeartbeatFactory:
    def __init__(self, heartbeat):
        self.heartbeat = heartbeat
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self.heartbeat


def make_runner(executor, heartbeat=None):
    repo = InMemoryTaskRepository(default_lease_duration=timedelta(minutes=5))
    task = make_task()
    repo.register(task)
    heartbeat = heartbeat or RecordingHeartbeat()
    factory = HeartbeatFactory(heartbeat)
    runner = LeasedWorkerRunner(
        task_repository=repo,
        executor=executor,
        clock=lambda: T0,
        lease_duration=timedelta(minutes=5),
        heartbeat_interval=timedelta(minutes=1),
        heartbeat_factory=factory,
    )
    return runner, repo, task, heartbeat, factory


def test_runner_claims_starts_heartbeat_executes_and_succeeds():
    executor = RecordingExecutor()
    runner, repo, task, heartbeat, factory = make_runner(executor)

    attempt = runner.run_once("exp_1", "run_1", "worker_1")

    assert attempt is not None
    assert attempt.status is TaskStatus.SUCCEEDED
    assert executor.calls == [attempt.attempt_id]
    assert heartbeat.started
    assert heartbeat.stopped
    assert factory.calls[0]["attempt"].task_id == task.task_id


def test_runner_backend_failure_marks_attempt_failed_and_stops_heartbeat():
    executor = RecordingExecutor(error=RuntimeError("backend exploded"))
    runner, _, _, heartbeat, _ = make_runner(executor)

    attempt = runner.run_once("exp_1", "run_1", "worker_1")

    assert attempt is not None
    assert attempt.status is TaskStatus.FAILED
    assert "backend exploded" in attempt.error
    assert heartbeat.stopped


def test_heartbeat_failure_prevents_success():
    heartbeat = RecordingHeartbeat(error=RuntimeError("heartbeat lost"))
    executor = RecordingExecutor()
    runner, _, _, _, _ = make_runner(executor, heartbeat)

    attempt = runner.run_once("exp_1", "run_1", "worker_1")

    assert attempt is not None
    assert attempt.status is TaskStatus.FAILED
    assert "heartbeat lost" in attempt.error


def test_no_task_does_not_create_heartbeat():
    repo = InMemoryTaskRepository()
    executor = RecordingExecutor()
    factory = HeartbeatFactory(RecordingHeartbeat())
    runner = LeasedWorkerRunner(
        task_repository=repo,
        executor=executor,
        clock=lambda: T0,
        heartbeat_factory=factory,
    )

    assert runner.run_once("exp_1", "run_1", "worker_1") is None
    assert factory.calls == []


def test_stop_prevents_new_claims():
    executor = RecordingExecutor()
    runner, repo, task, _, factory = make_runner(executor)
    runner.stop()

    assert runner.run_once("exp_1", "run_1", "worker_1") is None
    assert executor.calls == []
    assert factory.calls == []
    assert repo.attempts_for(task.task_id, "run_1") == ()


def test_stop_during_execution_does_not_cancel_active_attempt():
    runner_box = {}

    def request_stop():
        runner_box["runner"].stop()

    executor = RecordingExecutor(on_execute=request_stop)
    runner, _, _, _, _ = make_runner(executor)
    runner_box["runner"] = runner

    attempt = runner.run_once("exp_1", "run_1", "worker_1")

    assert attempt is not None
    assert attempt.status is TaskStatus.SUCCEEDED
    assert runner.stopped


class MutableClock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def test_runner_finalizes_only_the_attempt_it_claimed_after_retry_is_created():
    clock = MutableClock(T0)
    repo = InMemoryTaskRepository(
        default_lease_duration=timedelta(minutes=1),
    )
    task = make_task()
    repo.register(task)
    heartbeat = RecordingHeartbeat()
    factory = HeartbeatFactory(heartbeat)
    retry_box = {}

    def expire_and_reclaim():
        clock.now = T0 + timedelta(minutes=2)
        retry_box["attempt"] = repo.claim_next(
            experiment_id="exp_1",
            run_id="run_1",
            worker_id="worker_2",
            at=clock(),
            lease_duration=timedelta(minutes=5),
        )

    runner = LeasedWorkerRunner(
        task_repository=repo,
        executor=RecordingExecutor(on_execute=expire_and_reclaim),
        clock=clock,
        lease_duration=timedelta(minutes=1),
        heartbeat_interval=timedelta(seconds=30),
        heartbeat_factory=factory,
    )

    result = runner.run_once("exp_1", "run_1", "worker_1")

    history = repo.attempts_for(task.task_id, "run_1")
    assert len(history) == 2
    assert result is not None
    assert result.attempt_id == history[0].attempt_id
    assert result.status is TaskStatus.FAILED
    assert retry_box["attempt"].attempt_id == history[1].attempt_id
    assert history[1].status is TaskStatus.RUNNING


@pytest.mark.parametrize(
    ("lease_duration", "heartbeat_interval"),
    [
        (timedelta(seconds=30), timedelta(minutes=1)),
        (timedelta(minutes=1), timedelta(minutes=1)),
        (timedelta(minutes=1), timedelta(0)),
    ],
)
def test_invalid_heartbeat_timing_is_rejected_before_any_claim(
    lease_duration,
    heartbeat_interval,
):
    repo = InMemoryTaskRepository()
    task = make_task()
    repo.register(task)

    with pytest.raises(DomainValidationError):
        LeasedWorkerRunner(
            task_repository=repo,
            executor=RecordingExecutor(),
            clock=lambda: T0,
            lease_duration=lease_duration,
            heartbeat_interval=heartbeat_interval,
        )

    assert repo.attempts_for(task.task_id, "run_1") == ()


def test_finalization_lease_expiry_returns_durable_failed_attempt():
    times = iter((T0, T0 + timedelta(minutes=2)))
    repo = InMemoryTaskRepository(
        default_lease_duration=timedelta(minutes=1),
    )
    task = make_task()
    repo.register(task)
    runner = LeasedWorkerRunner(
        task_repository=repo,
        executor=RecordingExecutor(),
        clock=lambda: next(times),
        lease_duration=timedelta(minutes=1),
        heartbeat_interval=timedelta(seconds=30),
        heartbeat_factory=HeartbeatFactory(RecordingHeartbeat()),
    )

    result = runner.run_once("exp_1", "run_1", "worker_1")

    assert result is not None
    assert result.status is TaskStatus.FAILED
    assert result.error == "lease expired"


def test_stop_is_serialized_with_claim():
    entered_claim = Event()
    allow_claim = Event()

    class BlockingRepository:
        def __init__(self):
            self.inner = InMemoryTaskRepository()
            self.task = make_task()
            self.inner.register(self.task)

        def claim_next(self, **kwargs):
            entered_claim.set()
            allow_claim.wait(timeout=2)
            return self.inner.claim_next(**kwargs)

        def __getattr__(self, name):
            return getattr(self.inner, name)

    repo = BlockingRepository()
    runner = LeasedWorkerRunner(
        task_repository=repo,
        executor=RecordingExecutor(),
        clock=lambda: T0,
        heartbeat_factory=HeartbeatFactory(RecordingHeartbeat()),
    )
    result_box = {}

    run_thread = Thread(
        target=lambda: result_box.setdefault(
            "attempt",
            runner.run_once("exp_1", "run_1", "worker_1"),
        )
    )
    run_thread.start()
    assert entered_claim.wait(timeout=2)

    stop_returned = Event()
    stop_thread = Thread(target=lambda: (runner.stop(), stop_returned.set()))
    stop_thread.start()

    assert not stop_returned.wait(timeout=0.05)
    allow_claim.set()
    run_thread.join(timeout=2)
    stop_thread.join(timeout=2)

    assert stop_returned.is_set()
    assert runner.stopped
    assert result_box["attempt"] is not None
    assert runner.run_once("exp_1", "run_1", "worker_2") is None


def test_heartbeat_start_failure_finalizes_claimed_attempt_and_stops_controller():
    class FailingStartHeartbeat(RecordingHeartbeat):
        def start(self):
            self.started = True
            raise RuntimeError("cannot start heartbeat thread")

    heartbeat = FailingStartHeartbeat()
    executor = RecordingExecutor()
    runner, repo, task, _, _ = make_runner(executor, heartbeat)

    result = runner.run_once("exp_1", "run_1", "worker_1")

    assert result is not None
    assert result.status is TaskStatus.FAILED
    assert "cannot start heartbeat thread" in result.error
    assert heartbeat.started
    assert heartbeat.stopped
    assert executor.calls == []
    history = repo.attempts_for(task.task_id, "run_1")
    assert history == (result,)
