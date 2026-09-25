from datetime import datetime, timezone

from moldock.backends import FakeDockingBackend
from moldock.domain import (
    DockingBox,
    DockingOutputArtifact,
    DockingResult,
    DockingTask,
    FailureKind,
    TaskStatus,
)
from moldock.execution import MemoryDockingInputResolver, Worker
from moldock.repositories import InMemoryArtifactRepository, InMemoryTaskRepository
from moldock.storage import MemoryArtifactStore


UTC = timezone.utc
T0 = datetime(2026, 9, 25, 15, 0, tzinfo=UTC)


def make_task(
    ligand_id: str = "lig_1",
    prepared_ligand_id: str = "prepared_lig_1",
) -> DockingTask:
    box = DockingBox(1, 2, 3, 20, 20, 20)
    return DockingTask(
        experiment_id="exp_1",
        receptor_id="rec_1",
        ligand_id=ligand_id,
        prepared_receptor_id="prepared_rec_1",
        prepared_ligand_id=prepared_ligand_id,
        search_space_id=box.search_space_id,
    )


def make_resolver(task: DockingTask) -> MemoryDockingInputResolver:
    box = DockingBox(1, 2, 3, 20, 20, 20)
    resolver = MemoryDockingInputResolver()
    resolver.register_receptor(task.prepared_receptor_id, b"REC")
    resolver.register_ligand(task.prepared_ligand_id, b"LIG")
    resolver.register_search_space(box)
    resolver.register_parameters(task.experiment_id, {"exhaustiveness": 8})
    return resolver


def make_worker(backend=None, task=None):
    tasks = InMemoryTaskRepository()
    artifacts = InMemoryArtifactRepository()
    store = MemoryArtifactStore()
    backend = backend or FakeDockingBackend()
    task = task or make_task()
    worker = Worker(
        task_repository=tasks,
        artifact_repository=artifacts,
        artifact_store=store,
        input_resolver=make_resolver(task),
        backend=backend,
        clock=lambda: T0,
    )
    return worker, tasks, artifacts, store, backend, task


def test_run_once_claims_resolves_executes_persists_and_succeeds():
    worker, tasks, artifacts, store, backend, task = make_worker()
    tasks.register(task)

    attempt = worker.run_once("exp_1", "run_1", "worker_1")

    assert attempt is not None
    assert attempt.status is TaskStatus.SUCCEEDED
    assert backend.calls == (task.task_id,)

    produced = artifacts.list_for_attempt(attempt.attempt_id)
    assert len(produced) == 1
    assert produced[0].kind == "docking_pose"
    assert produced[0].producer_attempt_id == attempt.attempt_id
    assert store.get(produced[0].uri.rsplit("/", 1)[-1]) == (
        f"FAKE_PDBQT\nREMARK task_id={task.task_id}\n".encode()
    )


def test_run_once_returns_none_when_no_task_is_available():
    worker, _, _, _, backend, _ = make_worker()

    assert worker.run_once("exp_1", "run_1", "worker_1") is None
    assert backend.calls == ()


def test_backend_failure_marks_attempt_failed_without_artifacts():
    task = make_task()
    backend = FakeDockingBackend(fail_task_ids={task.task_id})
    worker, tasks, artifacts, _, _, _ = make_worker(backend, task)
    tasks.register(task)

    attempt = worker.run_once("exp_1", "run_1", "worker_1")

    assert attempt is not None
    assert attempt.status is TaskStatus.FAILED
    assert attempt.failure_kind is FailureKind.BACKEND
    assert "DockingBackendError" in attempt.error
    assert artifacts.list_for_attempt(attempt.attempt_id) == ()


