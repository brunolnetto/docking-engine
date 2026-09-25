from datetime import datetime, timedelta, timezone

from moldock.domain import DockingTask, TaskStatus
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
