from datetime import datetime, timedelta, timezone

import pytest

from moldock.backends import DockingBackendError, DockingBackendTimeoutError
from moldock.domain import (
    DockingBox,
    DockingTask,
    DomainValidationError,
    ExecutionFailure,
    FailureKind,
)
from moldock.execution import MemoryDockingInputResolver, TaskExecutor
from moldock.repositories import InMemoryArtifactRepository, InMemoryTaskRepository
from moldock.storage import MemoryArtifactStore


T0 = datetime(2026, 9, 25, 15, 0, tzinfo=timezone.utc)


def make_claimed_executor(*, resolver=None, backend=None, store=None, interpreter=None):
    task_repo = InMemoryTaskRepository()
    artifact_repo = InMemoryArtifactRepository()
    task = DockingTask(
        experiment_id="exp_1",
        receptor_id="rec_1",
        ligand_id="lig_1",
        prepared_receptor_id="prepared_rec_1",
        prepared_ligand_id="prepared_lig_1",
        search_space_id=DockingBox(1, 2, 3, 20, 20, 20).search_space_id,
    )
    task_repo.register(task)
    attempt = task_repo.claim_next(
        "exp_1",
        "run_1",
        "worker_1",
        T0,
        lease_duration=timedelta(minutes=5),
    )
    assert attempt is not None

    if resolver is None:
        resolver = MemoryDockingInputResolver()

    executor = TaskExecutor(
        task_repository=task_repo,
        artifact_repository=artifact_repo,
        artifact_store=store or MemoryArtifactStore(),
        input_resolver=resolver,
        backend=backend,
        result_interpreter=interpreter,
    )
    return executor, attempt, task


class NeverBackend:
    def execute(self, request):
        raise AssertionError("backend should not be called")


def test_input_resolution_failures_are_classified_as_input():
    executor, attempt, _ = make_claimed_executor(
        backend=NeverBackend(),
    )

    with pytest.raises(ExecutionFailure) as error:
        executor.execute(attempt)

    assert error.value.kind is FailureKind.INPUT


class FailingBackend:
    def execute(self, request):
        raise DockingBackendError("vina exited")


def test_backend_failures_are_classified_as_backend():
    resolver = MemoryDockingInputResolver()
    box = DockingBox(1, 2, 3, 20, 20, 20)
    resolver.register_receptor("prepared_rec_1", b"REC")
    resolver.register_ligand("prepared_lig_1", b"LIG")
    resolver.register_search_space(box)

    executor, attempt, _ = make_claimed_executor(
        resolver=resolver,
        backend=FailingBackend(),
    )

    with pytest.raises(ExecutionFailure) as error:
        executor.execute(attempt)

    assert error.value.kind is FailureKind.BACKEND


class FailingStore:
    def put(self, content):
        raise RuntimeError("object store unavailable")


def test_artifact_failures_are_classified_as_artifact():
    from moldock.backends import FakeDockingBackend

    resolver = MemoryDockingInputResolver()
    box = DockingBox(1, 2, 3, 20, 20, 20)
    resolver.register_receptor("prepared_rec_1", b"REC")
    resolver.register_ligand("prepared_lig_1", b"LIG")
    resolver.register_search_space(box)

    executor, attempt, _ = make_claimed_executor(
        resolver=resolver,
        backend=FakeDockingBackend(),
        store=FailingStore(),
    )

    with pytest.raises(ExecutionFailure) as error:
        executor.execute(attempt)

    assert error.value.kind is FailureKind.ARTIFACT


class FailingInterpreter:
    def interpret(self, *, task_id, artifact):
        raise RuntimeError("invalid scientific output")


def test_interpretation_failures_are_classified_as_interpretation():
    from moldock.backends import FakeDockingBackend

    resolver = MemoryDockingInputResolver()
    box = DockingBox(1, 2, 3, 20, 20, 20)
    resolver.register_receptor("prepared_rec_1", b"REC")
    resolver.register_ligand("prepared_lig_1", b"LIG")
    resolver.register_search_space(box)

    executor, attempt, _ = make_claimed_executor(
        resolver=resolver,
        backend=FakeDockingBackend(),
        interpreter=FailingInterpreter(),
    )

    with pytest.raises(ExecutionFailure) as error:
        executor.execute(attempt)

    assert error.value.kind is FailureKind.INTERPRETATION


def test_missing_claimed_task_is_classified_as_infrastructure():
    executor, attempt, _ = make_claimed_executor(
        backend=NeverBackend(),
    )
    executor._tasks._tasks.clear()

    with pytest.raises(ExecutionFailure) as error:
        executor.execute(attempt)

    assert error.value.kind is FailureKind.INFRASTRUCTURE


class TimingOutBackend:
    def execute(self, request):
        raise DockingBackendTimeoutError("vina timed out after 30 seconds")


def test_backend_timeouts_are_classified_as_timeout():
    resolver = MemoryDockingInputResolver()
    box = DockingBox(1, 2, 3, 20, 20, 20)
    resolver.register_receptor("prepared_rec_1", b"REC")
    resolver.register_ligand("prepared_lig_1", b"LIG")
    resolver.register_search_space(box)

    executor, attempt, _ = make_claimed_executor(
        resolver=resolver,
        backend=TimingOutBackend(),
    )

    with pytest.raises(ExecutionFailure) as error:
        executor.execute(attempt)

    assert error.value.kind is FailureKind.TIMEOUT



class TypedFailingResolver:
    def __init__(self, failure):
        self.failure = failure

    def resolve(self, task):
        raise self.failure


def test_existing_execution_failure_is_preserved_without_reclassification():
    original = ExecutionFailure(
        FailureKind.TIMEOUT,
        "already classified",
    )
    executor, attempt, _ = make_claimed_executor(
        resolver=TypedFailingResolver(original),
        backend=NeverBackend(),
    )

    with pytest.raises(ExecutionFailure) as error:
        executor.execute(attempt)

    assert error.value is original
    assert error.value.kind is FailureKind.TIMEOUT
