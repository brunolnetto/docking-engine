from __future__ import annotations

from dataclasses import dataclass
import math
import re

from moldock.domain import (
    DomainValidationError,
    Pose,
    PoseClusterAssignment,
    PoseMetric,
    PoseMetricKind,
    ScoreKind,
    content_id,
)

from .repository import ScientificResultRepository


_MODEL = re.compile(rb"^MODEL\s+(\d+)\s*$")


@dataclass(frozen=True, slots=True)
class PoseGeometry:
    model_index: int
    atom_labels: tuple[str, ...]
    coordinates: tuple[tuple[float, float, float], ...]

    @property
    def heavy_atom_count(self) -> int:
        return len(self.coordinates)


class PdbqtPoseGeometryParser:
    """Extract heavy-atom coordinates from Vina multi-model PDBQT output."""

    def parse(self, content: bytes) -> tuple[PoseGeometry, ...]:
        blocks = self._model_blocks(content)
        geometries: list[PoseGeometry] = []
        for model_index, lines in blocks:
            labels: list[str] = []
            coordinates: list[tuple[float, float, float]] = []
            for raw in lines:
                if not raw.startswith((b"ATOM", b"HETATM")):
                    continue
                text = raw.decode("ascii")
                atom_type = text.split()[-1]
                if atom_type.upper().startswith("H"):
                    continue
                try:
                    x = float(text[30:38])
                    y = float(text[38:46])
                    z = float(text[46:54])
                except (ValueError, IndexError) as exc:
                    raise DomainValidationError(
                        f"invalid PDBQT coordinates in MODEL {model_index}"
                    ) from exc
                atom_name = text[12:16].strip()
                labels.append(f"{atom_name}:{atom_type}")
                coordinates.append((x, y, z))
            if not coordinates:
                raise DomainValidationError(
                    f"MODEL {model_index} has no heavy atoms"
                )
            geometries.append(
                PoseGeometry(
                    model_index=model_index,
                    atom_labels=tuple(labels),
                    coordinates=tuple(coordinates),
                )
            )
        if not geometries:
            raise DomainValidationError("no MODEL blocks found for pose analysis")
        reference_labels = geometries[0].atom_labels
        for geometry in geometries[1:]:
            if geometry.atom_labels != reference_labels:
                raise DomainValidationError(
                    "pose heavy-atom order differs across MODEL blocks"
                )
        return tuple(geometries)

    @staticmethod
    def _model_blocks(content: bytes) -> list[tuple[int, list[bytes]]]:
        blocks: list[tuple[int, list[bytes]]] = []
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
                    blocks.append((model_index, lines))
                model_index = None
                lines = []
                continue
            if model_index is not None:
                lines.append(raw)
        if model_index is not None:
            raise DomainValidationError(f"unterminated MODEL {model_index}")
        return blocks


def direct_rmsd(left: PoseGeometry, right: PoseGeometry) -> float:
    if left.atom_labels != right.atom_labels:
        raise DomainValidationError("cannot compare poses with different atom order")
    if len(left.coordinates) != len(right.coordinates):
        raise DomainValidationError("cannot compare poses with different atom counts")
    squared = 0.0
    for a, b in zip(left.coordinates, right.coordinates, strict=True):
        squared += (
            (a[0] - b[0]) ** 2
            + (a[1] - b[1]) ** 2
            + (a[2] - b[2]) ** 2
        )
    return math.sqrt(squared / len(left.coordinates))


