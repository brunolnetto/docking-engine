from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from benchmarks.common import BenchmarkSummary, load_case_results, summarize


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _number(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}{suffix}"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def render_markdown(
    *,
    summary: BenchmarkSummary,
    manifest: dict[str, Any],
    baseline: dict[str, Any] | None = None,
) -> str:
    dataset = manifest.get("dataset", {})
    protocol = manifest.get("protocol", {})
    docking = protocol.get("docking", {})
    search_space = protocol.get("search_space", {})
    evaluation = protocol.get("evaluation", {})

    lines = [
        "# Docking Engine Benchmark Report",
        "",
        f"**Benchmark:** {summary.benchmark}",
        f"**Cases:** {summary.total_cases}",
        "",
        "## Benchmark scope",
        "",
        (
            "This report separates scientific pose-quality evidence from engine "
            "reliability evidence. A scientifically unsuccessful pose is not the "
            "same thing as an execution failure."
        ),
        "",
        "## Protocol",
        "",
        f"- Dataset cases expected by manifest: {dataset.get('paper_case_count', 'n/a')}",
        f"- Dataset source: Zenodo {dataset.get('zenodo_record', 'n/a')}",
        f"- Task: {protocol.get('task', 'n/a')}",
        (
            "- Search space: "
            f"{search_space.get('side_angstrom', 'n/a')} Å cube centered on "
            f"{search_space.get('center', 'n/a')}"
        ),
        (
            "- Docking engine: "
            f"{docking.get('engine', 'n/a')} "
            f"{docking.get('engine_version', 'n/a')}"
        ),
        f"- Seed: {docking.get('seed', 'n/a')}",
        f"- Exhaustiveness: {docking.get('exhaustiveness', 'n/a')}",
        f"- Requested modes: {docking.get('num_modes', 'n/a')}",
        (
            "- Evaluation: PoseBusters "
            f"{evaluation.get('posebusters_version', 'n/a')} "
            f"({evaluation.get('config', 'n/a')})"
        ),
        "",
        "## Scientific quality",
        "",
        "| Metric | Result |",
        "| --- | ---: |",
        f"| Top-1 RMSD ≤ 2 Å | {_pct(summary.top1_rmsd_le_2a_rate)} |",
        f"| PB-valid | {_pct(summary.pb_valid_rate)} |",
        (
            "| RMSD ≤ 2 Å and PB-valid | "
            f"{_pct(summary.combined_success_rate)} |"
        ),
        (
            "| Median Top-1 RMSD | "
            f"{_number(summary.median_rmsd_angstrom, ' Å')} |"
        ),
        "",
        (
            "Scientific rates are computed over successfully evaluable cases, "
            "not silently over cases that failed execution or evaluation."
        ),
        "",
        "## Engine quality",
        "",
        "| Metric | Result |",
        "| --- | ---: |",
        f"| Completed/evaluable cases | {summary.completed_cases}/{summary.total_cases} |",
        f"| Execution success | {_pct(summary.execution_success_rate)} |",
        (
            "| Median case runtime | "
            f"{_number(summary.median_runtime_seconds, ' s')} |"
        ),
        "",
        "## Failure accounting",
        "",
    ]

    if summary.failures_by_stage:
        lines.extend(
            [
                "| Stage | Cases |",
                "| --- | ---: |",
                *[
                    f"| {stage} | {count} |"
                    for stage, count in sorted(summary.failures_by_stage.items())
                ],
            ]
        )
    else:
        lines.append("No failed cases were recorded.")

    lines.extend(
        [
            "",
            "## Published reference context",
            "",
        ]
    )

    if baseline is None:
        lines.append(
            "No published-reference metadata was supplied for this report."
        )
    else:
        reference_rate = baseline.get("top1_rmsd_le_2a_rate_approx")
        if isinstance(reference_rate, (int, float)) and not isinstance(
            reference_rate, bool
        ):
            lines.append(
                f"- Published Vina Top-1 RMSD ≤ 2 Å reference: ~{_pct(float(reference_rate))}"
            )
        source = baseline.get("source", {})
        if isinstance(source, dict):
            citation = source.get("citation")
            doi = source.get("doi")
            if citation:
                lines.append(f"- Source: {citation}")
            if doi:
                lines.append(f"- DOI: {doi}")
        warning = baseline.get("comparability_warning")
        if warning:
            lines.extend(["", f"> {warning}"])

    lines.extend(
        [
            "",
            "## Interpretation guardrails",
            "",
            "- RMSD here is reference-pose recovery, not RMSD between generated poses.",
            "- PB-valid evaluates physical plausibility checks and is reported separately from RMSD.",
            "- No composite confidence score is introduced.",
            "- A published Vina percentage is contextual evidence, not an automatic regression gate.",
            "- Direct comparison requires matching preparation, search-space, engine and evaluation semantics.",
            "",
            "## Reproducibility and provenance",
            "",
            f"- Benchmark manifest: {manifest.get('benchmark', 'n/a')}",
            f"- Dataset archive checksum: {dataset.get('archive_md5', 'n/a')}",
            (
                "- Preparation: receptor="
                f"{protocol.get('receptor', {}).get('preparation', 'n/a')} "
                f"{protocol.get('receptor', {}).get('preparation_version', 'n/a')}; "
                "ligand="
                f"{protocol.get('ligand', {}).get('preparation', 'n/a')} "
                f"{protocol.get('ligand', {}).get('preparation_version', 'n/a')}"
            ),
            "",
            "## Limitations and next analyses",
            "",
            "- Top-N pose-recovery is not yet included in this report.",
            "- Interaction-fingerprint recovery against the crystal pose remains a later benchmark stage.",
            "- The first complete 308-case run establishes the repository's own regression baseline.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluated-cases", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()

    results = load_case_results(args.evaluated_cases)
    manifest = _load_json(args.manifest)
    benchmark = str(manifest.get("benchmark") or "benchmark")
    summary = summarize(benchmark, results)
    baseline = _load_json(args.baseline) if args.baseline else None
    rendered = render_markdown(
        summary=summary,
        manifest=manifest,
        baseline=baseline,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
