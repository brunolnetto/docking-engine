from __future__ import annotations

from typing import Iterable


def aggregate_family_rows(
    case_families: Iterable[Iterable[dict[str, object]]],
) -> list[dict[str, object]]:
    accumulators: dict[str, list[int]] = {}
    for families in case_families:
        for family in families:
            kind = family.get("kind")
            if not isinstance(kind, str) or not kind:
                raise ValueError("interaction family must have a non-empty kind")
            values = accumulators.setdefault(kind, [0, 0, 0, 0, 0])
            for index, key in enumerate(
                (
                    "reference_count",
                    "predicted_count",
                    "true_positive",
                    "false_positive",
                    "false_negative",
                )
            ):
                value = family.get(key)
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    raise ValueError(
                        f"interaction family {kind} has invalid {key}: {value!r}"
                    )
                values[index] += value

    rows: list[dict[str, object]] = []
    for kind in sorted(accumulators):
        reference_count, predicted_count, tp, fp, fn = accumulators[kind]
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = (
            None
            if precision is None or recall is None
            else (
                0.0
                if precision + recall == 0
                else 2 * precision * recall / (precision + recall)
            )
        )
        union = tp + fp + fn
        rows.append(
            {
                "kind": kind,
                "reference_count": reference_count,
                "predicted_count": predicted_count,
                "true_positive": tp,
                "false_positive": fp,
                "false_negative": fn,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "jaccard": tp / union if union else None,
            }
        )
    return rows


def _format_metric(value: object) -> str:
    return "n/a" if value is None else f"{float(value):.3f}"


def render_interaction_report(summary: dict[str, object]) -> str:
    families = summary.get("families")
    if not isinstance(families, list):
        raise ValueError("interaction summary families must be a list")
    lines = [
        "# Interaction Recovery Benchmark",
        "",
        (
            "This benchmark compares residue-level interaction fingerprints "
            "between the prepared crystallographic ligand and the engine's "
            "Top-1 predicted pose."
        ),
        "",
        f"**Cases:** {summary.get('total_cases', 0)}",
        (
            "**Interaction-evaluable cases:** "
            f"{summary.get('interaction_evaluable_cases', 0)}"
        ),
        "",
        "| Family | Reference | Predicted | TP | FP | FN | Precision | Recall | F1 | Jaccard |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for family in families:
        if not isinstance(family, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    str(family.get("kind", "unknown")),
                    str(family.get("reference_count", 0)),
                    str(family.get("predicted_count", 0)),
                    str(family.get("true_positive", 0)),
                    str(family.get("false_positive", 0)),
                    str(family.get("false_negative", 0)),
                    _format_metric(family.get("precision")),
                    _format_metric(family.get("recall")),
                    _format_metric(family.get("f1")),
                    _format_metric(family.get("jaccard")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Semantics",
            "",
            "- Fingerprints are compared independently by interaction family.",
            "- The fingerprint unit is interaction family + receptor residue, not atom-pair count.",
            "- Empty reference/prediction families are reported as n/a rather than perfect recovery.",
            "- Salt bridges retain the engine's current putative-charge semantics.",
            "- These recurrence/recovery statistics are not molecular-dynamics occupancy.",
            "- No combined interaction confidence score is calculated.",
            "",
        ]
    )
    return "\n".join(lines)
