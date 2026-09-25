import pytest

from moldock.domain import (
    DockingOutputArtifact,
    DockingResult,
    DomainValidationError,
)


def test_output_artifact_requires_bytes_and_non_blank_metadata():
    with pytest.raises(DomainValidationError):
        DockingOutputArtifact(kind=" ", media_type="chemical/x-pdbqt", content=b"x")

    with pytest.raises(DomainValidationError):
        DockingOutputArtifact(kind="pose", media_type=" ", content=b"x")

    with pytest.raises(DomainValidationError):
        DockingOutputArtifact(kind="pose", media_type="chemical/x-pdbqt", content="x")


def test_docking_result_snapshots_artifacts_as_tuple():
    source = [
        DockingOutputArtifact(
            kind="pose",
            media_type="chemical/x-pdbqt",
            content=b"pose",
        )
    ]

    result = DockingResult(artifacts=source, stdout="ok", stderr="")
    source.clear()

    assert len(result.artifacts) == 1
    assert result.stdout == "ok"
