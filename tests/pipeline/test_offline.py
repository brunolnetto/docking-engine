from datetime import datetime, timezone

import pytest

from moldock.domain import (
    DockingBox,
    DockingOutputArtifact,
    DockingProtocol,
    DockingResult,
    DomainValidationError,
    TaskStatus,
)
from moldock.pipeline import (
    OfflineDockingPipeline,
    OfflineDockingSpec,
)
from moldock.preparation import (
    LigandPreparationArtifact,
    LigandPreparationProtocol,
    LigandPreparationRequest,
    ReceptorPreparationArtifact,
    ReceptorPreparationProtocol,
    ReceptorPreparationRequest,
)
from moldock.repositories import (
    DuckLakeArtifactRepository,
    DuckLakePreparedInputRepository,
    DuckLakeTaskRepository,
)
from moldock.reporting import (
    JsonPipelineReporter,
    PipelineReportBuilder,
    TextPipelineReporter,
)
from moldock.results import (
    DuckLakeScientificResultRepository,
    VinaResultInterpreter,
)
from moldock.storage import FilesystemArtifactStore


T0 = datetime(2026, 9, 26, 0, 30, tzinfo=timezone.utc)
BOX = DockingBox(1, 2, 3, 20, 20, 20)


class FakeReceptorPreparer:
    def __init__(self):
        self.calls = 0

    def prepare(self, request):
        self.calls += 1
        return ReceptorPreparationArtifact(
            receptor_id=request.receptor_id,
            preparation_id=request.protocol.preparation_id,
            model_id="model_1",
            chain_ids=("A",),
            pdbqt=b"REC",
        )


class FakeLigandPreparer:
    def __init__(self):
        self.calls = 0

    def prepare(self, request):
        self.calls += 1
        return (
            LigandPreparationArtifact(
                ligand_id=request.ligand_id,
                preparation_id=request.protocol.preparation_id,
                microstate_id="micro_1",
                conformer_id="conf_1",
                pdbqt=b"LIG-1",
            ),
            LigandPreparationArtifact(
                ligand_id=request.ligand_id,
                preparation_id=request.protocol.preparation_id,
                microstate_id="micro_1",
                conformer_id="conf_2",
                pdbqt=b"LIG-2",
            ),
        )


class VinaLikeBackend:
    def __init__(self):
        self.calls = []

    def execute(self, request):
        self.calls.append(request.task.task_id)
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


def make_protocols():
    receptor = ReceptorPreparationProtocol(
        method="fake-receptor",
        method_version="1",
        parameters={"ph": 7.4},
    )
    ligand = LigandPreparationProtocol(
        method="fake-ligand",
        method_version="1",
        parameters={"ph": 7.4},
    )
    docking = DockingProtocol(
        backend="vina",
        backend_version="1.2.7",
        receptor_preparation_id=receptor.preparation_id,
        ligand_preparation_id=ligand.preparation_id,
        parameters={"seed": 42, "exhaustiveness": 8},
    )
    return receptor, ligand, docking


def make_spec():
    receptor_protocol, ligand_protocol, docking_protocol = make_protocols()
    return OfflineDockingSpec(
        run_id="run_1",
        worker_id="offline-worker",
        ligand_set_id="set_1",
        search_space=BOX,
        docking_protocol=docking_protocol,
        receptor_request=ReceptorPreparationRequest(
            receptor_id="rec_1",
            source_format="pdb",
            content=b"RAW-REC",
            protocol=receptor_protocol,
        ),
        ligand_requests=(
            LigandPreparationRequest(
                ligand_id="lig_1",
                source_format="sdf",
                content=b"RAW-LIG",
                protocol=ligand_protocol,
            ),
        ),
    )


def make_stack(tmp_path):
    catalog = tmp_path / "catalog.sqlite"
    data = tmp_path / "data"
    store = FilesystemArtifactStore(tmp_path / "artifacts")
    prepared = DuckLakePreparedInputRepository(
        catalog_path=catalog,
        data_path=data,
        retry_delay_seconds=0,
    )
    tasks = DuckLakeTaskRepository(
        catalog_path=catalog,
        data_path=data,
        retry_delay_seconds=0,
    )
    artifacts = DuckLakeArtifactRepository(
        catalog_path=catalog,
        data_path=data,
        retry_delay_seconds=0,
    )
    science = DuckLakeScientificResultRepository(
        catalog_path=catalog,
        data_path=data,
        retry_delay_seconds=0,
    )
    return store, prepared, tasks, artifacts, science


