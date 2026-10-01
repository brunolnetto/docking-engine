from benchmarks.posebusters.diagnostic_report import render_markdown, stage_summary


def test_stage_summary_keeps_evidence_axes_independent():
    engine = {
        "a": {"completed": True},
        "b": {"completed": True},
        "c": {"completed": False},
    }
    evaluated = {
        "a": {"completed": True, "rmsd_angstrom": 1.0, "pb_valid": False},
        "b": {"completed": True, "rmsd_angstrom": 3.0, "pb_valid": True},
        "c": {"completed": False, "rmsd_angstrom": None, "pb_valid": None},
    }
    interactions = {
        "a": {"completed": True},
        "b": {"completed": False},
        "c": {"completed": False},
    }

    summary = stage_summary(engine, evaluated, interactions)

    assert summary["engine_execution"]["cases"] == 2
    assert summary["rmsd_evaluable"]["cases"] == 2
    assert summary["top1_rmsd_le_2a"]["cases"] == 1
    assert summary["pb_evaluable"]["cases"] == 2
    assert summary["pb_valid"]["cases"] == 1
    assert summary["interaction_evaluable"]["cases"] == 1


def test_stage_summary_uses_scientific_evaluable_denominators():
    engine = {
        "a": {"completed": True},
        "b": {"completed": True},
        "c": {"completed": True},
    }
    evaluated = {
        "a": {"completed": True, "rmsd_angstrom": 1.0, "pb_valid": True},
        "b": {"completed": True, "rmsd_angstrom": 3.0, "pb_valid": False},
        "c": {"completed": False, "rmsd_angstrom": None, "pb_valid": None},
    }
    interactions = {case_id: {"completed": True} for case_id in engine}

    summary = stage_summary(engine, evaluated, interactions)

    assert summary["top1_rmsd_le_2a"]["rate"] == 0.5
    assert summary["top1_rmsd_le_2a"]["denominator"] == 2
    assert summary["pb_valid"]["rate"] == 0.5
    assert summary["pb_valid"]["denominator"] == 2
    report = render_markdown(summary)
    assert "| Top-1 RMSD <= 2 A | 1/2 | 50.0% |" in report
    assert "| PB valid | 1/2 | 50.0% |" in report
