import pytest

from moldock.domain import ArtifactMetadata, DomainValidationError
from moldock.repositories import InMemoryArtifactRepository


def make_artifact(**overrides) -> ArtifactMetadata:
    values = dict(
        artifact_id="artifact_1",
        uri="s3://dock/runs/run_1/pose-1.pdbqt",
        sha256="a" * 64,
        size_bytes=128,
        media_type="chemical/x-pdbqt",
        kind="docking_pose",
        producer_attempt_id="attempt_1",
    )
    values.update(overrides)
    return ArtifactMetadata(**values)


def test_artifact_metadata_validates_required_fields():
    for field in (
        "artifact_id",
        "uri",
        "sha256",
        "media_type",
        "kind",
        "producer_attempt_id",
    ):
        with pytest.raises(DomainValidationError):
            make_artifact(**{field: " "})


def test_artifact_rejects_invalid_sha256():
    with pytest.raises(DomainValidationError):
        make_artifact(sha256="not-a-sha")


def test_artifact_rejects_negative_size():
    with pytest.raises(DomainValidationError):
        make_artifact(size_bytes=-1)


def test_register_is_idempotent_for_identical_metadata():
    repo = InMemoryArtifactRepository()
    artifact = make_artifact()

    repo.register(artifact)
    repo.register(artifact)

    assert repo.get("artifact_1") == artifact
    assert repo.list_for_attempt("attempt_1") == (artifact,)


def test_register_rejects_conflicting_metadata_for_same_artifact_id():
    repo = InMemoryArtifactRepository()
    repo.register(make_artifact())

    with pytest.raises(DomainValidationError):
        repo.register(make_artifact(uri="s3://other/location.pdbqt"))


def test_artifacts_are_listed_deterministically():
    repo = InMemoryArtifactRepository()
    b = make_artifact(artifact_id="b", sha256="b" * 64)
    a = make_artifact(artifact_id="a", sha256="c" * 64)

    repo.register(b)
    repo.register(a)

    assert repo.list_for_attempt("attempt_1") == (a, b)
