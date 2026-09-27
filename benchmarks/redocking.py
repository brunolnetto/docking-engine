from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time

from rdkit import Chem

from moldock.backends import VinaBackend
from moldock.domain import DockingBox, DockingProtocol
from moldock.pipeline import OfflineDockingPipeline, OfflineDockingSpec
from moldock.preparation import (
    LigandPreparationProtocol,
    LigandPreparationRequest,
    MeekoLigandPreparer,
    MeekoReceptorPreparer,
    ReceptorPreparationProtocol,
    ReceptorPreparationRequest,
)
from moldock.repositories import (
    DuckLakeArtifactRepository,
    DuckLakePreparedInputRepository,
    DuckLakeRunManifestRepository,
    DuckLakeTaskRepository,
)
from moldock.reporting import PipelineReportBuilder
from moldock.results import (
    DuckLakeScientificResultRepository,
    VinaResultInterpreter,
)
from moldock.storage import FilesystemArtifactStore
from moldock.toolchain import VinaMeekoToolchainPreflight


@dataclass(frozen=True)
class RedockingHarnessConfig:
    benchmark: str
    expected_case_count: int
    run_prefix: str
    worker_id: str
    meeko_version: str = "0.8.0"
    vina_version: str = "1.2.7"
    box_side_angstrom: float = 25.0
    seed: int = 42
    exhaustiveness: int = 8
    num_modes: int = 9
    energy_range: float = 3.0


class BenchmarkStageError(RuntimeError):
    def __init__(self, stage: str, cause: Exception | str) -> None:
        self.stage = stage
        message = (
            f"{type(cause).__name__}: {cause}"
            if isinstance(cause, Exception)
            else str(cause)
        )
        super().__init__(message)


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    receptor: Path
    ligand: Path


def discover_cases(dataset_root: Path) -> tuple[BenchmarkCase, ...]:
    cases = []
    for directory in sorted(
        path for path in dataset_root.iterdir() if path.is_dir()
    ):
        case_id = directory.name
        receptor = directory / f"{case_id}_protein.pdb"
        ligand = directory / f"{case_id}_ligand.sdf"
        if receptor.is_file() and ligand.is_file():
            cases.append(BenchmarkCase(case_id, receptor, ligand))
    return tuple(cases)


def crystal_ligand_center(path: Path) -> tuple[float, float, float]:
    supplier = Chem.SDMolSupplier(str(path), removeHs=False)
    molecule = next((mol for mol in supplier if mol is not None), None)
    if molecule is None:
        raise RuntimeError(f"cannot read crystal ligand: {path}")
    conformer = molecule.GetConformer()
    points = [
        conformer.GetAtomPosition(atom.GetIdx())
        for atom in molecule.GetAtoms()
        if atom.GetAtomicNum() > 1
    ]
    if not points:
        raise RuntimeError(f"crystal ligand has no heavy atoms: {path}")
    count = len(points)
    return (
        sum(point.x for point in points) / count,
        sum(point.y for point in points) / count,
        sum(point.z for point in points) / count,
    )


def make_spec(
    case: BenchmarkCase,
    config: RedockingHarnessConfig,
) -> OfflineDockingSpec:
    center = crystal_ligand_center(case.ligand)
    receptor_protocol = ReceptorPreparationProtocol(
        method="meeko",
        method_version=config.meeko_version,
        parameters={},
    )
    ligand_protocol = LigandPreparationProtocol(
        method="meeko",
        method_version=config.meeko_version,
        parameters={},
    )
    protocol = DockingProtocol(
        backend="vina",
        backend_version=config.vina_version,
        receptor_preparation_id=receptor_protocol.preparation_id,
        ligand_preparation_id=ligand_protocol.preparation_id,
        parameters={
            "seed": config.seed,
            "exhaustiveness": config.exhaustiveness,
            "num_modes": config.num_modes,
            "energy_range": config.energy_range,
        },
    )
    return OfflineDockingSpec(
        run_id=f"{config.run_prefix}-{case.case_id.lower()}",
        worker_id=config.worker_id,
        ligand_set_id=case.case_id,
        search_space=DockingBox(
            center_x=center[0],
            center_y=center[1],
            center_z=center[2],
            size_x=config.box_side_angstrom,
            size_y=config.box_side_angstrom,
            size_z=config.box_side_angstrom,
        ),
        docking_protocol=protocol,
        receptor_request=ReceptorPreparationRequest(
            receptor_id=case.case_id,
            source_format="pdb",
            content=case.receptor.read_bytes(),
            protocol=receptor_protocol,
        ),
        ligand_requests=(
            LigandPreparationRequest(
                ligand_id=case.case_id,
                source_format="sdf",
                content=case.ligand.read_bytes(),
                protocol=ligand_protocol,
            ),
        ),
    )


