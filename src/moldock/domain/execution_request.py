from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .common import DomainValidationError, deep_freeze
from .search_space import DockingBox
from .task import DockingTask


@dataclass(frozen=True, slots=True)
class DockingExecutionRequest:
    task: DockingTask
    receptor_pdbqt: bytes
    ligand_pdbqt: bytes
    search_space: DockingBox
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.receptor_pdbqt, bytes):
            raise DomainValidationError("receptor_pdbqt must be bytes")
        if not isinstance(self.ligand_pdbqt, bytes):
            raise DomainValidationError("ligand_pdbqt must be bytes")
        if self.search_space.search_space_id != self.task.search_space_id:
            raise DomainValidationError("search space does not match task")

        frozen_parameters = deep_freeze(self.parameters)
        if not isinstance(frozen_parameters, Mapping):
            raise DomainValidationError("parameters must be a mapping")
        object.__setattr__(self, "parameters", frozen_parameters)
