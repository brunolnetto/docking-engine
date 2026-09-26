from __future__ import annotations

from pathlib import Path

from moldock.domain import (
    DomainValidationError,
    InteractionKind,
    Pose,
    PoseClusterAssignment,
    PoseMetric,
    PoseMetricKind,
    PoseInteraction,
    PoseRanking,
    PoseScore,
    ScoreKind,
)
from moldock.repositories.ducklake_base import DuckLakeRepositoryBase
from moldock.repositories.metadata_codec import decode_metadata, encode_metadata


class DuckLakeScientificResultRepository(DuckLakeRepositoryBase):
    def __init__(
        self,
        *,
        catalog_path: str | Path,
        data_path: str | Path,
        max_transaction_retries: int = 5,
        retry_delay_seconds: float = 0.01,
    ) -> None:
        super().__init__(
            catalog_path=catalog_path,
            data_path=data_path,
            max_transaction_retries=max_transaction_retries,
            retry_delay_seconds=retry_delay_seconds,
        )
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        def operation() -> None:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS moldock.poses (
                    pose_id VARCHAR,
                    task_id VARCHAR,
                    attempt_id VARCHAR,
                    source_artifact_id VARCHAR,
                    model_index INTEGER,
                    geometry_sha256 VARCHAR
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS moldock.pose_scores (
                    score_id VARCHAR,
                    pose_id VARCHAR,
                    kind VARCHAR,
                    value DOUBLE,
                    unit VARCHAR,
                    method VARCHAR,
                    method_version VARCHAR,
                    metadata_json VARCHAR
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS moldock.pose_rankings (
                    ranking_id VARCHAR,
                    pose_id VARCHAR,
                    rank INTEGER,
                    method VARCHAR
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS moldock.pose_metrics (
                    metric_id VARCHAR,
                    pose_id VARCHAR,
                    kind VARCHAR,
                    value DOUBLE,
                    unit VARCHAR,
                    method VARCHAR,
                    method_version VARCHAR,
                    metadata_json VARCHAR
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS moldock.pose_interactions (
                    interaction_id VARCHAR,
                    pose_id VARCHAR,
                    kind VARCHAR,
                    receptor_residue VARCHAR,
                    receptor_atom VARCHAR,
                    ligand_atom VARCHAR,
                    distance_angstrom DOUBLE,
                    angle_degrees DOUBLE,
                    protein_is_donor BOOLEAN,
                    method VARCHAR,
                    method_version VARCHAR,
                    metadata_json VARCHAR
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS moldock.pose_cluster_assignments (
                    assignment_id VARCHAR,
                    pose_id VARCHAR,
                    cluster_id VARCHAR,
                    method VARCHAR,
                    method_version VARCHAR,
                    metadata_json VARCHAR
                )
                """
            )

        self._run_write(operation)

    def register_pose(self, pose: Pose) -> None:
        def operation() -> None:
            rows = self._pose_rows(pose.pose_id)
            if rows:
                current = self._pose_from_row(rows[0])
                if current != pose:
                    raise DomainValidationError(
                        "pose identity already exists with conflicting metadata"
                    )
                return
            self._connection.execute(
                """
                INSERT INTO moldock.poses
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    pose.pose_id,
                    pose.task_id,
                    pose.attempt_id,
                    pose.source_artifact_id,
                    pose.model_index,
                    pose.geometry_sha256,
                ],
            )

        self._run_write(operation)

    def register_score(self, score: PoseScore) -> None:
        def operation() -> None:
            self._require_pose(score.pose_id, "score")
            rows = self._score_rows(score.score_id)
            if rows:
                current = self._score_from_row(rows[0])
                if current != score:
                    raise DomainValidationError(
                        "score identity already exists with conflicting metadata"
                    )
                return
            self._connection.execute(
                """
                INSERT INTO moldock.pose_scores
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    score.score_id,
                    score.pose_id,
                    score.kind.value,
                    score.value,
                    score.unit,
                    score.method,
                    score.method_version,
                    encode_metadata(score.metadata),
                ],
            )

        self._run_write(operation)

    def register_ranking(self, ranking: PoseRanking) -> None:
        def operation() -> None:
            self._require_pose(ranking.pose_id, "ranking")
            rows = self._ranking_rows(ranking.ranking_id)
            if rows:
                current = self._ranking_from_row(rows[0])
                if current != ranking:
                    raise DomainValidationError(
                        "ranking identity already exists with conflicting metadata"
                    )
                return
            self._connection.execute(
                """
                INSERT INTO moldock.pose_rankings
                VALUES (?, ?, ?, ?)
                """,
                [
                    ranking.ranking_id,
                    ranking.pose_id,
                    ranking.rank,
                    ranking.method,
                ],
            )

        self._run_write(operation)

    def register_metric(self, metric: PoseMetric) -> None:
        def operation() -> None:
            self._require_pose(metric.pose_id, "metric")
            rows = self._metric_rows(metric.metric_id)
            if rows:
                current = self._metric_from_row(rows[0])
                if current != metric:
                    raise DomainValidationError(
                        "metric identity already exists with conflicting metadata"
                    )
                return
            self._connection.execute(
                """
                INSERT INTO moldock.pose_metrics
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    metric.metric_id,
                    metric.pose_id,
                    metric.kind.value,
                    metric.value,
                    metric.unit,
                    metric.method,
                    metric.method_version,
                    encode_metadata(metric.metadata),
                ],
            )

        self._run_write(operation)

    def register_interaction(self, interaction: PoseInteraction) -> None:
        def operation() -> None:
            self._require_pose(interaction.pose_id, "interaction")
            rows = self._interaction_rows(interaction.interaction_id)
            if rows:
                current = self._interaction_from_row(rows[0])
                if current != interaction:
                    raise DomainValidationError(
                        "interaction identity already exists "
                        "with conflicting metadata"
                    )
                return
            self._connection.execute(
                """
                INSERT INTO moldock.pose_interactions
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    interaction.interaction_id,
                    interaction.pose_id,
                    interaction.kind.value,
                    interaction.receptor_residue,
                    interaction.receptor_atom,
                    interaction.ligand_atom,
                    interaction.distance_angstrom,
                    interaction.angle_degrees,
                    interaction.protein_is_donor,
                    interaction.method,
                    interaction.method_version,
                    encode_metadata(interaction.metadata),
                ],
            )

        self._run_write(operation)

    def register_cluster_assignment(
        self,
        assignment: PoseClusterAssignment,
    ) -> None:
        def operation() -> None:
            self._require_pose(
                assignment.pose_id,
                "cluster assignment",
            )
            rows = self._cluster_rows(assignment.assignment_id)
            if rows:
                current = self._cluster_from_row(rows[0])
                if current != assignment:
                    raise DomainValidationError(
                        "cluster assignment identity already exists "
                        "with conflicting metadata"
                    )
                return
            self._connection.execute(
                """
                INSERT INTO moldock.pose_cluster_assignments
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    assignment.assignment_id,
                    assignment.pose_id,
                    assignment.cluster_id,
                    assignment.method,
                    assignment.method_version,
                    encode_metadata(assignment.metadata),
                ],
            )

        self._run_write(operation)

    def list_poses_for_attempt(
        self,
        attempt_id: str,
    ) -> tuple[Pose, ...]:
        rows = self._connection.execute(
            """
            SELECT
                pose_id,
                task_id,
                attempt_id,
                source_artifact_id,
                model_index,
                geometry_sha256
            FROM moldock.poses
            WHERE attempt_id = ?
            ORDER BY model_index, pose_id
            """,
            [attempt_id],
        ).fetchall()
        return tuple(self._pose_from_row(row) for row in rows)

    def list_scores_for_pose(
        self,
        pose_id: str,
    ) -> tuple[PoseScore, ...]:
        rows = self._connection.execute(
            """
            SELECT
                score_id,
                pose_id,
                kind,
                value,
                unit,
                method,
                method_version,
                metadata_json
            FROM moldock.pose_scores
            WHERE pose_id = ?
            ORDER BY score_id
            """,
            [pose_id],
        ).fetchall()
        return tuple(self._score_from_row(row) for row in rows)

    def list_rankings_for_pose(
        self,
        pose_id: str,
    ) -> tuple[PoseRanking, ...]:
        rows = self._connection.execute(
            """
            SELECT ranking_id, pose_id, rank, method
            FROM moldock.pose_rankings
            WHERE pose_id = ?
            ORDER BY rank, ranking_id
            """,
            [pose_id],
        ).fetchall()
        return tuple(self._ranking_from_row(row) for row in rows)

    def list_metrics_for_pose(
        self,
        pose_id: str,
    ) -> tuple[PoseMetric, ...]:
        rows = self._connection.execute(
            """
            SELECT
                metric_id,
                pose_id,
                kind,
                value,
                unit,
                method,
                method_version,
                metadata_json
            FROM moldock.pose_metrics
            WHERE pose_id = ?
            ORDER BY metric_id
            """,
            [pose_id],
        ).fetchall()
        return tuple(self._metric_from_row(row) for row in rows)

    def list_interactions_for_pose(
        self,
        pose_id: str,
    ) -> tuple[PoseInteraction, ...]:
        rows = self._connection.execute(
            """
            SELECT
                interaction_id,
                pose_id,
                kind,
                receptor_residue,
                receptor_atom,
                ligand_atom,
                distance_angstrom,
                angle_degrees,
                protein_is_donor,
                method,
                method_version,
                metadata_json
            FROM moldock.pose_interactions
            WHERE pose_id = ?
            ORDER BY interaction_id
            """,
            [pose_id],
        ).fetchall()
        return tuple(self._interaction_from_row(row) for row in rows)

    def list_cluster_assignments_for_pose(
        self,
        pose_id: str,
    ) -> tuple[PoseClusterAssignment, ...]:
        rows = self._connection.execute(
            """
            SELECT
                assignment_id,
                pose_id,
                cluster_id,
                method,
                method_version,
                metadata_json
            FROM moldock.pose_cluster_assignments
            WHERE pose_id = ?
            ORDER BY assignment_id
            """,
            [pose_id],
        ).fetchall()
        return tuple(self._cluster_from_row(row) for row in rows)

    def _require_pose(self, pose_id: str, object_name: str) -> None:
        if not self._pose_rows(pose_id):
            raise DomainValidationError(
                f"cannot register {object_name} for unknown pose: {pose_id}"
            )

    def _pose_rows(self, pose_id: str):
        return self._connection.execute(
            """
            SELECT
                pose_id,
                task_id,
                attempt_id,
                source_artifact_id,
                model_index,
                geometry_sha256
            FROM moldock.poses
            WHERE pose_id = ?
            """,
            [pose_id],
        ).fetchall()

    def _score_rows(self, score_id: str):
        return self._connection.execute(
            """
            SELECT
                score_id,
                pose_id,
                kind,
                value,
                unit,
                method,
                method_version,
                metadata_json
            FROM moldock.pose_scores
            WHERE score_id = ?
            """,
            [score_id],
        ).fetchall()

    def _ranking_rows(self, ranking_id: str):
        return self._connection.execute(
            """
            SELECT ranking_id, pose_id, rank, method
            FROM moldock.pose_rankings
            WHERE ranking_id = ?
            """,
            [ranking_id],
        ).fetchall()

    def _metric_rows(self, metric_id: str):
        return self._connection.execute(
            """
            SELECT
                metric_id,
                pose_id,
                kind,
                value,
                unit,
                method,
                method_version,
                metadata_json
            FROM moldock.pose_metrics
            WHERE metric_id = ?
            """,
            [metric_id],
        ).fetchall()

    def _interaction_rows(self, interaction_id: str):
        return self._connection.execute(
            """
            SELECT
                interaction_id,
                pose_id,
                kind,
                receptor_residue,
                receptor_atom,
                ligand_atom,
                distance_angstrom,
                angle_degrees,
                protein_is_donor,
                method,
                method_version,
                metadata_json
            FROM moldock.pose_interactions
            WHERE interaction_id = ?
            """,
            [interaction_id],
        ).fetchall()

    def _cluster_rows(self, assignment_id: str):
        return self._connection.execute(
            """
            SELECT
                assignment_id,
                pose_id,
                cluster_id,
                method,
                method_version,
                metadata_json
            FROM moldock.pose_cluster_assignments
            WHERE assignment_id = ?
            """,
            [assignment_id],
        ).fetchall()

    @staticmethod
    def _pose_from_row(row) -> Pose:
        return Pose(
            task_id=row[1],
            attempt_id=row[2],
            source_artifact_id=row[3],
            model_index=row[4],
            geometry_sha256=row[5],
        )

    @staticmethod
    def _score_from_row(row) -> PoseScore:
        return PoseScore(
            pose_id=row[1],
            kind=ScoreKind(row[2]),
            value=row[3],
            unit=row[4],
            method=row[5],
            method_version=row[6],
            metadata=decode_metadata(row[7]),
        )

    @staticmethod
    def _ranking_from_row(row) -> PoseRanking:
        return PoseRanking(
            pose_id=row[1],
            rank=row[2],
            method=row[3],
        )

    @staticmethod
    def _metric_from_row(row) -> PoseMetric:
        return PoseMetric(
            pose_id=row[1],
            kind=PoseMetricKind(row[2]),
            value=row[3],
            unit=row[4],
            method=row[5],
            method_version=row[6],
            metadata=decode_metadata(row[7]),
        )

    @staticmethod
    def _interaction_from_row(row) -> PoseInteraction:
        return PoseInteraction(
            pose_id=row[1],
            kind=InteractionKind(row[2]),
            receptor_residue=row[3],
            receptor_atom=row[4],
            ligand_atom=row[5],
            distance_angstrom=row[6],
            angle_degrees=row[7],
            protein_is_donor=row[8],
            method=row[9],
            method_version=row[10],
            metadata=decode_metadata(row[11]),
        )

    @staticmethod
    def _cluster_from_row(row) -> PoseClusterAssignment:
        return PoseClusterAssignment(
            pose_id=row[1],
            cluster_id=row[2],
            method=row[3],
            method_version=row[4],
            metadata=decode_metadata(row[5]),
        )
