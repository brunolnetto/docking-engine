from benchmarks.reliability import preparation_failure_reason, reliability_cohorts


def test_preparation_failure_reason_classifies_known_failure_modes():
    assert preparation_failure_reason("Failed building template from CCD for resname='HEM'") == "ccd_template:HEM"
    assert preparation_failure_reason("No template matched for residue_key='A:1'") == "residue_template_mismatch"
    assert preparation_failure_reason("Explicit valence for atom # 2") == "chemical_valence"


def test_reliability_cohorts_separate_ranking_from_sampling_and_preparation():
    engine = [
        {"case_id": "a", "completed": True},
        {"case_id": "b", "completed": True},
        {"case_id": "c", "completed": True},
        {"case_id": "d", "completed": False, "failure_stage": "preparation", "error": "Failed building template from CCD for resname='HEM'"},
    ]
    evaluated = [
        {"case_id": "a", "completed": True, "pose_rmsd_angstroms": [1.0, 4.0, 5.0], "pose_evaluation_limit": 3},
        {"case_id": "b", "completed": True, "pose_rmsd_angstroms": [4.0, 1.0, 5.0], "pose_evaluation_limit": 3},
        {"case_id": "c", "completed": True, "pose_rmsd_angstroms": [4.0, 5.0, 6.0], "pose_evaluation_limit": 3},
        {"case_id": "d", "completed": False},
    ]

    result = reliability_cohorts(engine, evaluated)

    assert result["counts"]["top1_hit"] == 1
    assert result["counts"]["ranking_recoverable_top3"] == 1
    assert result["counts"]["sampling_failure_top9"] == 0\n    assert result["counts"]["incomplete_top9_evidence"] == 1
    assert result["counts"]["preparation_failure"] == 1
    assert result["preparation_failure_reasons"] == {"ccd_template:HEM": 1}
