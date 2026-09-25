import pytest

from moldock.domain import DockingPose, DomainValidationError


def make_pose(**overrides):
    values = dict(
        task_id="task_1",
        attempt_id="attempt_1",
        rank=1,
        score=-8.7,
        pose_artifact_uri="s3://dock/run/pose-1.pdbqt",
    )
    values.update(overrides)
    return DockingPose(**values)


def test_pose_identity_is_deterministic():
    assert make_pose().pose_id == make_pose().pose_id


def test_pose_rank_starts_at_one():
    with pytest.raises(DomainValidationError):
        make_pose(rank=0)


@pytest.mark.parametrize(
    "field",
    ["task_id", "attempt_id", "pose_artifact_uri"],
)
def test_pose_rejects_blank_required_metadata(field):
    with pytest.raises(DomainValidationError):
        make_pose(**{field: " "})
