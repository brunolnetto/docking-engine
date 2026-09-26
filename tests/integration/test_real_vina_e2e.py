import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "examples" / "real_vina_report.py"


def test_real_vina_report_example_exposes_cli_help():
    process = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert process.returncode == 0
    assert "--workspace" in process.stdout
    assert "--run-id" in process.stdout


@pytest.mark.real_e2e
@pytest.mark.skipif(
    os.environ.get("MOLDOCK_RUN_REAL_E2E") != "1",
    reason="set MOLDOCK_RUN_REAL_E2E=1 to run Meeko/Vina integration",
)
def test_real_meeko_vina_pipeline_generates_restart_safe_report(tmp_path):
    workspace = tmp_path / "workspace"
    command = [
        sys.executable,
        str(SCRIPT),
        "--workspace",
        str(workspace),
        "--run-id",
        "integration-1iep",
    ]

    first = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert first.returncode == 0, first.stderr

    json_path = workspace / "reports" / "integration-1iep.json"
    markdown_path = workspace / "reports" / "integration-1iep.md"
    first_payload = json.loads(json_path.read_text())

    assert markdown_path.is_file()
    assert first_payload["succeeded_count"] == 1
    assert first_payload["failed_count"] == 0
    assert first_payload["attempt_count"] == 1
    assert first_payload["pose_count"] >= 1
    assert first_payload["score_count"] >= 1
    interactions = first_payload["tasks"][0]["interactions"]
    assert interactions
    assert any(item["kind"] == "contact" for item in interactions)
    assert (

        first_payload["provenance"]["toolchain"]["vina"]["version"]
        == "1.2.7"
    )
    assert (
        first_payload["provenance"]["toolchain"]["meeko_ligand"]["version"]
        == "0.8.0"
    )

    second = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert second.returncode == 0, second.stderr

    second_payload = json.loads(json_path.read_text())
    assert second_payload == first_payload
    assert second_payload["attempt_count"] == 1


def test_vendored_receptor_keeps_ser438_atom_order():
    receptor = (
        ROOT / "examples" / "fixtures" / "1iep_receptorH.pdb"
    ).read_text()
    atom_3428 = receptor.index("ATOM   3428")
    atom_3429 = receptor.index("ATOM   3429")
    atom_3430 = receptor.index("ATOM   3430")

    assert atom_3428 < atom_3429 < atom_3430
    assert receptor.count("ATOM   3429") == 1
