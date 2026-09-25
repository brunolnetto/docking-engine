from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .common import DomainValidationError, content_id, deep_freeze


@dataclass(frozen=True, slots=True)
class DockingProtocol:
    """Content-addressed scientific protocol for a docking calculation."""

    backend: str
    backend_version: str
    receptor_preparation_id: str
    ligand_preparation_id: str
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        required = {
            "backend": self.backend,
            "backend_version": self.backend_version,
            "receptor_preparation_id": self.receptor_preparation_id,
            "ligand_preparation_id": self.ligand_preparation_id,
        }
        blank = [
            name
            for name, value in required.items()
            if not str(value).strip()
        ]
        if blank:
            raise DomainValidationError(
                "required fields must not be blank: "
                + ", ".join(blank)
            )

        object.__setattr__(
            self,
            "parameters",
            deep_freeze(self.parameters),
        )

    @property
    def protocol_id(self) -> str:
        return content_id(
            "protocol",
            {
                "backend": self.backend,
                "backend_version": self.backend_version,
                "receptor_preparation_id": self.receptor_preparation_id,
                "ligand_preparation_id": self.ligand_preparation_id,
                "parameters": self.parameters,
            },
        )
