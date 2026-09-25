from types import MappingProxyType

import pytest

from moldock.domain import (
    DockingBox,
    DockingExecutionRequest,
    DockingTask,
    DomainValidationError,
)


def make_task() -> DockingTask:
    return DockingTask(
        experiment_id="exp_1",
        receptor_id="rec_1",
        ligand_id="lig_1",
        prepared_receptor_id="prepared_rec_1",
        prepared_ligand_id="prepared_lig_1",
        search_space_id="space_1",
    )


def make_request(**overrides) -> DockingExecutionRequest:
    values = dict(
        task=make_task(),
        receptor_pdbqt=b"RECEPTOR",
        ligand_pdbqt=b"LIGAND",
        search_space=DockingBox(1, 2, 3, 20, 21, 22),
        parameters={"exhaustiveness": 8, "seed": 42},
    )
    values.update(overrides)
    return DockingExecutionRequest(**values)


def test_request_snapshots_parameters():
    source = {"exhaustiveness": 8}
    request = make_request(parameters=source)

    source["exhaustiveness"] = 99

    assert request.parameters["exhaustiveness"] == 8
    assert isinstance(request.parameters, MappingProxyType)


@pytest.mark.parametrize("field", ["receptor_pdbqt", "ligand_pdbqt"])
def test_request_requires_bytes(field):
    with pytest.raises(DomainValidationError):
        make_request(**{field: "not-bytes"})


def test_request_search_space_must_match_task():
    with pytest.raises(DomainValidationError):
        make_request(
            search_space=DockingBox(0, 0, 0, 10, 10, 10),
        )
