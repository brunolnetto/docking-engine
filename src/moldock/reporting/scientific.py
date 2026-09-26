from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from moldock.domain import TaskStatus

from .model import PipelineReport


@dataclass(frozen=True, slots=True)
class ScientificPoseResult:
    ligand_id: str
    pose_id: str
    rank: int | None
    score_kind: str
    score_value: float
    score_unit: str | None
    method: str
    method_version: str
    rmsd_to_rank1: float | None = None
    ligand_efficiency: float | None = None
    cluster_id: str | None = None


@dataclass(frozen=True, slots=True)
class ScientificNarrative:
    title: str
    objective: str
    outcome: str
    conclusion: str
    interpretation: tuple[str, ...]
    limitations: tuple[str, ...]
    next_steps: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScientificExperimentReport:
    source: PipelineReport
    poses: tuple[ScientificPoseResult, ...]
    narrative: ScientificNarrative

    @property
    def completed(self) -> bool:
        return (
            self.source.task_count > 0
            and self.source.failed_count == 0
            and self.source.pending_count == 0
            and self.source.running_count == 0
            and self.source.succeeded_count == self.source.task_count
        )

    @property
    def score_min(self) -> float | None:
        values = [pose.score_value for pose in self.poses]
        return min(values) if values else None

    @property
    def score_max(self) -> float | None:
        values = [pose.score_value for pose in self.poses]
        return max(values) if values else None

    @property
    def score_spread(self) -> float | None:
        if self.score_min is None or self.score_max is None:
            return None
        return self.score_max - self.score_min


