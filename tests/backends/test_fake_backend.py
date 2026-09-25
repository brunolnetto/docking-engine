import pytest

from moldock.backends import (
    DockingBackend,
    DockingBackendError,
    FakeDockingBackend,
)
from moldock.domain import DockingTask


def make_task() -> DockingTask:
    return DockingTask(
        experiment_id="exp_1",
        receptor_id="rec_1",
        ligand_id="lig_1",
        prepared_receptor_id="prepared_rec_1",
        prepared_ligand_id="prepared_lig_1",
        search_space_id="space_1",
    )


def test_fake_backend_implements_backend_contract():
    assert isinstance(FakeDockingBackend(), DockingBackend)


def test_fake_backend_is_deterministic_for_same_task():
    backend = FakeDockingBackend()
    task = make_task()

    first = backend.execute(task)
    second = backend.execute(task)

    assert first == second
    assert len(first.artifacts) == 1
    assert first.artifacts[0].kind == "docking_pose"
    assert task.task_id.encode() in first.artifacts[0].content


def test_fake_backend_records_calls():
    backend = FakeDockingBackend()
    task = make_task()

    backend.execute(task)

    assert backend.calls == (task.task_id,)


def test_fake_backend_can_fail_selected_tasks():
    task = make_task()
    backend = FakeDockingBackend(fail_task_ids={task.task_id})

    with pytest.raises(DockingBackendError, match=task.task_id):
        backend.execute(task)
