from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Mapping

from .common import DomainValidationError, content_id, deep_freeze


class PoseInteractionKind(str, Enum):
    CONTACT = "contact"
    HYDROPHOBIC_CONTACT = "hydrophobic_contact"
    HYDROGEN_BOND = "hydrogen_bond"


@dataclass(frozen=True, slots=True)
class PoseInteraction:
    pose_id: str
    kind: PoseInteractionKind
    receptor_atom_serial: int
    receptor_atom_name: str
    receptor_residue_name: str
    receptor_chain: str
    receptor_residue_number: str
    ligand_atom_serial: int
    ligand_atom_name: str
    distance_angstrom: float
    method: str
    method_version: str
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.pose_id.strip():
            raise DomainValidationError("pose_id must not be blank")
        if not isinstance(self.kind, PoseInteractionKind):
            raise DomainValidationError("kind must be a PoseInteractionKind")
        if self.receptor_atom_serial < 1 or self.ligand_atom_serial < 1:
            raise DomainValidationError("atom serials must be >= 1")
        for name in (
            "receptor_atom_name",
            "receptor_residue_name",
            "receptor_residue_number",
            "ligand_atom_name",
            "method",
            "method_version",
        ):
            if not getattr(self, name).strip():
                raise DomainValidationError(f"{name} must not be blank")
        if not math.isfinite(self.distance_angstrom):
            raise DomainValidationError("interaction distance must be finite")
        if self.distance_angstrom <= 0:
            raise DomainValidationError("interaction distance must be > 0")
        object.__setattr__(self, "metadata", deep_freeze(self.metadata))

    @property
    def residue_label(self) -> str:
        chain = f"{self.receptor_chain}:" if self.receptor_chain else ""
        return (
            f"{chain}{self.receptor_residue_name}"
            f"{self.receptor_residue_number}"
        )

    @property
    def interaction_id(self) -> str:
        return content_id(
            "pose_interaction",
            {
                "pose_id": self.pose_id,
                "kind": self.kind,
                "receptor_atom_serial": self.receptor_atom_serial,
                "receptor_atom_name": self.receptor_atom_name,
                "receptor_residue_name": self.receptor_residue_name,
                "receptor_chain": self.receptor_chain,
                "receptor_residue_number": self.receptor_residue_number,
                "ligand_atom_serial": self.ligand_atom_serial,
                "ligand_atom_name": self.ligand_atom_name,
                "distance_angstrom": self.distance_angstrom,
                "method": self.method,
                "method_version": self.method_version,
                "metadata": self.metadata,
            },
        )
