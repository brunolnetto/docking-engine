from moldock.domain import Pose, PoseRanking, PoseScore, ScoreKind


def test_pose_score_and_ranking_identities_are_independent():
    pose = Pose(
        task_id="task_1",
        attempt_id="attempt_1",
        source_artifact_id="artifact_1",
        model_index=1,
        geometry_sha256="a" * 64,
    )
    score = PoseScore(
        pose_id=pose.pose_id,
        kind=ScoreKind.VINA_AFFINITY,
        value=-8.7,
        unit="kcal/mol",
        method="vina",
        method_version="1.2.7",
    )
    ranking = PoseRanking(
        pose_id=pose.pose_id,
        rank=1,
        method="vina_affinity",
    )

    assert pose.pose_id.startswith("pose_")
    assert score.score_id.startswith("score_")
    assert ranking.ranking_id.startswith("ranking_")
