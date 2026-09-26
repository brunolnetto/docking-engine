from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from moldock.backends import DockingBackend
from moldock.domain import (
    DockingBox,
    DockingExperiment,
    DockingProtocol,
    DomainValidationError,
)
from moldock.execution import PersistentDockingInputResolver, Worker
from moldock.planning import TaskPlanner
from moldock.preparation import (
    LigandPreparationRequest,
    LigandPreparer,
    ReceptorPreparationRequest,
    ReceptorPreparer,
)
from moldock.repositories import (
    ArtifactRepository,
    PreparedInputRepository,
    TaskRepository,
    RunManifestRepository,
)
from moldock.results import ScientificResultInterpreter
from moldock.storage import ArtifactStore
from moldock.pipeline.run_manifest import RunManifest
from moldock.toolchain import (
    ToolchainPreflight,
    ToolchainSnapshot,
)


@dataclass(frozen=True, slots=True)
class OfflineDockingSpec:
    run_id: str
    worker_id: str
    ligand_set_id: str
    search_space: DockingBox
    docking_protocol: DockingProtocol
    receptor_request: ReceptorPreparationRequest
    ligand_requests: tuple[LigandPreparationRequest, ...]

    def __post_init__(self) -> None:
        for name in ("run_id", "worker_id", "ligand_set_id"):
            if not getattr(self, name).strip():
                raise DomainValidationError(f"{name} must not be blank")
        if not self.ligand_requests:
            raise DomainValidationError(
                "ligand_requests must not be empty"
            )
        if (
            self.receptor_request.protocol.preparation_id
            != self.docking_protocol.receptor_preparation_id
        ):
            raise DomainValidationError(
                "receptor preparation does not match docking protocol"
            )
        for request in self.ligand_requests:
            if (
                request.protocol.preparation_id
                != self.docking_protocol.ligand_preparation_id
            ):
                raise DomainValidationError(
                    "ligand preparation does not match docking protocol"
                )


@dataclass(frozen=True, slots=True)
class PipelineRunResult:
    run_id: str
    experiment_id: str
    protocol_id: str
    manifest_id: str
    prepared_receptor_id: str
    prepared_ligand_ids: tuple[str, ...]
    task_ids: tuple[str, ...]
    toolchain_snapshot: ToolchainSnapshot | None = None

    def __post_init__(self) -> None:
        for name in (
            "run_id",
            "experiment_id",
            "protocol_id",
            "manifest_id",
            "prepared_receptor_id",
        ):
            if not getattr(self, name).strip():
                raise DomainValidationError(f"{name} must not be blank")
        if any(not value.strip() for value in self.prepared_ligand_ids):
            raise DomainValidationError(
                "prepared_ligand_ids must not contain blanks"
            )
        if any(not value.strip() for value in self.task_ids):
            raise DomainValidationError(
                "task_ids must not contain blanks"
            )

    @property
    def task_count(self) -> int:
        return len(self.task_ids)


