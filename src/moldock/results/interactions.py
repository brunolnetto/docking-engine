from __future__ import annotations

from dataclasses import dataclass
import math
import re

from moldock.domain import (
    DomainValidationError,
    Pose,
    PoseInteraction,
    PoseInteractionKind,
)

from .repository import ScientificResultRepository


_MODEL = re.compile(rb"^MODEL\s+(\d+)\s*$")
_ACCEPTOR_TYPES = frozenset({"NA", "OA", "SA"})
_HYDROPHOBIC_TYPES = frozenset({"C", "A"})
_POLAR_H_TYPES = frozenset({"HD", "HS"})


@dataclass(frozen=True, slots=True)
class PdbqtAtom:
    serial: int
    name: str
    residue_name: str
    chain: str
    residue_number: str
    x: float
    y: float
    z: float
    atom_type: str

    @property
    def is_hydrogen(self) -> bool:
        return self.atom_type.upper().startswith("H")

    @property
    def point(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


@dataclass(frozen=True, slots=True)
class PdbqtStructure:
    atoms: tuple[PdbqtAtom, ...]

    @property
    def heavy_atoms(self) -> tuple[PdbqtAtom, ...]:
        return tuple(atom for atom in self.atoms if not atom.is_hydrogen)


class PdbqtInteractionParser:
    def parse_single(self, content: bytes) -> PdbqtStructure:
        atoms = tuple(self._atoms(content.splitlines()))
        if not atoms:
            raise DomainValidationError("PDBQT structure has no atoms")
        return PdbqtStructure(atoms=atoms)

    def parse_models(self, content: bytes) -> dict[int, PdbqtStructure]:
        models: dict[int, PdbqtStructure] = {}
        model_index: int | None = None
        lines: list[bytes] = []
        for raw in content.splitlines():
            match = _MODEL.match(raw)
            if match is not None:
                if model_index is not None:
                    raise DomainValidationError(
                        f"unterminated MODEL {model_index}"
                    )
                model_index = int(match.group(1))
                lines = []
                continue
            if raw == b"ENDMDL":
                if model_index is not None:
                    atoms = tuple(self._atoms(lines))
                    if not atoms:
                        raise DomainValidationError(
                            f"MODEL {model_index} has no atoms"
                        )
                    models[model_index] = PdbqtStructure(atoms=atoms)
                model_index = None
                lines = []
                continue
            if model_index is not None:
                lines.append(raw)
        if model_index is not None:
            raise DomainValidationError(f"unterminated MODEL {model_index}")
        if not models:
            raise DomainValidationError(
                "no MODEL blocks found for interaction analysis"
            )
        return models

    @staticmethod
    def _atoms(lines) -> list[PdbqtAtom]:
        atoms: list[PdbqtAtom] = []
        for raw in lines:
            if not raw.startswith((b"ATOM", b"HETATM")):
                continue
            text = raw.decode("ascii")
            fields = text.split()
            try:
                atom = PdbqtAtom(
                    serial=int(text[6:11]),
                    name=text[12:16].strip(),
                    residue_name=text[17:20].strip() or "UNK",
                    chain=text[21:22].strip(),
                    residue_number=text[22:27].strip() or "0",
                    x=float(text[30:38]),
                    y=float(text[38:46]),
                    z=float(text[46:54]),
                    atom_type=fields[-1],
                )
            except (ValueError, IndexError) as exc:
                raise DomainValidationError(
                    "invalid PDBQT atom record for interaction analysis"
                ) from exc
            atoms.append(atom)
        return atoms


def _distance(left: PdbqtAtom, right: PdbqtAtom) -> float:
    return math.dist(left.point, right.point)


def _angle_degrees(
    first: PdbqtAtom,
    vertex: PdbqtAtom,
    last: PdbqtAtom,
) -> float:
    a = (
        first.x - vertex.x,
        first.y - vertex.y,
        first.z - vertex.z,
    )
    b = (
        last.x - vertex.x,
        last.y - vertex.y,
        last.z - vertex.z,
    )
    norm_a = math.sqrt(sum(value * value for value in a))
    norm_b = math.sqrt(sum(value * value for value in b))
    if norm_a == 0 or norm_b == 0:
        raise DomainValidationError("cannot compute angle for coincident atoms")
    cosine = sum(x * y for x, y in zip(a, b, strict=True)) / (
        norm_a * norm_b
    )
    cosine = max(-1.0, min(1.0, cosine))
    return math.degrees(math.acos(cosine))


class PoseInteractionAnalyzer:
    """Persist deterministic receptor-ligand geometric interactions."""

    METHOD_VERSION = "1"

    def __init__(
        self,
        *,
        repository: ScientificResultRepository,
        parser: PdbqtInteractionParser | None = None,
        contact_cutoff_angstrom: float = 4.0,
        hydrophobic_cutoff_angstrom: float = 4.5,
        hydrogen_bond_da_cutoff_angstrom: float = 3.5,
        hydrogen_bond_ha_cutoff_angstrom: float = 2.5,
        hydrogen_bond_angle_degrees: float = 120.0,
        donor_hydrogen_bond_cutoff_angstrom: float = 1.3,
    ) -> None:
        cutoffs = (
            contact_cutoff_angstrom,
            hydrophobic_cutoff_angstrom,
            hydrogen_bond_da_cutoff_angstrom,
            hydrogen_bond_ha_cutoff_angstrom,
            donor_hydrogen_bond_cutoff_angstrom,
        )
        if any(value <= 0 for value in cutoffs):
            raise DomainValidationError(
                "interaction distance cutoffs must be > 0"
            )
        if not 0 < hydrogen_bond_angle_degrees <= 180:
            raise DomainValidationError(
                "hydrogen bond angle cutoff must be in (0, 180]"
            )
        self._repository = repository
        self._parser = parser or PdbqtInteractionParser()
        self._contact_cutoff = contact_cutoff_angstrom
        self._hydrophobic_cutoff = hydrophobic_cutoff_angstrom
        self._hbond_da_cutoff = hydrogen_bond_da_cutoff_angstrom
        self._hbond_ha_cutoff = hydrogen_bond_ha_cutoff_angstrom
        self._hbond_angle = hydrogen_bond_angle_degrees
        self._donor_h_cutoff = donor_hydrogen_bond_cutoff_angstrom

    def analyze(
        self,
        *,
        attempt_id: str,
        receptor_pdbqt: bytes,
        pose_pdbqt: bytes,
    ) -> None:
        poses = self._repository.list_poses_for_attempt(attempt_id)
        if not poses:
            return
        receptor = self._parser.parse_single(receptor_pdbqt)
        models = self._parser.parse_models(pose_pdbqt)
        for pose in poses:
            ligand = models.get(pose.model_index)
            if ligand is None:
                raise DomainValidationError(
                    "interaction geometry does not match persisted pose models"
                )
            self._persist_contacts(pose, receptor, ligand)
            self._persist_hydrogen_bonds(pose, receptor, ligand)

    def _persist_contacts(
        self,
        pose: Pose,
        receptor: PdbqtStructure,
        ligand: PdbqtStructure,
    ) -> None:
        for rec in receptor.heavy_atoms:
            for lig in ligand.heavy_atoms:
                distance = _distance(rec, lig)
                if distance <= self._contact_cutoff:
                    self._register(
                        pose,
                        PoseInteractionKind.CONTACT,
                        rec,
                        lig,
                        distance,
                        metadata={
                            "cutoff_angstrom": self._contact_cutoff,
                        },
                    )
                if (
                    rec.atom_type in _HYDROPHOBIC_TYPES
                    and lig.atom_type in _HYDROPHOBIC_TYPES
                    and distance <= self._hydrophobic_cutoff
                ):
                    self._register(
                        pose,
                        PoseInteractionKind.HYDROPHOBIC_CONTACT,
                        rec,
                        lig,
                        distance,
                        metadata={
                            "cutoff_angstrom": self._hydrophobic_cutoff,
                            "receptor_atom_type": rec.atom_type,
                            "ligand_atom_type": lig.atom_type,
                        },
                    )

    def _persist_hydrogen_bonds(
        self,
        pose: Pose,
        receptor: PdbqtStructure,
        ligand: PdbqtStructure,
    ) -> None:
        self._hydrogen_bonds_one_direction(
            pose,
            donor_structure=receptor,
            acceptor_structure=ligand,
            receptor_is_donor=True,
        )
        self._hydrogen_bonds_one_direction(
            pose,
            donor_structure=ligand,
            acceptor_structure=receptor,
            receptor_is_donor=False,
        )

    def _hydrogen_bonds_one_direction(
        self,
        pose: Pose,
        *,
        donor_structure: PdbqtStructure,
        acceptor_structure: PdbqtStructure,
        receptor_is_donor: bool,
    ) -> None:
        for hydrogen in donor_structure.atoms:
            if hydrogen.atom_type not in _POLAR_H_TYPES:
                continue
            donor = self._nearest_heavy_atom(
                hydrogen,
                donor_structure.heavy_atoms,
            )
            if donor is None:
                continue
            for acceptor in acceptor_structure.heavy_atoms:
                if acceptor.atom_type not in _ACCEPTOR_TYPES:
                    continue
                da_distance = _distance(donor, acceptor)
                ha_distance = _distance(hydrogen, acceptor)
                if (
                    da_distance > self._hbond_da_cutoff
                    or ha_distance > self._hbond_ha_cutoff
                ):
                    continue
                angle = _angle_degrees(donor, hydrogen, acceptor)
                if angle < self._hbond_angle:
                    continue
                receptor_atom = donor if receptor_is_donor else acceptor
                ligand_atom = acceptor if receptor_is_donor else donor
                self._register(
                    pose,
                    PoseInteractionKind.HYDROGEN_BOND,
                    receptor_atom,
                    ligand_atom,
                    da_distance,
                    metadata={
                        "donor_side": (
                            "receptor" if receptor_is_donor else "ligand"
                        ),
                        "donor_hydrogen_serial": hydrogen.serial,
                        "hydrogen_acceptor_distance_angstrom": ha_distance,
                        "donor_hydrogen_acceptor_angle_degrees": angle,
                        "donor_acceptor_cutoff_angstrom": self._hbond_da_cutoff,
                        "hydrogen_acceptor_cutoff_angstrom": self._hbond_ha_cutoff,
                        "angle_cutoff_degrees": self._hbond_angle,
                    },
                )

    def _nearest_heavy_atom(
        self,
        hydrogen: PdbqtAtom,
        heavy_atoms: tuple[PdbqtAtom, ...],
    ) -> PdbqtAtom | None:
        candidates = [
            (distance, atom)
            for atom in heavy_atoms
            if (distance := _distance(hydrogen, atom)) <= self._donor_h_cutoff
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], item[1].serial))
        return candidates[0][1]

    def _register(
        self,
        pose: Pose,
        kind: PoseInteractionKind,
        receptor_atom: PdbqtAtom,
        ligand_atom: PdbqtAtom,
        distance: float,
        *,
        metadata: dict[str, object],
    ) -> None:
        self._repository.register_interaction(
            PoseInteraction(
                pose_id=pose.pose_id,
                kind=kind,
                receptor_atom_serial=receptor_atom.serial,
                receptor_atom_name=receptor_atom.name,
                receptor_residue_name=receptor_atom.residue_name,
                receptor_chain=receptor_atom.chain,
                receptor_residue_number=receptor_atom.residue_number,
                ligand_atom_serial=ligand_atom.serial,
                ligand_atom_name=ligand_atom.name,
                distance_angstrom=distance,
                method="pdbqt_geometric_interactions",
                method_version=self.METHOD_VERSION,
                metadata=metadata,
            )
        )
