from benchmarks.ranking_signals import attach_reference_labels, vina_pose_scores


def test_vina_pose_scores_extracts_only_production_signals():
    content = b"""MODEL 1
REMARK VINA RESULT: -8.2 0.000 0.000
ENDMDL
MODEL 2
REMARK VINA RESULT: -7.9 1.100 2.200
ENDMDL
"""
    rows = vina_pose_scores(content)

    assert rows == [
        {"rank": 1, "model_index": 1, "vina_affinity_kcal_mol": -8.2, "vina_internal_rmsd_lb": 0.0, "vina_internal_rmsd_ub": 0.0},
        {"rank": 2, "model_index": 2, "vina_affinity_kcal_mol": -7.9, "vina_internal_rmsd_lb": 1.1, "vina_internal_rmsd_ub": 2.2},
    ]
    assert all("reference" not in key for row in rows for key in row)


def test_reference_labels_are_attached_only_after_signal_extraction():
    signals = [{"rank": 1, "vina_affinity_kcal_mol": -8.2}]
    labeled = attach_reference_labels(signals, [1.5])

    assert labeled[0]["reference_rmsd_angstrom"] == 1.5
    assert labeled[0]["reference_success_le_2a"] is True


def test_vina_pose_scores_rejects_result_outside_model():
    content = b"""MODEL 1
REMARK VINA RESULT: -8.2 0.000 0.000
ENDMDL
REMARK VINA RESULT: -7.9 1.100 2.200
"""
    import pytest

    with pytest.raises(ValueError, match="outside MODEL"):
        vina_pose_scores(content)


def test_vina_pose_scores_rejects_duplicate_result_in_model():
    content = b"""MODEL 1
REMARK VINA RESULT: -8.2 0.000 0.000
REMARK VINA RESULT: -7.9 1.100 2.200
ENDMDL
"""
    import pytest

    with pytest.raises(ValueError, match="multiple VINA RESULT"):
        vina_pose_scores(content)
