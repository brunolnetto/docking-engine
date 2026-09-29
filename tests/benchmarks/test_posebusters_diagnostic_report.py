from benchmarks.posebusters.diagnostic_report import stage_summary


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
