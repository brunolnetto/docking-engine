from datetime import timedelta
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired

import pytest

from moldock.domain import DomainValidationError
from moldock.preparation import (
    ReceptorPreparationProtocol,
    ReceptorPreparationRequest,
    ReceptorPreparer,
    MeekoReceptorPreparationError,
    MeekoReceptorPreparationTimeoutError,
    MeekoReceptorPreparer,
)


PDB = (
    b"MODEL        7\n"
    b"ATOM      1  N   ALA B   1      11.104  13.207  14.099  1.00 20.00           N  \n"
    b"ATOM      2  C   GLY A   2      12.104  13.207  14.099  1.00 20.00           C  \n"
    b"ENDMDL\n"
)


def make_request(*, source_format="pdb", content=PDB, parameters=None, version="0.8.0"):
    protocol = ReceptorPreparationProtocol(
        method="meeko",
        method_version=version,
        parameters=parameters or {},
    )
    return ReceptorPreparationRequest(
        receptor_id="rec_1",
        source_format=source_format,
        content=content,
        protocol=protocol,
    )


class RecordingRunner:
    def __init__(self, *, returncode=0, stdout="prepared", stderr="", write_output=True):
        self.calls = []
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.write_output = write_output

    def __call__(self, command, *, cwd, timeout=None):
        self.calls.append((tuple(command), Path(cwd), timeout))
        input_path = Path(command[command.index("--read_pdb") + 1])
        assert input_path.read_bytes()
        if self.write_output:
            output_path = Path(command[command.index("--write_pdbqt") + 1])
            output_path.write_bytes(b"ATOM PDBQT\n")
        return CompletedProcess(command, self.returncode, self.stdout, self.stderr)


def test_meeko_receptor_preparer_implements_contract():
    preparer = MeekoReceptorPreparer(
        method_version="0.8.0",
        runner=RecordingRunner(),
    )

    assert isinstance(preparer, ReceptorPreparer)


def test_meeko_receptor_preparer_builds_cli_and_returns_identity():
    runner = RecordingRunner()
    preparer = MeekoReceptorPreparer(
        executable="mk_prepare_receptor-custom",
        method_version="0.8.0",
        runner=runner,
    )

    artifact = preparer.prepare(
        make_request(
            parameters={
                "delete_bad_res": True,
                "default_altloc": "A",
                "compute_charges": True,
                "charge_model": "gasteiger",
                "forgive_extra_bonds": True,
            }
        )
    )

    assert artifact.receptor_id == "rec_1"
    assert artifact.model_id == "model_7"
    assert artifact.chain_ids == ("A", "B")
    assert artifact.pdbqt == b"ATOM PDBQT\n"

    command, cwd, timeout = runner.calls[0]
    assert command[0] == "mk_prepare_receptor-custom"
    assert timeout is None
    assert Path(command[command.index("--read_pdb") + 1]).suffix == ".pdb"
    assert Path(command[command.index("--write_pdbqt") + 1]).parent == cwd
    assert "--delete_bad_res" in command
    assert command[command.index("--default_altloc") + 1] == "A"
    assert "--compute_charges" in command
    assert command[command.index("--charge_model") + 1] == "gasteiger"
    assert "--forgive_extra_bonds" in command


def test_receptor_without_model_record_defaults_to_model_1():
    pdb = b"ATOM      1  N   ALA A   1      11.104  13.207  14.099  1.00 20.00           N  \n"
    runner = RecordingRunner()
    preparer = MeekoReceptorPreparer(
        method_version="0.8.0",
        runner=runner,
    )

    artifact = preparer.prepare(make_request(content=pdb))

    assert artifact.model_id == "model_1"
    assert artifact.chain_ids == ("A",)


def test_meeko_receptor_preparer_rejects_multiple_models():
    pdb = (
        b"MODEL        1\n"
        b"ATOM      1  N   ALA A   1      11.104  13.207  14.099  1.00 20.00           N  \n"
        b"ENDMDL\n"
        b"MODEL        2\n"
        b"ATOM      1  N   ALA A   1      11.104  13.207  14.099  1.00 20.00           N  \n"
        b"ENDMDL\n"
    )
    preparer = MeekoReceptorPreparer(
        method_version="0.8.0",
        runner=RecordingRunner(),
    )

    with pytest.raises(DomainValidationError, match="multiple PDB models"):
        preparer.prepare(make_request(content=pdb))


def test_meeko_receptor_preparer_rejects_non_pdb_input():
    preparer = MeekoReceptorPreparer(
        method_version="0.8.0",
        runner=RecordingRunner(),
    )

    with pytest.raises(DomainValidationError, match="PDB"):
        preparer.prepare(make_request(source_format="cif"))


