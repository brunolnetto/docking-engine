from pathlib import Path

import pytest

from benchmarks.redocking import export_pdbqt_to_sdf, sdf_record_count


PDBQT = b"""MODEL 1
REMARK VINA RESULT: -8.0 0.000 0.000
ENDMDL
MODEL 2
REMARK VINA RESULT: -7.0 1.000 2.000
ENDMDL
"""


def test_sdf_record_count_counts_complete_records():
    assert sdf_record_count(b"mol1\n$$$$\nmol2\n$$$$\n") == 2


def test_export_contract_accepts_matching_pose_cardinality(tmp_path):
    source = tmp_path / "poses.pdbqt"
    target = tmp_path / "poses.sdf"
    source.write_bytes(PDBQT)

    def runner(command, **kwargs):
        assert command == ["mk_export.py", str(source), "-s", str(target)]
        target.write_bytes(b"mol1\n$$$$\nmol2\n$$$$\n")

    export_pdbqt_to_sdf(source, target, runner=runner)


def test_export_contract_rejects_pose_loss(tmp_path):
    source = tmp_path / "poses.pdbqt"
    target = tmp_path / "poses.sdf"
    source.write_bytes(PDBQT)

    def runner(command, **kwargs):
        target.write_bytes(b"mol1\n$$$$\n")

    with pytest.raises(ValueError, match="pose cardinality mismatch"):
        export_pdbqt_to_sdf(source, target, runner=runner)
