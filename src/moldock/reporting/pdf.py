from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from .model import PipelineReport


class ReportLabPipelineReporter:
    """Render an auditable, deterministic PDF presentation of a pipeline report.

    ReportLab is an optional dependency. Install ``docking-engine[pdf]`` to
    enable this renderer. The PDF is presentation-only: scientific identity
    remains anchored by the durable report/run-manifest data.
    """

    def render(self, report: PipelineReport) -> bytes:
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib.units import mm
            from reportlab.pdfgen.canvas import Canvas
            from reportlab.platypus import (
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

        navy = colors.HexColor("#17324D")
        pale = colors.HexColor("#F4F7FB")
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
                fontSize=22,
                leading=26,
                textColor=navy,
                spaceAfter=5 * mm,
            )
        )
        styles.add(
            ParagraphStyle(
                name="DockingSubtitle",
                parent=styles["BodyText"],
                fontName="Helvetica",
                fontSize=10,
                leading=14,
                textColor=muted,
                spaceAfter=5 * mm,
            )
        )
        styles.add(
            ParagraphStyle(
                name="DockingH2",
                parent=styles["Heading2"],
                fontName="Helvetica-Bold",
                fontSize=13,
                leading=16,
                textColor=navy,
                spaceBefore=4 * mm,
                spaceAfter=2.5 * mm,
            )
        )
        styles.add(
            ParagraphStyle(
                name="DockingBody",
                parent=styles["BodyText"],
                fontName="Helvetica",
                fontSize=8.5,
                leading=11,
                textColor=text,
            )
        )
        styles.add(
            ParagraphStyle(
                name="DockingHeader",
                parent=styles["BodyText"],
                fontName="Helvetica-Bold",
                fontSize=8,
                leading=10,
                textColor=white,
            )
        )
        styles.add(
            ParagraphStyle(
                name="DockingMono",
                parent=styles["BodyText"],
                fontName="Courier",
                fontSize=7.2,
                leading=9.2,
                textColor=text,
                wordWrap="CJK",
            )
        )
        styles.add(
            ParagraphStyle(
                name="DockingMetric",
                parent=styles["BodyText"],
                fontName="Helvetica-Bold",
                fontSize=17,
                leading=19,
                alignment=2,
                textColor=navy,
            )
        )
        styles.add(
            ParagraphStyle(
                name="DockingMetricLabel",
                parent=styles["BodyText"],
                fontName="Helvetica",
                fontSize=7.5,
                leading=9,
                textColor=muted,
            )
        )
        styles.add(
            ParagraphStyle(
                name="DockingNote",
                parent=styles["BodyText"],
                fontName="Helvetica",
                fontSize=8,
                leading=11,
                textColor=muted,
            )
        )

        class InvariantCanvas(Canvas):
            def __init__(self, *args, **kwargs):
                kwargs["invariant"] = 1
                kwargs["pageCompression"] = 1
                super().__init__(*args, **kwargs)

        def paragraph(value: object, style: str = "DockingBody"):
            escaped = (
                str("" if value is None else value)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            return Paragraph(escaped, styles[style])

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
                        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
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

        buffer = BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=18 * mm,
            leftMargin=18 * mm,
            topMargin=16 * mm,
            bottomMargin=20 * mm,
            title="Molecular Docking Report",
            author="docking-engine",
            subject=f"Auditable report for run {report.run_id}",
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
                f"Molecular Docking Report | Run {report.run_id}",
            )
            canvas.drawRightString(
                width - 18 * mm,
                9 * mm,
                f"Page {doc.page}",
            )
            canvas.restoreState()

        story = [
            paragraph("MOLECULAR DOCKING REPORT", "DockingTitle"),
            paragraph(
                "Reproducible execution record with durable provenance, "
                "task state, and method-scoped scientific observations.",
                "DockingSubtitle",
            ),
        ]

        successful = (
            report.task_count > 0
            and report.failed_count == 0
            and report.succeeded_count == report.task_count
        )
        status = "SUCCEEDED" if successful else "ATTENTION"
        status_color = green if successful else red
        status_style = ParagraphStyle(
            "DockingStatus",
            parent=styles["DockingMetric"],
            textColor=status_color,
        )
        status_table = Table(
            [
                [
                    paragraph("RUN STATUS", "DockingMetricLabel"),
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
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.extend([status_table, Spacer(1, 5 * mm)])

        metric_cells = []
        for label, value in (
            ("Tasks", report.task_count),
            ("Attempts", report.attempt_count),
            ("Poses", report.pose_count),
            ("Scores", report.score_count),
        ):
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
        metric_table = Table(
            [metric_cells],
            colWidths=[43.5 * mm] * 4,
        )
        metric_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(metric_table)

        story.append(paragraph("Provenance", "DockingH2"))
        provenance_rows = [
            ("Run ID", report.run_id),
            ("Run manifest ID", report.run_manifest_id or "n/a"),
            ("Experiment ID", report.experiment_id),
            ("Protocol ID", report.protocol_id),
            ("Task manifest ID", report.manifest_id),
            ("Search space ID", report.search_space_id or "n/a"),
            ("Receptor ID", report.receptor_id or "n/a"),
            (
                "Receptor source SHA-256",
                report.receptor_source_sha256 or "n/a",
            ),
        ]
        provenance_rows.extend(
            (
                f"Ligand source SHA-256 ({ligand_id})",
                source_sha256,
            )
            for ligand_id, source_sha256 in report.ligand_sources
        )
        story.append(key_value_table(provenance_rows))

        snapshot = report.toolchain_snapshot
        if snapshot is not None:
            story.append(paragraph("Toolchain", "DockingH2"))
            story.append(
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
                )
            )

        story.append(paragraph("Execution", "DockingH2"))
        execution_rows = [
            ["Task", "Ligand", "Status", "Attempts", "Failure"]
        ]
        for task in report.tasks:
            failure = ""
            if task.failure_kind is not None:
                failure = task.failure_kind.value
            if task.error:
                failure = (
                    f"{failure}: {task.error}"
                    if failure
                    else task.error
                )
            execution_rows.append(
                [
                    task.task_id,
                    task.ligand_id,
                    task.status.value,
                    task.attempt_count,
                    failure,
                ]
            )
        story.append(
            striped_table(
                execution_rows,
                [75 * mm, 25 * mm, 29 * mm, 20 * mm, 25 * mm],
                mono_columns=(0, 4),
                right_columns=(3,),
            )
        )

        story.append(PageBreak())
        story.extend(
            [
                paragraph("Scientific observations", "DockingH2"),
                paragraph(
                    "Scores are reported in their native method context. "
                    "This report does not create a cross-method global "
                    "best_score or compare heterogeneous scoring methods "
                    "implicitly.",
                    "DockingNote",
                ),
                Spacer(1, 2 * mm),
            ]
        )

        score_rows = [
            [
                "Ligand",
                "Pose",
                "Kind",
                "Value",
                "Unit",
                "Method",
                "Version",
            ]
        ]
        for task in report.tasks:
            for score in task.scores:
                score_rows.append(
                    [
                        task.ligand_id,
                        score.pose_id,
                        score.kind,
                        f"{score.value:.3f}",
                        score.unit or "",
                        score.method,
                        score.method_version,
                    ]
                )
        story.append(
            striped_table(
                score_rows,
                [
                    16 * mm,
                    55 * mm,
                    29 * mm,
                    18 * mm,
                    20 * mm,
                    20 * mm,
                    16 * mm,
                ],
                mono_columns=(1,),
                right_columns=(3,),
            )
        )

        ranking_rows = [
            ["Ligand", "Pose", "Rank", "Ranking method"]
        ]
        for task in report.tasks:
            for ranking in task.rankings:
                ranking_rows.append(
                    [
                        task.ligand_id,
                        ranking.pose_id,
                        ranking.rank,
                        ranking.method,
                    ]
                )
        if len(ranking_rows) > 1:
            story.extend(
                [
                    paragraph(
                        "Within-method pose rankings",
                        "DockingH2",
                    ),
                    paragraph(
                        "Ranks below are preserved exactly as emitted "
                        "for their named method. They are not a ranking "
                        "across scoring methods.",
                        "DockingNote",
                    ),
                    Spacer(1, 2 * mm),
                    striped_table(
                        ranking_rows,
                        [25 * mm, 85 * mm, 20 * mm, 44 * mm],
                        mono_columns=(1,),
                        right_columns=(2,),
                    ),
                ]
            )

        artifact_rows = [["Task", "Artifact ID"]]
        for task in report.tasks:
            for artifact_id in task.artifact_ids:
                artifact_rows.append(
                    [task.task_id, artifact_id]
                )
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

        story.extend(
            [
                paragraph("Audit note", "DockingH2"),
                paragraph(
                    "This PDF is a deterministic presentation of durable "
                    "pipeline state. Scientific identity remains anchored "
                    "by the run manifest, source SHA-256 values, "
                    "prepared-artifact identities, task/attempt history, "
                    "and captured executable toolchain.",
                    "DockingNote",
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
