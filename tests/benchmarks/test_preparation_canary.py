from benchmarks.posebusters.preparation_canary import (
    CanaryOutcome,
    cohort_case_ids,
    promotion_summary,
)


def test_cohort_selection_uses_chemistry_evidence_and_failure_class():
    rows = [
        {
            "case_id": "hem",
            "completed": False,
            "preparation_evidence": {
                "decisions": [
                    {"residue": {"residue_name": "HEM"}, "decision": "preserve"}
                ]
            },
        },
        {
            "case_id": "template",
            "completed": False,
            "failure_stage": "preparation",
            "error": "Residue XYZ is not in residue_templates",
            "preparation_evidence": {"decisions": []},
        },
        {"case_id": "ok", "completed": True},
    ]
    assert cohort_case_ids(rows, residue_names=frozenset({"HEM"})) == ("hem",)
    assert cohort_case_ids(
        rows,
        failure_classes=frozenset({"unresolved_nonstandard_residue"}),
    ) == ("template",)


def test_promotion_requires_recovery_without_downstream_regression():
    result = promotion_summary(
        [
            CanaryOutcome("failed", "HEM", False, True, treatment_rmsd=1.4, treatment_pb_valid=True),
            CanaryOutcome("control", "control", True, True, 1.0, 1.2, True, True),
        ]
    )
    assert result["preparation_recoveries"] == 1
    assert result["promotion_eligible"] is True


def test_promotion_rejects_execution_rmsd_and_pb_regressions():
    result = promotion_summary(
        [
            CanaryOutcome("recovered", "K", False, True),
            CanaryOutcome("execution", "control", True, False),
            CanaryOutcome("rmsd", "control", True, True, 1.0, 1.6, True, True),
            CanaryOutcome("pb", "control", True, True, 1.0, 1.0, True, False),
        ]
    )
    assert result["promotion_eligible"] is False
    assert result["execution_regressions"] == 1
    assert result["rmsd_regressions_gt_0_5a"] == 1
    assert result["pb_valid_regressions"] == 1


def test_promotion_fails_closed_without_complete_paired_control():
    result = promotion_summary(
        [
            CanaryOutcome("recovered", "HEM", False, True),
            CanaryOutcome("missing", "control", True, True, None, 1.0, True, True),
        ]
    )
    assert result["complete_paired_controls"] == 0
    assert result["incomplete_paired_controls"] == 1
    assert result["promotion_eligible"] is False


def test_promotion_fails_closed_on_non_finite_rmsd():
    result = promotion_summary(
        [
            CanaryOutcome("recovered", "HEM", False, True),
            CanaryOutcome("nan", "control", True, True, float("nan"), 1.0, True, True),
        ]
    )
    assert result["promotion_eligible"] is False


def test_failure_taxonomy_does_not_select_non_preparation_failure():
    rows = [
        {
            "case_id": "docking",
            "completed": False,
            "failure_stage": "docking",
            "error": "Residue XYZ is not in residue_templates",
            "preparation_evidence": {"decisions": []},
        }
    ]
    assert cohort_case_ids(
        rows,
        failure_classes=frozenset({"unresolved_nonstandard_residue"}),
    ) == ()
