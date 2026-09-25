from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
from datetime import timedelta

import pytest

from moldock.backends import (
    DockingBackend,
    DockingBackendError,
    DockingBackendTimeoutError,
    VinaBackend,
)
from moldock.domain import DockingBox, DockingExecutionRequest, DockingTask


def make_request(parameters=None) -> DockingExecutionRequest:
    box = DockingBox(1.5, -2.0, 3.25, 20.0, 21.0, 22.0)
    task = DockingTask(
        experiment_id="exp_1",
        receptor_id="rec_1",
        ligand_id="lig_1",
        prepared_receptor_id="prepared_rec_1",
        prepared_ligand_id="prepared_lig_1",
        search_space_id=box.search_space_id,
    )
    return DockingExecutionRequest(
        task=task,
        receptor_pdbqt=b"RECEPTOR",
        ligand_pdbqt=b"LIGAND",
        search_space=box,
        parameters=parameters or {"exhaustiveness": 8, "num_modes": 4, "seed": 42},
    )


class RecordingRunner:
    def __init__(self, *, returncode=0, stdout="vina stdout", stderr=""):
        self.calls = []
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def __call__(self, command, *, cwd, timeout=None):
        self.calls.append((tuple(command), Path(cwd), timeout))
        out_path = Path(command[command.index("--out") + 1])
        out_path.write_bytes(b"MODEL 1\nREMARK VINA RESULT: -8.1 0.0 0.0\nENDMDL\n")
        return CompletedProcess(command, self.returncode, self.stdout, self.stderr)


def test_vina_backend_implements_contract():
    assert isinstance(VinaBackend(runner=RecordingRunner()), DockingBackend)


def test_vina_backend_builds_cli_and_returns_raw_pose():
    runner = RecordingRunner()
    backend = VinaBackend(executable="vina-custom", runner=runner)

    result = backend.execute(make_request())

    assert len(runner.calls) == 1
    command, cwd, timeout = runner.calls[0]
    assert command[0] == "vina-custom"
    assert timeout is None
    assert command[command.index("--center_x") + 1] == "1.5"
    assert command[command.index("--center_y") + 1] == "-2.0"
    assert command[command.index("--center_z") + 1] == "3.25"
    assert command[command.index("--size_x") + 1] == "20.0"
    assert command[command.index("--size_y") + 1] == "21.0"
    assert command[command.index("--size_z") + 1] == "22.0"
    assert command[command.index("--exhaustiveness") + 1] == "8"
    assert command[command.index("--num_modes") + 1] == "4"
    assert command[command.index("--seed") + 1] == "42"

    receptor_path = Path(command[command.index("--receptor") + 1])
    ligand_path = Path(command[command.index("--ligand") + 1])
    assert receptor_path.parent == cwd
    assert ligand_path.parent == cwd

    assert result.stdout == "vina stdout"
    assert result.stderr == ""
    assert len(result.artifacts) == 1
    assert result.artifacts[0].kind == "docking_pose"
    assert b"REMARK VINA RESULT: -8.1" in result.artifacts[0].content


def test_vina_backend_maps_optional_supported_parameters():
    runner = RecordingRunner()
    backend = VinaBackend(runner=runner)

    backend.execute(
        make_request(
            {
                "exhaustiveness": 16,
                "num_modes": 7,
                "energy_range": 5,
                "seed": 123,
                "cpu": 2,
                "verbosity": 1,
            }
        )
    )

    command, _, _ = runner.calls[0]
    for flag, value in {
        "--exhaustiveness": "16",
        "--num_modes": "7",
        "--energy_range": "5",
        "--seed": "123",
        "--cpu": "2",
        "--verbosity": "1",
    }.items():
        assert command[command.index(flag) + 1] == value


def test_vina_backend_rejects_unsupported_parameter():
    backend = VinaBackend(runner=RecordingRunner())

    with pytest.raises(DockingBackendError, match="unsupported Vina parameter"):
        backend.execute(make_request({"mystery_option": 1}))


def test_vina_backend_failure_includes_process_diagnostics():
    runner = RecordingRunner(returncode=2, stdout="partial", stderr="bad ligand")
    backend = VinaBackend(runner=runner)

    with pytest.raises(DockingBackendError, match="bad ligand"):
        backend.execute(make_request())


def test_vina_backend_wraps_launch_errors():
    class MissingExecutableRunner:
        def __call__(self, command, *, cwd, timeout=None):
            raise FileNotFoundError("vina executable not found")

    backend = VinaBackend(runner=MissingExecutableRunner())

    with pytest.raises(DockingBackendError, match="failed to launch Vina") as error:
        backend.execute(make_request())

    assert isinstance(error.value.__cause__, FileNotFoundError)


def test_vina_backend_requires_output_file():
    class NoOutputRunner:
        def __call__(self, command, *, cwd, timeout=None):
            return CompletedProcess(command, 0, "ok", "")

    backend = VinaBackend(runner=NoOutputRunner())

    with pytest.raises(DockingBackendError, match="did not produce"):
        backend.execute(make_request())


def test_default_vina_runner_delegates_to_subprocess(monkeypatch):
    import moldock.backends.vina as vina_module

    calls = []

    def fake_run(command, *, cwd, capture_output, text, check, timeout):
        calls.append((command, cwd, capture_output, text, check, timeout))
        return CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(vina_module.subprocess, "run", fake_run)

    result = vina_module._default_runner(
        ["vina", "--version"],
        cwd=Path("/tmp"),
    )

    assert result.returncode == 0
    assert calls == [
        (["vina", "--version"], Path("/tmp"), True, True, False, None)
    ]


def test_vina_backend_passes_configured_timeout_to_runner():
    runner = RecordingRunner()
    backend = VinaBackend(
        runner=runner,
        execution_timeout=timedelta(seconds=90),
    )

    backend.execute(make_request())

    _, _, timeout = runner.calls[0]
    assert timeout == 90.0


def test_vina_backend_rejects_non_positive_timeout():
    with pytest.raises(ValueError, match="execution_timeout"):
        VinaBackend(execution_timeout=timedelta(0))


def test_vina_backend_maps_subprocess_timeout_to_typed_backend_timeout():
    class TimingOutRunner:
        def __call__(self, command, *, cwd, timeout=None):
            raise TimeoutExpired(command, timeout)

    backend = VinaBackend(
        runner=TimingOutRunner(),
        execution_timeout=timedelta(seconds=30),
    )

    with pytest.raises(DockingBackendTimeoutError, match="timed out") as error:
        backend.execute(make_request())

    assert isinstance(error.value.__cause__, TimeoutExpired)


def test_vina_backend_keeps_legacy_injected_runner_signature_without_timeout():
    calls = []

    class LegacyRunner:
        def __call__(self, command, *, cwd):
            calls.append((command, cwd))
            out_path = Path(command[command.index("--out") + 1])
            out_path.write_bytes(
                b"MODEL 1\nREMARK VINA RESULT: -8.1 0.0 0.0\nENDMDL\n"
            )
            return CompletedProcess(command, 0, "ok", "")

    backend = VinaBackend(runner=LegacyRunner())
    backend.execute(make_request())

    assert len(calls) == 1
