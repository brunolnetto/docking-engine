import pytest

import moldock.domain.analysis as analysis_module
import moldock.domain.interaction as interaction_module
import moldock.domain.result as result_module
from moldock.domain import (
    DomainValidationError,
    Pose,
    PoseInteraction,
    PoseClusterAssignment,
    PoseInteractionKind,
    PoseMetric,
    PoseMetricKind,
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


def make_score(pose_id, value=-8.0):
    return PoseScore(
        pose_id=pose_id,
        kind=ScoreKind.VINA_AFFINITY,
        value=value,
        unit="kcal/mol",
        method="vina",
        method_version="1.2.7",
    )


def test_memory_repository_implements_contract():
    assert isinstance(InMemoryScientificResultRepository(), ScientificResultRepository)


def test_repository_registers_and_lists_pose_data():
    repo = InMemoryScientificResultRepository()
    pose = make_pose()
    score = make_score(pose.pose_id)
    ranking = PoseRanking(pose_id=pose.pose_id, rank=1, method="vina_affinity")

    repo.register_pose(pose)
    repo.register_score(score)
    repo.register_ranking(ranking)

    assert repo.list_poses_for_attempt("attempt_1") == (pose,)
    assert repo.list_scores_for_pose(pose.pose_id) == (score,)
    assert repo.list_rankings_for_pose(pose.pose_id) == (ranking,)


def test_repository_registration_is_idempotent():
    repo = InMemoryScientificResultRepository()
    pose = make_pose()
    score = make_score(pose.pose_id)
    ranking = PoseRanking(pose_id=pose.pose_id, rank=1, method="vina_affinity")

    repo.register_pose(pose)
    repo.register_pose(pose)
    repo.register_score(score)
    repo.register_score(score)
    repo.register_ranking(ranking)
    repo.register_ranking(ranking)

    assert repo.list_poses_for_attempt(pose.attempt_id) == (pose,)
    assert repo.list_scores_for_pose(pose.pose_id) == (score,)
    assert repo.list_rankings_for_pose(pose.pose_id) == (ranking,)


def test_repository_rejects_unknown_pose_for_score_and_ranking():
    repo = InMemoryScientificResultRepository()

    with pytest.raises(DomainValidationError, match="unknown pose"):
        repo.register_score(make_score("missing"))

    with pytest.raises(DomainValidationError, match="unknown pose"):
        repo.register_ranking(
            PoseRanking(pose_id="missing", rank=1, method="vina_affinity")
        )


def test_repository_detects_pose_id_collision(monkeypatch):
    monkeypatch.setattr(
        result_module,
        "content_id",
        lambda prefix, value: f"{prefix}_forced_collision",
    )
    repo = InMemoryScientificResultRepository()
    first = make_pose(sha="a" * 64)
    second = make_pose(sha="b" * 64)

    assert first.pose_id == second.pose_id
    repo.register_pose(first)

    with pytest.raises(DomainValidationError, match="conflicting"):
        repo.register_pose(second)


def test_repository_detects_score_id_collision(monkeypatch):
    repo = InMemoryScientificResultRepository()
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

    assert first.score_id == second.score_id
    repo.register_score(first)

    with pytest.raises(DomainValidationError, match="conflicting"):
        repo.register_score(second)


def test_repository_detects_ranking_id_collision(monkeypatch):
    repo = InMemoryScientificResultRepository()
    pose = make_pose()
    repo.register_pose(pose)
    pose_id = pose.pose_id

    monkeypatch.setattr(
        result_module,
        "content_id",
        lambda prefix, value: f"{prefix}_forced_collision",
    )
    first = PoseRanking(pose_id=pose_id, rank=1, method="vina_affinity")
    second = PoseRanking(pose_id=pose_id, rank=2, method="vina_affinity")

    assert first.ranking_id == second.ranking_id
    repo.register_ranking(first)

    with pytest.raises(DomainValidationError, match="conflicting"):
        repo.register_ranking(second)



def make_interaction(pose_id, distance=3.0):
    return PoseInteraction(
        pose_id=pose_id,
        kind=PoseInteractionKind.CONTACT,
        receptor_atom_serial=1,
        receptor_atom_name="CA",
        receptor_residue_name="ALA",
        receptor_chain="A",
        receptor_residue_number="10",
        ligand_atom_serial=2,
        ligand_atom_name="C1",
        distance_angstrom=distance,
        method="pdbqt_geometric_interactions",
        method_version="1",
    )


def test_repository_registers_lists_and_reuses_interactions():
    repo = InMemoryScientificResultRepository()
    pose = make_pose()
    interaction = make_interaction(pose.pose_id)
    repo.register_pose(pose)

    repo.register_interaction(interaction)
    repo.register_interaction(interaction)

    assert repo.list_interactions_for_pose(pose.pose_id) == (interaction,)
    assert repo.list_interactions_for_pose("missing") == ()


def test_repository_rejects_unknown_pose_for_interaction():
    repo = InMemoryScientificResultRepository()

    with pytest.raises(DomainValidationError, match="unknown pose"):
        repo.register_interaction(make_interaction("missing"))


def test_repository_detects_interaction_id_collision(monkeypatch):
    repo = InMemoryScientificResultRepository()
    pose = make_pose()
    repo.register_pose(pose)

    monkeypatch.setattr(
        interaction_module,
        "content_id",
        lambda prefix, value: f"{prefix}_forced_collision",
    )
    first = make_interaction(pose.pose_id, distance=3.0)
    second = make_interaction(pose.pose_id, distance=3.5)

    assert first.interaction_id == second.interaction_id
    repo.register_interaction(first)

    with pytest.raises(DomainValidationError, match="conflicting"):
        repo.register_interaction(second)



def make_metric(pose_id, value=1.0):
    return PoseMetric(
        pose_id=pose_id,
        kind=PoseMetricKind.RMSD_TO_RANK1,
        value=value,
        unit="angstrom",
        method="test",
        method_version="1",
    )


def make_cluster(pose_id, cluster_id="cluster_1"):
    return PoseClusterAssignment(
        pose_id=pose_id,
        cluster_id=cluster_id,
        method="rank_ordered_leader_rmsd",
        method_version="1",
    )


def test_repository_registers_metrics_and_clusters_idempotently():
    repo = InMemoryScientificResultRepository()
    pose = make_pose()
    metric = make_metric(pose.pose_id)
    cluster = make_cluster(pose.pose_id)
    repo.register_pose(pose)

    repo.register_metric(metric)
    repo.register_metric(metric)
    repo.register_cluster_assignment(cluster)
    repo.register_cluster_assignment(cluster)

    assert repo.list_metrics_for_pose(pose.pose_id) == (metric,)
    assert repo.list_cluster_assignments_for_pose(pose.pose_id) == (cluster,)
    assert repo.list_metrics_for_pose("missing") == ()
    assert repo.list_cluster_assignments_for_pose("missing") == ()


def test_repository_rejects_unknown_pose_for_metric_and_cluster():
    repo = InMemoryScientificResultRepository()

    with pytest.raises(DomainValidationError, match="unknown pose"):
        repo.register_metric(make_metric("missing"))

    with pytest.raises(DomainValidationError, match="unknown pose"):
        repo.register_cluster_assignment(make_cluster("missing"))


def test_repository_detects_metric_and_cluster_id_collisions(monkeypatch):
    repo = InMemoryScientificResultRepository()
    pose = make_pose()
    repo.register_pose(pose)

    monkeypatch.setattr(
        analysis_module,
        "content_id",
        lambda prefix, value: f"{prefix}_forced_collision",
    )

    first_metric = make_metric(pose.pose_id, value=1.0)
    second_metric = make_metric(pose.pose_id, value=2.0)
    assert first_metric.metric_id == second_metric.metric_id
    repo.register_metric(first_metric)
    with pytest.raises(DomainValidationError, match="conflicting"):
        repo.register_metric(second_metric)

    first_cluster = make_cluster(pose.pose_id, "cluster_1")
    second_cluster = make_cluster(pose.pose_id, "cluster_2")
    assert first_cluster.assignment_id == second_cluster.assignment_id
    repo.register_cluster_assignment(first_cluster)
    with pytest.raises(DomainValidationError, match="conflicting"):
        repo.register_cluster_assignment(second_cluster)
