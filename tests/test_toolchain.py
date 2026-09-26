from pathlib import Path
from subprocess import CompletedProcess

import pytest

from moldock.domain import DomainValidationError
from moldock.pipeline import OfflineDockingPipeline
from moldock.toolchain import (
    ExecutableInfo,
    ToolchainSnapshot,
    VinaMeekoToolchainPreflight,
)


def make_which():
    paths = {
        "vina": "/opt/tools/vina",
        "mk_prepare_ligand.py": "/opt/tools/mk_prepare_ligand.py",
        "mk_prepare_receptor.py": "/opt/tools/mk_prepare_receptor.py",
    }
    return paths.get


class VersionRunner:
    def __init__(self, stdout="AutoDock Vina v1.2.7\n", returncode=0):
        self.calls = []
        self.stdout = stdout
        self.returncode = returncode

    def __call__(self, command):
        self.calls.append(tuple(command))
        return CompletedProcess(command, self.returncode, self.stdout, "")


def test_toolchain_snapshot_is_content_addressed():
    info = ExecutableInfo(
        name="vina",
        executable="vina",
        resolved_path="/opt/tools/vina",
        version="1.2.7",
    )
    a = ToolchainSnapshot(vina=info, meeko_ligand=info, meeko_receptor=info)
    b = ToolchainSnapshot(vina=info, meeko_ligand=info, meeko_receptor=info)

    assert a.snapshot_id == b.snapshot_id
    assert a.snapshot_id.startswith("toolchain_")


def test_preflight_resolves_tools_and_verifies_versions():
    runner = VersionRunner()
    preflight = VinaMeekoToolchainPreflight(
        which=make_which(),
        runner=runner,
        package_version=lambda package: "0.8.0",
    )

    snapshot = preflight.inspect(
        expected_vina_version="1.2.7",
        expected_ligand_method="meeko",
        expected_ligand_version="0.8.0",
        expected_receptor_method="meeko",
        expected_receptor_version="0.8.0",
    )

    assert snapshot.vina.version == "1.2.7"
    assert snapshot.vina.resolved_path == "/opt/tools/vina"
    assert snapshot.meeko_ligand.version == "0.8.0"
    assert snapshot.meeko_receptor.version == "0.8.0"
    assert runner.calls == [("/opt/tools/vina", "--version")]


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"expected_vina_version": "1.2.6"}, "Vina version"),
        ({"expected_ligand_version": "0.7.1"}, "ligand version"),
        ({"expected_receptor_version": "0.7.1"}, "receptor version"),
        ({"expected_ligand_method": "other"}, "ligand preparation method"),
        ({"expected_receptor_method": "other"}, "receptor preparation method"),
    ],
)
def test_preflight_rejects_declared_toolchain_mismatch(kwargs, match):
    values = dict(
        expected_vina_version="1.2.7",
        expected_ligand_method="meeko",
        expected_ligand_version="0.8.0",
        expected_receptor_method="meeko",
        expected_receptor_version="0.8.0",
    )
    values.update(kwargs)
    preflight = VinaMeekoToolchainPreflight(
        which=make_which(),
        runner=VersionRunner(),
        package_version=lambda package: "0.8.0",
    )

    with pytest.raises(DomainValidationError, match=match):
        preflight.inspect(**values)


def test_preflight_rejects_missing_executable():
    preflight = VinaMeekoToolchainPreflight(
        which=lambda executable: None,
        runner=VersionRunner(),
        package_version=lambda package: "0.8.0",
    )

    with pytest.raises(DomainValidationError, match="not found"):
        preflight.inspect(
            expected_vina_version="1.2.7",
            expected_ligand_method="meeko",
            expected_ligand_version="0.8.0",
            expected_receptor_method="meeko",
            expected_receptor_version="0.8.0",
        )


@pytest.mark.parametrize(
    "stdout",
    ["", "vina development build", "AutoDock Vina"],
)
def test_preflight_rejects_unparseable_vina_version(stdout):
    preflight = VinaMeekoToolchainPreflight(
        which=make_which(),
        runner=VersionRunner(stdout=stdout),
        package_version=lambda package: "0.8.0",
    )

    with pytest.raises(DomainValidationError, match="parse Vina version"):
        preflight.inspect(
            expected_vina_version="1.2.7",
            expected_ligand_method="meeko",
            expected_ligand_version="0.8.0",
            expected_receptor_method="meeko",
            expected_receptor_version="0.8.0",
        )


def test_preflight_rejects_vina_version_command_failure():
    preflight = VinaMeekoToolchainPreflight(
        which=make_which(),
        runner=VersionRunner(returncode=2),
        package_version=lambda package: "0.8.0",
    )

    with pytest.raises(DomainValidationError, match="version probe failed"):
        preflight.inspect(
            expected_vina_version="1.2.7",
            expected_ligand_method="meeko",
            expected_ligand_version="0.8.0",
            expected_receptor_method="meeko",
            expected_receptor_version="0.8.0",
        )
