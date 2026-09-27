from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from typing import Iterable

from moldock.domain import Pose, PoseInteraction, PoseInteractionKind
from moldock.results import (
    InMemoryScientificResultRepository,
    PoseInteractionAnalyzer,
)


@dataclass(frozen=True, order=True)
class InteractionFingerprintKey:
    kind: str
    receptor_chain: str
    receptor_residue_name: str
    receptor_residue_number: str


@dataclass(frozen=True)
class InteractionRecoveryMetrics:
    kind: str
    reference_count: int
    predicted_count: int
    true_positive: int
    false_positive: int
    false_negative: int
    precision: float | None
    recall: float | None
    f1: float | None
    jaccard: float | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def fingerprint(
    interactions: Iterable[PoseInteraction],
) -> frozenset[InteractionFingerprintKey]:
    return frozenset(
        InteractionFingerprintKey(
            kind=interaction.kind.value,
            receptor_chain=interaction.receptor_chain,
            receptor_residue_name=interaction.receptor_residue_name,
            receptor_residue_number=interaction.receptor_residue_number,
        )
        for interaction in interactions
    )


def compare_family(
    *,
    kind: str,
    reference: frozenset[InteractionFingerprintKey],
    predicted: frozenset[InteractionFingerprintKey],
) -> InteractionRecoveryMetrics:
    reference_family = frozenset(item for item in reference if item.kind == kind)
    predicted_family = frozenset(item for item in predicted if item.kind == kind)
    tp = len(reference_family & predicted_family)
    fp = len(predicted_family - reference_family)
    fn = len(reference_family - predicted_family)

    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None
        and recall is not None
        and precision + recall
        else None
    )
    union = len(reference_family | predicted_family)
    jaccard = tp / union if union else None

    return InteractionRecoveryMetrics(
        kind=kind,
        reference_count=len(reference_family),
        predicted_count=len(predicted_family),
        true_positive=tp,
        false_positive=fp,
        false_negative=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        jaccard=jaccard,
    )


def compare_fingerprints(
    reference: frozenset[InteractionFingerprintKey],
    predicted: frozenset[InteractionFingerprintKey],
    *,
    kinds: tuple[str, ...] = tuple(kind.value for kind in PoseInteractionKind),
) -> tuple[InteractionRecoveryMetrics, ...]:
    return tuple(
        compare_family(kind=kind, reference=reference, predicted=predicted)
        for kind in kinds
    )


def _as_model_one(ligand_pdbqt: bytes) -> bytes:
    if any(
        line.startswith(b"MODEL")
        for line in ligand_pdbqt.splitlines()
    ):
        return ligand_pdbqt
    return b"MODEL 1\n" + ligand_pdbqt.rstrip() + b"\nENDMDL\n"


def extract_pdbqt_fingerprint(
    *,
    receptor_pdbqt: bytes,
    ligand_pdbqt: bytes,
) -> frozenset[InteractionFingerprintKey]:
    repository = InMemoryScientificResultRepository()
    attempt_id = "benchmark_interaction_reference_attempt"
    pose = Pose(
        task_id="benchmark_interaction_reference_task",
        attempt_id=attempt_id,
        source_artifact_id="benchmark_interaction_reference_artifact",
        model_index=1,
        geometry_sha256=hashlib.sha256(ligand_pdbqt).hexdigest(),
    )
    repository.register_pose(pose)
    PoseInteractionAnalyzer(repository=repository).analyze(
        attempt_id=attempt_id,
        receptor_pdbqt=receptor_pdbqt,
        pose_pdbqt=_as_model_one(ligand_pdbqt),
    )
    return fingerprint(repository.list_interactions_for_pose(pose.pose_id))


def aggregate_metrics(
    case_metrics: Iterable[Iterable[InteractionRecoveryMetrics]],
) -> tuple[InteractionRecoveryMetrics, ...]:
    accumulators: dict[str, list[int]] = {}
    for metrics in case_metrics:
        for metric in metrics:
            values = accumulators.setdefault(metric.kind, [0, 0, 0, 0, 0])
            values[0] += metric.reference_count
            values[1] += metric.predicted_count
            values[2] += metric.true_positive
            values[3] += metric.false_positive
            values[4] += metric.false_negative

    aggregated = []
    for kind in sorted(accumulators):
        reference_count, predicted_count, tp, fp, fn = accumulators[kind]
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision is not None
            and recall is not None
            and precision + recall
            else None
        )
        union = tp + fp + fn
        aggregated.append(
            InteractionRecoveryMetrics(
                kind=kind,
                reference_count=reference_count,
                predicted_count=predicted_count,
                true_positive=tp,
                false_positive=fp,
                false_negative=fn,
                precision=precision,
                recall=recall,
                f1=f1,
                jaccard=tp / union if union else None,
            )
        )
    return tuple(aggregated)
