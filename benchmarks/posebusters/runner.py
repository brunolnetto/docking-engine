from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import tempfile
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


MEEKO_VERSION = "0.8.0"
VINA_VERSION = "1.2.7"
BOX_SIDE_ANGSTROM = 25.0


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    receptor: Path
    ligand: Path


def discover_cases(dataset_root: Path) -> tuple[BenchmarkCase, ...]:
    cases = []
    for directory in sorted(path for path in dataset_root.iterdir() if path.is_dir()):
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


def make_spec(case: BenchmarkCase) -> OfflineDockingSpec:
    center = crystal_ligand_center(case.ligand)
    receptor_protocol = ReceptorPreparationProtocol(
        method="meeko",
        method_version=MEEKO_VERSION,
        parameters={},
    )
    ligand_protocol = LigandPreparationProtocol(
        method="meeko",
        method_version=MEEKO_VERSION,
        parameters={},
    )
    protocol = DockingProtocol(
        backend="vina",
        backend_version=VINA_VERSION,
        receptor_preparation_id=receptor_protocol.preparation_id,
        ligand_preparation_id=ligand_protocol.preparation_id,
        parameters={
            "seed": 42,
            "exhaustiveness": 8,
            "num_modes": 9,
            "energy_range": 3.0,
        },
    )
    return OfflineDockingSpec(
        run_id=f"posebusters-{case.case_id.lower()}",
        worker_id="posebusters-benchmark",
        ligand_set_id=case.case_id,
        search_space=DockingBox(
            center_x=center[0],
            center_y=center[1],
            center_z=center[2],
            size_x=BOX_SIDE_ANGSTROM,
            size_y=BOX_SIDE_ANGSTROM,
            size_z=BOX_SIDE_ANGSTROM,
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


def run_case(case: BenchmarkCase, output_root: Path) -> dict[str, object]:
    started = time.monotonic()
    workspace = output_root / case.case_id
    workspace.mkdir(parents=True, exist_ok=True)
    catalog = workspace / "catalog.sqlite"
    data = workspace / "ducklake"
    artifact_store = FilesystemArtifactStore(workspace / "artifacts")

    prepared = DuckLakePreparedInputRepository(catalog_path=catalog, data_path=data)
    tasks = DuckLakeTaskRepository(catalog_path=catalog, data_path=data)
    artifacts = DuckLakeArtifactRepository(catalog_path=catalog, data_path=data)
    science = DuckLakeScientificResultRepository(catalog_path=catalog, data_path=data)
    runs = DuckLakeRunManifestRepository(catalog_path=catalog, data_path=data)
    spec = make_spec(case)

    try:
        interpreter = VinaResultInterpreter(
            artifact_store=artifact_store,
            repository=science,
            method_version=VINA_VERSION,
        )
        pipeline = OfflineDockingPipeline(
            receptor_preparer=MeekoReceptorPreparer(method_version=MEEKO_VERSION),
            ligand_preparer=MeekoLigandPreparer(method_version=MEEKO_VERSION),
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
        pipeline.run(spec)
        report = PipelineReportBuilder(
            task_repository=tasks,
            artifact_repository=artifacts,
            scientific_result_repository=science,
        ).build_for_run(spec.run_id, run_manifest_repository=runs)

        task_report = report.tasks[0]
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    cases = discover_cases(args.dataset_root)
    if args.limit is not None:
        cases = cases[: args.limit]
    if not cases:
        raise RuntimeError("no PoseBusters benchmark cases discovered")

    args.output_root.mkdir(parents=True, exist_ok=True)
    rows = []
    for case in cases:
        try:
            rows.append(run_case(case, args.output_root))
        except Exception as exc:
            rows.append(
                {
                    "case_id": case.case_id,
                    "completed": False,
                    "failure_stage": "engine",
                    "error": f"{type(exc).__name__}: {exc}",
                    "runtime_seconds": None,
                }
            )
    path = args.output_root / "engine_cases.json"
    path.write_text(json.dumps({"cases": rows}, indent=2) + "\n")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
