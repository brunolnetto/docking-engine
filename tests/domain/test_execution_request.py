from types import MappingProxyType

import pytest

from moldock.domain import (
    DockingBox,
    DockingExecutionRequest,
    DockingTask,
    DomainValidationError,
)


BOX = DockingBox(1, 2, 3, 20, 21, 22)


def make_task() -> DockingTask:
    return DockingTask(
        experiment_id="exp_1",
        receptor_id="rec_1",
        ligand_id="lig_1",
        prepared_receptor_id="prepared_rec_1",
        prepared_ligand_id="prepared_lig_1",
        search_space_id=BOX.search_space_id,
    )


def make_request(**overrides) -> DockingExecutionRequest:
    values = dict(
        task=make_task(),
        receptor_pdbqt=b"RECEPTOR",
        ligand_pdbqt=b"LIGAND",
        search_space=BOX,
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


def test_request_deep_freezes_nested_parameters():
    source = {
        "search": {
            "weights": [1.0, 2.0],
            "options": {"local_only": False},
        }
    }
    request = make_request(parameters=source)

    source["search"]["weights"].append(3.0)
    source["search"]["options"]["local_only"] = True

    assert request.parameters["search"]["weights"] == (1.0, 2.0)
    assert request.parameters["search"]["options"]["local_only"] is False
    assert isinstance(request.parameters["search"], MappingProxyType)

    with pytest.raises(TypeError):
        request.parameters["search"]["options"]["local_only"] = True


@pytest.mark.parametrize("field", ["receptor_pdbqt", "ligand_pdbqt"])
def test_request_requires_bytes(field):
    with pytest.raises(DomainValidationError):
        make_request(**{field: "not-bytes"})


def test_request_search_space_must_match_task():
    with pytest.raises(DomainValidationError):
        make_request(
            search_space=DockingBox(0, 0, 0, 10, 10, 10),
        )
