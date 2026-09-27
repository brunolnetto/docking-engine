from __future__ import annotations

from benchmarks.common import BenchmarkSummary
from benchmarks.posebusters.report import render_markdown


def _summary() -> BenchmarkSummary:
    return BenchmarkSummary(
        benchmark="posebusters_benchmark_v1",
        total_cases=4,
        completed_cases=3,
        execution_success_rate=0.75,
        top1_rmsd_le_2a_rate=2 / 3,
        pb_valid_rate=2 / 3,
        combined_success_rate=1 / 3,
        median_rmsd_angstrom=1.5,
        median_runtime_seconds=20.0,
        failures_by_stage={"preparation": 1},
    )


def _manifest() -> dict[str, object]:
    return {
        "benchmark": "posebusters_benchmark_v1",
        "dataset": {
            "zenodo_record": "8278563",
            "archive_md5": "deadbeef",
            "paper_case_count": 308,
        },
        "protocol": {
            "task": "cognate_ligand_redocking",
            "search_space": {
                "side_angstrom": 25.0,
                "center": "geometric_center_of_crystal_ligand_heavy_atoms",
            },
            "receptor": {
                "preparation": "meeko",
                "preparation_version": "0.8.0",
            },
            "ligand": {
                "preparation": "meeko",
                "preparation_version": "0.8.0",
            },
            "docking": {
                "engine": "vina",
                "engine_version": "1.2.7",
                "seed": 42,
                "exhaustiveness": 8,
                "num_modes": 9,
            },
            "evaluation": {
                "posebusters_version": "0.6.5",
                "config": "redock",
            },
        },
    }


def test_report_separates_scientific_and_engine_quality():
    rendered = render_markdown(summary=_summary(), manifest=_manifest())

    assert "## Scientific quality" in rendered
    assert "| Top-1 RMSD ≤ 2 Å | 66.7% |" in rendered
    assert "| PB-valid | 66.7% |" in rendered
    assert "## Engine quality" in rendered
    assert "| Completed/evaluable cases | 3/4 |" in rendered
    assert "| Execution success | 75.0% |" in rendered
    assert "| preparation | 1 |" in rendered


def test_report_keeps_published_reference_contextual():
    baseline = {
        "top1_rmsd_le_2a_rate_approx": 0.58,
        "source": {
            "citation": "Example citation",
            "doi": "10.example/test",
        },
        "comparability_warning": "Only compare equivalent protocols.",
    }

    rendered = render_markdown(
        summary=_summary(),
        manifest=_manifest(),
        baseline=baseline,
    )

    assert "Published Vina Top-1 RMSD ≤ 2 Å reference: ~58.0%" in rendered
    assert "> Only compare equivalent protocols." in rendered
    assert "automatic regression gate" in rendered
    assert "Delta" not in rendered


def test_report_documents_current_scope_limitations():
    rendered = render_markdown(summary=_summary(), manifest=_manifest())

    assert "Top-N pose-recovery is not yet included" in rendered
    assert "Interaction-fingerprint recovery" in rendered
    assert "308-case run establishes" in rendered
