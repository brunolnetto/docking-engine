from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Mapping

from .common import DomainValidationError, content_id, deep_freeze


class PoseInteractionKind(str, Enum):
    CONTACT = "contact"
    HYDROPHOBIC = "hydrophobic"
    HYDROGEN_BOND = "hydrogen_bond"
    SALT_BRIDGE = "salt_bridge"


@dataclass(frozen=True, slots=True)
class PoseInteraction:
    pose_id: str
    kind: PoseInteractionKind
    receptor_chain_id: str
    receptor_residue_name: str
    receptor_residue_number: str
    receptor_atom_name: str
    ligand_atom_name: str
    distance_angstrom: float
    method: str
    method_version: str
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "pose_id",
            "receptor_chain_id",
            "receptor_residue_name",
            "receptor_residue_number",
            "receptor_atom_name",
            "ligand_atom_name",
            "method",
            "method_version",
        ):
            if not getattr(self, name).strip():
                raise DomainValidationError(f"{name} must not be blank")
        if not isinstance(self.kind, PoseInteractionKind):
            raise DomainValidationError("kind must be a PoseInteractionKind")
        if (
            not math.isfinite(self.distance_angstrom)
            or self.distance_angstrom <= 0
        ):
            raise DomainValidationError(
                "distance_angstrom must be finite and > 0"
            )
        object.__setattr__(self, "metadata", deep_freeze(self.metadata))

    @property
    def receptor_residue_id(self) -> str:
        return (
            f"{self.receptor_chain_id}:"
            f"{self.receptor_residue_name}"
            f"{self.receptor_residue_number}"
        )

    @property
    def interaction_id(self) -> str:
        return content_id(
            "pose_interaction",
            {
                "pose_id": self.pose_id,
                "kind": self.kind,
                "receptor_chain_id": self.receptor_chain_id,
                "receptor_residue_name": self.receptor_residue_name,
                "receptor_residue_number": self.receptor_residue_number,
                "receptor_atom_name": self.receptor_atom_name,
                "ligand_atom_name": self.ligand_atom_name,
                "distance_angstrom": self.distance_angstrom,
                "method": self.method,
                "method_version": self.method_version,
                "metadata": self.metadata,
            },
        )
