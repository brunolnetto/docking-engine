from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


Decision = Literal[
    "preserve",
    "safe_remove_candidate",
    "manual_template_required",
]

# Conservative benchmark policy. These are not automatic deletions.
WATER_RESIDUES = frozenset({"HOH", "WAT", "DOD"})
COMMON_ADDITIVES = frozenset({"GOL", "EDO", "PEG", "MPD"})
FUNCTIONAL_COFACTORS = frozenset({"HEM", "HEC", "FAD", "FMN", "NAD", "NAP"})
METAL_IONS = frozenset({"K", "NA", "CA", "MG", "MN", "FE", "CO", "NI", "CU", "ZN"})


@dataclass(frozen=True, slots=True)
class ResidueEvidence:
    residue_name: str
    chain_id: str
    residue_number: str
    record_type: str


@dataclass(frozen=True, slots=True)
class PreparationDecision:
    residue: ResidueEvidence
    decision: Decision
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "residue": asdict(self.residue),
            "decision": self.decision,
            "reason": self.reason,
        }


def pdb_hetero_residues(content: bytes) -> tuple[ResidueEvidence, ...]:
    residues: dict[tuple[str, str, str], ResidueEvidence] = {}
    for line in content.decode("utf-8", errors="replace").splitlines():
        if not line.startswith("HETATM"):
            continue
        name = line[17:20].strip().upper()
        chain = line[21:22].strip() or "_"
        number = line[22:27].strip()
        if not name:
            continue
        key = (name, chain, number)
        residues[key] = ResidueEvidence(name, chain, number, "HETATM")
    return tuple(residues[key] for key in sorted(residues))


def classify_residue(residue: ResidueEvidence) -> PreparationDecision:
    name = residue.residue_name
    if name in WATER_RESIDUES or name in COMMON_ADDITIVES:
        return PreparationDecision(
            residue,
            "safe_remove_candidate",
            "common crystallographic solvent/additive; removal requires explicit policy",
        )
    if name in FUNCTIONAL_COFACTORS:
        return PreparationDecision(
            residue,
            "preserve",
            "known functional cofactor; never delete merely to make preparation pass",
        )
    if name in METAL_IONS:
        return PreparationDecision(
            residue,
            "preserve",
            "metal/ion may be structural or catalytic; retain unless case evidence justifies removal",
        )
    return PreparationDecision(
        residue,
        "manual_template_required",
        "unclassified hetero residue; require an explicit template or case-specific disposition",
    )


def preparation_decisions(content: bytes) -> tuple[PreparationDecision, ...]:
    return tuple(classify_residue(residue) for residue in pdb_hetero_residues(content))
