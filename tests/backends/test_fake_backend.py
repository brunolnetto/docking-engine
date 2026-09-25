import pytest

from moldock.backends import (
    DockingBackend,
    DockingBackendError,
    FakeDockingBackend,
)
from moldock.domain import DockingBox, DockingExecutionRequest, DockingTask


def make_request() -> DockingExecutionRequest:
    box = DockingBox(1, 2, 3, 20, 20, 20)
    task = DockingTask(
        experiment_id="exp_1",
        receptor_id="rec_1",
        ligand_id="lig_1",
        prepared_receptor_id="prepared_rec_1",
        prepared_ligand_id="prepared_lig_1",
        search_space_id=box.search_space_id,
    )
    return DockingExecutionRequest(
        task=task,
        receptor_pdbqt=b"REC",
        ligand_pdbqt=b"LIG",
        search_space=box,
    )


def test_fake_backend_implements_backend_contract():
    assert isinstance(FakeDockingBackend(), DockingBackend)


def test_fake_backend_is_deterministic_for_same_request():
    backend = FakeDockingBackend()
    request = make_request()

    first = backend.execute(request)
    second = backend.execute(request)

    assert first == second
    assert len(first.artifacts) == 1
    assert first.artifacts[0].kind == "docking_pose"
    assert request.task.task_id.encode() in first.artifacts[0].content


def test_fake_backend_records_calls():
    backend = FakeDockingBackend()
    request = make_request()

    backend.execute(request)

    assert backend.calls == (request.task.task_id,)


def test_fake_backend_can_fail_selected_tasks():
    request = make_request()
    backend = FakeDockingBackend(fail_task_ids={request.task.task_id})

    with pytest.raises(DockingBackendError, match=request.task.task_id):
        backend.execute(request)
