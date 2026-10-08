"""Generates a simple PDF research report summarizing sensor + anomaly + ARGO
context for a given query/date range. Uses reportlab (no external service)."""
import io
from datetime import datetime, timezone

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors


def generate_report_pdf(
    title: str,
    summary_text: str,
    sensor_rows: list[dict],
    anomaly_rows: list[dict],
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("OceanMind AI — Research Report", styles["Title"]))
    story.append(Paragraph(title, styles["Heading2"]))
    story.append(
        Paragraph(
            f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph("Summary", styles["Heading3"]))
    story.append(Paragraph(summary_text, styles["Normal"]))
    story.append(Spacer(1, 0.5 * cm))

    if sensor_rows:
        story.append(Paragraph("Sensor Readings", styles["Heading3"]))
        data = [["Time (UTC)", "Temp (C)", "TDS (ppm)", "Pressure (hPa)"]]
        for r in sensor_rows:
            data.append([
                str(r.get("created_at", "")), str(r.get("temp_c", "")),
                str(r.get("tds_ppm", "")), str(r.get("pressure_hpa", "")),
            ])
        t = Table(data, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B5394")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.5 * cm))

    if anomaly_rows:
        story.append(Paragraph("Detected Anomalies", styles["Heading3"]))
        data = [["Time (UTC)", "Type", "Severity", "Description"]]
        for a in anomaly_rows:
            data.append([
                str(a.get("created_at", "")), str(a.get("anomaly_type", "")),
                str(a.get("severity", "")), str(a.get("description", "")),
            ])
        t = Table(data, hAlign="LEFT", colWidths=[3.2 * cm, 2.8 * cm, 2 * cm, 7 * cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#B45309")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(t)

    doc.build(story)
    return buf.getvalue()
