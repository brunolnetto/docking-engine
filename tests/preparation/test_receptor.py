from types import MappingProxyType

import pytest

from moldock.domain import DomainValidationError, PreparedReceptor
from moldock.preparation import (
    ReceptorPreparationArtifact,
    ReceptorPreparationProtocol,
    ReceptorPreparationRequest,
    ReceptorPreparer,
)


def make_protocol(**overrides):
    values = dict(
        method="mock-receptor-preparer",
        method_version="1.0",
        parameters={
            "remove_waters": True,
            "ph": 7.4,
        },
    )
    values.update(overrides)
    return ReceptorPreparationProtocol(**values)


def test_receptor_protocol_is_content_addressed_and_immutable():
    source = {"settings": {"chains": ["A", "B"]}}
    protocol = make_protocol(parameters=source)
    same = make_protocol(parameters={"settings": {"chains": ["A", "B"]}})
    original_id = protocol.preparation_id

    source["settings"]["chains"].append("C")

    assert protocol.preparation_id == same.preparation_id == original_id
    assert protocol.parameters["settings"]["chains"] == ("A", "B")
    assert isinstance(protocol.parameters, MappingProxyType)


def test_request_preserves_source_identity_separately_from_preparation():
    protocol = make_protocol()
    request = ReceptorPreparationRequest(
        receptor_id="rec_1",
        source_format="pdb",
        content=b"ATOM",
        protocol=protocol,
    )

    assert request.receptor_id == "rec_1"
    assert len(request.source_sha256) == 64
    assert request.protocol.preparation_id == protocol.preparation_id


def test_prepared_identity_tracks_model_chain_selection_and_content():
    protocol = make_protocol()
    base = dict(
        receptor_id="rec_1",
        preparation_id=protocol.preparation_id,
        model_id="model_1",
        chain_ids=("B", "A"),
        pdbqt=b"REC",
    )
    first = ReceptorPreparationArtifact(**base)
    same_selection = ReceptorPreparationArtifact(
        **{**base, "chain_ids": ("A", "B")}
    )
    different_model = ReceptorPreparationArtifact(
        **{**base, "model_id": "model_2"}
    )
    different_chain = ReceptorPreparationArtifact(
        **{**base, "chain_ids": ("A",)}
    )
    different_content = ReceptorPreparationArtifact(
        **{**base, "pdbqt": b"REC2"}
    )

    assert first.chain_ids == ("A", "B")
    assert first.prepared_receptor_id == same_selection.prepared_receptor_id
    assert first.prepared_receptor_id != different_model.prepared_receptor_id
    assert first.prepared_receptor_id != different_chain.prepared_receptor_id
    assert first.prepared_receptor_id != different_content.prepared_receptor_id


def test_artifact_converts_to_existing_prepared_receptor_model():
    artifact = ReceptorPreparationArtifact(
        receptor_id="rec_1",
        preparation_id="rprep_1",
        model_id="model_1",
        chain_ids=("A",),
        pdbqt=b"REC",
    )

    assert artifact.as_prepared_receptor() == PreparedReceptor(
        receptor_id="rec_1",
        preparation_id="rprep_1",
        prepared_receptor_id=artifact.prepared_receptor_id,
    )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: make_protocol(method=" "),
        lambda: ReceptorPreparationRequest(
            receptor_id=" ",
            source_format="pdb",
            content=b"x",
            protocol=make_protocol(),
        ),
        lambda: ReceptorPreparationRequest(
            receptor_id="rec_1",
            source_format=" ",
            content=b"x",
            protocol=make_protocol(),
        ),
        lambda: ReceptorPreparationRequest(
            receptor_id="rec_1",
            source_format="pdb",
            content="not-bytes",
            protocol=make_protocol(),
        ),
        lambda: ReceptorPreparationArtifact(
            receptor_id="rec_1",
            preparation_id="rprep_1",
            model_id=" ",
            chain_ids=("A",),
            pdbqt=b"x",
        ),
        lambda: ReceptorPreparationArtifact(
            receptor_id="rec_1",
            preparation_id="rprep_1",
            model_id="model_1",
            chain_ids=(),
            pdbqt=b"x",
        ),
        lambda: ReceptorPreparationArtifact(
            receptor_id="rec_1",
            preparation_id="rprep_1",
            model_id="model_1",
            chain_ids=(" ",),
            pdbqt=b"x",
        ),
    ],
)
def test_receptor_preparation_validates_inputs(factory):
    with pytest.raises(DomainValidationError):
        factory()


class FakeReceptorPreparer:
    def prepare(self, request):
        return ReceptorPreparationArtifact(
            receptor_id=request.receptor_id,
            preparation_id=request.protocol.preparation_id,
            model_id="model_1",
            chain_ids=("A",),
            pdbqt=b"REC",
        )


def test_receptor_preparer_is_runtime_checkable_port():
    assert isinstance(FakeReceptorPreparer(), ReceptorPreparer)
