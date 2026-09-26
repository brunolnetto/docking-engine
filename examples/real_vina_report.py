#!/usr/bin/env python
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

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
from moldock.reporting import (
    JsonPipelineReporter,
    MarkdownPipelineReporter,
    PipelineReportBuilder,
    ReportLabPipelineReporter,
)
from moldock.results import (
    DuckLakeScientificResultRepository,
    VinaResultInterpreter,
)
from moldock.storage import FilesystemArtifactStore
from moldock.toolchain import VinaMeekoToolchainPreflight


ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"
DEFAULT_RECEPTOR = FIXTURES / "1iep_receptorH.pdb"
DEFAULT_LIGAND = FIXTURES / "1iep_ligand.sdf"

MEEKO_VERSION = "0.8.0"
VINA_VERSION = "1.2.7"

BOX = DockingBox(
    center_x=15.190,
    center_y=53.903,
    center_z=16.917,
    size_x=20.0,
    size_y=20.0,
    size_z=20.0,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the official 1IEP/Imatinib example through "
            "Meeko + AutoDock Vina and write reproducible reports."
        )
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path(".moldock") / "1iep",
        help="durable DuckLake/artifact/report workspace",
    )
    parser.add_argument(
        "--run-id",
        default="1iep-vina-1",
        help="stable run identity used for restart/idempotency",
    )
    parser.add_argument(
        "--receptor",
        type=Path,
        default=DEFAULT_RECEPTOR,
        help="hydrogenated receptor PDB",
    )
    parser.add_argument(
        "--ligand",
        type=Path,
        default=DEFAULT_LIGAND,
        help="single-molecule 3D SDF ligand",
    )
    parser.add_argument(
        "--pdf",
        action="store_true",
        help="also write an auditable ReportLab PDF (requires docking-engine[pdf])",
    )
    return parser.parse_args()


def make_spec(
    *,
    run_id: str,
    receptor_content: bytes,
    ligand_content: bytes,
) -> OfflineDockingSpec:
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
    docking_protocol = DockingProtocol(
        backend="vina",
        backend_version=VINA_VERSION,
        receptor_preparation_id=(
            receptor_protocol.preparation_id
        ),
        ligand_preparation_id=ligand_protocol.preparation_id,
        parameters={
            "seed": 42,
            "exhaustiveness": 8,
            "num_modes": 9,
            "energy_range": 3.0,
        },
    )
    return OfflineDockingSpec(
        run_id=run_id,
        worker_id="offline-local",
        ligand_set_id="1iep-imatinib",
        search_space=BOX,
        docking_protocol=docking_protocol,
        receptor_request=ReceptorPreparationRequest(
            receptor_id="1iep",
            source_format="pdb",
            content=receptor_content,
            protocol=receptor_protocol,
        ),
        ligand_requests=(
            LigandPreparationRequest(
                ligand_id="STI",
                source_format="sdf",
                content=ligand_content,
                protocol=ligand_protocol,
            ),
        ),
    )


def main() -> int:
    args = parse_args()
    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    reports_dir = workspace / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    receptor_content = args.receptor.read_bytes()
    ligand_content = args.ligand.read_bytes()

    catalog = workspace / "catalog.sqlite"
    data = workspace / "ducklake"
    artifact_store = FilesystemArtifactStore(
        workspace / "artifacts"
    )

    prepared = DuckLakePreparedInputRepository(
        catalog_path=catalog,
        data_path=data,
    )
    tasks = DuckLakeTaskRepository(
        catalog_path=catalog,
        data_path=data,
    )
    artifacts = DuckLakeArtifactRepository(
        catalog_path=catalog,
        data_path=data,
    )
    science = DuckLakeScientificResultRepository(
        catalog_path=catalog,
        data_path=data,
    )
    runs = DuckLakeRunManifestRepository(
        catalog_path=catalog,
        data_path=data,
    )

    try:
        interpreter = VinaResultInterpreter(
            artifact_store=artifact_store,
            repository=science,
            method_version=VINA_VERSION,
        )
        pipeline = OfflineDockingPipeline(
            receptor_preparer=MeekoReceptorPreparer(
                method_version=MEEKO_VERSION
            ),
            ligand_preparer=MeekoLigandPreparer(
                method_version=MEEKO_VERSION
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

        pipeline.run(
            make_spec(
                run_id=args.run_id,
                receptor_content=receptor_content,
                ligand_content=ligand_content,
            )
        )

        report = PipelineReportBuilder(
            task_repository=tasks,
            artifact_repository=artifacts,
            scientific_result_repository=science,
        ).build_for_run(
            args.run_id,
            run_manifest_repository=runs,
        )

        markdown_path = reports_dir / f"{args.run_id}.md"
        json_path = reports_dir / f"{args.run_id}.json"
        pdf_path = reports_dir / f"{args.run_id}.pdf"
        markdown_path.write_text(
            MarkdownPipelineReporter().render(report),
            encoding="utf-8",
        )
        json_path.write_text(
            JsonPipelineReporter().render(report) + "\n",
            encoding="utf-8",
        )
        if args.pdf:
            ReportLabPipelineReporter().write(report, pdf_path)
    finally:
        runs.close()
        science.close()
        artifacts.close()
        tasks.close()
        prepared.close()

    print(markdown_path)
    print(json_path)
    if args.pdf:
        print(pdf_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
