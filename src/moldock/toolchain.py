from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
import re
import shutil
import subprocess
from typing import Callable, Protocol, runtime_checkable

from moldock.domain import DomainValidationError
from moldock.domain.common import content_id


VersionRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]
Which = Callable[[str], str | None]
PackageVersion = Callable[[str], str]


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
        expected_vina_version: str,
        expected_ligand_method: str,
        expected_ligand_version: str,
        expected_receptor_method: str,
        expected_receptor_version: str,
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


class VinaMeekoToolchainPreflight:
    """Verify the concrete local Vina/Meeko toolchain before execution."""

    _VERSION_PATTERN = re.compile(
        r"(?:AutoDock\s+Vina\s+)?v?(\d+\.\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )

    def __init__(
        self,
        *,
        vina_executable: str = "vina",
        meeko_ligand_executable: str = "mk_prepare_ligand.py",
        meeko_receptor_executable: str = "mk_prepare_receptor.py",
        runner: VersionRunner | None = None,
        which: Which | None = None,
        package_version: PackageVersion | None = None,
    ) -> None:
        self._vina_executable = vina_executable
        self._meeko_ligand_executable = meeko_ligand_executable
        self._meeko_receptor_executable = meeko_receptor_executable
        self._runner = runner or _default_runner
        self._which = which or shutil.which
        self._package_version = (
            package_version or metadata.version
        )

    def inspect(
        self,
        *,
        expected_vina_version: str,
        expected_ligand_method: str,
        expected_ligand_version: str,
        expected_receptor_method: str,
        expected_receptor_version: str,
    ) -> ToolchainSnapshot:
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

        vina_path = self._resolve(self._vina_executable)
        ligand_path = self._resolve(
            self._meeko_ligand_executable
        )
        receptor_path = self._resolve(
            self._meeko_receptor_executable
        )

        process = self._runner([vina_path, "--version"])
        if process.returncode != 0:
            raise DomainValidationError(
                "Vina version probe failed"
            )
        match = self._VERSION_PATTERN.search(
            process.stdout or ""
        )
        if match is None:
            raise DomainValidationError(
                "could not parse Vina version"
            )
        vina_version = match.group(1)

        try:
            meeko_version = self._package_version("meeko")
        except metadata.PackageNotFoundError as exc:
            raise DomainValidationError(
                "Meeko package is not installed"
            ) from exc

        if vina_version != expected_vina_version:
            raise DomainValidationError(
                "Vina version mismatch: "
                f"expected {expected_vina_version}, got {vina_version}"
            )
        if meeko_version != expected_ligand_version:
            raise DomainValidationError(
                "Meeko ligand version mismatch: "
                f"expected {expected_ligand_version}, got {meeko_version}"
            )
        if meeko_version != expected_receptor_version:
            raise DomainValidationError(
                "Meeko receptor version mismatch: "
                f"expected {expected_receptor_version}, got {meeko_version}"
            )

        return ToolchainSnapshot(
            vina=ExecutableInfo(
                name="vina",
                executable=self._vina_executable,
                resolved_path=vina_path,
                version=vina_version,
            ),
            meeko_ligand=ExecutableInfo(
                name="meeko_ligand",
                executable=self._meeko_ligand_executable,
                resolved_path=ligand_path,
                version=meeko_version,
            ),
            meeko_receptor=ExecutableInfo(
                name="meeko_receptor",
                executable=self._meeko_receptor_executable,
                resolved_path=receptor_path,
                version=meeko_version,
            ),
        )

    def _resolve(self, executable: str) -> str:
        resolved = self._which(executable)
        if resolved is None:
            raise DomainValidationError(
                f"required executable not found: {executable}"
            )
        return resolved