class ScientificReportBuilder:
    """Derive conservative scientific observations from durable pipeline state."""

    def build(self, report: PipelineReport) -> ScientificExperimentReport:
        poses = self._poses(report)
        narrative = self._narrative(report, poses)
        return ScientificExperimentReport(
            source=report,
            poses=poses,
            narrative=narrative,
        )

    def _poses(
        self,
        report: PipelineReport,
    ) -> tuple[ScientificPoseResult, ...]:
        rows: list[ScientificPoseResult] = []
        for task in report.tasks:
            rankings = {
                (ranking.pose_id, ranking.method): ranking.rank
                for ranking in task.rankings
            }
            metrics_by_pose: dict[str, dict[str, float]] = {}
            for metric in task.metrics:
                metrics_by_pose.setdefault(metric.pose_id, {})[
                    metric.kind
                ] = metric.value
            clusters_by_pose = {
                item.pose_id: item.cluster_id
                for item in task.clusters
                if item.method == "rank_ordered_leader_rmsd"
            }
            for score in task.scores:
                if not isfinite(score.value):
                    continue
                pose_metrics = metrics_by_pose.get(score.pose_id, {})
                rows.append(
                    ScientificPoseResult(
                        ligand_id=task.ligand_id,
                        pose_id=score.pose_id,
                        rank=rankings.get((score.pose_id, score.kind)),
                        score_kind=score.kind,
                        score_value=score.value,
                        score_unit=score.unit,
                        method=score.method,
                        method_version=score.method_version,
                        rmsd_to_rank1=pose_metrics.get("rmsd_to_rank1"),
                        ligand_efficiency=pose_metrics.get(
                            "ligand_efficiency"
                        ),
                        cluster_id=clusters_by_pose.get(score.pose_id),
                    )
                )

        return tuple(
            sorted(
                rows,
                key=lambda row: (
                    row.ligand_id,
                    row.method,
                    row.score_kind,
                    row.rank is None,
                    row.rank if row.rank is not None else 10**9,
                    row.score_value,
                    row.pose_id,
                ),
            )
        )

    def _narrative(
        self,
        report: PipelineReport,
        poses: tuple[ScientificPoseResult, ...],
    ) -> ScientificNarrative:
        ligand_ids = sorted({task.ligand_id for task in report.tasks})
        receptor = report.receptor_id or "the selected receptor"
        ligand_label = (
            ligand_ids[0]
            if len(ligand_ids) == 1
            else f"{len(ligand_ids)} ligands"
        )
        title = f"Molecular Docking Study — {ligand_label} / {receptor}"
        objective = (
            f"Evaluate docking poses generated for {ligand_label} against "
            f"{receptor} within the configured search region, while preserving "
            "method-specific score semantics and reproducible execution state."
        )

        if report.failed_count:
            outcome = (
                f"The experiment did not complete successfully: "
                f"{report.failed_count} of {report.task_count} docking task(s) "
                "failed. Scientific interpretation is therefore limited."
            )
        elif not poses:
            outcome = (
                "The execution completed without persisted score observations. "
                "No score-based scientific interpretation can be made."
            )
        else:
            values = [pose.score_value for pose in poses]
            units = sorted({pose.score_unit or "" for pose in poses})
            methods = sorted({(pose.method, pose.score_kind) for pose in poses})
            unit = units[0] if len(units) == 1 else "method-specific units"
            outcome = (
                f"The experiment produced {len(poses)} scored pose(s). "
                f"Observed values ranged from {min(values):g} to "
                f"{max(values):g} {unit} across "
                f"{len(methods)} score family/families."
            )

        interpretation: list[str] = []
        conclusion = (
            "The current durable results support descriptive reporting only; "
            "no pose-level scientific conclusion is justified yet."
        )
        limitations = [
            (
                "Docking scores are model outputs and do not by themselves "
                "establish experimental binding affinity, potency, or "
                "biological activity."
            ),
            (
                "Comparisons are valid only within the same scoring method, "
                "score kind, version, and unit."
            ),
        ]
        next_steps: list[str] = []

        groups: dict[
            tuple[str, str, str | None],
            list[ScientificPoseResult],
        ] = {}
        for pose in poses:
            groups.setdefault(
                (pose.method, pose.score_kind, pose.score_unit),
                [],
            ).append(pose)

        for (method, kind, unit), group in sorted(groups.items()):
            ranked = sorted(
                (pose for pose in group if pose.rank is not None),
                key=lambda pose: pose.rank or 10**9,
            )
            if kind == "vina_affinity" and method == "vina" and ranked:
                top = ranked[0]
                suffix = f" {unit}" if unit else ""
                interpretation.append(
                    f"Within Vina affinity scoring, rank 1 was "
                    f"{top.score_value:g}{suffix}."
                )
                if len(ranked) > 1:
                    gap = ranked[1].score_value - top.score_value
                    interpretation.append(
                        f"The rank-1 to rank-2 score gap was "
                        f"{gap:g}{suffix}; this describes separation within "
                        "the Vina scoring function, not experimental affinity."
                    )
                    conclusion = (
                        f"Within this Vina run, rank 1 is the scoring-function "
                        f"preferred pose and is separated from rank 2 by "
                        f"{gap:g}{suffix}. This supports prioritizing rank 1 "
                        "for structural follow-up, not claiming experimental "
                        "binding superiority."
                    )
                else:
                    conclusion = (
                        "The available Vina result identifies a rank-1 pose, "
                        "but there is no second ranked pose with which to "
                        "evaluate score separation."
                    )
            elif ranked:
                interpretation.append(
                    f"{len(ranked)} ranked pose(s) were persisted for "
                    f"{method}/{kind}; no cross-method ordering was inferred."
                )
                conclusion = (
                    f"The {method}/{kind} results support prioritization only "
                    "within that score family; no cross-method conclusion was "
                    "derived."
                )

        if not interpretation:
            interpretation.append(
                "The current durable state supports descriptive reporting only; "
                "no stronger pose preference statement is justified."
            )

        if poses:
            analyzed = [
                pose
                for pose in poses
                if pose.rmsd_to_rank1 is not None
            ]
            if analyzed:
                clusters = {
                    pose.cluster_id
                    for pose in analyzed
                    if pose.cluster_id is not None
                }
                rank1_cluster = next(
                    (
                        pose.cluster_id
                        for pose in analyzed
                        if pose.rank == 1
                    ),
                    None,
                )
                rank1_cluster_size = sum(
                    pose.cluster_id == rank1_cluster
                    for pose in analyzed
                    if rank1_cluster is not None
                )
                interpretation.append(
                    f"Structural analysis grouped {len(analyzed)} pose(s) "
                    f"into {len(clusters)} RMSD cluster(s) at the configured "
                    "2.0 Å threshold."
                )
                if rank1_cluster is not None:
                    interpretation.append(
                        f"The rank-1 cluster contains {rank1_cluster_size} "
                        "pose(s), providing a direct view of pose convergence "
                        "around the scoring-function preferred solution."
                    )
                    peer_count = max(0, rank1_cluster_size - 1)
                    if peer_count:
                        conclusion += (
                            f" Structurally, rank 1 shares its 2.0 Å RMSD "
                            f"cluster with {peer_count} additional pose(s)."
                        )
                    if len(clusters) > 1:
                        conclusion += (
                            f" The {len(analyzed)} analyzed poses span "
                            f"{len(clusters)} clusters at this threshold, "
                            "so the generated modes retain substantial "
                            "structural diversity."
                        )
                limitations.append(
                    "RMSD v1 is a heavy-atom, atom-order, direct coordinate "
                    "RMSD in the receptor frame; it is not symmetry-corrected "
                    "and does not perform an additional structural alignment."
                )
            else:
                limitations.append(
                    "No durable RMSD or clustering observations were available."
                )

            efficient = [
                pose
                for pose in poses
                if pose.ligand_efficiency is not None
            ]
            if efficient:
                top = next(
                    (pose for pose in efficient if pose.rank == 1),
                    efficient[0],
                )
                interpretation.append(
                    f"Rank 1 ligand efficiency was "
                    f"{top.ligand_efficiency:g} kcal/mol/heavy_atom, derived "
                    "from the Vina score and ligand heavy-atom count."
                )
                limitations.append(
                    "Docking-derived ligand efficiency is a size-normalized "
                    "scoring descriptor, not an experimental thermodynamic "
                    "ligand efficiency measurement."
                )

            limitations.append(
                "Protein-ligand contact chemistry is not yet included: "
                "hydrogen bonds, hydrophobic contacts, salt bridges, and "
                "residue-level interaction fingerprints remain the next "
                "analysis layer."
            )
            next_steps.extend(
                [
                    "Inspect the leading RMSD cluster structurally in the binding site.",
                    "Characterize protein-ligand contacts for the leading pose families.",
                    "Add chemistry-aware hydrogen-bond and hydrophobic-contact profiling.",
                ]
            )
        if report.failed_count:
            conclusion = (
                "No scientific docking conclusion should be drawn until the "
                "failed execution state is resolved."
            )
            next_steps.insert(
                0,
                "Resolve failed docking tasks before drawing scientific conclusions.",
            )

        return ScientificNarrative(
            title=title,
            objective=objective,
            outcome=outcome,
            conclusion=conclusion,
            interpretation=tuple(interpretation),
            limitations=tuple(limitations),
            next_steps=tuple(next_steps),
        )
