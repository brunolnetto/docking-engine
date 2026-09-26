from subprocess import CompletedProcess

import pytest

import moldock.toolchain as toolchain_module

from moldock.backends import VinaBackend
from moldock.domain import DomainValidationError
from moldock.preparation import (
    MeekoLigandPreparer,
    MeekoReceptorPreparer,
)
from moldock.toolchain import (
    ExecutableInfo,
    ToolchainSnapshot,
    VinaMeekoToolchainPreflight,
)


PATHS = {
    "custom-vina": "/opt/vina/bin/vina",
    "custom-ligand": "/opt/meeko-lig/bin/mk_prepare_ligand.py",
    "custom-receptor": "/opt/meeko-rec/bin/mk_prepare_receptor.py",
}
INTERPRETERS = {
    "/opt/meeko-lig/bin/mk_prepare_ligand.py": "/opt/meeko-lig/bin/python",
    "/opt/meeko-rec/bin/mk_prepare_receptor.py": "/opt/meeko-rec/bin/python",
}


class VersionRunner:
    def __init__(
        self,
        *,
        vina_version="1.2.7",
        ligand_version="0.8.0",
        receptor_version="0.8.0",
        fail_command=None,
    ):
        self.calls = []
        self.vina_version = vina_version
        self.ligand_version = ligand_version
        self.receptor_version = receptor_version
        self.fail_command = fail_command

    def __call__(self, command):
        call = tuple(command)
        self.calls.append(call)
        if self.fail_command and command[0] == self.fail_command:
            return CompletedProcess(command, 2, "", "failed")
        if command[0] == "/opt/vina/bin/vina":
            return CompletedProcess(
                command,
                0,
                f"AutoDock Vina v{self.vina_version}\n",
                "",
            )
        if command[0] == "/opt/meeko-lig/bin/python":
            return CompletedProcess(
                command, 0, self.ligand_version + "\n", ""
            )
        if command[0] == "/opt/meeko-rec/bin/python":
            return CompletedProcess(
                command, 0, self.receptor_version + "\n", ""
            )
        raise AssertionError(f"unexpected command: {command!r}")


def inspect(preflight, **overrides):
    values = dict(
        expected_backend="vina",
        expected_vina_version="1.2.7",
        expected_ligand_method="meeko",
        expected_ligand_version="0.8.0",
        expected_receptor_method="meeko",
        expected_receptor_version="0.8.0",
        vina_executable="custom-vina",
        ligand_executable="custom-ligand",
        receptor_executable="custom-receptor",
    )
    values.update(overrides)
    return preflight.inspect(**values)


def make_preflight(runner=None):
    return VinaMeekoToolchainPreflight(
        runner=runner or VersionRunner(),
        which=PATHS.get,
        interpreter_for_executable=INTERPRETERS.get,
    )


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


def test_components_expose_the_executable_they_actually_run():
    assert VinaBackend(executable="custom-vina").executable == "custom-vina"
    assert (
        MeekoLigandPreparer(
            executable="custom-ligand",
            method_version="0.8.0",
        ).executable
        == "custom-ligand"
    )
    assert (
        MeekoReceptorPreparer(
            executable="custom-receptor",
            method_version="0.8.0",
        ).executable
        == "custom-receptor"
    )


def test_preflight_probes_versions_from_each_resolved_tool_environment():
    runner = VersionRunner()
    snapshot = inspect(make_preflight(runner))

    assert snapshot.vina.resolved_path == "/opt/vina/bin/vina"
    assert snapshot.vina.version == "1.2.7"
    assert snapshot.meeko_ligand.resolved_path.endswith(
        "mk_prepare_ligand.py"
    )
    assert snapshot.meeko_receptor.resolved_path.endswith(
        "mk_prepare_receptor.py"
    )
    assert snapshot.meeko_ligand.version == "0.8.0"
    assert snapshot.meeko_receptor.version == "0.8.0"
    assert runner.calls[0] == ("/opt/vina/bin/vina", "--version")
    assert runner.calls[1][0] == "/opt/meeko-lig/bin/python"
    assert runner.calls[2][0] == "/opt/meeko-rec/bin/python"


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"expected_backend": "gnina"}, "backend"),
        ({"expected_vina_version": "1.2.6"}, "Vina version"),
        ({"expected_ligand_version": "0.7.1"}, "ligand version"),
        ({"expected_receptor_version": "0.7.1"}, "receptor version"),
        ({"expected_ligand_method": "other"}, "ligand preparation method"),
        ({"expected_receptor_method": "other"}, "receptor preparation method"),
    ],
)
def test_preflight_rejects_declared_toolchain_mismatch(overrides, match):
    with pytest.raises(DomainValidationError, match=match):
        inspect(make_preflight(), **overrides)


def test_preflight_detects_different_meeko_environments():
    runner = VersionRunner(receptor_version="0.7.1")

    with pytest.raises(DomainValidationError, match="receptor version"):
        inspect(make_preflight(runner))


