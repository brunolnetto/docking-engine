from datetime import datetime, timezone

from moldock.domain import (
    DockingBox,
    DockingOutputArtifact,
    DockingResult,
    DockingTask,
    ScoreKind,
    TaskStatus,
)
from moldock.execution import MemoryDockingInputResolver, Worker
from moldock.repositories import (
    DuckLakeArtifactRepository,
    InMemoryTaskRepository,
)
from moldock.results import (
    DuckLakeScientificResultRepository,
    VinaResultInterpreter,
)
from moldock.storage import MemoryArtifactStore


T0 = datetime(2026, 9, 25, 20, 0, tzinfo=timezone.utc)


class VinaLikeBackend:
    def execute(self, request):
        return DockingResult(
            artifacts=(
                DockingOutputArtifact(
                    kind="docking_pose",
                    media_type="chemical/x-pdbqt",
                    content=(
                        b"MODEL 1\n"
                        b"REMARK VINA RESULT: -8.0 0.0 0.0\n"
                        b"ATOM      1  C   LIG A   1       0.000   0.000   0.000\n"
                        b"ENDMDL\n"
                    ),
                ),
            ),
            stdout="ok",
            stderr="",
        )


def make_task():
    box = DockingBox(1, 2, 3, 20, 20, 20)
    task = DockingTask(
        experiment_id="exp_1",
        receptor_id="rec_1",
        ligand_id="lig_1",
        prepared_receptor_id="prepared_rec_1",
        prepared_ligand_id="prepared_lig_1",
        search_space_id=box.search_space_id,
    )
    return task, box


def make_resolver(task, box):
    resolver = MemoryDockingInputResolver()
    resolver.register_receptor(task.prepared_receptor_id, b"REC")
    resolver.register_ligand(task.prepared_ligand_id, b"LIG")
    resolver.register_search_space(box)
    return resolver


def test_successful_attempt_is_reconstructable_from_ducklake_after_restart(tmp_path):
    task, box = make_task()
    tasks = InMemoryTaskRepository()
    tasks.register(task)
    store = MemoryArtifactStore()

    artifact_repo = DuckLakeArtifactRepository(
        catalog_path=tmp_path / "catalog.sqlite",
        data_path=tmp_path / "data",
        retry_delay_seconds=0,
    )
    scientific_repo = DuckLakeScientificResultRepository(
        catalog_path=tmp_path / "catalog.sqlite",
        data_path=tmp_path / "data",
        retry_delay_seconds=0,
    )
    interpreter = VinaResultInterpreter(
        artifact_store=store,
        repository=scientific_repo,
        method_version="1.2.7",
    )

    worker = Worker(
        task_repository=tasks,
        artifact_repository=artifact_repo,
        artifact_store=store,
        input_resolver=make_resolver(task, box),
        backend=VinaLikeBackend(),
        result_interpreter=interpreter,
        clock=lambda: T0,
    )

    attempt = worker.run_once("exp_1", "run_1", "worker_1")
    assert attempt is not None
    assert attempt.status is TaskStatus.SUCCEEDED

    produced = artifact_repo.list_for_attempt(attempt.attempt_id)
    assert len(produced) == 1
    artifact_id = produced[0].artifact_id

    artifact_repo.close()
    scientific_repo.close()

    reopened_artifacts = DuckLakeArtifactRepository(
        catalog_path=tmp_path / "catalog.sqlite",
        data_path=tmp_path / "data",
        retry_delay_seconds=0,
    )
    reopened_science = DuckLakeScientificResultRepository(
        catalog_path=tmp_path / "catalog.sqlite",
        data_path=tmp_path / "data",
        retry_delay_seconds=0,
    )
    try:
        artifact = reopened_artifacts.get(artifact_id)
        assert artifact is not None
        assert artifact.producer_attempt_id == attempt.attempt_id

        poses = reopened_science.list_poses_for_attempt(attempt.attempt_id)
        assert len(poses) == 1
        assert poses[0].source_artifact_id == artifact_id

        scores = reopened_science.list_scores_for_pose(poses[0].pose_id)
        rankings = reopened_science.list_rankings_for_pose(poses[0].pose_id)
        assert len(scores) == 1
        assert scores[0].kind is ScoreKind.VINA_AFFINITY
        assert scores[0].value == -8.0
        assert len(rankings) == 1
        assert rankings[0].rank == 1
    finally:
        reopened_artifacts.close()
        reopened_science.close()
