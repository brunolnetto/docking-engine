from types import MappingProxyType

import pytest

from moldock.domain import DomainValidationError, PreparedLigand
from moldock.preparation import (
    LigandPreparationArtifact,
    LigandPreparationProtocol,
    LigandPreparationRequest,
    LigandPreparer,
)


def make_protocol(**overrides):
    values = dict(
        method="mock-preparer",
        method_version="1.0",
        parameters={"ph": 7.4, "max_conformers": 3},
    )
    values.update(overrides)
    return LigandPreparationProtocol(**values)


def test_ligand_preparation_protocol_is_content_addressed_and_immutable():
    source = {"settings": {"values": [1, 2]}}
    protocol = make_protocol(parameters=source)
    same = make_protocol(parameters={"settings": {"values": [1, 2]}})
    original_id = protocol.preparation_id

    source["settings"]["values"].append(3)

    assert protocol.preparation_id == same.preparation_id == original_id
    assert protocol.parameters["settings"]["values"] == (1, 2)
    assert isinstance(protocol.parameters, MappingProxyType)


def test_request_preserves_source_identity_separately_from_preparation():
    protocol = make_protocol()
    request = LigandPreparationRequest(
        ligand_id="lig_1",
        source_format="sdf",
        content=b"MOLECULE",
        protocol=protocol,
    )

    assert request.ligand_id == "lig_1"
    assert request.source_sha256
    assert request.protocol.preparation_id == protocol.preparation_id


def test_prepared_artifact_distinguishes_microstate_and_conformer_identity():
    protocol = make_protocol()
    first = LigandPreparationArtifact(
        ligand_id="lig_1",
        preparation_id=protocol.preparation_id,
        microstate_id="micro_1",
        conformer_id="conf_1",
        pdbqt=b"ATOM 1",
    )
    second = LigandPreparationArtifact(
        ligand_id="lig_1",
        preparation_id=protocol.preparation_id,
        microstate_id="micro_1",
        conformer_id="conf_2",
        pdbqt=b"ATOM 2",
    )

    assert first.prepared_ligand_id != second.prepared_ligand_id
    assert first.as_prepared_ligand() == PreparedLigand(
        ligand_id="lig_1",
        preparation_id=protocol.preparation_id,
        prepared_ligand_id=first.prepared_ligand_id,
    )


def test_prepared_identity_is_stable_for_same_scientific_artifact():
    values = dict(
        ligand_id="lig_1",
        preparation_id="lprep_1",
        microstate_id="micro_1",
        conformer_id="conf_1",
        pdbqt=b"ATOM 1",
    )

    assert (
        LigandPreparationArtifact(**values).prepared_ligand_id
        == LigandPreparationArtifact(**values).prepared_ligand_id
    )


def test_preparation_types_validate_inputs():
    with pytest.raises(DomainValidationError):
        make_protocol(method=" ")

    with pytest.raises(DomainValidationError):
        LigandPreparationRequest(
            ligand_id=" ",
            source_format="sdf",
            content=b"x",
            protocol=make_protocol(),
        )

    with pytest.raises(DomainValidationError):
        LigandPreparationRequest(
            ligand_id="lig_1",
            source_format="sdf",
            content="not-bytes",
            protocol=make_protocol(),
        )

    with pytest.raises(DomainValidationError):
        LigandPreparationArtifact(
            ligand_id="lig_1",
            preparation_id="lprep_1",
            microstate_id=" ",
            conformer_id="conf_1",
            pdbqt=b"x",
        )


class FakePreparer:
    def prepare(self, request):
        return ()


def test_ligand_preparer_is_runtime_checkable_port():
    assert isinstance(FakePreparer(), LigandPreparer)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: make_protocol(method_version=" "),
        lambda: LigandPreparationRequest(
            ligand_id="lig_1",
            source_format=" ",
            content=b"x",
            protocol=make_protocol(),
        ),
        lambda: LigandPreparationRequest(
            ligand_id="lig_1",
            source_format="sdf",
            content=b"x",
            protocol=object(),
        ),
        lambda: LigandPreparationArtifact(
            ligand_id=" ",
            preparation_id="lprep_1",
            microstate_id="micro_1",
            conformer_id="conf_1",
            pdbqt=b"x",
        ),
        lambda: LigandPreparationArtifact(
            ligand_id="lig_1",
            preparation_id=" ",
            microstate_id="micro_1",
            conformer_id="conf_1",
            pdbqt=b"x",
        ),
        lambda: LigandPreparationArtifact(
            ligand_id="lig_1",
            preparation_id="lprep_1",
            microstate_id="micro_1",
            conformer_id=" ",
            pdbqt=b"x",
        ),
        lambda: LigandPreparationArtifact(
            ligand_id="lig_1",
            preparation_id="lprep_1",
            microstate_id="micro_1",
            conformer_id="conf_1",
            pdbqt="not-bytes",
        ),
    ],
)
def test_ligand_preparation_covers_all_validation_boundaries(factory):
    with pytest.raises(DomainValidationError):
        factory()
