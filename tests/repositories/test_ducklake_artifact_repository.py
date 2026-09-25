import pytest

from moldock.domain import ArtifactMetadata, DomainValidationError
from moldock.repositories import (
    ArtifactRepository,
    DuckLakeArtifactRepository,
)


def make_artifact(**overrides):
    values = dict(
        artifact_id="artifact_1",
        uri="memory://blob/a",
        sha256="a" * 64,
        size_bytes=128,
        media_type="chemical/x-pdbqt",
        kind="docking_pose",
        producer_attempt_id="attempt_1",
    )
    values.update(overrides)
    return ArtifactMetadata(**values)


def make_repo(tmp_path):
    return DuckLakeArtifactRepository(
        catalog_path=tmp_path / "catalog.sqlite",
        data_path=tmp_path / "data",
        retry_delay_seconds=0,
    )


def test_ducklake_artifact_repository_satisfies_contract(tmp_path):
    repo = make_repo(tmp_path)
    try:
        assert isinstance(repo, ArtifactRepository)
    finally:
        repo.close()


def test_artifact_metadata_survives_repository_restart(tmp_path):
    artifact = make_artifact()
    repo = make_repo(tmp_path)
    repo.register(artifact)
    repo.close()

    reopened = make_repo(tmp_path)
    try:
        assert reopened.get(artifact.artifact_id) == artifact
        assert reopened.list_for_attempt("attempt_1") == (artifact,)
    finally:
        reopened.close()


def test_artifact_registration_is_idempotent_across_clients(tmp_path):
    artifact = make_artifact()
    first = make_repo(tmp_path)
    second = make_repo(tmp_path)
    try:
        first.register(artifact)
        second.register(artifact)

        assert first.get(artifact.artifact_id) == artifact
        assert second.get(artifact.artifact_id) == artifact
    finally:
        first.close()
        second.close()


def test_artifact_repository_rejects_conflicting_metadata(tmp_path):
    repo = make_repo(tmp_path)
    try:
        repo.register(make_artifact())
        with pytest.raises(DomainValidationError, match="conflicting"):
            repo.register(
                make_artifact(uri="memory://blob/other")
            )
    finally:
        repo.close()


def test_artifacts_are_listed_deterministically(tmp_path):
    repo = make_repo(tmp_path)
    try:
        b = make_artifact(
            artifact_id="b",
            sha256="b" * 64,
        )
        a = make_artifact(
            artifact_id="a",
            sha256="c" * 64,
        )
        repo.register(b)
        repo.register(a)

        assert repo.list_for_attempt("attempt_1") == (a, b)
    finally:
        repo.close()