@pytest.mark.parametrize(
    "field",
    ["vina_executable", "ligand_executable", "receptor_executable"],
)
def test_preflight_requires_actual_adapter_executables(field):
    with pytest.raises(DomainValidationError, match="executable"):
        inspect(make_preflight(), **{field: None})


def test_preflight_rejects_missing_executable():
    preflight = VinaMeekoToolchainPreflight(
        which=lambda executable: None,
        runner=VersionRunner(),
        interpreter_for_executable=INTERPRETERS.get,
    )

    with pytest.raises(DomainValidationError, match="not found"):
        inspect(preflight)


def test_preflight_rejects_unknown_meeko_owning_interpreter():
    preflight = VinaMeekoToolchainPreflight(
        which=PATHS.get,
        runner=VersionRunner(),
        interpreter_for_executable=lambda executable: None,
    )

    with pytest.raises(DomainValidationError, match="Python environment"):
        inspect(preflight)


def test_preflight_rejects_vina_version_command_failure():
    runner = VersionRunner(fail_command="/opt/vina/bin/vina")

    with pytest.raises(DomainValidationError, match="version probe failed"):
        inspect(make_preflight(runner))


def test_preflight_rejects_meeko_version_command_failure():
    runner = VersionRunner(
        fail_command="/opt/meeko-lig/bin/python"
    )

    with pytest.raises(DomainValidationError, match="Meeko version probe"):
        inspect(make_preflight(runner))



@pytest.mark.parametrize(
    "field",
    ["name", "executable", "resolved_path", "version"],
)
def test_executable_info_rejects_blank_fields(field):
    values = {
        "name": "vina",
        "executable": "vina",
        "resolved_path": "/opt/vina",
        "version": "1.2.7",
    }
    values[field] = " "

    with pytest.raises(DomainValidationError, match=field):
        ExecutableInfo(**values)


def test_default_runner_delegates_to_subprocess_run(monkeypatch):
    expected = CompletedProcess(["tool", "--version"], 0, "ok", "")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return expected

    monkeypatch.setattr(toolchain_module.subprocess, "run", fake_run)

    result = toolchain_module._default_runner(["tool", "--version"])

    assert result is expected
    assert calls == [
        (
            ["tool", "--version"],
            {
                "capture_output": True,
                "text": True,
                "check": False,
            },
        )
    ]


def test_default_interpreter_returns_none_for_missing_or_empty_file(tmp_path):
    missing = tmp_path / "missing"
    empty = tmp_path / "empty"
    empty.write_text("")

    assert toolchain_module._default_interpreter_for_executable(str(missing)) is None
    assert toolchain_module._default_interpreter_for_executable(str(empty)) is None


def test_default_interpreter_requires_shebang(tmp_path):
    script = tmp_path / "tool.py"
    script.write_text("print('x')\n")

    assert toolchain_module._default_interpreter_for_executable(str(script)) is None


def test_default_interpreter_handles_env_shebang(monkeypatch, tmp_path):
    script = tmp_path / "tool.py"
    script.write_text("#!/usr/bin/env python3\nprint('x')\n")
    monkeypatch.setattr(
        toolchain_module.shutil,
        "which",
        lambda name: "/venv/bin/python3" if name == "python3" else None,
    )

    assert (
        toolchain_module._default_interpreter_for_executable(str(script))
        == "/venv/bin/python3"
    )


def test_default_interpreter_rejects_env_without_program(tmp_path):
    script = tmp_path / "tool.py"
    script.write_text("#!/usr/bin/env\n")

    assert toolchain_module._default_interpreter_for_executable(str(script)) is None


def test_default_interpreter_returns_direct_shebang_interpreter(tmp_path):
    script = tmp_path / "tool.py"
    script.write_text("#!/opt/venv/bin/python\n")

    assert (
        toolchain_module._default_interpreter_for_executable(str(script))
        == "/opt/venv/bin/python"
    )


def test_preflight_rejects_unparseable_vina_version():
    class Runner(VersionRunner):
        def __call__(self, command):
            if command[0] == "/opt/vina/bin/vina":
                return CompletedProcess(command, 0, "unknown version", "")
            return super().__call__(command)

    with pytest.raises(DomainValidationError, match="parse Vina version"):
        inspect(make_preflight(Runner()))


def test_preflight_rejects_empty_meeko_version():
    class Runner(VersionRunner):
        def __call__(self, command):
            if command[0] == "/opt/meeko-lig/bin/python":
                return CompletedProcess(command, 0, "\n", "")
            return super().__call__(command)

    with pytest.raises(DomainValidationError, match="returned no version"):
        inspect(make_preflight(Runner()))



def test_default_interpreter_rejects_empty_shebang_command(tmp_path):
    script = tmp_path / "tool.py"
    script.write_text("#!   \n")

    assert toolchain_module._default_interpreter_for_executable(str(script)) is None