@pytest.mark.parametrize(
    "parameters",
    [
        {"unknown": 1},
        {"delete_bad_res": "yes"},
        {"charge_model": "bogus"},
        {"default_altloc": 1},
    ],
)
def test_meeko_receptor_preparer_rejects_invalid_parameters(parameters):
    preparer = MeekoReceptorPreparer(
        method_version="0.8.0",
        runner=RecordingRunner(),
    )

    with pytest.raises(DomainValidationError):
        preparer.prepare(make_request(parameters=parameters))


def test_meeko_receptor_preparer_requires_matching_method_and_version():
    preparer = MeekoReceptorPreparer(
        method_version="0.8.0",
        runner=RecordingRunner(),
    )
    wrong_method = ReceptorPreparationRequest(
        receptor_id="rec_1",
        source_format="pdb",
        content=PDB,
        protocol=ReceptorPreparationProtocol(
            method="other",
            method_version="0.8.0",
        ),
    )

    with pytest.raises(DomainValidationError, match="method"):
        preparer.prepare(wrong_method)

    with pytest.raises(DomainValidationError, match="version"):
        preparer.prepare(make_request(version="0.7.1"))


def test_meeko_receptor_preparer_surfaces_process_failure():
    preparer = MeekoReceptorPreparer(
        method_version="0.8.0",
        runner=RecordingRunner(returncode=1, stderr="template failed"),
    )

    with pytest.raises(MeekoReceptorPreparationError, match="template failed"):
        preparer.prepare(make_request())


def test_meeko_receptor_preparer_wraps_launch_errors():
    class MissingRunner:
        def __call__(self, command, *, cwd, timeout=None):
            raise FileNotFoundError("missing meeko")

    preparer = MeekoReceptorPreparer(
        method_version="0.8.0",
        runner=MissingRunner(),
    )

    with pytest.raises(MeekoReceptorPreparationError, match="launch") as error:
        preparer.prepare(make_request())

    assert isinstance(error.value.__cause__, FileNotFoundError)


def test_meeko_receptor_preparer_requires_output_file():
    preparer = MeekoReceptorPreparer(
        method_version="0.8.0",
        runner=RecordingRunner(write_output=False),
    )

    with pytest.raises(MeekoReceptorPreparationError, match="output"):
        preparer.prepare(make_request())


def test_meeko_receptor_preparer_maps_timeout():
    class TimingOutRunner:
        def __call__(self, command, *, cwd, timeout=None):
            raise TimeoutExpired(command, timeout)

    preparer = MeekoReceptorPreparer(
        method_version="0.8.0",
        runner=TimingOutRunner(),
        execution_timeout=timedelta(seconds=30),
    )

    with pytest.raises(MeekoReceptorPreparationTimeoutError, match="timed out"):
        preparer.prepare(make_request())


def test_meeko_receptor_preparer_rejects_non_positive_timeout():
    with pytest.raises(ValueError, match="execution_timeout"):
        MeekoReceptorPreparer(
            method_version="0.8.0",
            execution_timeout=timedelta(0),
        )


def test_meeko_receptor_preparer_uses_output_basename_and_write_switch():
    class BasenameRunner:
        def __init__(self):
            self.calls = []

        def __call__(self, command, *, cwd, timeout=None):
            self.calls.append(tuple(command))
            basename = Path(command[command.index("--output_basename") + 1])
            assert command[command.index("--write_pdbqt") + 1:] == []
            Path(str(basename) + ".pdbqt").write_bytes(b"ATOM PDBQT\n")
            return CompletedProcess(command, 0, "ok", "")

    runner = BasenameRunner()
    preparer = MeekoReceptorPreparer(
        method_version="0.8.0",
        runner=runner,
    )

    artifact = preparer.prepare(make_request())

    assert artifact.pdbqt == b"ATOM PDBQT\n"
    command = runner.calls[0]
    assert "--output_basename" in command
    assert "--write_pdbqt" in command


def test_meeko_receptor_preparer_keeps_legacy_runner_signature_without_timeout():
    calls = []

    class LegacyRunner:
        def __call__(self, command, *, cwd):
            calls.append((tuple(command), Path(cwd)))
            basename = Path(command[command.index("--output_basename") + 1])
            Path(str(basename) + ".pdbqt").write_bytes(b"ATOM PDBQT\n")
            return CompletedProcess(command, 0, "ok", "")

    preparer = MeekoReceptorPreparer(
        method_version="0.8.0",
        runner=LegacyRunner(),
    )

    artifact = preparer.prepare(make_request())

    assert artifact.pdbqt == b"ATOM PDBQT\n"
    assert len(calls) == 1
