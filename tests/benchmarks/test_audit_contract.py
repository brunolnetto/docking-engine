import json

from benchmarks.audit_contract import coverage_contract, provenance


def _write(path, cases):
    path.write_text(json.dumps({"cases": cases}), encoding="utf-8")


def test_coverage_contract_keeps_evaluability_axes_separate(tmp_path):
    engine = tmp_path / "engine.json"
    evaluated = tmp_path / "evaluated.json"
    interactions = tmp_path / "interactions.json"
    _write(engine, [{"completed": True}, {"completed": False}])
    _write(
        evaluated,
        [
            {"completed": True, "rmsd_angstrom": 1.0, "pb_valid": True},
            {"completed": False, "rmsd_angstrom": None, "pb_valid": None},
        ],
    )
    _write(interactions, [{"completed": True}, {"completed": False}])

    result = coverage_contract(
        engine_cases=engine,
        evaluated_cases=evaluated,
        interaction_cases=interactions,
        expected_cases=2,
    )

    assert result["axes"]["dataset_accounted"]["rate"] == 1.0
    assert result["axes"]["engine_completed"]["rate"] == 0.5
    assert result["axes"]["rmsd_evaluable"]["rate"] == 0.5
    assert result["axes"]["pb_evaluable"]["rate"] == 0.5
    assert result["axes"]["interaction_evaluable"]["rate"] == 0.5
    assert result["fully_evaluable"] is False


def test_provenance_hashes_manifest_and_artifacts(tmp_path):
    manifest = tmp_path / "manifest.json"
    artifact = tmp_path / "summary.json"
    manifest.write_text("{}", encoding="utf-8")
    artifact.write_text('{"ok": true}', encoding="utf-8")

    result = provenance(
        source_commit="abc123",
        workflow_run_id="42",
        manifest=manifest,
        artifacts=[artifact],
    )

    assert result["source_commit"] == "abc123"
    assert result["workflow_run_id"] == "42"
    assert len(result["manifest_sha256"]) == 64
    assert len(result["artifacts"]["summary.json"]) == 64
