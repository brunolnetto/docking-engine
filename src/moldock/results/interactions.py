from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import re

from moldock.domain import (
    DomainValidationError,
    InteractionKind,
    PoseInteraction,
)
from moldock.repositories import PreparedInputRepository, TaskRepository
from moldock.storage import ArtifactStore

from .repository import ScientificResultRepository


_MODEL = re.compile(rb"^MODEL\s+(\d+)\s*$")
_ACCEPTOR_TYPES = frozenset({"NA", "OA", "SA"})
_HYDROPHOBIC_TYPES = frozenset({"C", "A"})
_DONOR_HEAVY_TYPES = frozenset({"N", "NA", "OA", "O", "S", "SA"})


@dataclass(frozen=True, slots=True)
class PdbqtAtom:
    serial: int
    atom_name: str
    residue_name: str
    chain_id: str
    residue_number: str
    atom_type: str
    x: float
    y: float
    z: float

    @property
    def residue_id(self) -> str:
        chain = self.chain_id or "_"
        return f"{self.residue_name}:{chain}:{self.residue_number}"

    @property
    def label(self) -> str:
        return f"{self.atom_name}:{self.serial}:{self.atom_type}"

    @property
    def is_hydrogen(self) -> bool:
        return self.atom_type.upper().startswith("H")

    @property
    def xyz(self) -> tuple[float, float, float]:
        return self.x, self.y, self.z


class PdbqtInteractionParser:
    def receptor_atoms(self, content: bytes) -> tuple[PdbqtAtom, ...]:
        atoms = tuple(
            self._atom(line)
            for line in content.splitlines()
            if line.startswith((b"ATOM", b"HETATM"))
        )
        if not atoms:
            raise DomainValidationError("prepared receptor has no PDBQT atoms")
        return atoms

    def ligand_models(
        self,
        content: bytes,
    ) -> dict[int, tuple[PdbqtAtom, ...]]:
        models: dict[int, tuple[PdbqtAtom, ...]] = {}
        current: int | None = None
        lines: list[bytes] = []
        for line in content.splitlines():
            match = _MODEL.match(line)
            if match is not None:
                if current is not None:
                    raise DomainValidationError(
                        f"unterminated MODEL {current}"
                    )
                current = int(match.group(1))
                lines = []
                continue
            if line == b"ENDMDL":
                if current is None:
                    continue
                atoms = tuple(
                    self._atom(item)
                    for item in lines
                    if item.startswith((b"ATOM", b"HETATM"))
                )
                if not atoms:
                    raise DomainValidationError(
                        f"MODEL {current} has no PDBQT atoms"
                    )
                models[current] = atoms
                current = None
                lines = []
                continue
            if current is not None:
                lines.append(line)
        if current is not None:
            raise DomainValidationError(f"unterminated MODEL {current}")
        if not models:
            raise DomainValidationError("no ligand MODEL blocks found")
        return models

    @staticmethod
    def _atom(raw: bytes) -> PdbqtAtom:
        text = raw.decode("ascii")
        parts = text.split()
        try:
            return PdbqtAtom(
                serial=int(text[6:11]),
                atom_name=text[12:16].strip(),
                residue_name=text[17:20].strip() or "UNK",
                chain_id=text[21:22].strip(),
                residue_number=text[22:27].strip() or "0",
                atom_type=parts[-1],
                x=float(text[30:38]),
                y=float(text[38:46]),
                z=float(text[46:54]),
            )
        except (ValueError, IndexError) as exc:
            raise DomainValidationError(
                f"invalid PDBQT atom record: {text!r}"
            ) from exc


def _distance(left: PdbqtAtom, right: PdbqtAtom) -> float:
    return math.sqrt(
        (left.x - right.x) ** 2
        + (left.y - right.y) ** 2
        + (left.z - right.z) ** 2
    )


def _angle(
    donor: PdbqtAtom,
    hydrogen: PdbqtAtom,
    acceptor: PdbqtAtom,
) -> float:
    hd = (
        donor.x - hydrogen.x,
        donor.y - hydrogen.y,
        donor.z - hydrogen.z,
    )
    ha = (
        acceptor.x - hydrogen.x,
        acceptor.y - hydrogen.y,
        acceptor.z - hydrogen.z,
    )
    left = math.sqrt(sum(value * value for value in hd))
    right = math.sqrt(sum(value * value for value in ha))
    if left == 0 or right == 0:
        raise DomainValidationError("cannot calculate H-bond angle at zero distance")
    cosine = sum(a * b for a, b in zip(hd, ha, strict=True)) / (left * right)
    cosine = max(-1.0, min(1.0, cosine))
    return math.degrees(math.acos(cosine))


