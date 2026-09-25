import pytest

from moldock.domain import (
    DomainValidationError,
    Pose,
    PoseRanking,
    PoseScore,
    ScoreKind,
)
from moldock.results import InMemoryScientificResultRepository, ScientificResultRepository


def make_pose(index=1, sha="a" * 64):
    return Pose(
        task_id="task_1",
        attempt_id="attempt_1",
        source_artifact_id="artifact_1",
        model_index=index,
        geometry_sha256=sha,
    )


def test_memory_repository_implements_contract():
    assert isinstance(InMemoryScientificResultRepository(), ScientificResultRepository)


def test_repository_registers_and_lists_pose_data():
    repo = InMemoryScientificResultRepository()
    pose = make_pose()
    score = PoseScore(
        pose_id=pose.pose_id,
        kind=ScoreKind.VINA_AFFINITY,
        value=-8.0,
        unit="kcal/mol",
        method="vina",
        method_version="1.2.7",
    )
    ranking = PoseRanking(pose_id=pose.pose_id, rank=1, method="vina_affinity")

    repo.register_pose(pose)
    repo.register_score(score)
    repo.register_ranking(ranking)

    assert repo.list_poses_for_attempt("attempt_1") == (pose,)
    assert repo.list_scores_for_pose(pose.pose_id) == (score,)
    assert repo.list_rankings_for_pose(pose.pose_id) == (ranking,)


def test_repository_registration_is_idempotent_but_rejects_conflicts():
    repo = InMemoryScientificResultRepository()
    pose = make_pose()
    repo.register_pose(pose)
    repo.register_pose(pose)

    conflicting = Pose(
        task_id=pose.task_id,
        attempt_id=pose.attempt_id,
        source_artifact_id=pose.source_artifact_id,
        model_index=pose.model_index,
        geometry_sha256="b" * 64,
    )

    assert conflicting.pose_id != pose.pose_id
    repo.register_pose(conflicting)

    with pytest.raises(DomainValidationError):
        repo.register_score(
            PoseScore(
                pose_id="missing",
                kind=ScoreKind.VINA_AFFINITY,
                value=-7.0,
                unit="kcal/mol",
                method="vina",
                method_version="1.2.7",
            )
        )
