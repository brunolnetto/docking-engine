from __future__ import annotations

from collections import defaultdict
from threading import RLock
from typing import Protocol, runtime_checkable

from moldock.domain import (
    DomainValidationError,
    Pose,
    PoseRanking,
    PoseScore,
)


@runtime_checkable
class ScientificResultRepository(Protocol):
    def register_pose(self, pose: Pose) -> None: ...
    def register_score(self, score: PoseScore) -> None: ...
    def register_ranking(self, ranking: PoseRanking) -> None: ...
    def list_poses_for_attempt(self, attempt_id: str) -> tuple[Pose, ...]: ...
    def list_scores_for_pose(self, pose_id: str) -> tuple[PoseScore, ...]: ...
    def list_rankings_for_pose(self, pose_id: str) -> tuple[PoseRanking, ...]: ...


class InMemoryScientificResultRepository:
    def __init__(self) -> None:
        self._poses: dict[str, Pose] = {}
        self._scores: dict[str, PoseScore] = {}
        self._rankings: dict[str, PoseRanking] = {}
        self._pose_ids_by_attempt: dict[str, list[str]] = defaultdict(list)
        self._score_ids_by_pose: dict[str, list[str]] = defaultdict(list)
        self._ranking_ids_by_pose: dict[str, list[str]] = defaultdict(list)
        self._lock = RLock()

    def register_pose(self, pose: Pose) -> None:
        with self._lock:
            existing = self._poses.get(pose.pose_id)
            if existing is None:
                self._poses[pose.pose_id] = pose
                self._pose_ids_by_attempt[pose.attempt_id].append(pose.pose_id)
                return
            if existing != pose:
                raise DomainValidationError(
                    "pose identity already exists with conflicting metadata"
                )

    def register_score(self, score: PoseScore) -> None:
        with self._lock:
            if score.pose_id not in self._poses:
                raise DomainValidationError(
                    f"cannot register score for unknown pose: {score.pose_id}"
                )
            existing = self._scores.get(score.score_id)
            if existing is None:
                self._scores[score.score_id] = score
                self._score_ids_by_pose[score.pose_id].append(score.score_id)
                return
            if existing != score:
                raise DomainValidationError(
                    "score identity already exists with conflicting metadata"
                )

    def register_ranking(self, ranking: PoseRanking) -> None:
        with self._lock:
            if ranking.pose_id not in self._poses:
                raise DomainValidationError(
                    f"cannot register ranking for unknown pose: {ranking.pose_id}"
                )
            existing = self._rankings.get(ranking.ranking_id)
            if existing is None:
                self._rankings[ranking.ranking_id] = ranking
                self._ranking_ids_by_pose[ranking.pose_id].append(
                    ranking.ranking_id
                )
                return
            if existing != ranking:
                raise DomainValidationError(
                    "ranking identity already exists with conflicting metadata"
                )

    def list_poses_for_attempt(self, attempt_id: str) -> tuple[Pose, ...]:
        with self._lock:
            poses = (
                self._poses[pose_id]
                for pose_id in self._pose_ids_by_attempt.get(attempt_id, ())
            )
            return tuple(sorted(poses, key=lambda pose: pose.model_index))

    def list_scores_for_pose(self, pose_id: str) -> tuple[PoseScore, ...]:
        with self._lock:
            return tuple(
                self._scores[score_id]
                for score_id in sorted(
                    self._score_ids_by_pose.get(pose_id, ())
                )
            )

    def list_rankings_for_pose(self, pose_id: str) -> tuple[PoseRanking, ...]:
        with self._lock:
            rankings = (
                self._rankings[ranking_id]
                for ranking_id in self._ranking_ids_by_pose.get(pose_id, ())
            )
            return tuple(sorted(rankings, key=lambda ranking: ranking.rank))