def _donor_hydrogens(
    atoms: tuple[PdbqtAtom, ...],
    *,
    max_bond_distance: float = 1.35,
) -> tuple[tuple[PdbqtAtom, PdbqtAtom], ...]:
    heavy = [
        atom
        for atom in atoms
        if (
            not atom.is_hydrogen
            and atom.atom_type.upper() in _DONOR_HEAVY_TYPES
        )
    ]
    pairs: list[tuple[PdbqtAtom, PdbqtAtom]] = []
    for hydrogen in (atom for atom in atoms if atom.atom_type.upper() == "HD"):
        candidates = [
            (distance, atom)
            for atom in heavy
            if (distance := _distance(atom, hydrogen)) <= max_bond_distance
        ]
        if not candidates:
            continue
        _, donor = min(
            candidates,
            key=lambda item: (item[0], item[1].serial),
        )
        pairs.append((donor, hydrogen))
    return tuple(pairs)


class PreparedReceptorResolver:
    def __init__(
        self,
        *,
        task_repository: TaskRepository,
        prepared_inputs: PreparedInputRepository,
        artifact_store: ArtifactStore,
    ) -> None:
        self._tasks = task_repository
        self._prepared = prepared_inputs
        self._store = artifact_store

    def resolve(self, task_id: str) -> bytes:
        task = self._tasks.get(task_id)
        if task is None:
            raise DomainValidationError(f"interaction task not found: {task_id}")
        binding = self._prepared.get_receptor(task.prepared_receptor_id)
        if binding is None:
            raise DomainValidationError(
                "prepared receptor not found for interaction analysis: "
                f"{task.prepared_receptor_id}"
            )
        content = self._store.read(binding.blob.uri)
        digest = hashlib.sha256(content).hexdigest()
        if (
            digest != binding.blob.sha256
            or len(content) != binding.blob.size_bytes
        ):
            raise DomainValidationError(
                "prepared receptor integrity check failed: "
                f"{binding.blob.blob_id}"
            )
        return content


