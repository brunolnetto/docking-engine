from datetime import datetime, timezone

from moldock.backends import FakeDockingBackend
from moldock.domain import DockingBox, DockingTask, TaskStatus
from moldock.execution import MemoryDockingInputResolver, Worker
from moldock.repositories import InMemoryArtifactRepository, InMemoryTaskRepository
from moldock.storage import MemoryArtifactStore


T0 = datetime(2026, 9, 25, 15, 0, tzinfo=timezone.utc)


def make_task():
    box = DockingBox(1, 2, 3, 20, 20, 20)
    return DockingTask(
        experiment_id="exp_1",
        receptor_id="rec_1",
        ligand_id="lig_1",
        prepared_receptor_id="prepared_rec_1",
        prepared_ligand_id="prepared_lig_1",
        search_space_id=box.search_space_id,
    ), box


def make_resolver(task, box):
    resolver = MemoryDockingInputResolver()
    resolver.register_receptor(task.prepared_receptor_id, b"REC")
    resolver.register_ligand(task.prepared_ligand_id, b"LIG")
    resolver.register_search_space(box)
    return resolver


class RecordingInterpreter:
    def __init__(self, artifact_repository):
        self.calls = []
        self._artifacts = artifact_repository

    def interpret(self, *, task_id, artifact):
        assert self._artifacts.get(artifact.artifact_id) == artifact
        self.calls.append((task_id, artifact.artifact_id))


def test_worker_invokes_result_interpreter_after_artifact_registration():
    task, box = make_task()
    tasks = InMemoryTaskRepository()
    artifacts = InMemoryArtifactRepository()
    store = MemoryArtifactStore()
    interpreter = RecordingInterpreter(artifacts)
    tasks.register(task)

    worker = Worker(
        task_repository=tasks,
        artifact_repository=artifacts,
        artifact_store=store,
        input_resolver=make_resolver(task, box),
        backend=FakeDockingBackend(),
        result_interpreter=interpreter,
        clock=lambda: T0,
    )

    attempt = worker.run_once("exp_1", "run_1", "worker_1")

    assert attempt is not None
    assert attempt.status is TaskStatus.SUCCEEDED
    assert len(interpreter.calls) == 1
    assert interpreter.calls[0][0] == task.task_id


class FailingInterpreter:
    def interpret(self, *, task_id, artifact):
        raise RuntimeError("scientific parsing failed")


def test_interpreter_failure_marks_attempt_failed():
    task, box = make_task()
    tasks = InMemoryTaskRepository()
    artifacts = InMemoryArtifactRepository()
    tasks.register(task)

    worker = Worker(
        task_repository=tasks,
        artifact_repository=artifacts,
        artifact_store=MemoryArtifactStore(),
        input_resolver=make_resolver(task, box),
        backend=FakeDockingBackend(),
        result_interpreter=FailingInterpreter(),
        clock=lambda: T0,
    )

    attempt = worker.run_once("exp_1", "run_1", "worker_1")

    assert attempt is not None
    assert attempt.status is TaskStatus.FAILED
    assert "scientific parsing failed" in attempt.error
