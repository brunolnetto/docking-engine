from __future__ import annotations

import json
from pathlib import Path

from moldock.domain import (
    DomainValidationError,
    Pose,
    PoseRanking,
    PoseScore,
    ScoreKind,
)
from moldock.domain.common import canonical_json
from moldock.repositories.ducklake_base import DuckLakeRepositoryBase


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
            if not self._pose_rows(score.pose_id):
                raise DomainValidationError(
                    f"cannot register score for unknown pose: {score.pose_id}"
                )
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
                    canonical_json(score.metadata),
                ],
            )

        self._run_write(operation)

    def register_ranking(self, ranking: PoseRanking) -> None:
        def operation() -> None:
            if not self._pose_rows(ranking.pose_id):
                raise DomainValidationError(
                    f"cannot register ranking for unknown pose: {ranking.pose_id}"
                )
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
            SELECT
                ranking_id,
                pose_id,
                rank,
                method
            FROM moldock.pose_rankings
            WHERE pose_id = ?
            ORDER BY rank, ranking_id
            """,
            [pose_id],
        ).fetchall()
        return tuple(self._ranking_from_row(row) for row in rows)

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
            metadata=json.loads(row[7]),
        )

    @staticmethod
    def _ranking_from_row(row) -> PoseRanking:
        return PoseRanking(
            pose_id=row[1],
            rank=row[2],
            method=row[3],
        )
