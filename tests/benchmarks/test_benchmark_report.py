from __future__ import annotations

from benchmarks.common import BenchmarkSummary
from benchmarks.posebusters.report import engine_completion, render_markdown


def _summary(*, completed_cases: int = 3) -> BenchmarkSummary:
    return BenchmarkSummary(
        benchmark="posebusters_benchmark_v1",
        total_cases=4,
        completed_cases=completed_cases,
        execution_success_rate=completed_cases / 4,
        top1_rmsd_le_2a_rate=2 / 3 if completed_cases else 0.0,
        pb_valid_rate=2 / 3 if completed_cases else 0.0,
        combined_success_rate=1 / 3 if completed_cases else 0.0,
        median_rmsd_angstrom=1.5 if completed_cases else None,
        median_runtime_seconds=20.0 if completed_cases else None,
        failures_by_stage={} if completed_cases == 4 else {"evaluation": 4 - completed_cases},
        rmsd_evaluable_cases=completed_cases,
        pb_evaluable_cases=completed_cases,
        combined_evaluable_cases=completed_cases,
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
            "receptor": {"preparation": "meeko", "preparation_version": "0.8.0"},
            "ligand": {"preparation": "meeko", "preparation_version": "0.8.0"},
            "docking": {
                "engine": "vina",
                "engine_version": "1.2.7",
                "seed": 42,
                "exhaustiveness": 8,
                "num_modes": 9,
            },
            "evaluation": {"posebusters_version": "0.6.5", "config": "redock"},
        },
    }


def test_engine_completion_is_independent_of_evaluation():
    completed, total, rate = engine_completion(
        {"cases": [{"completed": True}, {"completed": True}, {"completed": False}]}
    )
    assert (completed, total) == (2, 3)
    assert rate == 2 / 3


def test_engine_completion_handles_empty_payload():
    assert engine_completion({"cases": []}) == (0, 0, None)


def test_report_separates_scientific_engine_and_evaluation_quality():
    rendered = render_markdown(
        summary=_summary(),
        manifest=_manifest(),
        engine_completed_cases=4,
        engine_total_cases=4,
        engine_success_rate=1.0,
    )
    assert "| Top-1 RMSD ≤ 2 Å | 66.7% |" in rendered
    assert "| Engine-completed cases | 4/4 |" in rendered
    assert "| Engine execution success | 100.0% |" in rendered
    assert "| End-to-end evaluable cases | 3/4 |" in rendered
    assert "| End-to-end evaluability | 75.0% |" in rendered


def test_report_renders_scientific_rates_as_na_without_evaluable_cases():
    rendered = render_markdown(
        summary=_summary(completed_cases=0),
        manifest=_manifest(),
        engine_completed_cases=4,
        engine_total_cases=4,
        engine_success_rate=1.0,
    )
    assert "| Top-1 RMSD ≤ 2 Å | n/a |" in rendered
    assert "| PB-valid | n/a |" in rendered
    assert "| RMSD ≤ 2 Å and PB-valid | n/a |" in rendered
    assert "| Engine execution success | 100.0% |" in rendered


def test_report_keeps_published_reference_contextual():
    baseline = {
        "top1_rmsd_le_2a_rate_approx": 0.58,
        "source": {"citation": "Example citation", "doi": "10.example/test"},
        "comparability_warning": "Only compare equivalent protocols.",
    }
    rendered = render_markdown(
        summary=_summary(),
        manifest=_manifest(),
        baseline=baseline,
        engine_completed_cases=4,
        engine_total_cases=4,
        engine_success_rate=1.0,
    )
    assert "Published Vina Top-1 RMSD ≤ 2 Å reference: ~58.0%" in rendered
    assert "> Only compare equivalent protocols." in rendered
    assert "automatic regression gate" in rendered
    assert "Delta" not in rendered


def test_report_uses_metric_specific_availability():
    summary = BenchmarkSummary(
        benchmark="posebusters_benchmark_v1",
        total_cases=1,
        completed_cases=1,
        execution_success_rate=1.0,
        top1_rmsd_le_2a_rate=1.0,
        pb_valid_rate=0.0,
        combined_success_rate=0.0,
        median_rmsd_angstrom=1.0,
        median_runtime_seconds=1.0,
        failures_by_stage={},
        rmsd_evaluable_cases=1,
        pb_evaluable_cases=0,
        combined_evaluable_cases=0,
    )
    rendered = render_markdown(summary=summary, manifest=_manifest())

    assert "| Top-1 RMSD ≤ 2 Å | 100.0% |" in rendered
    assert "| PB-valid | n/a |" in rendered
    assert "| RMSD ≤ 2 Å and PB-valid | n/a |" in rendered


def test_report_fallback_engine_rate_matches_fallback_counts():
    rendered = render_markdown(summary=_summary(), manifest=_manifest())

    assert "| Engine-completed cases | 3/4 |" in rendered
    assert "| Engine execution success | 75.0% |" in rendered