def test_offline_pipeline_runs_preparation_planning_execution_and_reporting(tmp_path):
    store, prepared, tasks, artifacts, science = make_stack(tmp_path)
    receptor_preparer = FakeReceptorPreparer()
    ligand_preparer = FakeLigandPreparer()
    backend = VinaLikeBackend()
    interpreter = VinaResultInterpreter(
        artifact_store=store,
        repository=science,
        method_version="1.2.7",
    )
    pipeline = OfflineDockingPipeline(
        receptor_preparer=receptor_preparer,
        ligand_preparer=ligand_preparer,
        prepared_inputs=prepared,
        task_repository=tasks,
        artifact_repository=artifacts,
        artifact_store=store,
        backend=backend,
        result_interpreter=interpreter,
        clock=lambda: T0,
    )

    try:
        result = pipeline.run(make_spec())

        assert result.run_id == "run_1"
        assert result.task_count == 2
        assert len(result.prepared_ligand_ids) == 2
        assert len(backend.calls) == 2

        report = PipelineReportBuilder(
            task_repository=tasks,
            artifact_repository=artifacts,
            scientific_result_repository=science,
        ).build(result)

        assert report.task_count == 2
        assert report.succeeded_count == 2
        assert report.failed_count == 0
        assert report.artifact_count == 2
        assert report.pose_count == 2
        assert report.score_count == 2
        assert all(task.status is TaskStatus.SUCCEEDED for task in report.tasks)

        text = TextPipelineReporter().render(report)
        payload = JsonPipelineReporter().render(report)
        assert "succeeded=2" in text
        assert '"score_count": 2' in payload
        assert "vina_affinity" in payload
    finally:
        prepared.close()
        tasks.close()
        artifacts.close()
        science.close()


def test_same_run_id_reuses_succeeded_tasks_without_redocking(tmp_path):
    store, prepared, tasks, artifacts, science = make_stack(tmp_path)
    receptor_preparer = FakeReceptorPreparer()
    ligand_preparer = FakeLigandPreparer()
    backend = VinaLikeBackend()
    pipeline = OfflineDockingPipeline(
        receptor_preparer=receptor_preparer,
        ligand_preparer=ligand_preparer,
        prepared_inputs=prepared,
        task_repository=tasks,
        artifact_repository=artifacts,
        artifact_store=store,
        backend=backend,
        clock=lambda: T0,
    )

    try:
        first = pipeline.run(make_spec())
        second = pipeline.run(make_spec())

        assert first.manifest_id == second.manifest_id
        assert first.task_ids == second.task_ids
        assert len(backend.calls) == 2
        assert all(
            len(tasks.attempts_for(task_id, "run_1")) == 1
            for task_id in first.task_ids
        )
    finally:
        prepared.close()
        tasks.close()
        artifacts.close()
        science.close()


def test_spec_rejects_preparation_protocol_mismatch():
    receptor_protocol, ligand_protocol, docking_protocol = make_protocols()
    wrong_receptor = ReceptorPreparationProtocol(
        method="other",
        method_version="1",
    )

    with pytest.raises(DomainValidationError, match="receptor preparation"):
        OfflineDockingSpec(
            run_id="run_1",
            worker_id="worker_1",
            ligand_set_id="set_1",
            search_space=BOX,
            docking_protocol=docking_protocol,
            receptor_request=ReceptorPreparationRequest(
                receptor_id="rec_1",
                source_format="pdb",
                content=b"REC",
                protocol=wrong_receptor,
            ),
            ligand_requests=(
                LigandPreparationRequest(
                    ligand_id="lig_1",
                    source_format="sdf",
                    content=b"LIG",
                    protocol=ligand_protocol,
                ),
            ),
        )
