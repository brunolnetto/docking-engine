import pytest

from moldock.domain import DockingTask, DomainValidationError
from moldock.planning import TaskManifest


def make_task(ligand_id: str, prepared_ligand_id: str) -> DockingTask:
    return DockingTask(
        experiment_id="exp_1",
        receptor_id="rec_1",
        ligand_id=ligand_id,
        prepared_receptor_id="prepared_rec_1",
        prepared_ligand_id=prepared_ligand_id,
        search_space_id="space_1",
    )


def test_manifest_orders_tasks_deterministically():
    a = make_task("lig_a", "prepared_a")
    b = make_task("lig_b", "prepared_b")

    left = TaskManifest("exp_1", (b, a))
    right = TaskManifest("exp_1", (a, b))

    assert left.tasks == right.tasks
    assert left.manifest_id == right.manifest_id


def test_manifest_rejects_blank_experiment_id():
    with pytest.raises(DomainValidationError):
        TaskManifest(" ", ())


def test_manifest_rejects_task_from_another_experiment():
    task = DockingTask(
        experiment_id="other",
        receptor_id="rec_1",
        ligand_id="lig_a",
        prepared_receptor_id="prepared_rec_1",
        prepared_ligand_id="prepared_a",
        search_space_id="space_1",
    )

    with pytest.raises(DomainValidationError):
        TaskManifest("exp_1", (task,))


def test_manifest_rejects_duplicate_task_ids():
    task = make_task("lig_a", "prepared_a")

    with pytest.raises(DomainValidationError):
        TaskManifest("exp_1", (task, task))


def test_manifest_exposes_pending_tasks_without_mutating_itself():
    a = make_task("lig_a", "prepared_a")
    b = make_task("lig_b", "prepared_b")
    manifest = TaskManifest("exp_1", (a, b))

    pending = manifest.pending_tasks({a.task_id})

    assert pending == (b,)
    assert manifest.task_count == 2


def test_empty_manifest_is_valid():
    manifest = TaskManifest("exp_1", ())

    assert manifest.task_count == 0
    assert manifest.pending_tasks(set()) == ()
