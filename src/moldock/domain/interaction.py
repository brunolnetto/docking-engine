from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Mapping

from .common import DomainValidationError, content_id, deep_freeze


class InteractionKind(str, Enum):
    RESIDUE_CONTACT = "residue_contact"
    HYDROPHOBIC_CONTACT = "hydrophobic_contact"
    HYDROGEN_BOND = "hydrogen_bond"


@dataclass(frozen=True, slots=True)
class PoseInteraction:
    pose_id: str
    kind: InteractionKind
    receptor_residue: str
    receptor_atom: str
    ligand_atom: str
    distance_angstrom: float
    method: str
    method_version: str
    angle_degrees: float | None = None
    protein_is_donor: bool | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.pose_id.strip():
            raise DomainValidationError("pose_id must not be blank")
        if not isinstance(self.kind, InteractionKind):
            raise DomainValidationError("kind must be an InteractionKind")
        for name in (
            "receptor_residue",
            "receptor_atom",
            "ligand_atom",
            "method",
            "method_version",
        ):
            if not getattr(self, name).strip():
                raise DomainValidationError(f"{name} must not be blank")
        if (
            not math.isfinite(self.distance_angstrom)
            or self.distance_angstrom < 0
        ):
            raise DomainValidationError(
                "distance_angstrom must be finite and >= 0"
            )
        if self.angle_degrees is not None and (
            not math.isfinite(self.angle_degrees)
            or not 0 <= self.angle_degrees <= 180
        ):
            raise DomainValidationError(
                "angle_degrees must be finite and between 0 and 180"
            )
        object.__setattr__(self, "metadata", deep_freeze(self.metadata))

    @property
    def interaction_id(self) -> str:
        return content_id(
            "pose_interaction",
            {
                "pose_id": self.pose_id,
                "kind": self.kind,
                "receptor_residue": self.receptor_residue,
                "receptor_atom": self.receptor_atom,
                "ligand_atom": self.ligand_atom,
                "distance_angstrom": self.distance_angstrom,
                "angle_degrees": self.angle_degrees,
                "protein_is_donor": self.protein_is_donor,
                "method": self.method,
                "method_version": self.method_version,
                "metadata": self.metadata,
            },
        )
