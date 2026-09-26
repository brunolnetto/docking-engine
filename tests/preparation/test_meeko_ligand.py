from datetime import timedelta
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired

import pytest

from moldock.domain import DomainValidationError
from moldock.preparation import (
    LigandPreparationProtocol,
    LigandPreparationRequest,
    LigandPreparer,
    MeekoLigandPreparationError,
    MeekoLigandPreparationTimeoutError,
    MeekoLigandPreparer,
)


SDF = b"""ligand
  moldock

  0  0  0  0  0  0            999 V2000
M  END
$$$$
"""


def make_request(*, source_format="sdf", content=SDF, parameters=None, version="0.8.0"):
    protocol = LigandPreparationProtocol(
        method="meeko",
        method_version=version,
        parameters=parameters or {},
    )
    return LigandPreparationRequest(
        ligand_id="lig_1",
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
        input_path = Path(command[command.index("-i") + 1])
        assert input_path.read_bytes()
        if self.write_output:
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_bytes(b"ROOT\nENDROOT\n")
        return CompletedProcess(command, self.returncode, self.stdout, self.stderr)


def test_meeko_ligand_preparer_implements_contract():
    preparer = MeekoLigandPreparer(
        method_version="0.8.0",
        runner=RecordingRunner(),
    )

    assert isinstance(preparer, LigandPreparer)


def test_meeko_ligand_preparer_builds_cli_and_returns_artifact():
    runner = RecordingRunner()
    preparer = MeekoLigandPreparer(
        executable="mk_prepare_ligand-custom",
        method_version="0.8.0",
        runner=runner,
    )

    artifacts = preparer.prepare(
        make_request(
            parameters={
                "charge_model": "gasteiger",
                "add_index_map": True,
                "remove_smiles": True,
                "rename_atoms": True,
            }
        )
    )

    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact.ligand_id == "lig_1"
    assert artifact.pdbqt == b"ROOT\nENDROOT\n"
    assert artifact.microstate_id.startswith("microstate_")
    assert artifact.conformer_id.startswith("conformer_")

    command, cwd, timeout = runner.calls[0]
    assert command[0] == "mk_prepare_ligand-custom"
    assert timeout is None
    assert Path(command[command.index("-i") + 1]).suffix == ".sdf"
    assert Path(command[command.index("-o") + 1]).parent == cwd
    assert command[command.index("--charge_model") + 1] == "gasteiger"
    assert "--add_index_map" in command
    assert "--remove_smiles" in command
    assert "--rename_atoms" in command


def test_same_input_produces_stable_source_microstate_and_conformer_ids():
    preparer = MeekoLigandPreparer(
        method_version="0.8.0",
        runner=RecordingRunner(),
    )

    first = preparer.prepare(make_request())[0]
    second = preparer.prepare(make_request())[0]

    assert first.microstate_id == second.microstate_id
    assert first.conformer_id == second.conformer_id


@pytest.mark.parametrize("source_format", ["smi", "pdb", "xyz"])
def test_meeko_ligand_preparer_rejects_unsupported_source_format(source_format):
    preparer = MeekoLigandPreparer(
        method_version="0.8.0",
        runner=RecordingRunner(),
    )

    with pytest.raises(DomainValidationError, match="source format"):
        preparer.prepare(make_request(source_format=source_format))


def test_meeko_ligand_preparer_rejects_multimolecule_sdf_for_single_request():
    preparer = MeekoLigandPreparer(
        method_version="0.8.0",
        runner=RecordingRunner(),
    )

    with pytest.raises(DomainValidationError, match="single molecule"):
        preparer.prepare(make_request(content=SDF + SDF))


@pytest.mark.parametrize(
    "parameters",
    [
        {"unknown": 1},
        {"charge_model": "bogus"},
        {"add_index_map": "yes"},
    ],
)
def test_meeko_ligand_preparer_rejects_invalid_parameters(parameters):
    preparer = MeekoLigandPreparer(
        method_version="0.8.0",
        runner=RecordingRunner(),
    )

    with pytest.raises(DomainValidationError):
        preparer.prepare(make_request(parameters=parameters))


def test_meeko_ligand_preparer_requires_matching_method_and_version():
    preparer = MeekoLigandPreparer(
        method_version="0.8.0",
        runner=RecordingRunner(),
    )
    wrong_method = LigandPreparationRequest(
        ligand_id="lig_1",
        source_format="sdf",
        content=SDF,
        protocol=LigandPreparationProtocol(
            method="other",
            method_version="0.8.0",
        ),
    )

    with pytest.raises(DomainValidationError, match="method"):
        preparer.prepare(wrong_method)

    with pytest.raises(DomainValidationError, match="version"):
        preparer.prepare(make_request(version="0.7.1"))


def test_meeko_ligand_preparer_surfaces_process_failure():
    preparer = MeekoLigandPreparer(
        method_version="0.8.0",
        runner=RecordingRunner(returncode=2, stderr="bad molecule"),
    )

    with pytest.raises(MeekoLigandPreparationError, match="bad molecule"):
        preparer.prepare(make_request())


def test_meeko_ligand_preparer_wraps_launch_errors():
    class MissingRunner:
        def __call__(self, command, *, cwd, timeout=None):
            raise FileNotFoundError("missing meeko")

    preparer = MeekoLigandPreparer(
        method_version="0.8.0",
        runner=MissingRunner(),
    )

    with pytest.raises(MeekoLigandPreparationError, match="launch") as error:
        preparer.prepare(make_request())

    assert isinstance(error.value.__cause__, FileNotFoundError)


def test_meeko_ligand_preparer_requires_output_file():
    preparer = MeekoLigandPreparer(
        method_version="0.8.0",
        runner=RecordingRunner(write_output=False),
    )

    with pytest.raises(MeekoLigandPreparationError, match="output"):
        preparer.prepare(make_request())


def test_meeko_ligand_preparer_maps_timeout():
    class TimingOutRunner:
        def __call__(self, command, *, cwd, timeout=None):
            raise TimeoutExpired(command, timeout)

    preparer = MeekoLigandPreparer(
        method_version="0.8.0",
        runner=TimingOutRunner(),
        execution_timeout=timedelta(seconds=30),
    )

    with pytest.raises(MeekoLigandPreparationTimeoutError, match="timed out"):
        preparer.prepare(make_request())


def test_meeko_ligand_preparer_rejects_non_positive_timeout():
    with pytest.raises(ValueError, match="execution_timeout"):
        MeekoLigandPreparer(
            method_version="0.8.0",
            execution_timeout=timedelta(0),
        )