class PoseScientificAnalyzer:
    """Persist deterministic structural descriptors derived from Vina poses."""

    METHOD_VERSION = "1"

    def __init__(
        self,
        *,
        repository: ScientificResultRepository,
        cluster_threshold_angstrom: float = 2.0,
        geometry_parser: PdbqtPoseGeometryParser | None = None,
    ) -> None:
        if cluster_threshold_angstrom <= 0:
            raise DomainValidationError("cluster threshold must be > 0")
        self._repository = repository
        self._threshold = cluster_threshold_angstrom
        self._parser = geometry_parser or PdbqtPoseGeometryParser()

    def analyze(
        self,
        *,
        attempt_id: str,
        content: bytes,
    ) -> None:
        poses = self._repository.list_poses_for_attempt(attempt_id)
        if not poses:
            return
        geometries = {
            geometry.model_index: geometry
            for geometry in self._parser.parse(content)
        }
        by_model = {pose.model_index: pose for pose in poses}
        if set(geometries) != set(by_model):
            raise DomainValidationError(
                "pose analysis geometry does not match persisted pose models"
            )

        ranked = self._ranked_poses(poses)
        if not ranked:
            return
        rank_one = ranked[0]
        reference_geometry = geometries[rank_one.model_index]

        for pose in ranked:
            geometry = geometries[pose.model_index]
            self._repository.register_metric(
                PoseMetric(
                    pose_id=pose.pose_id,
                    kind=PoseMetricKind.RMSD_TO_RANK1,
                    value=direct_rmsd(geometry, reference_geometry),
                    unit="angstrom",
                    method="pdbqt_atom_order_direct_rmsd",
                    method_version=self.METHOD_VERSION,
                    metadata={
                        "reference_pose_id": rank_one.pose_id,
                        "heavy_atom_count": geometry.heavy_atom_count,
                        "aligned": False,
                        "symmetry_corrected": False,
                    },
                )
            )
            for score in self._repository.list_scores_for_pose(pose.pose_id):
                if score.kind is not ScoreKind.VINA_AFFINITY:
                    continue
                self._repository.register_metric(
                    PoseMetric(
                        pose_id=pose.pose_id,
                        kind=PoseMetricKind.LIGAND_EFFICIENCY,
                        value=-score.value / geometry.heavy_atom_count,
                        unit="kcal/mol/heavy_atom",
                        method="vina_affinity_per_heavy_atom",
                        method_version=score.method_version,
                        metadata={
                            "source_score_id": score.score_id,
                            "heavy_atom_count": geometry.heavy_atom_count,
                        },
                    )
                )

        self._cluster(ranked, geometries)

    def _ranked_poses(self, poses: tuple[Pose, ...]) -> list[Pose]:
        ranked: list[tuple[int, Pose]] = []
        for pose in poses:
            ranks = [
                ranking
                for ranking in self._repository.list_rankings_for_pose(
                    pose.pose_id
                )
                if ranking.method == ScoreKind.VINA_AFFINITY.value
            ]
            if ranks:
                ranked.append((min(item.rank for item in ranks), pose))
        ranked.sort(key=lambda item: (item[0], item[1].pose_id))
        return [pose for _, pose in ranked]

    def _cluster(
        self,
        ranked: list[Pose],
        geometries: dict[int, PoseGeometry],
    ) -> None:
        representatives: list[Pose] = []
        for pose in ranked:
            geometry = geometries[pose.model_index]
            representative: Pose | None = None
            for candidate in representatives:
                if (
                    direct_rmsd(
                        geometry,
                        geometries[candidate.model_index],
                    )
                    <= self._threshold
                ):
                    representative = candidate
                    break
            if representative is None:
                representative = pose
                representatives.append(pose)
            cluster_id = content_id(
                "pose_cluster",
                {
                    "method": "rank_ordered_leader_rmsd",
                    "method_version": self.METHOD_VERSION,
                    "threshold_angstrom": self._threshold,
                    "representative_pose_id": representative.pose_id,
                },
            )
            self._repository.register_cluster_assignment(
                PoseClusterAssignment(
                    pose_id=pose.pose_id,
                    cluster_id=cluster_id,
                    method="rank_ordered_leader_rmsd",
                    method_version=self.METHOD_VERSION,
                    metadata={
                        "threshold_angstrom": self._threshold,
                        "representative_pose_id": representative.pose_id,
                    },
                )
            )
