import duckdb
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


def test_artifact_write_conflict_reconnects_and_retries(tmp_path):
    repo = DuckLakeArtifactRepository(
        catalog_path=tmp_path / "catalog.sqlite",
        data_path=tmp_path / "data",
        max_transaction_retries=3,
        retry_delay_seconds=0,
    )
    artifact = make_artifact()
    inner = repo._connection
    state = {"conflicts": 0}

    class CommitConflictOnceConnection:
        def execute(self, query, parameters=None):
            if (
                query.strip().upper() == "COMMIT"
                and state["conflicts"] == 0
            ):
                state["conflicts"] += 1
                raise duckdb.TransactionException(
                    "transaction conflict injected by test"
                )
            if parameters is None:
                return inner.execute(query)
            return inner.execute(query, parameters)

        def close(self):
            return inner.close()

        def __getattr__(self, name):
            return getattr(inner, name)

    repo._connection = CommitConflictOnceConnection()
    try:
        repo.register(artifact)

        assert state["conflicts"] == 1
        assert repo.get(artifact.artifact_id) == artifact
        assert repo.list_for_attempt("attempt_1") == (artifact,)
    finally:
        repo.close()


def test_shared_adapter_writes_touch_coordination_row(tmp_path):
    repo = make_repo(tmp_path)
    try:
        before = repo._connection.execute(
            """
            SELECT epoch
            FROM moldock.repository_coordination
            WHERE coordination_key = 'shared_adapters'
            """
        ).fetchone()[0]

        repo.register(make_artifact())

        after = repo._connection.execute(
            """
            SELECT epoch
            FROM moldock.repository_coordination
            WHERE coordination_key = 'shared_adapters'
            """
        ).fetchone()[0]
        assert after == before + 1
    finally:
        repo.close()


def test_domain_conflict_is_not_retried_as_transaction_conflict(tmp_path):
    repo = make_repo(tmp_path)
    first = make_artifact()
    conflicting = make_artifact(uri="memory://blob/conflicting")
    repo.register(first)

    with pytest.raises(DomainValidationError, match="conflicting"):
        repo.register(conflicting)

    assert repo.get(first.artifact_id) == first