class PoseInteractionAnalyzer:
    METHOD = "autodock_atom_type_geometry"
    METHOD_VERSION = "1"
    CONTACT_MAX = 4.0
    HYDROPHOBIC_MAX = 4.0
    HBOND_DA_MAX = 4.1
    HBOND_ANGLE_MIN = 100.0

    def __init__(
        self,
        *,
        repository: ScientificResultRepository,
        receptor_resolver: PreparedReceptorResolver,
        parser: PdbqtInteractionParser | None = None,
    ) -> None:
        self._repository = repository
        self._receptor_resolver = receptor_resolver
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
        receptor_atoms = self._parser.receptor_atoms(
            self._receptor_resolver.resolve(task_id)
        )
        ligand_models = self._parser.ligand_models(pose_content)
        by_model = {pose.model_index: pose for pose in poses}
        if set(by_model) != set(ligand_models):
            raise DomainValidationError(
                "interaction geometry does not match persisted pose models"
            )
        for model_index, pose in sorted(by_model.items()):
            ligand_atoms = ligand_models[model_index]
            for interaction in self._contacts(
                pose.pose_id,
                receptor_atoms,
                ligand_atoms,
            ):
                self._repository.register_interaction(interaction)
            for interaction in self._hydrophobic(
                pose.pose_id,
                receptor_atoms,
                ligand_atoms,
            ):
                self._repository.register_interaction(interaction)
            for interaction in self._hydrogen_bonds(
                pose.pose_id,
                receptor_atoms,
                ligand_atoms,
            ):
                self._repository.register_interaction(interaction)

    def _metadata(self) -> dict[str, object]:
        return {
            "contact_distance_max_angstrom": self.CONTACT_MAX,
            "hydrophobic_distance_max_angstrom": self.HYDROPHOBIC_MAX,
            "hbond_da_distance_max_angstrom": self.HBOND_DA_MAX,
            "hbond_dha_angle_min_degrees": self.HBOND_ANGLE_MIN,
            "donor_h_parent_distance_max_angstrom": 1.35,
        }

    def _contacts(
        self,
        pose_id: str,
        receptor: tuple[PdbqtAtom, ...],
        ligand: tuple[PdbqtAtom, ...],
    ) -> tuple[PoseInteraction, ...]:
        ligand_heavy = [atom for atom in ligand if not atom.is_hydrogen]
        receptor_by_residue: dict[str, list[PdbqtAtom]] = {}
        for atom in receptor:
            if not atom.is_hydrogen:
                receptor_by_residue.setdefault(atom.residue_id, []).append(atom)

        interactions: list[PoseInteraction] = []
        for residue_id, receptor_atoms in sorted(receptor_by_residue.items()):
            candidates = [
                (_distance(rec, lig), rec, lig)
                for rec in receptor_atoms
                for lig in ligand_heavy
                if _distance(rec, lig) <= self.CONTACT_MAX
            ]
            if not candidates:
                continue
            distance, rec, lig = min(
                candidates,
                key=lambda item: (
                    item[0],
                    item[1].serial,
                    item[2].serial,
                ),
            )
            interactions.append(
                PoseInteraction(
                    pose_id=pose_id,
                    kind=InteractionKind.RESIDUE_CONTACT,
                    receptor_residue=residue_id,
                    receptor_atom=rec.label,
                    ligand_atom=lig.label,
                    distance_angstrom=distance,
                    method=self.METHOD,
                    method_version=self.METHOD_VERSION,
                    metadata=self._metadata(),
                )
            )
        return tuple(interactions)

    def _hydrophobic(
        self,
        pose_id: str,
        receptor: tuple[PdbqtAtom, ...],
        ligand: tuple[PdbqtAtom, ...],
    ) -> tuple[PoseInteraction, ...]:
        rec_atoms = [
            atom
            for atom in receptor
            if atom.atom_type.upper() in _HYDROPHOBIC_TYPES
        ]
        lig_atoms = [
            atom
            for atom in ligand
            if atom.atom_type.upper() in _HYDROPHOBIC_TYPES
        ]
        nearest: dict[tuple[str, str], tuple[float, PdbqtAtom, PdbqtAtom]] = {}
        for rec in rec_atoms:
            for lig in lig_atoms:
                distance = _distance(rec, lig)
                if distance > self.HYDROPHOBIC_MAX:
                    continue
                key = (rec.residue_id, lig.label)
                current = nearest.get(key)
                candidate = (distance, rec, lig)
                if current is None or (
                    candidate[0],
                    candidate[1].serial,
                ) < (
                    current[0],
                    current[1].serial,
                ):
                    nearest[key] = candidate

        return tuple(
            PoseInteraction(
                pose_id=pose_id,
                kind=InteractionKind.HYDROPHOBIC_CONTACT,
                receptor_residue=rec.residue_id,
                receptor_atom=rec.label,
                ligand_atom=lig.label,
                distance_angstrom=distance,
                method=self.METHOD,
                method_version=self.METHOD_VERSION,
                metadata=self._metadata(),
            )
            for distance, rec, lig in sorted(
                nearest.values(),
                key=lambda item: (
                    item[1].residue_id,
                    item[2].serial,
                    item[0],
                ),
            )
        )

    def _hydrogen_bonds(
        self,
        pose_id: str,
        receptor: tuple[PdbqtAtom, ...],
        ligand: tuple[PdbqtAtom, ...],
    ) -> tuple[PoseInteraction, ...]:
        interactions: list[PoseInteraction] = []
        receptor_acceptors = [
            atom
            for atom in receptor
            if atom.atom_type.upper() in _ACCEPTOR_TYPES
        ]
        ligand_acceptors = [
            atom
            for atom in ligand
            if atom.atom_type.upper() in _ACCEPTOR_TYPES
        ]

        directions = (
            (True, _donor_hydrogens(receptor), ligand_acceptors),
            (False, _donor_hydrogens(ligand), receptor_acceptors),
        )
        for protein_is_donor, donor_pairs, acceptors in directions:
            for donor, hydrogen in donor_pairs:
                for acceptor in acceptors:
                    distance = _distance(donor, acceptor)
                    if distance > self.HBOND_DA_MAX:
                        continue
                    angle = _angle(donor, hydrogen, acceptor)
                    if angle < self.HBOND_ANGLE_MIN:
                        continue
                    protein_atom = donor if protein_is_donor else acceptor
                    ligand_atom = acceptor if protein_is_donor else donor
                    interactions.append(
                        PoseInteraction(
                            pose_id=pose_id,
                            kind=InteractionKind.HYDROGEN_BOND,
                            receptor_residue=protein_atom.residue_id,
                            receptor_atom=protein_atom.label,
                            ligand_atom=ligand_atom.label,
                            distance_angstrom=distance,
                            angle_degrees=angle,
                            protein_is_donor=protein_is_donor,
                            method=self.METHOD,
                            method_version=self.METHOD_VERSION,
                            metadata={
                                **self._metadata(),
                                "hydrogen_atom": hydrogen.label,
                            },
                        )
                    )
        return tuple(
            sorted(
                interactions,
                key=lambda item: (
                    item.receptor_residue,
                    item.protein_is_donor is False,
                    item.receptor_atom,
                    item.ligand_atom,
                    item.distance_angstrom,
                ),
            )
        )
