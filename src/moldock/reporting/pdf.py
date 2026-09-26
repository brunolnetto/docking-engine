from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from .model import PipelineReport
from .scientific import ScientificExperimentReport, ScientificReportBuilder


def _score_value(value: float) -> str:
    return repr(value)


class ReportLabPipelineReporter:
    """Render a scientist-facing PDF with a reproducibility appendix."""

    def render(self, report: PipelineReport) -> bytes:
        try:
            from reportlab.graphics.shapes import Drawing, Rect, String
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib.units import mm
            from reportlab.pdfgen.canvas import Canvas
            from reportlab.platypus import (
                KeepTogether,
                PageBreak,
                Paragraph,
                SimpleDocTemplate,
                Spacer,
                Table,
                TableStyle,
            )
        except ImportError as exc:
            raise RuntimeError(
                "PDF reporting requires the 'pdf' extra: "
                "pip install 'docking-engine[pdf]'"
            ) from exc

        scientific = ScientificReportBuilder().build(report)

        navy = colors.HexColor("#17324D")
        blue = colors.HexColor("#285F8F")
        pale = colors.HexColor("#F4F7FB")
        pale_blue = colors.HexColor("#EAF2F8")
        line = colors.HexColor("#D8E1EA")
        text = colors.HexColor("#1D2733")
        muted = colors.HexColor("#667788")
        green = colors.HexColor("#16794B")
        red = colors.HexColor("#B42318")
        white = colors.white

        styles = getSampleStyleSheet()
        styles.add(
            ParagraphStyle(
                name="DockingTitle",
                parent=styles["Title"],
                fontName="Helvetica-Bold",
                fontSize=21,
                leading=25,
                textColor=navy,
                spaceAfter=2.5 * mm,
            )
        )
        styles.add(
            ParagraphStyle(
                name="DockingSubtitle",
                parent=styles["BodyText"],
                fontName="Helvetica",
                fontSize=9.5,
                leading=13,
                textColor=muted,
                spaceAfter=4 * mm,
            )
        )
        styles.add(
            ParagraphStyle(
                name="DockingH2",
                parent=styles["Heading2"],
                fontName="Helvetica-Bold",
                fontSize=12.5,
                leading=15,
                textColor=navy,
                spaceBefore=4 * mm,
                spaceAfter=2 * mm,
            )
        )
        styles.add(
            ParagraphStyle(
                name="DockingH3",
                parent=styles["Heading3"],
                fontName="Helvetica-Bold",
                fontSize=9.5,
                leading=12,
                textColor=navy,
                spaceBefore=2.5 * mm,
                spaceAfter=1.5 * mm,
            )
        )
        styles.add(
            ParagraphStyle(
                name="DockingBody",
                parent=styles["BodyText"],
                fontName="Helvetica",
                fontSize=8.7,
                leading=12,
                textColor=text,
            )
        )
        styles.add(
            ParagraphStyle(
                name="DockingHeader",
                parent=styles["BodyText"],
                fontName="Helvetica-Bold",
                fontSize=7.5,
                leading=9,
                textColor=white,
            )
        )
        styles.add(
            ParagraphStyle(
                name="DockingMono",
                parent=styles["BodyText"],
                fontName="Courier",
                fontSize=6.7,
                leading=8.5,
                textColor=text,
                wordWrap="CJK",
            )
        )
        styles.add(
            ParagraphStyle(
                name="DockingMetric",
                parent=styles["BodyText"],
                fontName="Helvetica-Bold",
                fontSize=16,
                leading=18,
                alignment=2,
                textColor=navy,
            )
        )
        styles.add(
            ParagraphStyle(
                name="DockingMetricLabel",
                parent=styles["BodyText"],
                fontName="Helvetica",
                fontSize=7.2,
                leading=9,
                textColor=muted,
            )
        )
        styles.add(
            ParagraphStyle(
                name="DockingNote",
                parent=styles["BodyText"],
                fontName="Helvetica",
                fontSize=7.8,
                leading=10.5,
                textColor=muted,
            )
        )
        styles.add(
            ParagraphStyle(
                name="DockingCallout",
                parent=styles["BodyText"],
                fontName="Helvetica",
                fontSize=9.2,
                leading=13,
                textColor=text,
                backColor=pale_blue,
                borderColor=line,
                borderWidth=0.5,
                borderPadding=8,
                spaceAfter=3 * mm,
            )
        )
        styles.add(
            ParagraphStyle(
                name="DockingDiagnostic",
                parent=styles["BodyText"],
                fontName="Courier",
                fontSize=6.7,
                leading=8.5,
                textColor=text,
                wordWrap="CJK",
                backColor=pale,
                borderColor=line,
                borderWidth=0.5,
                borderPadding=6,
                spaceAfter=3 * mm,
            )
        )

        class InvariantCanvas(Canvas):
            def __init__(self, *args, **kwargs):
                kwargs["invariant"] = 1
                kwargs["pageCompression"] = 1
                super().__init__(*args, **kwargs)

        def esc(value: object) -> str:
            return (
                str("" if value is None else value)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )

        def paragraph(value: object, style: str = "DockingBody"):
            return Paragraph(esc(value), styles[style])

        def bullets(items: tuple[str, ...] | list[str]):
            if not items:
                return paragraph(
                    "No additional items are supported by the current durable state.",
                    "DockingNote",
                )
            rows = []
            for item in items:
                rows.append(
                    [
                        paragraph("•", "DockingBody"),
                        paragraph(item, "DockingBody"),
                    ]
                )
            table = Table(rows, colWidths=[5 * mm, 169 * mm])
            table.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                        ("TOPPADDING", (0, 0), (-1, -1), 1),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ]
                )
            )
            return table

        def striped_table(rows, widths, mono_columns=(), right_columns=()):
            rendered = []
            for row_index, row in enumerate(rows):
                rendered.append(
                    [
                        paragraph(
                            cell,
                            "DockingHeader"
                            if row_index == 0
                            else (
                                "DockingMono"
                                if column_index in mono_columns
                                else "DockingBody"
                            ),
                        )
                        for column_index, cell in enumerate(row)
                    ]
                )
            table = Table(rendered, colWidths=widths, repeatRows=1)
            commands = [
                ("BACKGROUND", (0, 0), (-1, 0), navy),
                ("GRID", (0, 0), (-1, -1), 0.35, line),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, pale]),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
            for column in right_columns:
                commands.append(("ALIGN", (column, 1), (column, -1), "RIGHT"))
            table.setStyle(TableStyle(commands))
            return table

        def key_value_table(rows):
            table = Table(
                [
                    [paragraph(key), paragraph(value, "DockingMono")]
                    for key, value in rows
                ],
                colWidths=[48 * mm, 126 * mm],
                hAlign="LEFT",
            )
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (0, -1), pale),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("GRID", (0, 0), (-1, -1), 0.35, line),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )
            return table

        def score_chart(
            scientific_report: ScientificExperimentReport,
        ):
            poses = [
                pose
                for pose in scientific_report.poses
                if pose.rank is not None
            ]
            if not poses:
                return None
            families = {
                (pose.method, pose.score_kind, pose.score_unit)
                for pose in poses
            }
            if len(families) != 1:
                return None
            poses = sorted(poses, key=lambda item: item.rank or 10**9)[:10]
            values = [pose.score_value for pose in poses]
            low = min(values)
            high = max(values)
            span = high - low or 1.0
            width = 174 * mm
            row_h = 8 * mm
            height = (len(poses) * row_h) + 11 * mm
            drawing = Drawing(width, height)
            label_x = 0
            bar_x = 37 * mm
            bar_width = 102 * mm
            value_x = 144 * mm
            for index, pose in enumerate(poses):
                y = height - 9 * mm - ((index + 1) * row_h)
                drawing.add(
                    String(
                        label_x,
                        y + 1.5 * mm,
                        f"Rank {pose.rank}",
                        fontName="Helvetica",
                        fontSize=7.5,
                        fillColor=muted,
                    )
                )
                normalized = (high - pose.score_value) / span
                length = max(5 * mm, (25 + 75 * normalized) / 100 * bar_width)
                drawing.add(
                    Rect(
                        bar_x,
                        y,
                        length,
                        4.2 * mm,
                        fillColor=blue,
                        strokeColor=None,
                    )
                )
                drawing.add(
                    String(
                        value_x,
                        y + 1.5 * mm,
                        _score_value(pose.score_value),
                        fontName="Helvetica-Bold",
                        fontSize=7.5,
                        fillColor=text,
                    )
                )
            unit = poses[0].score_unit or ""
            drawing.add(
                String(
                    bar_x,
                    height - 5 * mm,
                    f"{poses[0].method}/{poses[0].score_kind} ({unit})",
                    fontName="Helvetica",
                    fontSize=7,
                    fillColor=muted,
                )
            )
            return drawing

        buffer = BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=18 * mm,
            leftMargin=18 * mm,
            topMargin=15 * mm,
            bottomMargin=20 * mm,
            title=scientific.narrative.title,
            author="docking-engine",
            subject=f"Scientific docking report for run {report.run_id}",
        )

        def footer(canvas, doc):
            canvas.saveState()
            width, _ = A4
            canvas.setStrokeColor(line)
            canvas.setLineWidth(0.4)
            canvas.line(18 * mm, 14 * mm, width - 18 * mm, 14 * mm)
            canvas.setFont("Helvetica", 7)
            canvas.setFillColor(muted)
            canvas.drawString(
                18 * mm,
                9 * mm,
                f"{scientific.narrative.title} | Run {report.run_id}",
            )
            canvas.drawRightString(
                width - 18 * mm,
                9 * mm,
                f"Page {doc.page}",
            )
            canvas.restoreState()

        story = [
            paragraph(scientific.narrative.title.upper(), "DockingTitle"),
            paragraph(
                "Scientist-facing interpretation of a reproducible molecular "
                "docking experiment.",
                "DockingSubtitle",
            ),
            paragraph("Study objective", "DockingH2"),
            paragraph(scientific.narrative.objective, "DockingCallout"),
        ]

        status = "COMPLETED" if scientific.completed else "REVIEW REQUIRED"
        status_color = green if scientific.completed else red
        status_style = ParagraphStyle(
            "DockingStatus",
            parent=styles["DockingMetric"],
            textColor=status_color,
        )
        status_table = Table(
            [
                [
                    paragraph("EXPERIMENT STATUS", "DockingMetricLabel"),
                    Paragraph(status, status_style),
                ]
            ],
            colWidths=[115 * mm, 59 * mm],
        )
        status_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), pale),
                    ("BOX", (0, 0), (-1, -1), 0.8, line),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        story.extend([status_table, Spacer(1, 3 * mm)])

        metric_specs = [
            ("Ligands", len({task.ligand_id for task in report.tasks})),
            ("Scored poses", len(scientific.poses)),
            (
                "Score range",
                (
                    "n/a"
                    if scientific.score_min is None
                    else f"{scientific.score_min:g} to {scientific.score_max:g}"
                ),
            ),
            (
                "Spread",
                (
                    "n/a"
                    if scientific.score_spread is None
                    else f"{scientific.score_spread:g}"
                ),
            ),
        ]
        metric_cells = []
        for label, value in metric_specs:
            cell = Table(
                [
                    [paragraph(label, "DockingMetricLabel")],
                    [paragraph(value, "DockingMetric")],
                ],
                colWidths=[40 * mm],
                rowHeights=[7 * mm, 10 * mm],
            )
            cell.setStyle(
                TableStyle(
                    [
                        ("BOX", (0, 0), (-1, -1), 0.7, line),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ]
                )
            )
            metric_cells.append(cell)
        metrics = Table([metric_cells], colWidths=[43.5 * mm] * 4)
        metrics.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(metrics)

        story.extend(
            [
                paragraph("What happened?", "DockingH2"),
                paragraph(scientific.narrative.outcome, "DockingCallout"),
            ]
        )
        chart = score_chart(scientific)
        if chart is not None:
            story.extend(
                [
                    paragraph("Pose score profile", "DockingH2"),
                    chart,
                ]
            )

        if scientific.poses:
            ranked_values = {
                pose.rank: pose.score_value
                for pose in scientific.poses
                if pose.rank is not None
            }
            rank_one = ranked_values.get(1)
            score_rows = [
                ["Rank", "Ligand", "Score", "Δ vs rank 1", "Unit", "Method"]
            ]
            for pose in scientific.poses:
                delta = (
                    ""
                    if rank_one is None or pose.rank is None
                    else f"{pose.score_value - rank_one:.3f}"
                )
                score_rows.append(
                    [
                        pose.rank if pose.rank is not None else "—",
                        pose.ligand_id,
                        _score_value(pose.score_value),
                        delta,
                        pose.score_unit or "",
                        f"{pose.method} {pose.method_version}",
                    ]
                )
            story.extend(
                [
                    paragraph("Pose-level results", "DockingH2"),
                    striped_table(
                        score_rows,
                        [14 * mm, 24 * mm, 28 * mm, 31 * mm, 25 * mm, 52 * mm],
                        right_columns=(0, 2, 3),
                    ),
                ]
            )

        story.extend(
            [
                paragraph("Interpretation", "DockingH2"),
                bullets(scientific.narrative.interpretation),
                KeepTogether(
                    [
                        paragraph("Conclusion", "DockingH2"),
                        paragraph(
                            scientific.narrative.conclusion,
                            "DockingCallout",
                        ),
                    ]
                ),
                paragraph("What this result does not establish", "DockingH2"),
                bullets(scientific.narrative.limitations),
                paragraph("Recommended next analyses", "DockingH2"),
                bullets(scientific.narrative.next_steps),
                Spacer(1, 9 * mm),
                paragraph("Reproducibility Appendix", "DockingTitle"),
                paragraph(
                    "Technical identities and execution provenance are retained "
                    "here for audit and reconstruction, separate from the "
                    "scientific narrative. Scientific identity remains anchored "
                    "by the durable run manifest, source hashes, prepared "
                    "artifacts, task/attempt history, and captured toolchain.",
                    "DockingSubtitle",
                ),
            ]
        )

        provenance_rows = [
            ("Run ID", report.run_id),
            ("Run manifest ID", report.run_manifest_id or "n/a"),
            ("Experiment ID", report.experiment_id),
            ("Protocol ID", report.protocol_id),
            ("Task manifest ID", report.manifest_id),
            ("Search space ID", report.search_space_id or "n/a"),
            ("Receptor ID", report.receptor_id or "n/a"),
            ("Prepared receptor ID", report.prepared_receptor_id),
            (
                "Receptor source SHA-256",
                report.receptor_source_sha256 or "n/a",
            ),
        ]
        for ligand_id, source_sha256 in report.ligand_sources:
            provenance_rows.append(
                (f"Ligand source SHA-256 ({ligand_id})", source_sha256)
            )
        story.extend(
            [
                paragraph("Scientific identities", "DockingH2"),
                key_value_table(provenance_rows),
            ]
        )

        snapshot = report.toolchain_snapshot
        if snapshot is not None:
            story.extend(
                [
                    paragraph("Toolchain", "DockingH2"),
                    striped_table(
                        [
                            ["Tool", "Version", "Resolved executable"],
                            [
                                "AutoDock Vina",
                                snapshot.vina.version,
                                snapshot.vina.resolved_path,
                            ],
                            [
                                "Meeko ligand",
                                snapshot.meeko_ligand.version,
                                snapshot.meeko_ligand.resolved_path,
                            ],
                            [
                                "Meeko receptor",
                                snapshot.meeko_receptor.version,
                                snapshot.meeko_receptor.resolved_path,
                            ],
                        ],
                        [36 * mm, 22 * mm, 116 * mm],
                        mono_columns=(2,),
                    ),
                ]
            )

        pose_trace_rows = [["Ligand", "Rank", "Pose ID", "Score family"]]
        for pose in scientific.poses:
            pose_trace_rows.append(
                [
                    pose.ligand_id,
                    pose.rank if pose.rank is not None else "—",
                    pose.pose_id,
                    f"{pose.method}/{pose.score_kind}",
                ]
            )
        if len(pose_trace_rows) > 1:
            story.extend(
                [
                    paragraph("Pose traceability", "DockingH2"),
                    striped_table(
                        pose_trace_rows,
                        [25 * mm, 16 * mm, 88 * mm, 45 * mm],
                        mono_columns=(2,),
                        right_columns=(1,),
                    ),
                ]
            )

        execution_rows = [
            ["Task", "Ligand", "Status", "Attempts", "Final attempt"]
        ]
        for task in report.tasks:
            execution_rows.append(
                [
                    task.task_id,
                    task.ligand_id,
                    task.status.value,
                    task.attempt_count,
                    task.final_attempt_id or "",
                ]
            )
        story.extend(
            [
                paragraph("Execution state", "DockingH2"),
                striped_table(
                    execution_rows,
                    [58 * mm, 22 * mm, 26 * mm, 18 * mm, 50 * mm],
                    mono_columns=(0, 4),
                    right_columns=(3,),
                ),
            ]
        )

        failed = [task for task in report.tasks if task.error]
        if failed:
            story.append(paragraph("Failure diagnostics", "DockingH2"))
            for task in failed:
                kind = (
                    task.failure_kind.value
                    if task.failure_kind is not None
                    else "UNCLASSIFIED"
                )
                diagnostic = (
                    str(task.error)
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                    .replace("\n", "<br/>")
                )
                story.extend(
                    [
                        paragraph(f"{task.task_id} | {kind}", "DockingMono"),
                        Paragraph(diagnostic, styles["DockingDiagnostic"]),
                    ]
                )

        artifact_rows = [["Task", "Artifact ID"]]
        for task in report.tasks:
            for artifact_id in task.artifact_ids:
                artifact_rows.append([task.task_id, artifact_id])
        if len(artifact_rows) > 1:
            story.extend(
                [
                    paragraph("Execution artifacts", "DockingH2"),
                    striped_table(
                        artifact_rows,
                        [87 * mm, 87 * mm],
                        mono_columns=(0, 1),
                    ),
                ]
            )

        document.build(
            story,
            onFirstPage=footer,
            onLaterPages=footer,
            canvasmaker=InvariantCanvas,
        )
        return buffer.getvalue()

    def write(
        self,
        report: PipelineReport,
        destination: str | Path | BinaryIO,
    ):
        payload = self.render(report)
        if hasattr(destination, "write"):
            destination.write(payload)
            return destination
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path
