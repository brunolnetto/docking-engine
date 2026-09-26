from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from typing import Callable

from moldock.domain import DomainValidationError

from .receptor import (
    ReceptorPreparationArtifact,
    ReceptorPreparationRequest,
)


Runner = Callable[..., subprocess.CompletedProcess[str]]

_CHARGE_MODELS = {"gasteiger", "espaloma", "nagl", "zero", "read"}
_STRING_PARAMETERS = {
    "default_altloc": "--default_altloc",
    "wanted_altloc": "--wanted_altloc",
    "set_template": "--set_template",
    "delete_residues": "--delete_residues",
    "blunt_ends": "--blunt_ends",
    "charge_model": "--charge_model",
}
_FLAG_PARAMETERS = {
    "delete_bad_res": "--delete_bad_res",
    "compute_charges": "--compute_charges",
    "forgive_extra_bonds": "--forgive_extra_bonds",
}


class MeekoReceptorPreparationError(RuntimeError):
    pass


class MeekoReceptorPreparationTimeoutError(MeekoReceptorPreparationError):
    pass


def _default_runner(
    command: list[str],
    *,
    cwd: Path,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


class MeekoReceptorPreparer:
    """Prepare a single rigid PDB receptor through Meeko's CLI."""

    def __init__(
        self,
        *,
        method_version: str,
        executable: str = "mk_prepare_receptor.py",
        runner: Runner | None = None,
        execution_timeout: timedelta | None = None,
    ) -> None:
        if not method_version.strip():
            raise ValueError("method_version must not be blank")
        if execution_timeout is not None and execution_timeout <= timedelta(0):
            raise ValueError("execution_timeout must be > 0")
        self._method_version = method_version
        self._executable = executable
        self._runner = runner or _default_runner
        self._execution_timeout = execution_timeout

    @property
    def executable(self) -> str:
        return self._executable

    def prepare(
        self,
        request: ReceptorPreparationRequest,
    ) -> ReceptorPreparationArtifact:
        self._validate_request(request)
        model_id, chain_ids = self._pdb_identity(request.content)

        with TemporaryDirectory(prefix="moldock-meeko-receptor-") as tmp:
            cwd = Path(tmp)
            source = cwd / "receptor.pdb"
            output_basename = cwd / "receptor"
            output = cwd / "receptor.pdbqt"
            source.write_bytes(request.content)

            command = [
                self._executable,
                "--read_pdb",
                str(source),
                "--output_basename",
                str(output_basename),
            ]
            self._append_parameters(command, request.protocol.parameters)
            command.append("--write_pdbqt")

            try:
                if self._execution_timeout is None:
                    process = self._runner(command, cwd=cwd)
                else:
                    process = self._runner(
                        command,
                        cwd=cwd,
                        timeout=self._execution_timeout.total_seconds(),
                    )
            except subprocess.TimeoutExpired as exc:
                raise MeekoReceptorPreparationTimeoutError(
                    "Meeko receptor preparation timed out"
                ) from exc
            except OSError as exc:
                raise MeekoReceptorPreparationError(
                    f"failed to launch Meeko receptor preparation: {exc}"
                ) from exc

            if process.returncode != 0:
                diagnostics = process.stderr or process.stdout or "no diagnostics"
                raise MeekoReceptorPreparationError(
                    f"Meeko receptor preparation exited with code "
                    f"{process.returncode}: {diagnostics}"
                )
            if not output.is_file():
                raise MeekoReceptorPreparationError(
                    "Meeko receptor preparation did not produce an output PDBQT"
                )

            pdbqt = output.read_bytes()
            if not pdbqt:
                raise MeekoReceptorPreparationError(
                    "Meeko receptor preparation produced an empty output PDBQT"
                )

        return ReceptorPreparationArtifact(
            receptor_id=request.receptor_id,
            preparation_id=request.protocol.preparation_id,
            model_id=model_id,
            chain_ids=chain_ids,
            pdbqt=pdbqt,
        )

    def _validate_request(self, request: ReceptorPreparationRequest) -> None:
        if request.protocol.method.strip().lower() != "meeko":
            raise DomainValidationError(
                "receptor preparation method must be meeko"
            )
        if request.protocol.method_version != self._method_version:
            raise DomainValidationError(
                "receptor preparation version does not match Meeko adapter"
            )
        if request.source_format.strip().lower().lstrip(".") != "pdb":
            raise DomainValidationError(
                "MeekoReceptorPreparer currently accepts PDB input only"
            )

    @staticmethod
    def _pdb_identity(content: bytes) -> tuple[str, tuple[str, ...]]:
        text = content.decode("utf-8", errors="replace")
        model_records: list[str] = []
        chains: set[str] = set()

        for line in text.splitlines():
            if line.startswith("MODEL"):
                serial = line[5:].strip()
                model_records.append(serial or "1")
            if line.startswith(("ATOM  ", "HETATM")):
                chain = line[21:22].strip() if len(line) >= 22 else ""
                chains.add(chain or "_")

        if len(model_records) > 1:
            raise DomainValidationError(
                "multiple PDB models are not supported by MeekoReceptorPreparer"
            )
        if not chains:
            raise DomainValidationError(
                "PDB receptor must contain at least one ATOM or HETATM record"
            )

        model_serial = model_records[0] if model_records else "1"
        return f"model_{model_serial}", tuple(sorted(chains))

    @staticmethod
    def _append_parameters(command: list[str], parameters) -> None:
        unsupported = sorted(
            set(parameters) - set(_STRING_PARAMETERS) - set(_FLAG_PARAMETERS)
        )
        if unsupported:
            raise DomainValidationError(
                "unsupported Meeko receptor parameter(s): "
                + ", ".join(unsupported)
            )

        for name, flag in _STRING_PARAMETERS.items():
            if name not in parameters:
                continue
            value = parameters[name]
            if not isinstance(value, str) or not value.strip():
                raise DomainValidationError(
                    f"Meeko receptor parameter {name} must be a non-blank string"
                )
            if name == "charge_model" and value not in _CHARGE_MODELS:
                raise DomainValidationError(
                    f"unsupported Meeko charge_model: {value}"
                )
            command.extend([flag, value])

        for name, flag in _FLAG_PARAMETERS.items():
            if name not in parameters:
                continue
            value = parameters[name]
            if not isinstance(value, bool):
                raise DomainValidationError(
                    f"Meeko receptor parameter {name} must be boolean"
                )
            if value:
                command.append(flag)