def test_failed_execution_is_retryable():
    task = make_task()
    failing = FakeDockingBackend(fail_task_ids={task.task_id})
    worker, tasks, artifacts, store, _, _ = make_worker(failing, task)
    tasks.register(task)

    first = worker.run_once("exp_1", "run_1", "worker_1")
    assert first is not None
    assert first.status is TaskStatus.FAILED

    succeeding_worker = Worker(
        task_repository=tasks,
        artifact_repository=artifacts,
        artifact_store=store,
        input_resolver=make_resolver(task),
        backend=FakeDockingBackend(),
        clock=lambda: T0,
    )
    second = succeeding_worker.run_once("exp_1", "run_1", "worker_2")

    assert second is not None
    assert second.status is TaskStatus.SUCCEEDED
    assert second.attempt_number == 2


class DuplicateContentBackend:
    def execute(self, request):
        return DockingResult(
            artifacts=(
                DockingOutputArtifact(
                    kind="pose",
                    media_type="chemical/x-pdbqt",
                    content=b"same-bytes",
                ),
                DockingOutputArtifact(
                    kind="log",
                    media_type="text/plain",
                    content=b"same-bytes",
                ),
            )
        )


def test_same_blob_can_have_multiple_artifact_provenance_records():
    task = make_task()
    worker, tasks, artifacts, store, _, _ = make_worker(
        DuplicateContentBackend(),
        task,
    )
    tasks.register(task)

    attempt = worker.run_once("exp_1", "run_1", "worker_1")
    assert attempt is not None

    produced = artifacts.list_for_attempt(attempt.attempt_id)

    assert len(produced) == 2
    assert produced[0].artifact_id != produced[1].artifact_id
    assert produced[0].uri == produced[1].uri
    assert store.blob_count == 1


class FailingArtifactStore:
    def put(self, content):
        raise RuntimeError("object store unavailable")

    def get(self, blob_id):
        raise AssertionError("not expected")


def test_artifact_persistence_failure_marks_attempt_failed():
    task = make_task()
    tasks = InMemoryTaskRepository()
    artifacts = InMemoryArtifactRepository()
    tasks.register(task)
    worker = Worker(
        task_repository=tasks,
        artifact_repository=artifacts,
        artifact_store=FailingArtifactStore(),
        input_resolver=make_resolver(task),
        backend=FakeDockingBackend(),
        clock=lambda: T0,
    )

    attempt = worker.run_once("exp_1", "run_1", "worker_1")

    assert attempt is not None
    assert attempt.status is TaskStatus.FAILED
    assert attempt.failure_kind is FailureKind.ARTIFACT
    assert "object store unavailable" in attempt.error
    assert artifacts.list_for_attempt(attempt.attempt_id) == ()


def test_input_resolution_failure_marks_attempt_failed():
    task = make_task()
    tasks = InMemoryTaskRepository()
    artifacts = InMemoryArtifactRepository()
    tasks.register(task)
    worker = Worker(
        task_repository=tasks,
        artifact_repository=artifacts,
        artifact_store=MemoryArtifactStore(),
        input_resolver=MemoryDockingInputResolver(),
        backend=FakeDockingBackend(),
        clock=lambda: T0,
    )

    attempt = worker.run_once("exp_1", "run_1", "worker_1")

    assert attempt is not None
    assert attempt.status is TaskStatus.FAILED
    assert attempt.failure_kind is FailureKind.INPUT
    assert "prepared receptor" in attempt.error


class VanishingTaskRepository(InMemoryTaskRepository):
    def get(self, task_id):
        return None


def test_claimed_task_missing_from_repository_marks_attempt_failed():
    task = make_task()
    tasks = VanishingTaskRepository()
    artifacts = InMemoryArtifactRepository()
    tasks.register(task)
    worker = Worker(
        task_repository=tasks,
        artifact_repository=artifacts,
        artifact_store=MemoryArtifactStore(),
        input_resolver=make_resolver(task),
        backend=FakeDockingBackend(),
        clock=lambda: T0,
    )

    attempt = worker.run_once("exp_1", "run_1", "worker_1")

    assert attempt is not None
    assert attempt.status is TaskStatus.FAILED
    assert attempt.failure_kind is FailureKind.INFRASTRUCTURE
    assert "claimed task not found" in attempt.error
