from datetime import datetime, timezone

import pytest

from moldock.backends import FakeDockingBackend
from moldock.domain import DockingBox, DockingTask
from moldock.execution import MemoryDockingInputResolver, TaskExecutor
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


def make_executor(task, box):
    tasks = InMemoryTaskRepository()
    artifacts = InMemoryArtifactRepository()
    store = MemoryArtifactStore()
    resolver = MemoryDockingInputResolver()
    resolver.register_receptor(task.prepared_receptor_id, b"REC")
    resolver.register_ligand(task.prepared_ligand_id, b"LIG")
    resolver.register_search_space(box)
    return (
        TaskExecutor(
            task_repository=tasks,
            artifact_repository=artifacts,
            artifact_store=store,
            input_resolver=resolver,
            backend=FakeDockingBackend(),
        ),
        tasks,
        artifacts,
    )


def test_executor_executes_claimed_attempt_without_finalizing_it():
    task, box = make_task()
    executor, tasks, artifacts = make_executor(task, box)
    tasks.register(task)
    attempt = tasks.claim_next("exp_1", "run_1", "worker_1", T0)
    assert attempt is not None

    executor.execute(attempt)

    history = tasks.attempts_for(task.task_id, "run_1")
    assert history[-1].status.value == "RUNNING"
    assert len(artifacts.list_for_attempt(attempt.attempt_id)) == 1


def test_executor_rejects_claimed_attempt_whose_task_disappeared():
    task, box = make_task()
    executor, tasks, _ = make_executor(task, box)
    tasks.register(task)
    attempt = tasks.claim_next("exp_1", "run_1", "worker_1", T0)
    assert attempt is not None
    tasks._tasks.clear()

    with pytest.raises(RuntimeError, match="claimed task not found"):
        executor.execute(attempt)