def run_case(
    case: BenchmarkCase,
    output_root: Path,
    config: RedockingHarnessConfig,
) -> dict[str, object]:
    started = time.monotonic()
    workspace = output_root / case.case_id
    workspace.mkdir(parents=True, exist_ok=True)
    catalog = workspace / "catalog.sqlite"
    data = workspace / "ducklake"
    artifact_store = FilesystemArtifactStore(workspace / "artifacts")

    prepared = DuckLakePreparedInputRepository(
        catalog_path=catalog,
        data_path=data,
    )
    tasks = DuckLakeTaskRepository(catalog_path=catalog, data_path=data)
    artifacts = DuckLakeArtifactRepository(catalog_path=catalog, data_path=data)
    science = DuckLakeScientificResultRepository(
        catalog_path=catalog,
        data_path=data,
    )
    runs = DuckLakeRunManifestRepository(catalog_path=catalog, data_path=data)
    try:
        try:
            spec = make_spec(case, config)
        except Exception as exc:
            raise BenchmarkStageError("dataset", exc) from exc

        interpreter = VinaResultInterpreter(
            artifact_store=artifact_store,
            repository=science,
            method_version=config.vina_version,
        )
        pipeline = OfflineDockingPipeline(
            receptor_preparer=MeekoReceptorPreparer(
                method_version=config.meeko_version
            ),
            ligand_preparer=MeekoLigandPreparer(
                method_version=config.meeko_version
            ),
            prepared_inputs=prepared,
            task_repository=tasks,
            artifact_repository=artifacts,
            artifact_store=artifact_store,
            backend=VinaBackend(),
            result_interpreter=interpreter,
            clock=lambda: datetime.now(timezone.utc),
            toolchain_preflight=VinaMeekoToolchainPreflight(),
            run_manifest_repository=runs,
        )
        try:
            pipeline.run(spec)
        except Exception as exc:
            name = type(exc).__name__
            if "Preparation" in name or name.startswith("Meeko"):
                stage = "preparation"
            elif "DockingBackend" in name or "Vina" in name:
                stage = "docking"
            else:
                stage = "engine"
            raise BenchmarkStageError(stage, exc) from exc

        report = PipelineReportBuilder(
            task_repository=tasks,
            artifact_repository=artifacts,
            scientific_result_repository=science,
        ).build_for_run(spec.run_id, run_manifest_repository=runs)

        task_report = report.tasks[0]
        try:
            if not task_report.artifact_ids:
                raise RuntimeError("docking completed without a pose artifact")
            artifact = artifacts.get(task_report.artifact_ids[-1])
            if artifact is None:
                raise RuntimeError("pose artifact metadata is missing")
            pdbqt = artifact_store.read(artifact.uri)
            predicted_pdbqt = workspace / "predicted.pdbqt"
            predicted_sdf = workspace / "predicted.sdf"
            predicted_pdbqt.write_bytes(pdbqt)
            subprocess.run(
                [
                    "mk_export.py",
                    str(predicted_pdbqt),
                    "-s",
                    str(predicted_sdf),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except Exception as exc:
            raise BenchmarkStageError("export", exc) from exc

        return {
            "case_id": case.case_id,
            "completed": True,
            "runtime_seconds": time.monotonic() - started,
            "predicted_sdf": str(predicted_sdf),
            "crystal_ligand_sdf": str(case.ligand),
            "receptor_pdb": str(case.receptor),
        }
    finally:
        runs.close()
        science.close()
        artifacts.close()
        tasks.close()
        prepared.close()


def run_dataset(
    *,
    dataset_root: Path,
    output_root: Path,
    config: RedockingHarnessConfig,
    limit: int | None = None,
) -> Path:
    cases = discover_cases(dataset_root)
    if not cases:
        raise RuntimeError(f"no {config.benchmark} benchmark cases discovered")
    if limit is None and len(cases) != config.expected_case_count:
        raise RuntimeError(
            f"full {config.benchmark} benchmark requires exactly "
            f"{config.expected_case_count} cases; discovered {len(cases)}"
        )
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        cases = cases[:limit]

    output_root.mkdir(parents=True, exist_ok=True)
    rows = []
    for case in cases:
        case_started = time.monotonic()
        try:
            rows.append(run_case(case, output_root, config))
        except BenchmarkStageError as exc:
            rows.append(
                {
                    "case_id": case.case_id,
                    "completed": False,
                    "failure_stage": exc.stage,
                    "error": str(exc),
                    "runtime_seconds": time.monotonic() - case_started,
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "case_id": case.case_id,
                    "completed": False,
                    "failure_stage": "engine",
                    "error": f"{type(exc).__name__}: {exc}",
                    "runtime_seconds": time.monotonic() - case_started,
                }
            )

    path = output_root / "engine_cases.json"
    path.write_text(
        json.dumps({"cases": rows}, indent=2) + "\n",
        encoding="utf-8",
    )
    return path
