import pytest

from moldock.domain import (
    DomainValidationError,
    Pose,
    PoseRanking,
    PoseScore,
    ScoreKind,
)


def make_pose(**overrides):
    values = dict(
        task_id="task_1",
        attempt_id="attempt_1",
        source_artifact_id="artifact_1",
        model_index=1,
        geometry_sha256="a" * 64,
    )
    values.update(overrides)
    return Pose(**values)


def test_pose_identity_depends_on_geometry_not_score_or_rank():
    pose = make_pose()

    assert pose.pose_id == make_pose().pose_id


@pytest.mark.parametrize(
    "field",
    ["task_id", "attempt_id", "source_artifact_id"],
)
def test_pose_rejects_blank_identifiers(field):
    with pytest.raises(DomainValidationError):
        make_pose(**{field: " "})


def test_pose_rejects_invalid_geometry_hash_and_model_index():
    with pytest.raises(DomainValidationError):
        make_pose(geometry_sha256="bad")

    with pytest.raises(DomainValidationError):
        make_pose(model_index=0)


def test_pose_score_has_explicit_semantics():
    pose = make_pose()
    score = PoseScore(
        pose_id=pose.pose_id,
        kind=ScoreKind.VINA_AFFINITY,
        value=-8.7,
        unit="kcal/mol",
        method="vina",
        method_version="1.2.x",
    )

    assert score.kind is ScoreKind.VINA_AFFINITY
    assert score.value == -8.7


def test_pose_score_rejects_untyped_kind():
    pose = make_pose()

    with pytest.raises(DomainValidationError, match="ScoreKind"):
        PoseScore(
            pose_id=pose.pose_id,
            kind="vina_affinity",
            value=-8.7,
            unit="kcal/mol",
            method="vina",
            method_version="1.2.x",
        )


def test_ranking_is_separate_from_pose_identity():
    pose = make_pose()
    ranking = PoseRanking(
        pose_id=pose.pose_id,
        rank=1,
        method="vina_affinity",
    )

    assert ranking.pose_id == pose.pose_id
    assert ranking.rank == 1


@pytest.mark.parametrize("rank", [0, -1])
def test_ranking_starts_at_one(rank):
    with pytest.raises(DomainValidationError):
        PoseRanking(pose_id="pose_1", rank=rank, method="vina_affinity")
