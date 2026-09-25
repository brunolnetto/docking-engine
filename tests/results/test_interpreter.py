from moldock.domain import ArtifactMetadata
from moldock.results import (
    InMemoryScientificResultRepository,
    VinaResultInterpreter,
)
from moldock.storage import MemoryArtifactStore


def test_interpreter_reads_raw_artifact_and_persists_scientific_records():
    store = MemoryArtifactStore()
    repository = InMemoryScientificResultRepository()
    blob = store.put(
        b"MODEL 1\n"
        b"REMARK VINA RESULT: -8.4 0.0 0.0\n"
        b"ATOM      1  C   LIG A   1       0.000   0.000   0.000  0.00  0.00     0.000 C\n"
        b"ENDMDL\n"
    )
    artifact = ArtifactMetadata(
        artifact_id="artifact_1",
        uri=blob.uri,
        sha256=blob.sha256,
        size_bytes=blob.size_bytes,
        media_type="chemical/x-pdbqt",
        kind="docking_pose",
        producer_attempt_id="attempt_1",
    )

    interpreter = VinaResultInterpreter(
        artifact_store=store,
        repository=repository,
        method_version="1.2.7",
    )

    interpreter.interpret(task_id="task_1", artifact=artifact)

    poses = repository.list_poses_for_attempt("attempt_1")
    assert len(poses) == 1
    scores = repository.list_scores_for_pose(poses[0].pose_id)
    assert scores[0].value == -8.4
    assert repository.list_rankings_for_pose(poses[0].pose_id)[0].rank == 1


def test_interpreter_ignores_non_pose_artifacts():
    store = MemoryArtifactStore()
    repository = InMemoryScientificResultRepository()
    blob = store.put(b"log")
    artifact = ArtifactMetadata(
        artifact_id="artifact_log",
        uri=blob.uri,
        sha256=blob.sha256,
        size_bytes=blob.size_bytes,
        media_type="text/plain",
        kind="log",
        producer_attempt_id="attempt_1",
    )

    VinaResultInterpreter(
        artifact_store=store,
        repository=repository,
        method_version="1.2.7",
    ).interpret(task_id="task_1", artifact=artifact)

    assert repository.list_poses_for_attempt("attempt_1") == ()
