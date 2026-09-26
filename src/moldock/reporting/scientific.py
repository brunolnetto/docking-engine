from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from moldock.domain import TaskStatus

from .model import PipelineReport


@dataclass(frozen=True, slots=True)
class ScientificPoseResult:
    ligand_id: str
    pose_id: str
    attempt_id: str | None
    rank: int | None
    score_kind: str
    score_value: float
    score_unit: str | None
    method: str
    method_version: str
    rmsd_to_rank1: float | None = None
    ligand_efficiency: float | None = None
    cluster_id: str | None = None
    contact_count: int = 0
    hydrophobic_contact_count: int = 0
    hydrogen_bond_count: int = 0
    salt_bridge_count: int = 0
    contact_residues: tuple[str, ...] = ()
    hydrophobic_residues: tuple[str, ...] = ()
    hydrogen_bond_residues: tuple[str, ...] = ()
    salt_bridge_residues: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResidueSupport:
    interaction_kind: str
    residue_label: str
    pose_count: int
    cluster_size: int

    @property
    def fraction(self) -> float:
        return self.pose_count / self.cluster_size


@dataclass(frozen=True, slots=True)
class PoseEvidenceSummary:
    ligand_id: str
    pose_id: str
    attempt_id: str | None
    rank: int | None
    score_kind: str
    score_value: float
    score_unit: str | None
    method: str
    method_version: str
    delta_to_rank1: float | None
    rmsd_to_rank1: float | None
    cluster_id: str | None
    cluster_size: int | None
    ligand_efficiency: float | None
    hydrogen_bond_residues: tuple[str, ...]
    hydrophobic_residues: tuple[str, ...]
    cluster_hydrogen_bond_support: tuple[ResidueSupport, ...] = ()
    cluster_hydrophobic_support: tuple[ResidueSupport, ...] = ()


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
    evidence: tuple[PoseEvidenceSummary, ...]
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
        evidence = self._evidence(poses)
        narrative = self._narrative(report, poses, evidence)
        return ScientificExperimentReport(
            source=report,
            poses=poses,
            evidence=evidence,
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
            interactions_by_pose: dict[str, list] = {}
            for interaction in task.interactions:
                interactions_by_pose.setdefault(
                    interaction.pose_id,
                    [],
                ).append(interaction)
            for score in task.scores:
                if (
                    task.status is TaskStatus.SUCCEEDED
                    and task.final_attempt_id is not None
                    and score.attempt_id is not None
                    and score.attempt_id != task.final_attempt_id
                ):
                    continue
                if not isfinite(score.value):
                    continue
                pose_metrics = metrics_by_pose.get(score.pose_id, {})
                interactions = interactions_by_pose.get(score.pose_id, [])
                contacts = [
                    item for item in interactions
                    if item.kind == "contact"
                ]
                hydrophobic = [
                    item for item in interactions
                    if item.kind == "hydrophobic_contact"
                ]
                hydrogen_bonds = [
                    item for item in interactions
                    if item.kind == "hydrogen_bond"
                ]
                salt_bridges = [
                    item for item in interactions
                    if item.kind == "salt_bridge"
                ]
                rows.append(
                    ScientificPoseResult(
                        ligand_id=task.ligand_id,
                        pose_id=score.pose_id,
                        attempt_id=score.attempt_id,
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
                        contact_count=len(contacts),
                        hydrophobic_contact_count=len(hydrophobic),
                        hydrogen_bond_count=len(hydrogen_bonds),
                        salt_bridge_count=len(salt_bridges),
                        contact_residues=tuple(
                            sorted({item.residue_label for item in contacts})
                        ),
                        hydrophobic_residues=tuple(
                            sorted(
                                {
                                    item.residue_label
                                    for item in hydrophobic
                                }
                            )
                        ),
                        hydrogen_bond_residues=tuple(
                            sorted(
                                {
                                    item.residue_label
                                    for item in hydrogen_bonds
                                }
                            )
                        ),
                        salt_bridge_residues=tuple(
                            sorted(
                                {
                                    item.residue_label
                                    for item in salt_bridges
                                }
                            )
                        ),
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

    def _evidence(
        self,
        poses: tuple[ScientificPoseResult, ...],
    ) -> tuple[PoseEvidenceSummary, ...]:
        by_family: dict[
            tuple[str, str | None, str, str, str, str | None],
            list[ScientificPoseResult],
        ] = {}
        for pose in poses:
            by_family.setdefault(
                (
                    pose.ligand_id,
                    pose.attempt_id,
                    pose.method,
                    pose.method_version,
                    pose.score_kind,
                    pose.score_unit,
                ),
                [],
            ).append(pose)

        evidence: list[PoseEvidenceSummary] = []
        for family in by_family.values():
            ranked = sorted(
                family,
                key=lambda pose: (
                    pose.rank is None,
                    pose.rank if pose.rank is not None else 10**9,
                    pose.pose_id,
                ),
            )
            rank_one = next(
                (pose for pose in ranked if pose.rank == 1),
                None,
            )
            cluster_members: dict[str, list[ScientificPoseResult]] = {}
            for pose in ranked:
                if pose.cluster_id is not None:
                    cluster_members.setdefault(
                        pose.cluster_id,
                        [],
                    ).append(pose)

            for pose in ranked:
                members = (
                    cluster_members.get(pose.cluster_id, [])
                    if pose.cluster_id is not None
                    else []
                )
                cluster_size = len(members) if members else None
                hbond_support = self._residue_support(
                    members,
                    interaction_kind="hydrogen_bond",
                )
                hydrophobic_support = self._residue_support(
                    members,
                    interaction_kind="hydrophobic_contact",
                )
                evidence.append(
                    PoseEvidenceSummary(
                        ligand_id=pose.ligand_id,
                        pose_id=pose.pose_id,
                        attempt_id=pose.attempt_id,
                        rank=pose.rank,
                        score_kind=pose.score_kind,
                        score_value=pose.score_value,
                        score_unit=pose.score_unit,
                        method=pose.method,
                        method_version=pose.method_version,
                        delta_to_rank1=(
                            None
                            if rank_one is None
                            else pose.score_value - rank_one.score_value
                        ),
                        rmsd_to_rank1=pose.rmsd_to_rank1,
                        cluster_id=pose.cluster_id,
                        cluster_size=cluster_size,
                        ligand_efficiency=pose.ligand_efficiency,
                        hydrogen_bond_residues=pose.hydrogen_bond_residues,
                        hydrophobic_residues=pose.hydrophobic_residues,
                        cluster_hydrogen_bond_support=hbond_support,
                        cluster_hydrophobic_support=hydrophobic_support,
                    )
                )

        return tuple(
            sorted(
                evidence,
                key=lambda item: (
                    item.ligand_id,
                    item.method,
                    item.method_version,
                    item.score_kind,
                    item.score_unit or "",
                    item.attempt_id or "",
                    item.rank is None,
                    item.rank if item.rank is not None else 10**9,
                    item.pose_id,
                ),
            )
        )

    @staticmethod
    def _residue_support(
        members: list[ScientificPoseResult],
        *,
        interaction_kind: str,
    ) -> tuple[ResidueSupport, ...]:
        if not members:
            return ()
        counts: dict[str, int] = {}
        for pose in members:
            residues = (
                pose.hydrogen_bond_residues
                if interaction_kind == "hydrogen_bond"
                else pose.hydrophobic_residues
            )
            for residue in set(residues):
                counts[residue] = counts.get(residue, 0) + 1
        return tuple(
            ResidueSupport(
                interaction_kind=interaction_kind,
                residue_label=residue,
                pose_count=count,
                cluster_size=len(members),
            )
            for residue, count in sorted(
                counts.items(),
                key=lambda item: (-item[1], item[0]),
            )
        )

    def _narrative(
        self,
        report: PipelineReport,
        poses: tuple[ScientificPoseResult, ...],
        evidence: tuple[PoseEvidenceSummary, ...],
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
            tuple[str, str, str, str | None],
            list[ScientificPoseResult],
        ] = {}
        for pose in poses:
            groups.setdefault(
                (
                    pose.method,
                    pose.method_version,
                    pose.score_kind,
                    pose.score_unit,
                ),
                [],
            ).append(pose)

        for (method, method_version, kind, unit), group in sorted(
            groups.items()
        ):
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
                    f"{method}@{method_version}/{kind}; no cross-method "
                    "or cross-version ordering was inferred."
                )
                conclusion = (
                    f"The {method}@{method_version}/{kind} results support "
                    "prioritization only within that score family; no "
                    "cross-method or cross-version conclusion was derived."
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

            interaction_poses = [
                pose
                for pose in poses
                if (
                    pose.contact_count
                    or pose.hydrophobic_contact_count
                    or pose.hydrogen_bond_count
                    or pose.salt_bridge_count
                )
            ]
            if interaction_poses:
                top = next(
                    (
                        pose
                        for pose in interaction_poses
                        if pose.rank == 1
                    ),
                    interaction_poses[0],
                )
                interpretation.append(
                    f"Rank 1 has {top.contact_count} heavy-atom proximity "
                    f"contact(s), {top.hydrophobic_contact_count} "
                    f"hydrophobic contact(s), and "
                    f"{top.hydrogen_bond_count} geometry-qualified hydrogen "
                    f"bond(s), and {top.salt_bridge_count} putative salt "
                    "bridge(s)."
                )
                if top.hydrogen_bond_residues:
                    interpretation.append(
                        "Rank-1 hydrogen-bond residues: "
                        + ", ".join(top.hydrogen_bond_residues)
                        + "."
                    )
                if top.hydrophobic_residues:
                    interpretation.append(
                        "Rank-1 hydrophobic-contact residues: "
                        + ", ".join(top.hydrophobic_residues)
                        + "."
                    )
                if top.salt_bridge_residues:
                    interpretation.append(
                        "Rank-1 putative salt-bridge residues: "
                        + ", ".join(top.salt_bridge_residues)
                        + "."
                    )
                limitations.append(
                    "Interaction assignments use deterministic PDBQT geometry "
                    "and AutoDock atom types; they are not a substitute for "
                    "a full chemistry-perception package or experimental "
                    "interaction evidence."
                )
                limitations.append(
                    "Salt bridges are putative: protein charge is inferred "
                    "from canonical charged side-chain atoms and ligand charge "
                    "from PDBQT partial-charge thresholds, not a formal-charge "
                    "chemistry model."
                )
                next_steps.extend(
                    [
                        "Compare interaction fingerprints across the leading RMSD cluster.",
                        "Inspect whether rank-1 hydrogen bonds, hydrophobic contacts, and putative salt bridges are chemically plausible in 3D.",
                        "Add aromatic interaction perception as a separate typed interaction family.",
                    ]
                )
            else:
                limitations.append(
                    "No durable receptor-ligand interaction observations were available."
                )
                next_steps.append(
                    "Characterize protein-ligand contacts for the leading pose families."
                )
        if evidence:
            top_evidence = next(
                (item for item in evidence if item.rank == 1),
                evidence[0],
            )
            if top_evidence.cluster_size is not None:
                interpretation.append(
                    f"Rank 1 belongs to an RMSD cluster containing "
                    f"{top_evidence.cluster_size} pose(s)."
                )
            recurrent_hbonds = [
                item
                for item in top_evidence.cluster_hydrogen_bond_support
                if item.pose_count > 1
            ]
            recurrent_hydrophobic = [
                item
                for item in top_evidence.cluster_hydrophobic_support
                if item.pose_count > 1
            ]
            if recurrent_hbonds:
                interpretation.append(
                    "Hydrogen-bond residues recurring within the rank-1 "
                    "cluster: "
                    + ", ".join(
                        f"{item.residue_label} "
                        f"({item.pose_count}/{item.cluster_size} poses)"
                        for item in recurrent_hbonds
                    )
                    + "."
                )
            if recurrent_hydrophobic:
                interpretation.append(
                    "Hydrophobic-contact residues recurring within the "
                    "rank-1 cluster: "
                    + ", ".join(
                        f"{item.residue_label} "
                        f"({item.pose_count}/{item.cluster_size} poses)"
                        for item in recurrent_hydrophobic
                    )
                    + "."
                )
            if recurrent_hbonds or recurrent_hydrophobic:
                conclusion += (
                    " The rank-1 pose family also shows recurring "
                    "residue-level interactions across structurally similar "
                    "poses, providing convergent structural evidence for "
                    "follow-up without creating a cross-signal ranking."
                )
            limitations.append(
                "Cluster interaction support is a pose-family recurrence "
                "summary, not dynamic occupancy from a molecular-dynamics "
                "ensemble."
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
