from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from .common import DomainValidationError, content_id


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_deep_freeze(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class DockingExperiment:
    receptor_id: str
    ligand_set_id: str
    search_space_id: str
    backend: str
    backend_version: str
    receptor_preparation_id: str
    ligand_preparation_id: str
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        required = {
            "receptor_id": self.receptor_id,
            "ligand_set_id": self.ligand_set_id,
            "search_space_id": self.search_space_id,
            "backend": self.backend,
            "backend_version": self.backend_version,
            "receptor_preparation_id": self.receptor_preparation_id,
            "ligand_preparation_id": self.ligand_preparation_id,
        }
        blank = [name for name, value in required.items() if not str(value).strip()]
        if blank:
            raise DomainValidationError(
                f"required fields must not be blank: {', '.join(blank)}"
            )

        object.__setattr__(self, "parameters", _deep_freeze(self.parameters))

    @property
    def experiment_id(self) -> str:
        return content_id(
            "exp",
            {
                "receptor_id": self.receptor_id,
                "ligand_set_id": self.ligand_set_id,
                "search_space_id": self.search_space_id,
                "backend": self.backend,
                "backend_version": self.backend_version,
                "receptor_preparation_id": self.receptor_preparation_id,
                "ligand_preparation_id": self.ligand_preparation_id,
                "parameters": self.parameters,
            },
        )
