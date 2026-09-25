import pytest

from moldock.domain import DockingPose, DomainValidationError


def test_pose_identity_is_deterministic():
    a = DockingPose(
        task_id="task_1",
        attempt_id="attempt_1",
        rank=1,
        score=-8.7,
        pose_artifact_uri="s3://dock/run/pose-1.pdbqt",
    )
    b = DockingPose(
        task_id="task_1",
        attempt_id="attempt_1",
        rank=1,
        score=-8.7,
        pose_artifact_uri="s3://dock/run/pose-1.pdbqt",
    )

    assert a.pose_id == b.pose_id


def test_pose_rank_starts_at_one():
    with pytest.raises(DomainValidationError):
        DockingPose(
            task_id="task_1",
            attempt_id="attempt_1",
            rank=0,
            score=-8.7,
            pose_artifact_uri="s3://dock/run/pose-1.pdbqt",
        )
