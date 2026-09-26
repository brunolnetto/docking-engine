import math

import pytest

import moldock.domain.analysis as analysis_module
from moldock.domain import (
    DomainValidationError,
    PoseClusterAssignment,
    PoseMetric,
    PoseMetricKind,
)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"pose_id": ""}, "pose_id"),
        ({"kind": "rmsd_to_rank1"}, "kind"),
        ({"value": math.inf}, "finite"),
        ({"unit": ""}, "unit"),
        ({"method": ""}, "method"),
        ({"method_version": ""}, "method_version"),
    ],
)
def test_pose_metric_validation(kwargs, message):
    values = {
        "pose_id": "pose_1",
        "kind": PoseMetricKind.RMSD_TO_RANK1,
        "value": 1.0,
        "unit": "angstrom",
        "method": "direct_rmsd",
        "method_version": "1",
    }
    values.update(kwargs)

    with pytest.raises(DomainValidationError, match=message):
        PoseMetric(**values)


def test_pose_metric_identity_includes_metadata():
    first = PoseMetric(
        pose_id="pose_1",
        kind=PoseMetricKind.RMSD_TO_RANK1,
        value=1.0,
        unit="angstrom",
        method="direct_rmsd",
        method_version="1",
        metadata={"reference": "pose_0"},
    )
    second = PoseMetric(
        pose_id="pose_1",
        kind=PoseMetricKind.RMSD_TO_RANK1,
        value=1.0,
        unit="angstrom",
        method="direct_rmsd",
        method_version="1",
        metadata={"reference": "pose_2"},
    )

    assert first.metric_id != second.metric_id


@pytest.mark.parametrize(
    "field",
    ["pose_id", "cluster_id", "method", "method_version"],
)
def test_cluster_assignment_rejects_blank_identity_fields(field):
    values = {
        "pose_id": "pose_1",
        "cluster_id": "cluster_1",
        "method": "leader",
        "method_version": "1",
    }
    values[field] = ""

    with pytest.raises(DomainValidationError, match=field):
        PoseClusterAssignment(**values)


def test_cluster_assignment_detects_content_identity_collision(monkeypatch):
    monkeypatch.setattr(
        analysis_module,
        "content_id",
        lambda prefix, value: f"{prefix}_forced",
    )
    first = PoseClusterAssignment(
        pose_id="pose_1",
        cluster_id="cluster_1",
        method="leader",
        method_version="1",
    )
    second = PoseClusterAssignment(
        pose_id="pose_2",
        cluster_id="cluster_2",
        method="leader",
        method_version="1",
    )

    assert first.assignment_id == second.assignment_id
