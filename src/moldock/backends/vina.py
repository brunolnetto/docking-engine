from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from typing import Callable

from moldock.domain import (
    DockingExecutionRequest,
    DockingOutputArtifact,
    DockingResult,
)

from .base import DockingBackendError, DockingBackendTimeoutError


Runner = Callable[..., subprocess.CompletedProcess[str]]

_SUPPORTED_PARAMETERS = {
    "exhaustiveness": "--exhaustiveness",
    "num_modes": "--num_modes",
    "energy_range": "--energy_range",
    "seed": "--seed",
    "cpu": "--cpu",
    "verbosity": "--verbosity",
}


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


class VinaBackend:
    def __init__(
        self,
        *,
        executable: str = "vina",
        runner: Runner | None = None,
        execution_timeout: timedelta | None = None,
    ) -> None:
        if execution_timeout is not None and execution_timeout <= timedelta(0):
            raise ValueError("execution_timeout must be > 0")
        self._executable = executable
        self._runner = runner or _default_runner
        self._execution_timeout = execution_timeout

    def execute(self, request: DockingExecutionRequest) -> DockingResult:
        unsupported = sorted(set(request.parameters) - set(_SUPPORTED_PARAMETERS))
        if unsupported:
            raise DockingBackendError(
                f"unsupported Vina parameter(s): {', '.join(unsupported)}"
            )

        with TemporaryDirectory(prefix="moldock-vina-") as tmp:
            cwd = Path(tmp)
            receptor = cwd / "receptor.pdbqt"
            ligand = cwd / "ligand.pdbqt"
            output = cwd / "out.pdbqt"

            receptor.write_bytes(request.receptor_pdbqt)
            ligand.write_bytes(request.ligand_pdbqt)

            box = request.search_space
            command = [
                self._executable,
                "--receptor",
                str(receptor),
                "--ligand",
                str(ligand),
                "--center_x",
                str(box.center_x),
                "--center_y",
                str(box.center_y),
                "--center_z",
                str(box.center_z),
                "--size_x",
                str(box.size_x),
                "--size_y",
                str(box.size_y),
                "--size_z",
                str(box.size_z),
                "--out",
                str(output),
            ]

            for name, flag in _SUPPORTED_PARAMETERS.items():
                if name in request.parameters:
                    command.extend([flag, str(request.parameters[name])])

            try:
                timeout = (
                    self._execution_timeout.total_seconds()
                    if self._execution_timeout is not None
                    else None
                )
                process = self._runner(command, cwd=cwd, timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                duration = (
                    f" after {exc.timeout:g} seconds"
                    if exc.timeout is not None
                    else ""
                )
                raise DockingBackendTimeoutError(
                    f"Vina execution timed out{duration}"
                ) from exc
            except OSError as exc:
                raise DockingBackendError(f"failed to launch Vina: {exc}") from exc

            if process.returncode != 0:
                diagnostics = process.stderr or process.stdout or "no diagnostics"
                raise DockingBackendError(
                    f"Vina exited with code {process.returncode}: {diagnostics}"
                )

            if not output.exists():
                raise DockingBackendError(
                    "Vina did not produce the requested output file"
                )

            return DockingResult(
                artifacts=(
                    DockingOutputArtifact(
                        kind="docking_pose",
                        media_type="chemical/x-pdbqt",
                        content=output.read_bytes(),
                    ),
                ),
                stdout=process.stdout or "",
                stderr=process.stderr or "",
            )
