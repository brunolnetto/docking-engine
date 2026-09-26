from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Protocol, runtime_checkable

from moldock.domain import (
    DomainValidationError,
    PoseInteraction,
    PoseInteractionKind,
)
from moldock.repositories import PreparedInputRepository, TaskRepository
from moldock.storage import ArtifactStore

from .repository import ScientificResultRepository


_MODEL = re.compile(rb"^MODEL\s+(\d+)\s*$")


@dataclass(frozen=True, slots=True)
class PdbqtAtom:
    serial: int
    atom_name: str
    residue_name: str
    chain_id: str
    residue_number: str
    x: float
    y: float
    z: float
    charge: float
    atom_type: str

    @property
    def coordinates(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)

    @property
    def is_hydrogen(self) -> bool:
        return self.atom_type.upper().startswith("H")

    @property
    def is_hydrophobic(self) -> bool:
        return self.atom_type.upper() in {"C", "A"}

    @property
    def is_acceptor(self) -> bool:
        return self.atom_type.upper() in {"OA", "NA", "SA"}

    @property
    def is_polar_heavy(self) -> bool:
        return (
            not self.is_hydrogen
            and self.atom_type.upper()[:1] in {"N", "O", "S"}
        )


class PdbqtInteractionParser:
    """Parse the atom fields needed for deterministic interaction heuristics."""

    def parse_receptor(self, content: bytes) -> tuple[PdbqtAtom, ...]:
        atoms = tuple(
            self._atom(line)
            for line in content.splitlines()
            if line.startswith((b"ATOM", b"HETATM"))
        )
        if not atoms:
            raise DomainValidationError("prepared receptor contains no PDBQT atoms")
        return atoms

    def parse_pose_models(
        self,
        content: bytes,
    ) -> dict[int, tuple[PdbqtAtom, ...]]:
        models: dict[int, list[PdbqtAtom]] = {}
        current: int | None = None
        for line in content.splitlines():
            match = _MODEL.match(line)
            if match is not None:
                if current is not None:
                    raise DomainValidationError(
                        f"unterminated MODEL {current} in docking output"
                    )
                current = int(match.group(1))
                models[current] = []
                continue
            if line == b"ENDMDL":
                current = None
                continue
            if current is not None and line.startswith((b"ATOM", b"HETATM")):
                models[current].append(self._atom(line))
        if current is not None:
            raise DomainValidationError(
                f"unterminated MODEL {current} in docking output"
            )
        if not models:
            raise DomainValidationError("docking output contains no MODEL atoms")
        if any(not atoms for atoms in models.values()):
            raise DomainValidationError("docking output contains an empty MODEL")
        return {
            model_index: tuple(atoms)
            for model_index, atoms in models.items()
        }

    @staticmethod
    def _atom(raw: bytes) -> PdbqtAtom:
        try:
            text = raw.decode("ascii")
            fields = text.split()
            residue_number = (
                text[22:26].strip() + text[26:27].strip()
            ) or "?"
            return PdbqtAtom(
                serial=int(text[6:11]),
                atom_name=text[12:16].strip() or "?",
                residue_name=text[17:20].strip() or "UNK",
                chain_id=text[21:22].strip() or "?",
                residue_number=residue_number,
                x=float(text[30:38]),
                y=float(text[38:46]),
                z=float(text[46:54]),
                charge=float(fields[-2]),
                atom_type=fields[-1],
            )
        except (UnicodeDecodeError, ValueError, IndexError) as exc:
            raise DomainValidationError(
                "invalid PDBQT atom record for interaction analysis"
            ) from exc


def atom_distance(left: PdbqtAtom, right: PdbqtAtom) -> float:
    return math.dist(left.coordinates, right.coordinates)


