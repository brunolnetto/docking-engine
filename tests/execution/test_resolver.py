import pytest

from moldock.domain import DockingBox, DockingTask, DomainValidationError
from moldock.execution import DockingInputResolver, MemoryDockingInputResolver


def make_task() -> DockingTask:
    return DockingTask(
        experiment_id="exp_1",
        receptor_id="rec_1",
        ligand_id="lig_1",
        prepared_receptor_id="prepared_rec_1",
        prepared_ligand_id="prepared_lig_1",
        search_space_id=DockingBox(1, 2, 3, 20, 20, 20).search_space_id,
    )


def test_memory_resolver_implements_contract():
    assert isinstance(MemoryDockingInputResolver(), DockingInputResolver)


def test_resolver_builds_execution_request():
    task = make_task()
    box = DockingBox(1, 2, 3, 20, 20, 20)
    resolver = MemoryDockingInputResolver()
    resolver.register_receptor("prepared_rec_1", b"REC")
    resolver.register_ligand("prepared_lig_1", b"LIG")
    resolver.register_search_space(box)
    resolver.register_parameters("exp_1", {"exhaustiveness": 12})

    request = resolver.resolve(task)

    assert request.task == task
    assert request.receptor_pdbqt == b"REC"
    assert request.ligand_pdbqt == b"LIG"
    assert request.search_space == box
    assert request.parameters["exhaustiveness"] == 12


def test_identical_prepared_input_reregistration_is_idempotent():
    resolver = MemoryDockingInputResolver()

    resolver.register_receptor("prepared_rec_1", b"REC")
    resolver.register_receptor("prepared_rec_1", b"REC")
    resolver.register_ligand("prepared_lig_1", b"LIG")
    resolver.register_ligand("prepared_lig_1", b"LIG")


def test_conflicting_prepared_receptor_registration_is_rejected():
    resolver = MemoryDockingInputResolver()
    resolver.register_receptor("prepared_rec_1", b"REC-v1")

    with pytest.raises(DomainValidationError, match="prepared receptor ID"):
        resolver.register_receptor("prepared_rec_1", b"REC-v2")


def test_conflicting_prepared_ligand_registration_is_rejected():
    resolver = MemoryDockingInputResolver()
    resolver.register_ligand("prepared_lig_1", b"LIG-v1")

    with pytest.raises(DomainValidationError, match="prepared ligand ID"):
        resolver.register_ligand("prepared_lig_1", b"LIG-v2")


def test_resolver_rejects_missing_inputs():
    resolver = MemoryDockingInputResolver()

    with pytest.raises(DomainValidationError, match="prepared receptor"):
        resolver.resolve(make_task())
