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
    assert result["counts"]["sampling_failure_top9"] == 0
    assert result["counts"]["incomplete_top9_evidence"] == 1
    assert result["counts"]["preparation_failure"] == 1
    assert result["preparation_failure_reasons"] == {"ccd_template:HEM": 1}


def test_reliability_cohorts_reports_ranking_diagnostics():
    engine = [{"case_id": "rank", "completed": True}]
    evaluated = [
        {
            "case_id": "rank",
            "completed": True,
            "pose_rmsd_angstroms": [4.5, 1.5, 3.0],
            "pose_evaluation_limit": 3,
        }
    ]

    result = reliability_cohorts(engine, evaluated)

    assert result["ranking_diagnostics"] == [
        {
            "case_id": "rank",
            "top1_rmsd_angstrom": 4.5,
            "best_rmsd_angstrom": 1.5,
            "best_pose_rank": 2,
            "top1_regret_angstrom": 3.0,
        }
    ]


def test_reliability_cohorts_requires_complete_top9_for_sampling_failure():
    engine = [
        {"case_id": "complete", "completed": True},
        {"case_id": "partial", "completed": True},
    ]
    evaluated = [
        {
            "case_id": "complete",
            "completed": True,
            "pose_rmsd_angstroms": [3.0] * 9,
            "pose_evaluation_limit": 9,
        },
        {
            "case_id": "partial",
            "completed": True,
            "pose_rmsd_angstroms": [3.0] * 8 + [None],
            "pose_evaluation_limit": 9,
        },
    ]

    result = reliability_cohorts(engine, evaluated)

    assert result["cohorts"]["sampling_failure_top9"] == ["complete"]
    assert result["cohorts"]["incomplete_top9_evidence"] == ["partial"]
