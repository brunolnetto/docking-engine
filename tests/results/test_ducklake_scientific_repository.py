import pytest

import moldock.domain.result as result_module
from moldock.domain import (
    DomainValidationError,
    Pose,
    PoseClusterAssignment,
    PoseMetric,
    PoseMetricKind,
    PoseRanking,
    PoseScore,
    ScoreKind,
)
from moldock.results import (
    DuckLakeScientificResultRepository,
    ScientificResultRepository,
)


def make_pose(index=1, sha="a" * 64):
    return Pose(
        task_id="task_1",
        attempt_id="attempt_1",
        source_artifact_id="artifact_1",
        model_index=index,
        geometry_sha256=sha,
    )


def make_score(pose_id, value=-8.0, metadata=None):
    return PoseScore(
        pose_id=pose_id,
        kind=ScoreKind.VINA_AFFINITY,
        value=value,
        unit="kcal/mol",
        method="vina",
        method_version="1.2.7",
        metadata=metadata or {},
    )


def make_repo(tmp_path):
    return DuckLakeScientificResultRepository(
        catalog_path=tmp_path / "catalog.sqlite",
        data_path=tmp_path / "data",
        retry_delay_seconds=0,
    )


def test_ducklake_scientific_repository_satisfies_contract(tmp_path):
    repo = make_repo(tmp_path)
    try:
        assert isinstance(repo, ScientificResultRepository)
    finally:
        repo.close()


def test_scientific_results_survive_repository_restart(tmp_path):
    pose = make_pose()
    score = make_score(
        pose.pose_id,
        metadata={
            "rmsd_lb": 0.0,
            "labels": ["vina", "primary"],
        },
    )
    ranking = PoseRanking(
        pose_id=pose.pose_id,
        rank=1,
        method="vina_affinity",
    )
    metric = PoseMetric(
        pose_id=pose.pose_id,
        kind=PoseMetricKind.RMSD_TO_RANK1,
        value=0.0,
        unit="angstrom",
        method="pdbqt_atom_order_direct_rmsd",
        method_version="1",
    )
    cluster = PoseClusterAssignment(
        pose_id=pose.pose_id,
        cluster_id="cluster_1",
        method="rank_ordered_leader_rmsd",
        method_version="1",
    )

    repo = make_repo(tmp_path)
    repo.register_pose(pose)
    repo.register_score(score)
    repo.register_ranking(ranking)
    repo.register_metric(metric)
    repo.register_cluster_assignment(cluster)
    repo.close()

    reopened = make_repo(tmp_path)
    try:
        assert reopened.list_poses_for_attempt("attempt_1") == (pose,)
        assert reopened.list_scores_for_pose(pose.pose_id) == (score,)
        assert reopened.list_rankings_for_pose(pose.pose_id) == (ranking,)
        assert reopened.list_metrics_for_pose(pose.pose_id) == (metric,)
        assert reopened.list_cluster_assignments_for_pose(
            pose.pose_id
        ) == (cluster,)
    finally:
        reopened.close()


def test_scientific_registration_is_idempotent_across_clients(tmp_path):
    pose = make_pose()
    score = make_score(pose.pose_id)
    ranking = PoseRanking(
        pose_id=pose.pose_id,
        rank=1,
        method="vina_affinity",
    )
    first = make_repo(tmp_path)
    second = make_repo(tmp_path)
    try:
        first.register_pose(pose)
        second.register_pose(pose)
        first.register_score(score)
        second.register_score(score)
        first.register_ranking(ranking)
        second.register_ranking(ranking)

        assert first.list_poses_for_attempt(pose.attempt_id) == (pose,)
        assert first.list_scores_for_pose(pose.pose_id) == (score,)
        assert first.list_rankings_for_pose(pose.pose_id) == (ranking,)
    finally:
        first.close()
        second.close()


def test_score_and_ranking_require_known_pose(tmp_path):
    repo = make_repo(tmp_path)
    try:
        with pytest.raises(DomainValidationError, match="unknown pose"):
            repo.register_score(make_score("missing"))

        with pytest.raises(DomainValidationError, match="unknown pose"):
            repo.register_ranking(
                PoseRanking(
                    pose_id="missing",
                    rank=1,
                    method="vina_affinity",
                )
            )
    finally:
        repo.close()


def test_pose_collision_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(
        result_module,
        "content_id",
        lambda prefix, value: f"{prefix}_forced_collision",
    )
    first = make_pose(sha="a" * 64)
    second = make_pose(sha="b" * 64)
    repo = make_repo(tmp_path)
    try:
        repo.register_pose(first)
        with pytest.raises(DomainValidationError, match="conflicting"):
            repo.register_pose(second)
    finally:
        repo.close()


def test_score_collision_is_rejected(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    pose = make_pose()
    repo.register_pose(pose)
    pose_id = pose.pose_id

    monkeypatch.setattr(
        result_module,
        "content_id",
        lambda prefix, value: f"{prefix}_forced_collision",
    )
    first = make_score(pose_id, value=-8.0)
    second = make_score(pose_id, value=-7.0)
    try:
        repo.register_score(first)
        with pytest.raises(DomainValidationError, match="conflicting"):
            repo.register_score(second)
    finally:
        repo.close()


def test_ranking_collision_is_rejected(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    pose = make_pose()
    repo.register_pose(pose)
    pose_id = pose.pose_id

    monkeypatch.setattr(
        result_module,
        "content_id",
        lambda prefix, value: f"{prefix}_forced_collision",
    )
    first = PoseRanking(
        pose_id=pose_id,
        rank=1,
        method="vina_affinity",
    )
    second = PoseRanking(
        pose_id=pose_id,
        rank=2,
        method="vina_affinity",
    )
    try:
        repo.register_ranking(first)
        with pytest.raises(DomainValidationError, match="conflicting"):
            repo.register_ranking(second)
    finally:
        repo.close()


def test_scientific_lists_are_deterministic(tmp_path):
    repo = make_repo(tmp_path)
    first_pose = make_pose(index=2, sha="b" * 64)
    second_pose = make_pose(index=1, sha="a" * 64)
    try:
        repo.register_pose(first_pose)
        repo.register_pose(second_pose)

        assert repo.list_poses_for_attempt("attempt_1") == (
            second_pose,
            first_pose,
        )
    finally:
        repo.close()


def test_score_metadata_preserves_collection_types_across_restart(tmp_path):
    pose = make_pose()
    score = make_score(
        pose.pose_id,
        metadata={
            "labels": {"vina", "primary"},
            "ordered": ("first", "second"),
            "nested": {
                "sets": frozenset({"a", "b"}),
            },
        },
    )
    repo = make_repo(tmp_path)
    repo.register_pose(pose)
    repo.register_score(score)
    repo.close()

    reopened = make_repo(tmp_path)
    try:
        reloaded = reopened.list_scores_for_pose(pose.pose_id)
        assert reloaded == (score,)
        reopened.register_score(score)
        assert reopened.list_scores_for_pose(pose.pose_id) == (score,)
    finally:
        reopened.close()
