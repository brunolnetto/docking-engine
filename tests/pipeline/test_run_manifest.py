import pytest

from moldock.domain import DomainValidationError
from moldock.pipeline import PipelineRunResult, RunManifest
from moldock.repositories import (
    DuckLakeRunManifestRepository,
    RunManifestRepository,
)
from moldock.toolchain import ExecutableInfo, ToolchainSnapshot


def snapshot():
    return ToolchainSnapshot(
        vina=ExecutableInfo(
            name="vina",
            executable="vina",
            resolved_path="/opt/vina",
            version="1.2.7",
        ),
        meeko_ligand=ExecutableInfo(
            name="meeko_ligand",
            executable="mk_prepare_ligand.py",
            resolved_path="/opt/mk_prepare_ligand.py",
            version="0.8.0",
        ),
        meeko_receptor=ExecutableInfo(
            name="meeko_receptor",
            executable="mk_prepare_receptor.py",
            resolved_path="/opt/mk_prepare_receptor.py",
            version="0.8.0",
        ),
    )


def manifest(**overrides):
    values = dict(
        run_id="run_1",
        experiment_id="exp_1",
        protocol_id="protocol_1",
        task_manifest_id="manifest_1",
        search_space_id="space_1",
        receptor_id="rec_1",
        receptor_source_sha256="a" * 64,
        ligand_sources=(("lig_1", "b" * 64),),
        prepared_receptor_id="prec_1",
        prepared_ligand_ids=("plig_1",),
        task_ids=("task_1",),
        toolchain_snapshot=snapshot(),
    )
    values.update(overrides)
    return RunManifest(**values)


def make_repo(tmp_path):
    return DuckLakeRunManifestRepository(
        catalog_path=tmp_path / "catalog.sqlite",
        data_path=tmp_path / "data",
        retry_delay_seconds=0,
    )


def test_run_manifest_is_content_addressed_and_reconstructs_pipeline_result():
    value = manifest()

    result = value.to_pipeline_result()

    assert value.run_manifest_id.startswith("run_manifest_")
    assert result == PipelineRunResult(
        run_id="run_1",
        experiment_id="exp_1",
        protocol_id="protocol_1",
        manifest_id="manifest_1",
        prepared_receptor_id="prec_1",
        prepared_ligand_ids=("plig_1",),
        task_ids=("task_1",),
        toolchain_snapshot=snapshot(),
    )


def test_ducklake_run_manifest_repository_satisfies_contract(tmp_path):
    repo = make_repo(tmp_path)
    try:
        assert isinstance(repo, RunManifestRepository)
    finally:
        repo.close()


def test_run_manifest_survives_repository_restart(tmp_path):
    repo = make_repo(tmp_path)
    expected = manifest()
    repo.register(expected)
    repo.close()

    reopened = make_repo(tmp_path)
    try:
        assert reopened.get("run_1") == expected
        assert (
            reopened.get("run_1").toolchain_snapshot.snapshot_id
            == expected.toolchain_snapshot.snapshot_id
        )
    finally:
        reopened.close()


def test_identical_run_manifest_registration_is_idempotent(tmp_path):
    repo = make_repo(tmp_path)
    expected = manifest()
    try:
        repo.register(expected)
        repo.register(expected)
        assert repo.get(expected.run_id) == expected
    finally:
        repo.close()


def test_same_run_id_with_different_manifest_is_rejected(tmp_path):
    repo = make_repo(tmp_path)
    try:
        repo.register(manifest())
        with pytest.raises(DomainValidationError, match="conflicting"):
            repo.register(
                manifest(
                    task_manifest_id="manifest_2",
                    task_ids=("task_2",),
                )
            )
    finally:
        repo.close()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("run_id", " "),
        ("experiment_id", " "),
        ("protocol_id", " "),
        ("task_manifest_id", " "),
        ("search_space_id", " "),
        ("receptor_id", " "),
        ("receptor_source_sha256", " "),
        ("prepared_receptor_id", " "),
    ],
)
def test_run_manifest_rejects_blank_required_fields(field, value):
    with pytest.raises(DomainValidationError):
        manifest(**{field: value})


def test_run_manifest_rejects_blank_nested_identity():
    with pytest.raises(DomainValidationError):
        manifest(ligand_sources=((" ", "b" * 64),))

    with pytest.raises(DomainValidationError):
        manifest(prepared_ligand_ids=(" ",))

    with pytest.raises(DomainValidationError):
        manifest(task_ids=(" ",))


def test_run_manifest_without_toolchain_survives_restart(tmp_path):
    repo = make_repo(tmp_path)
    expected = manifest(toolchain_snapshot=None)
    repo.register(expected)
    repo.close()

    reopened = make_repo(tmp_path)
    try:
        restored = reopened.get(expected.run_id)
        assert restored == expected
        assert restored.toolchain_snapshot is None
    finally:
        reopened.close()



def test_run_manifest_get_returns_none_for_unknown_run(tmp_path):
    repo = make_repo(tmp_path)
    try:
        assert repo.get("missing") is None
    finally:
        repo.close()


def test_run_manifest_repository_detects_duplicate_identity_rows(tmp_path):
    repo = make_repo(tmp_path)
    value = manifest()
    try:
        repo.register(value)
        row = repo._connection.execute(
            """
            SELECT *
            FROM moldock.run_manifests
            WHERE run_id = ?
            """,
            [value.run_id],
        ).fetchone()
        placeholders = ", ".join(["?"] * len(row))
        repo._connection.execute(
            f"INSERT INTO moldock.run_manifests VALUES ({placeholders})",
            list(row),
        )

        with pytest.raises(RuntimeError, match="duplicated"):
            repo.get(value.run_id)
    finally:
        repo.close()


def test_run_manifest_repository_detects_persisted_identity_corruption(tmp_path):
    repo = make_repo(tmp_path)
    value = manifest()
    try:
        repo.register(value)
        repo._connection.execute(
            """
            UPDATE moldock.run_manifests
            SET run_manifest_id = ?
            WHERE run_id = ?
            """,
            ["run_manifest_corrupt", value.run_id],
        )

        with pytest.raises(RuntimeError, match="does not match"):
            repo.get(value.run_id)
    finally:
        repo.close()