class OfflineDockingPipeline:
    """Local deterministic orchestration from preparation through execution."""

    def __init__(
        self,
        *,
        receptor_preparer: ReceptorPreparer,
        ligand_preparer: LigandPreparer,
        prepared_inputs: PreparedInputRepository,
        task_repository: TaskRepository,
        artifact_repository: ArtifactRepository,
        artifact_store: ArtifactStore,
        backend: DockingBackend,
        clock: Callable[[], datetime],
        result_interpreter: ScientificResultInterpreter | None = None,
        toolchain_preflight: ToolchainPreflight | None = None,
        run_manifest_repository: RunManifestRepository | None = None,
    ) -> None:
        self._receptor_preparer = receptor_preparer
        self._ligand_preparer = ligand_preparer
        self._prepared_inputs = prepared_inputs
        self._tasks = task_repository
        self._artifacts = artifact_repository
        self._store = artifact_store
        self._backend = backend
        self._clock = clock
        self._interpreter = result_interpreter
        self._toolchain_preflight = toolchain_preflight
        self._run_manifests = run_manifest_repository

    def run(self, spec: OfflineDockingSpec) -> PipelineRunResult:
        toolchain_snapshot = None
        if self._toolchain_preflight is not None:
            toolchain_snapshot = self._toolchain_preflight.inspect(
                expected_backend=spec.docking_protocol.backend,
                expected_vina_version=(
                    spec.docking_protocol.backend_version
                ),
                expected_ligand_method=(
                    spec.ligand_requests[0].protocol.method
                ),
                expected_ligand_version=(
                    spec.ligand_requests[0].protocol.method_version
                ),
                expected_receptor_method=(
                    spec.receptor_request.protocol.method
                ),
                expected_receptor_version=(
                    spec.receptor_request.protocol.method_version
                ),
                vina_executable=getattr(
                    self._backend,
                    "executable",
                    None,
                ),
                ligand_executable=getattr(
                    self._ligand_preparer,
                    "executable",
                    None,
                ),
                receptor_executable=getattr(
                    self._receptor_preparer,
                    "executable",
                    None,
                ),
            )

        receptor_artifact = self._receptor_preparer.prepare(
            spec.receptor_request
        )
        self._validate_receptor_artifact(
            spec.receptor_request,
            receptor_artifact,
        )
        receptor_blob = self._store.put(receptor_artifact.pdbqt)
        prepared_receptor = receptor_artifact.as_prepared_receptor()
        self._prepared_inputs.register_receptor(
            prepared_receptor,
            receptor_blob,
        )

        prepared_ligands_by_id = {}
        for request in spec.ligand_requests:
            artifacts = self._ligand_preparer.prepare(request)
            if not artifacts:
                raise DomainValidationError(
                    f"ligand preparation produced no artifacts: {request.ligand_id}"
                )
            for artifact in artifacts:
                self._validate_ligand_artifact(request, artifact)
                blob = self._store.put(artifact.pdbqt)
                prepared = artifact.as_prepared_ligand()
                self._prepared_inputs.register_ligand(
                    prepared,
                    blob,
                )
                prepared_ligands_by_id[
                    prepared.prepared_ligand_id
                ] = prepared

        prepared_ligands = tuple(
            prepared_ligands_by_id[key]
            for key in sorted(prepared_ligands_by_id)
        )
        if not prepared_ligands:
            raise DomainValidationError(
                "pipeline requires at least one prepared ligand"
            )

        protocol = spec.docking_protocol
        experiment = DockingExperiment(
            receptor_id=spec.receptor_request.receptor_id,
            ligand_set_id=spec.ligand_set_id,
            search_space_id=spec.search_space.search_space_id,
            backend=protocol.backend,
            backend_version=protocol.backend_version,
            receptor_preparation_id=protocol.receptor_preparation_id,
            ligand_preparation_id=protocol.ligand_preparation_id,
            parameters=protocol.parameters,
        )

        manifest = TaskPlanner.plan(
            experiment,
            prepared_receptor,
            prepared_ligands,
        )
        for task in manifest.tasks:
            self._tasks.register(task)

        run_manifest = RunManifest(
            run_id=spec.run_id,
            experiment_id=experiment.experiment_id,
            protocol_id=protocol.protocol_id,
            task_manifest_id=manifest.manifest_id,
            search_space_id=spec.search_space.search_space_id,
            receptor_id=spec.receptor_request.receptor_id,
            receptor_source_sha256=(
                spec.receptor_request.source_sha256
            ),
            ligand_sources=tuple(
                (
                    request.ligand_id,
                    request.source_sha256,
                )
                for request in spec.ligand_requests
            ),
            prepared_receptor_id=(
                prepared_receptor.prepared_receptor_id
            ),
            prepared_ligand_ids=tuple(
                ligand.prepared_ligand_id
                for ligand in prepared_ligands
            ),
            task_ids=tuple(
                task.task_id for task in manifest.tasks
            ),
            toolchain_snapshot=toolchain_snapshot,
        )
        if self._run_manifests is not None:
            self._run_manifests.register(run_manifest)

        resolver = PersistentDockingInputResolver(
            prepared_inputs=self._prepared_inputs,
            artifact_store=self._store,
        )
        resolver.register_search_space(spec.search_space)
        resolver.register_parameters(
            experiment.experiment_id,
            protocol.parameters,
        )

        worker = Worker(
            task_repository=self._tasks,
            artifact_repository=self._artifacts,
            artifact_store=self._store,
            input_resolver=resolver,
            backend=self._backend,
            result_interpreter=self._interpreter,
            clock=self._clock,
        )

        manifest_task_ids = frozenset(
            task.task_id for task in manifest.tasks
        )
        while worker.run_once(
            experiment.experiment_id,
            spec.run_id,
            spec.worker_id,
            allowed_task_ids=manifest_task_ids,
        ) is not None:
            pass

        return run_manifest.to_pipeline_result()

    @staticmethod
    def _validate_receptor_artifact(request, artifact) -> None:
        if artifact.receptor_id != request.receptor_id:
            raise DomainValidationError(
                "prepared receptor artifact has unexpected receptor identity"
            )
        if (
            artifact.preparation_id
            != request.protocol.preparation_id
        ):
            raise DomainValidationError(
                "prepared receptor artifact has unexpected preparation identity"
            )

    @staticmethod
    def _validate_ligand_artifact(request, artifact) -> None:
        if artifact.ligand_id != request.ligand_id:
            raise DomainValidationError(
                "prepared ligand artifact has unexpected ligand identity"
            )
        if (
            artifact.preparation_id
            != request.protocol.preparation_id
        ):
            raise DomainValidationError(
                "prepared ligand artifact has unexpected preparation identity"
            )
