from datetime import datetime, timedelta, timezone
from threading import Event

import pytest

from moldock.domain import DockingTask, DomainValidationError
from moldock.execution import LeaseHeartbeat
from moldock.repositories import InMemoryTaskRepository


T0 = datetime(2026, 9, 25, 15, 0, tzinfo=timezone.utc)


def make_attempt():
    repo = InMemoryTaskRepository(default_lease_duration=timedelta(minutes=1))
    task = DockingTask(
        experiment_id="exp_1",
        receptor_id="rec_1",
        ligand_id="lig_1",
        prepared_receptor_id="prepared_rec_1",
        prepared_ligand_id="prepared_lig_1",
        search_space_id="space_1",
    )
    repo.register(task)
    attempt = repo.claim_next("exp_1", "run_1", "worker_1", T0)
    assert attempt is not None
    return repo, attempt


class ControlledWaiter:
    def __init__(self):
        self.tick = Event()
        self.calls = 0

    def __call__(self, stop_event, interval_seconds):
        self.calls += 1
        while not stop_event.is_set():
            if self.tick.wait(timeout=0.01):
                self.tick.clear()
                return False
        return True


def test_heartbeat_renews_lease_on_tick():
    repo, attempt = make_attempt()
    times = iter([
        T0 + timedelta(seconds=20),
        T0 + timedelta(seconds=40),
    ])
    waiter = ControlledWaiter()
    heartbeat = LeaseHeartbeat(
        repository=repo,
        attempt=attempt,
        worker_id="worker_1",
        clock=lambda: next(times),
        lease_duration=timedelta(minutes=1),
        interval=timedelta(seconds=10),
        waiter=waiter,
    )

    heartbeat.start()
    waiter.tick.set()
    heartbeat.wait_for_heartbeat(timeout=1)
    heartbeat.stop()

    updated = repo.attempts_for(attempt.task_id, attempt.run_id)[-1]
    assert updated.heartbeat_at == T0 + timedelta(seconds=20)
    assert updated.lease_expires_at == T0 + timedelta(seconds=80)
    assert heartbeat.error is None


def test_heartbeat_captures_repository_failure():
    repo, attempt = make_attempt()
    waiter = ControlledWaiter()
    heartbeat = LeaseHeartbeat(
        repository=repo,
        attempt=attempt,
        worker_id="wrong-worker",
        clock=lambda: T0 + timedelta(seconds=20),
        lease_duration=timedelta(minutes=1),
        interval=timedelta(seconds=10),
        waiter=waiter,
    )

    heartbeat.start()
    waiter.tick.set()
    heartbeat.wait_for_heartbeat(timeout=1)
    heartbeat.stop()

    assert isinstance(heartbeat.error, DomainValidationError)


@pytest.mark.parametrize(
    "interval, lease_duration",
    [
        (timedelta(0), timedelta(minutes=1)),
        (timedelta(seconds=1), timedelta(0)),
        (timedelta(minutes=2), timedelta(minutes=1)),
    ],
)
def test_heartbeat_validates_timing(interval, lease_duration):
    repo, attempt = make_attempt()

    with pytest.raises(DomainValidationError):
        LeaseHeartbeat(
            repository=repo,
            attempt=attempt,
            worker_id="worker_1",
            clock=lambda: T0,
            lease_duration=lease_duration,
            interval=interval,
        )



def test_heartbeat_cannot_be_started_twice():
    repo, attempt = make_attempt()
    waiter = ControlledWaiter()
    heartbeat = LeaseHeartbeat(
        repository=repo,
        attempt=attempt,
        worker_id="worker_1",
        clock=lambda: T0,
        lease_duration=timedelta(minutes=1),
        interval=timedelta(seconds=10),
        waiter=waiter,
    )

    heartbeat.start()
    try:
        with pytest.raises(RuntimeError, match="already started"):
            heartbeat.start()
    finally:
        heartbeat.stop()


def test_stopping_never_started_heartbeat_is_safe():
    repo, attempt = make_attempt()
    heartbeat = LeaseHeartbeat(
        repository=repo,
        attempt=attempt,
        worker_id="worker_1",
        clock=lambda: T0,
        lease_duration=timedelta(minutes=1),
        interval=timedelta(seconds=10),
    )

    heartbeat.stop()

    assert heartbeat.error is None
