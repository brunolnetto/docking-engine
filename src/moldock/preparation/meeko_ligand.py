from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from typing import Callable

from moldock.domain import DomainValidationError
from moldock.domain.common import content_id

from .ligand import (
    LigandPreparationArtifact,
    LigandPreparationRequest,
)


Runner = Callable[..., subprocess.CompletedProcess[str]]

_SUPPORTED_FORMATS = {"sdf", "mol2"}
_CHARGE_MODELS = {"gasteiger", "espaloma", "zero", "read", "nagl"}
_VALUE_PARAMETERS = {"charge_model": "--charge_model"}
_FLAG_PARAMETERS = {
    "add_index_map": "--add_index_map",
    "remove_smiles": "--remove_smiles",
    "rename_atoms": "--rename_atoms",
}


class MeekoLigandPreparationError(RuntimeError):
    pass


class MeekoLigandPreparationTimeoutError(MeekoLigandPreparationError):
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


class MeekoLigandPreparer:
    """Prepare one already-3D ligand record through Meeko's CLI."""

    def __init__(
        self,
        *,
        method_version: str,
        executable: str = "mk_prepare_ligand.py",
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
        request: LigandPreparationRequest,
    ) -> tuple[LigandPreparationArtifact, ...]:
        source_format = request.source_format.strip().lower().lstrip(".")
        self._validate_request(request, source_format)

        with TemporaryDirectory(prefix="moldock-meeko-ligand-") as tmp:
            cwd = Path(tmp)
            source = cwd / f"ligand.{source_format}"
            output = cwd / "ligand.pdbqt"
            source.write_bytes(request.content)

            command = [
                self._executable,
                "-i",
                str(source),
                "-o",
                str(output),
            ]
            self._append_parameters(command, request.protocol.parameters)

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
                raise MeekoLigandPreparationTimeoutError(
                    "Meeko ligand preparation timed out"
                ) from exc
            except OSError as exc:
                raise MeekoLigandPreparationError(
                    f"failed to launch Meeko ligand preparation: {exc}"
                ) from exc

            if process.returncode != 0:
                diagnostics = process.stderr or process.stdout or "no diagnostics"
                raise MeekoLigandPreparationError(
                    f"Meeko ligand preparation exited with code "
                    f"{process.returncode}: {diagnostics}"
                )
            if not output.is_file():
                raise MeekoLigandPreparationError(
                    "Meeko ligand preparation did not produce an output PDBQT"
                )

            pdbqt = output.read_bytes()
            if not pdbqt:
                raise MeekoLigandPreparationError(
                    "Meeko ligand preparation produced an empty output PDBQT"
                )

        microstate_id = content_id(
            "microstate",
            {
                "ligand_id": request.ligand_id,
                "source_sha256": request.source_sha256,
            },
        )
        conformer_id = content_id(
            "conformer",
            {
                "microstate_id": microstate_id,
                "source_sha256": request.source_sha256,
            },
        )
        return (
            LigandPreparationArtifact(
                ligand_id=request.ligand_id,
                preparation_id=request.protocol.preparation_id,
                microstate_id=microstate_id,
                conformer_id=conformer_id,
                pdbqt=pdbqt,
            ),
        )

    def _validate_request(
        self,
        request: LigandPreparationRequest,
        source_format: str,
    ) -> None:
        if request.protocol.method.strip().lower() != "meeko":
            raise DomainValidationError(
                "ligand preparation method must be meeko"
            )
        if request.protocol.method_version != self._method_version:
            raise DomainValidationError(
                "ligand preparation version does not match Meeko adapter"
            )
        if source_format not in _SUPPORTED_FORMATS:
            raise DomainValidationError(
                f"unsupported Meeko ligand source format: {source_format}"
            )
        if (
            source_format == "sdf"
            and self._count_record_lines(request.content, b"$$$$") > 1
        ):
            raise DomainValidationError(
                "MeekoLigandPreparer accepts a single molecule per SDF request"
            )
        if (
            source_format == "mol2"
            and self._count_record_lines(
                request.content,
                b"@<TRIPOS>MOLECULE",
            )
            > 1
        ):
            raise DomainValidationError(
                "MeekoLigandPreparer accepts a single molecule per MOL2 request"
            )

    @staticmethod
    def _count_record_lines(content: bytes, marker: bytes) -> int:
        marker = marker.upper()
        return sum(
            line.strip().upper() == marker
            for line in content.splitlines()
        )

    @staticmethod
    def _append_parameters(command: list[str], parameters) -> None:
        unsupported = sorted(
            set(parameters) - set(_VALUE_PARAMETERS) - set(_FLAG_PARAMETERS)
        )
        if unsupported:
            raise DomainValidationError(
                "unsupported Meeko ligand parameter(s): "
                + ", ".join(unsupported)
            )

        if "charge_model" in parameters:
            value = parameters["charge_model"]
            if value not in _CHARGE_MODELS:
                raise DomainValidationError(
                    f"unsupported Meeko charge_model: {value}"
                )
            command.extend([_VALUE_PARAMETERS["charge_model"], str(value)])

        for name, flag in _FLAG_PARAMETERS.items():
            if name not in parameters:
                continue
            value = parameters[name]
            if not isinstance(value, bool):
                raise DomainValidationError(
                    f"Meeko ligand parameter {name} must be boolean"
                )
            if value:
                command.append(flag)
