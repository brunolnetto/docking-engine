import hashlib

import pytest

from moldock.domain import (
    DockingBox,
    DockingTask,
    DomainValidationError,
    PreparedLigand,
    PreparedReceptor,
)
from moldock.execution import (
    DockingInputResolver,
    PersistentDockingInputResolver,
)
from moldock.repositories import (
    DuckLakePreparedInputRepository,
    PreparedInputRepository,
)
from moldock.storage import FilesystemArtifactStore


BOX = DockingBox(1, 2, 3, 20, 20, 20)


def make_task():
    return DockingTask(
        experiment_id="exp_1",
        receptor_id="rec_1",
        ligand_id="lig_1",
        prepared_receptor_id="prepared_rec_1",
        prepared_ligand_id="prepared_lig_1",
        search_space_id=BOX.search_space_id,
    )


def make_repo(tmp_path):
    return DuckLakePreparedInputRepository(
        catalog_path=tmp_path / "catalog.sqlite",
        data_path=tmp_path / "data",
        retry_delay_seconds=0,
    )


def prepared_receptor():
    return PreparedReceptor(
        receptor_id="rec_1",
        preparation_id="rprep_1",
        prepared_receptor_id="prepared_rec_1",
    )


def prepared_ligand():
    return PreparedLigand(
        ligand_id="lig_1",
        preparation_id="lprep_1",
        prepared_ligand_id="prepared_lig_1",
    )


def test_ducklake_prepared_repository_satisfies_contract(tmp_path):
    repo = make_repo(tmp_path)
    try:
        assert isinstance(repo, PreparedInputRepository)
    finally:
        repo.close()


def test_prepared_bindings_survive_repository_restart(tmp_path):
    store = FilesystemArtifactStore(tmp_path / "artifacts")
    receptor_blob = store.put(b"REC")
    ligand_blob = store.put(b"LIG")

    repo = make_repo(tmp_path)
    repo.register_receptor(prepared_receptor(), receptor_blob)
    repo.register_ligand(prepared_ligand(), ligand_blob)
    repo.close()

    reopened = make_repo(tmp_path)
    try:
        receptor = reopened.get_receptor("prepared_rec_1")
        ligand = reopened.get_ligand("prepared_lig_1")
        assert receptor.prepared == prepared_receptor()
        assert receptor.blob == receptor_blob
        assert ligand.prepared == prepared_ligand()
        assert ligand.blob == ligand_blob
    finally:
        reopened.close()


def test_identical_registration_is_idempotent_and_conflict_is_rejected(tmp_path):
    store = FilesystemArtifactStore(tmp_path / "artifacts")
    first_blob = store.put(b"LIG")
    second_blob = store.put(b"OTHER")
    repo = make_repo(tmp_path)
    ligand = prepared_ligand()

    try:
        repo.register_ligand(ligand, first_blob)
        repo.register_ligand(ligand, first_blob)

        with pytest.raises(DomainValidationError, match="conflicting"):
            repo.register_ligand(ligand, second_blob)
    finally:
        repo.close()


def test_persistent_resolver_reconstructs_pdbqt_after_restart(tmp_path):
    store = FilesystemArtifactStore(tmp_path / "artifacts")
    repo = make_repo(tmp_path)
    repo.register_receptor(prepared_receptor(), store.put(b"REC"))
    repo.register_ligand(prepared_ligand(), store.put(b"LIG"))
    repo.close()

    reopened = make_repo(tmp_path)
    resolver = PersistentDockingInputResolver(
        prepared_inputs=reopened,
        artifact_store=store,
    )
    resolver.register_search_space(BOX)
    resolver.register_parameters("exp_1", {"seed": 42})

    try:
        assert isinstance(resolver, DockingInputResolver)
        request = resolver.resolve(make_task())
        assert request.receptor_pdbqt == b"REC"
        assert request.ligand_pdbqt == b"LIG"
        assert request.search_space == BOX
        assert request.parameters["seed"] == 42
    finally:
        reopened.close()