def donor_angle(
    donor: PdbqtAtom,
    hydrogen: PdbqtAtom,
    acceptor: PdbqtAtom,
) -> float:
    left = (
        donor.x - hydrogen.x,
        donor.y - hydrogen.y,
        donor.z - hydrogen.z,
    )
    right = (
        acceptor.x - hydrogen.x,
        acceptor.y - hydrogen.y,
        acceptor.z - hydrogen.z,
    )
    norm_left = math.sqrt(sum(value * value for value in left))
    norm_right = math.sqrt(sum(value * value for value in right))
    if norm_left == 0 or norm_right == 0:
        raise DomainValidationError("degenerate hydrogen-bond geometry")
    cosine = sum(a * b for a, b in zip(left, right, strict=True))
    cosine /= norm_left * norm_right
    cosine = max(-1.0, min(1.0, cosine))
    return math.degrees(math.acos(cosine))


@runtime_checkable
class PoseInteractionAnalyzer(Protocol):
    def analyze(
        self,
        *,
        task_id: str,
        attempt_id: str,
        pose_content: bytes,
    ) -> None: ...


class PdbqtPoseInteractionAnalyzer:
    """Persist transparent PDBQT-native protein-ligand interaction heuristics."""

    METHOD = "pdbqt_geometric_interactions"
    METHOD_VERSION = "1"

    CONTACT_MAX = 4.0
    HYDROPHOBIC_MAX = 4.0
    HBOND_MAX = 4.1
    HBOND_ANGLE_MIN = 100.0
    SALT_BRIDGE_MAX = 5.5
    DONOR_H_MAX = 1.30
    LIGAND_CHARGE_MIN = 0.30

    def __init__(
        self,
        *,
        task_repository: TaskRepository,
        prepared_inputs: PreparedInputRepository,
        artifact_store: ArtifactStore,
        repository: ScientificResultRepository,
        parser: PdbqtInteractionParser | None = None,
    ) -> None:
        self._tasks = task_repository
        self._prepared_inputs = prepared_inputs
        self._store = artifact_store
        self._repository = repository
        self._parser = parser or PdbqtInteractionParser()

    def analyze(
        self,
        *,
        task_id: str,
        attempt_id: str,
        pose_content: bytes,
    ) -> None:
        poses = self._repository.list_poses_for_attempt(attempt_id)
        if not poses:
            return
        task = self._tasks.get(task_id)
        if task is None:
            raise DomainValidationError(
                f"interaction analysis task not found: {task_id}"
            )
        binding = self._prepared_inputs.get_receptor(
            task.prepared_receptor_id
        )
        if binding is None:
            raise DomainValidationError(
                "prepared receptor not found for interaction analysis: "
                f"{task.prepared_receptor_id}"
            )

        receptor_atoms = self._parser.parse_receptor(
            self._store.read(binding.blob.uri)
        )
        pose_models = self._parser.parse_pose_models(pose_content)
        by_model = {pose.model_index: pose for pose in poses}
        if set(pose_models) != set(by_model):
            raise DomainValidationError(
                "interaction geometry does not match persisted pose models"
            )

        receptor_donors = self._donors(receptor_atoms)
        receptor_acceptors = tuple(
            atom for atom in receptor_atoms if atom.is_acceptor
        )

        for model_index, ligand_atoms in pose_models.items():
            pose = by_model[model_index]
            interactions = self._interactions(
                pose_id=pose.pose_id,
                receptor_atoms=receptor_atoms,
                receptor_donors=receptor_donors,
                receptor_acceptors=receptor_acceptors,
                ligand_atoms=ligand_atoms,
            )
            for interaction in interactions:
                self._repository.register_interaction(interaction)

    def _interactions(
        self,
        *,
        pose_id: str,
        receptor_atoms: tuple[PdbqtAtom, ...],
        receptor_donors: tuple[tuple[PdbqtAtom, PdbqtAtom], ...],
        receptor_acceptors: tuple[PdbqtAtom, ...],
        ligand_atoms: tuple[PdbqtAtom, ...],
    ) -> tuple[PoseInteraction, ...]:
        interactions: list[PoseInteraction] = []
        receptor_heavy = tuple(
            atom for atom in receptor_atoms if not atom.is_hydrogen
        )
        ligand_heavy = tuple(
            atom for atom in ligand_atoms if not atom.is_hydrogen
        )

        interactions.extend(
            self._nearest_per_residue(
                pose_id,
                PoseInteractionKind.CONTACT,
                (
                    (rec, lig, atom_distance(rec, lig), {})
                    for rec in receptor_heavy
                    for lig in ligand_heavy
                    if atom_distance(rec, lig) <= self.CONTACT_MAX
                ),
                cutoff=self.CONTACT_MAX,
            )
        )
        interactions.extend(
            self._nearest_per_residue(
                pose_id,
                PoseInteractionKind.HYDROPHOBIC,
                (
                    (rec, lig, atom_distance(rec, lig), {})
                    for rec in receptor_heavy
                    if rec.is_hydrophobic
                    for lig in ligand_heavy
                    if lig.is_hydrophobic
                    and atom_distance(rec, lig) <= self.HYDROPHOBIC_MAX
                ),
                cutoff=self.HYDROPHOBIC_MAX,
            )
        )

        ligand_donors = self._donors(ligand_atoms)
        ligand_acceptors = tuple(
            atom for atom in ligand_atoms if atom.is_acceptor
        )
        for donor, hydrogen in receptor_donors:
            for acceptor in ligand_acceptors:
                self._maybe_hbond(
                    interactions,
                    pose_id,
                    donor,
                    hydrogen,
                    acceptor,
                    protein_is_donor=True,
                )
        for donor, hydrogen in ligand_donors:
            for acceptor in receptor_acceptors:
                self._maybe_hbond(
                    interactions,
                    pose_id,
                    acceptor,
                    hydrogen,
                    donor,
                    protein_is_donor=False,
                    ligand_donor=donor,
                    receptor_acceptor=acceptor,
                )

        salt_candidates = []
        receptor_charged = tuple(
            item
            for atom in receptor_heavy
            if (item := self._protein_charge(atom)) is not None
        )
        ligand_charged = tuple(
            atom
            for atom in ligand_heavy
            if abs(atom.charge) >= self.LIGAND_CHARGE_MIN
        )
        for receptor_sign, receptor_atom in receptor_charged:
            for ligand_atom in ligand_charged:
                ligand_sign = 1 if ligand_atom.charge > 0 else -1
                if receptor_sign == ligand_sign:
                    continue
                distance = atom_distance(receptor_atom, ligand_atom)
                if distance <= self.SALT_BRIDGE_MAX:
                    salt_candidates.append(
                        (
                            receptor_atom,
                            ligand_atom,
                            distance,
                            {
                                "putative": True,
                                "protein_charge_sign": receptor_sign,
                                "ligand_partial_charge": ligand_atom.charge,
                                "ligand_charge_threshold": self.LIGAND_CHARGE_MIN,
                            },
                        )
                    )
        interactions.extend(
            self._nearest_per_residue(
                pose_id,
                PoseInteractionKind.SALT_BRIDGE,
                salt_candidates,
                cutoff=self.SALT_BRIDGE_MAX,
            )
        )

        unique = {item.interaction_id: item for item in interactions}
        return tuple(
            sorted(
                unique.values(),
                key=lambda item: (
                    item.kind.value,
                    item.receptor_residue_id,
                    item.distance_angstrom,
                    item.receptor_atom_name,
                    item.ligand_atom_name,
                ),
            )
        )

    def _maybe_hbond(
        self,
        output: list[PoseInteraction],
        pose_id: str,
        receptor_atom: PdbqtAtom,
        hydrogen: PdbqtAtom,
        other_atom: PdbqtAtom,
        *,
        protein_is_donor: bool,
        ligand_donor: PdbqtAtom | None = None,
        receptor_acceptor: PdbqtAtom | None = None,
    ) -> None:
        if protein_is_donor:
            donor = receptor_atom
            acceptor = other_atom
            receptor = receptor_atom
            ligand = other_atom
        else:
            donor = ligand_donor
            acceptor = receptor_acceptor
            receptor = receptor_acceptor
            ligand = ligand_donor
        if donor is None or acceptor is None or receptor is None or ligand is None:
            return
        distance = atom_distance(donor, acceptor)
        if distance > self.HBOND_MAX:
            return
        angle = donor_angle(donor, hydrogen, acceptor)
        if angle < self.HBOND_ANGLE_MIN:
            return
        output.append(
            self._interaction(
                pose_id,
                PoseInteractionKind.HYDROGEN_BOND,
                receptor,
                ligand,
                distance,
                metadata={
                    "protein_is_donor": protein_is_donor,
                    "donor_angle_degrees": angle,
                    "distance_cutoff_angstrom": self.HBOND_MAX,
                    "donor_angle_min_degrees": self.HBOND_ANGLE_MIN,
                },
            )
        )

    def _nearest_per_residue(
        self,
        pose_id: str,
        kind: PoseInteractionKind,
        candidates,
        *,
        cutoff: float,
    ) -> tuple[PoseInteraction, ...]:
        nearest: dict[
            tuple[str, str, str],
            tuple[PdbqtAtom, PdbqtAtom, float, dict[str, object]],
        ] = {}
        for receptor, ligand, distance, metadata in candidates:
            key = (
                receptor.chain_id,
                receptor.residue_name,
                receptor.residue_number,
            )
            current = nearest.get(key)
            if current is None or distance < current[2]:
                nearest[key] = (receptor, ligand, distance, metadata)
        return tuple(
            self._interaction(
                pose_id,
                kind,
                receptor,
                ligand,
                distance,
                metadata={
                    "distance_cutoff_angstrom": cutoff,
                    **metadata,
                },
            )
            for receptor, ligand, distance, metadata in nearest.values()
        )

    def _interaction(
        self,
        pose_id: str,
        kind: PoseInteractionKind,
        receptor: PdbqtAtom,
        ligand: PdbqtAtom,
        distance: float,
        *,
        metadata: dict[str, object],
    ) -> PoseInteraction:
        return PoseInteraction(
            pose_id=pose_id,
            kind=kind,
            receptor_chain_id=receptor.chain_id,
            receptor_residue_name=receptor.residue_name,
            receptor_residue_number=receptor.residue_number,
            receptor_atom_name=receptor.atom_name,
            ligand_atom_name=ligand.atom_name,
            distance_angstrom=distance,
            method=self.METHOD,
            method_version=self.METHOD_VERSION,
            metadata=metadata,
        )

    def _donors(
        self,
        atoms: tuple[PdbqtAtom, ...],
    ) -> tuple[tuple[PdbqtAtom, PdbqtAtom], ...]:
        hydrogens = tuple(
            atom
            for atom in atoms
            if atom.atom_type.upper() == "HD"
        )
        donors = []
        for heavy in atoms:
            if not heavy.is_polar_heavy:
                continue
            for hydrogen in hydrogens:
                if atom_distance(heavy, hydrogen) <= self.DONOR_H_MAX:
                    donors.append((heavy, hydrogen))
        return tuple(donors)

    @staticmethod
    def _protein_charge(
        atom: PdbqtAtom,
    ) -> tuple[int, PdbqtAtom] | None:
        residue = atom.residue_name.upper()
        name = atom.atom_name.upper()
        if residue == "ASP" and name in {"OD1", "OD2"}:
            return (-1, atom)
        if residue == "GLU" and name in {"OE1", "OE2"}:
            return (-1, atom)
        if residue == "LYS" and name == "NZ":
            return (1, atom)
        if residue == "ARG" and name in {"NE", "NH1", "NH2"}:
            return (1, atom)
        return None
