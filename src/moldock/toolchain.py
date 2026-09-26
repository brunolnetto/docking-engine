from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shlex
import shutil
import subprocess
from typing import Callable, Protocol, runtime_checkable

from moldock.domain import DomainValidationError
from moldock.domain.common import content_id


VersionRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]
Which = Callable[[str], str | None]
InterpreterResolver = Callable[[str], str | None]


@dataclass(frozen=True, slots=True)
class ExecutableInfo:
    name: str
    executable: str
    resolved_path: str
    version: str

    def __post_init__(self) -> None:
        for field_name in (
            "name",
            "executable",
            "resolved_path",
            "version",
        ):
            if not getattr(self, field_name).strip():
                raise DomainValidationError(
                    f"{field_name} must not be blank"
                )


@dataclass(frozen=True, slots=True)
class ToolchainSnapshot:
    vina: ExecutableInfo
    meeko_ligand: ExecutableInfo
    meeko_receptor: ExecutableInfo

    @property
    def snapshot_id(self) -> str:
        return content_id(
            "toolchain",
            {
                "vina": self.vina,
                "meeko_ligand": self.meeko_ligand,
                "meeko_receptor": self.meeko_receptor,
            },
        )


@runtime_checkable
class ToolchainPreflight(Protocol):
    def inspect(
        self,
        *,
        expected_backend: str,
        expected_vina_version: str,
        expected_ligand_method: str,
        expected_ligand_version: str,
        expected_receptor_method: str,
        expected_receptor_version: str,
        vina_executable: str | None,
        ligand_executable: str | None,
        receptor_executable: str | None,
    ) -> ToolchainSnapshot: ...


def _default_runner(
    command: list[str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )


def _default_interpreter_for_executable(
    executable_path: str,
) -> str | None:
    try:
        first_line = Path(executable_path).read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines()[0]
    except (OSError, IndexError):
        return None

    if not first_line.startswith("#!"):
        return None
    tokens = shlex.split(first_line[2:].strip())
    if not tokens:
        return None

    interpreter = tokens[0]
    if Path(interpreter).name == "env":
        if len(tokens) < 2:
            return None
        return shutil.which(tokens[1])
    return interpreter


class VinaMeekoToolchainPreflight:
    """Verify the exact local executables used by Vina/Meeko adapters."""

    _VERSION_PATTERN = re.compile(
        r"(?:AutoDock\s+Vina\s+)?v?(\d+\.\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )
    _MEEKO_VERSION_CODE = (
        "from importlib.metadata import version;"
        "print(version('meeko'))"
    )

    def __init__(
        self,
        *,
        runner: VersionRunner | None = None,
        which: Which | None = None,
        interpreter_for_executable: InterpreterResolver | None = None,
    ) -> None:
        self._runner = runner or _default_runner
        self._which = which or shutil.which
        self._interpreter_for_executable = (
            interpreter_for_executable
            or _default_interpreter_for_executable
        )

    def inspect(
        self,
        *,
        expected_backend: str,
        expected_vina_version: str,
        expected_ligand_method: str,
        expected_ligand_version: str,
        expected_receptor_method: str,
        expected_receptor_version: str,
        vina_executable: str | None,
        ligand_executable: str | None,
        receptor_executable: str | None,
    ) -> ToolchainSnapshot:
        if expected_backend.strip().lower() != "vina":
            raise DomainValidationError(
                "backend must be vina for VinaMeekoToolchainPreflight"
            )
        if expected_ligand_method.strip().lower() != "meeko":
            raise DomainValidationError(
                "ligand preparation method must be meeko for "
                "VinaMeekoToolchainPreflight"
            )
        if expected_receptor_method.strip().lower() != "meeko":
            raise DomainValidationError(
                "receptor preparation method must be meeko for "
                "VinaMeekoToolchainPreflight"
            )

        vina_path = self._resolve_actual(
            "Vina", vina_executable
        )
        ligand_path = self._resolve_actual(
            "Meeko ligand", ligand_executable
        )
        receptor_path = self._resolve_actual(
            "Meeko receptor", receptor_executable
        )

        vina_version = self._probe_vina_version(vina_path)
        ligand_version = self._probe_meeko_version(
            ligand_path
        )
        receptor_version = self._probe_meeko_version(
            receptor_path
        )

        if vina_version != expected_vina_version:
            raise DomainValidationError(
                "Vina version mismatch: "
                f"expected {expected_vina_version}, got {vina_version}"
            )
        if ligand_version != expected_ligand_version:
            raise DomainValidationError(
                "Meeko ligand version mismatch: "
                f"expected {expected_ligand_version}, got {ligand_version}"
            )
        if receptor_version != expected_receptor_version:
            raise DomainValidationError(
                "Meeko receptor version mismatch: "
                f"expected {expected_receptor_version}, got {receptor_version}"
            )

        return ToolchainSnapshot(
            vina=ExecutableInfo(
                name="vina",
                executable=vina_executable,
                resolved_path=vina_path,
                version=vina_version,
            ),
            meeko_ligand=ExecutableInfo(
                name="meeko_ligand",
                executable=ligand_executable,
                resolved_path=ligand_path,
                version=ligand_version,
            ),
            meeko_receptor=ExecutableInfo(
                name="meeko_receptor",
                executable=receptor_executable,
                resolved_path=receptor_path,
                version=receptor_version,
            ),
        )

    def _resolve_actual(
        self,
        label: str,
        executable: str | None,
    ) -> str:
        if executable is None or not executable.strip():
            raise DomainValidationError(
                f"{label} adapter does not expose its executable"
            )
        resolved = self._which(executable)
        if resolved is None:
            raise DomainValidationError(
                f"required executable not found: {executable}"
            )
        return resolved

    def _probe_vina_version(self, path: str) -> str:
        process = self._runner([path, "--version"])
        if process.returncode != 0:
            raise DomainValidationError(
                "Vina version probe failed"
            )
        output = (process.stdout or "") + "\n" + (
            process.stderr or ""
        )
        match = self._VERSION_PATTERN.search(output)
        if match is None:
            raise DomainValidationError(
                "could not parse Vina version"
            )
        return match.group(1)

    def _probe_meeko_version(self, path: str) -> str:
        interpreter = self._interpreter_for_executable(path)
        if interpreter is None:
            raise DomainValidationError(
                "could not determine Python environment for "
                f"Meeko executable: {path}"
            )
        process = self._runner(
            [
                interpreter,
                "-c",
                self._MEEKO_VERSION_CODE,
            ]
        )
        if process.returncode != 0:
            raise DomainValidationError(
                f"Meeko version probe failed for: {path}"
            )
        version = (process.stdout or "").strip()
        if not version:
            raise DomainValidationError(
                f"Meeko version probe returned no version for: {path}"
            )
        return version