def test_resolver_rejects_missing_prepared_inputs(tmp_path):
    repo = make_repo(tmp_path)
    resolver = PersistentDockingInputResolver(
        prepared_inputs=repo,
        artifact_store=FilesystemArtifactStore(tmp_path / "artifacts"),
    )
    resolver.register_search_space(BOX)
    try:
        with pytest.raises(DomainValidationError, match="prepared receptor"):
            resolver.resolve(make_task())
    finally:
        repo.close()


class CorruptingStore:
    def read(self, uri):
        return b"CORRUPTED"


def test_resolver_verifies_stored_blob_integrity(tmp_path):
    store = FilesystemArtifactStore(tmp_path / "artifacts")
    repo = make_repo(tmp_path)
    repo.register_receptor(prepared_receptor(), store.put(b"REC"))
    repo.register_ligand(prepared_ligand(), store.put(b"LIG"))

    resolver = PersistentDockingInputResolver(
        prepared_inputs=repo,
        artifact_store=CorruptingStore(),
    )
    resolver.register_search_space(BOX)

    try:
        with pytest.raises(DomainValidationError, match="integrity"):
            resolver.resolve(make_task())
    finally:
        repo.close()


def test_resolver_rejects_missing_search_space(tmp_path):
    store = FilesystemArtifactStore(tmp_path / "artifacts")
    repo = make_repo(tmp_path)
    repo.register_receptor(prepared_receptor(), store.put(b"REC"))
    repo.register_ligand(prepared_ligand(), store.put(b"LIG"))
    resolver = PersistentDockingInputResolver(
        prepared_inputs=repo,
        artifact_store=store,
    )
    try:
        with pytest.raises(DomainValidationError, match="search space"):
            resolver.resolve(make_task())
    finally:
        repo.close()



def test_prepared_receptor_registration_is_idempotent_and_conflict_is_rejected(
    tmp_path,
):
    store = FilesystemArtifactStore(tmp_path / "artifacts")
    first_blob = store.put(b"REC")
    second_blob = store.put(b"OTHER")
    repo = make_repo(tmp_path)
    receptor = prepared_receptor()

    try:
        repo.register_receptor(receptor, first_blob)
        repo.register_receptor(receptor, first_blob)

        with pytest.raises(DomainValidationError, match="conflicting"):
            repo.register_receptor(receptor, second_blob)
    finally:
        repo.close()


def test_prepared_repository_missing_lookups_return_none(tmp_path):
    repo = make_repo(tmp_path)
    try:
        assert repo.get_ligand("missing") is None
        assert repo.get_receptor("missing") is None
    finally:
        repo.close()


def test_prepared_repository_detects_duplicate_ligand_identity(tmp_path):
    store = FilesystemArtifactStore(tmp_path / "artifacts")
    blob = store.put(b"LIG")
    repo = make_repo(tmp_path)
    ligand = prepared_ligand()
    try:
        repo.register_ligand(ligand, blob)
        repo._connection.execute(
            """
            INSERT INTO moldock.prepared_ligands
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ligand.prepared_ligand_id,
                ligand.ligand_id,
                ligand.preparation_id,
                blob.blob_id,
                blob.uri,
                blob.sha256,
                blob.size_bytes,
            ],
        )

        with pytest.raises(RuntimeError, match="duplicated"):
            repo.get_ligand(ligand.prepared_ligand_id)
    finally:
        repo.close()


def test_prepared_repository_detects_duplicate_receptor_identity(tmp_path):
    store = FilesystemArtifactStore(tmp_path / "artifacts")
    blob = store.put(b"REC")
    repo = make_repo(tmp_path)
    receptor = prepared_receptor()
    try:
        repo.register_receptor(receptor, blob)
        repo._connection.execute(
            """
            INSERT INTO moldock.prepared_receptors
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                receptor.prepared_receptor_id,
                receptor.receptor_id,
                receptor.preparation_id,
                blob.blob_id,
                blob.uri,
                blob.sha256,
                blob.size_bytes,
            ],
        )

        with pytest.raises(RuntimeError, match="duplicated"):
            repo.get_receptor(receptor.prepared_receptor_id)
    finally:
        repo.close()
