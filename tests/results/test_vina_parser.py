import pytest

from moldock.domain import ScoreKind
from moldock.results import VinaResultParseError, VinaResultParser


PDBQT = b"""MODEL 1
REMARK VINA RESULT: -8.1 0.000 0.000
ATOM      1  C   LIG A   1       0.000   0.000   0.000  0.00  0.00     0.000 C
ENDMDL
MODEL 2
REMARK VINA RESULT: -7.4 1.250 2.100
ATOM      1  C   LIG A   1       1.000   0.000   0.000  0.00  0.00     0.000 C
ENDMDL
"""


def test_parser_extracts_pose_score_ranking_and_rmsd():
    parsed = VinaResultParser().parse(
        task_id="task_1",
        attempt_id="attempt_1",
        source_artifact_id="artifact_1",
        content=PDBQT,
        method_version="1.2.7",
    )

    assert len(parsed.poses) == 2
    assert len(parsed.scores) == 2
    assert len(parsed.rankings) == 2

    first = parsed.poses[0]
    assert first.model_index == 1
    assert len(first.geometry_sha256) == 64

    first_score = parsed.scores[0]
    assert first_score.pose_id == first.pose_id
    assert first_score.kind is ScoreKind.VINA_AFFINITY
    assert first_score.value == -8.1
    assert first_score.unit == "kcal/mol"
    assert first_score.metadata["rmsd_lb"] == 0.0
    assert first_score.metadata["rmsd_ub"] == 0.0

    assert parsed.rankings[0].rank == 1
    assert parsed.rankings[1].rank == 2


def test_geometry_identity_changes_when_model_geometry_changes():
    parser = VinaResultParser()
    first = parser.parse(
        task_id="task_1",
        attempt_id="attempt_1",
        source_artifact_id="artifact_1",
        content=PDBQT,
        method_version="1.2.7",
    )

    changed = PDBQT.replace(b"       0.000   0.000", b"       9.000   0.000", 1)
    second = parser.parse(
        task_id="task_1",
        attempt_id="attempt_1",
        source_artifact_id="artifact_1",
        content=changed,
        method_version="1.2.7",
    )

    assert first.poses[0].pose_id != second.poses[0].pose_id


@pytest.mark.parametrize(
    "content, message",
    [
        (b"", "no MODEL blocks"),
        (b"MODEL 1\nATOM 1\nENDMDL\n", "missing VINA RESULT"),
        (
            b"MODEL 1\nREMARK VINA RESULT: nope 0.0 0.0\nENDMDL\n",
            "invalid VINA RESULT",
        ),
        (
            b"MODEL 1\nREMARK VINA RESULT: -8.0 0.0 0.0\n"
            b"REMARK VINA RESULT: -7.0 0.0 0.0\nENDMDL\n",
            "multiple VINA RESULT",
        ),
        (
            b"MODEL 1\nREMARK VINA RESULT: -8.0 0.0 0.0\n",
            "unterminated MODEL",
        ),
    ],
)
def test_parser_rejects_malformed_vina_output(content, message):
    with pytest.raises(VinaResultParseError, match=message):
        VinaResultParser().parse(
            task_id="task_1",
            attempt_id="attempt_1",
            source_artifact_id="artifact_1",
            content=content,
            method_version="1.2.7",
        )
