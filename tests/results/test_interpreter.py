from moldock.domain import (
    ArtifactMetadata,
    DockingBox,
    DockingExecutionRequest,
    DockingTask,
)
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
    metrics = repository.list_metrics_for_pose(poses[0].pose_id)
    assert {metric.kind.value for metric in metrics} == {
        "rmsd_to_rank1",
        "ligand_efficiency",
    }
    assert repository.list_cluster_assignments_for_pose(poses[0].pose_id)


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



class RecordingInteractionAnalyzer:
    def __init__(self):
        self.calls = []

    def analyze(self, **kwargs):
        self.calls.append(kwargs)


def test_interpreter_uses_resolved_receptor_context_when_available():
    store = MemoryArtifactStore()
    repository = InMemoryScientificResultRepository()
    output = (
        b"MODEL 1\n"
        b"REMARK VINA RESULT: -8.4 0.0 0.0\n"
        b"ATOM      1  O1  LIG L   1       2.200   0.000   0.000  0.00  0.00     0.000 OA\n"
        b"ENDMDL\n"
    )
    blob = store.put(output)
    artifact = ArtifactMetadata(
        artifact_id="artifact_1",
        uri=blob.uri,
        sha256=blob.sha256,
        size_bytes=blob.size_bytes,
        media_type="chemical/x-pdbqt",
        kind="docking_pose",
        producer_attempt_id="attempt_1",
    )
    box = DockingBox(
        center_x=0.0,
        center_y=0.0,
        center_z=0.0,
        size_x=10.0,
        size_y=10.0,
        size_z=10.0,
    )
    task = DockingTask(
        experiment_id="exp_1",
        receptor_id="rec_1",
        ligand_id="lig_1",
        prepared_receptor_id="prec_1",
        prepared_ligand_id="plig_1",
        search_space_id=box.search_space_id,
    )
    request = DockingExecutionRequest(
        task=task,
        receptor_pdbqt=(
            b"ATOM      1  N   LYS A  10       0.000   0.000   0.000  1.00  0.00     0.000 N\n"
        ),
        ligand_pdbqt=b"prepared ligand",
        search_space=box,
    )
    interactions = RecordingInteractionAnalyzer()
    interpreter = VinaResultInterpreter(
        artifact_store=store,
        repository=repository,
        method_version="1.2.7",
        interaction_analyzer=interactions,
    )

    interpreter.interpret_with_request(
        task_id="task_1",
        artifact=artifact,
        request=request,
    )

    assert len(interactions.calls) == 1
    assert interactions.calls[0]["attempt_id"] == "attempt_1"
    assert interactions.calls[0]["receptor_pdbqt"] == request.receptor_pdbqt
    assert interactions.calls[0]["pose_pdbqt"] == output


def test_interpreter_skips_interaction_enrichment_for_non_structural_context():
    store = MemoryArtifactStore()
    repository = InMemoryScientificResultRepository()
    output = (
        b"MODEL 1\n"
        b"REMARK VINA RESULT: -8.4 0.0 0.0\n"
        b"ATOM      1  C   LIG L   1       0.000   0.000   0.000  0.00  0.00     0.000 C\n"
        b"ENDMDL\n"
    )
    blob = store.put(output)
    artifact = ArtifactMetadata(
        artifact_id="artifact_1",
        uri=blob.uri,
        sha256=blob.sha256,
        size_bytes=blob.size_bytes,
        media_type="chemical/x-pdbqt",
        kind="docking_pose",
        producer_attempt_id="attempt_1",
    )
    box = DockingBox(
        center_x=0.0,
        center_y=0.0,
        center_z=0.0,
        size_x=10.0,
        size_y=10.0,
        size_z=10.0,
    )
    task = DockingTask(
        experiment_id="exp_1",
        receptor_id="rec_1",
        ligand_id="lig_1",
        prepared_receptor_id="prec_1",
        prepared_ligand_id="plig_1",
        search_space_id=box.search_space_id,
    )
    request = DockingExecutionRequest(
        task=task,
        receptor_pdbqt=b"fake receptor",
        ligand_pdbqt=b"fake ligand",
        search_space=box,
    )
    interactions = RecordingInteractionAnalyzer()
    interpreter = VinaResultInterpreter(
        artifact_store=store,
        repository=repository,
        method_version="1.2.7",
        interaction_analyzer=interactions,
    )

    interpreter.interpret_with_request(
        task_id="task_1",
        artifact=artifact,
        request=request,
    )

    assert interactions.calls == []
