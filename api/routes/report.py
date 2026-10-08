from datetime import date, datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
import io

from api.deps import get_db
from models.sensor import SensorReading
from models.anomaly import Anomaly
from core.report_gen import generate_report_pdf

router = APIRouter(prefix="/api/report", tags=["report"])


class ReportRequest(BaseModel):
    title: str = "Coastal Monitoring Report"
    summary: str = ""
    device_id: str | None = None
    date_from: date | None = None
    date_to: date | None = None


@router.post("/generate")
def generate(payload: ReportRequest, db: Session = Depends(get_db)):
    """
    Generates a PDF research report for a given query/date range, combining
    recent sensor readings and detected anomalies. Streams the PDF back
    directly — the frontend /report page offers it as a download.
    """
    sensor_q = db.query(SensorReading)
    anomaly_q = db.query(Anomaly)

    if payload.device_id:
        sensor_q = sensor_q.filter(SensorReading.device_id == payload.device_id)

    date_from = payload.date_from or (datetime.now(timezone.utc).date() - timedelta(days=7))
    date_to = payload.date_to or datetime.now(timezone.utc).date()
    start_dt = datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(date_to, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1)

    sensor_rows = (
        sensor_q.filter(SensorReading.created_at.between(start_dt, end_dt))
        .order_by(SensorReading.created_at)
        .limit(500)
        .all()
    )
    anomaly_rows = (
        anomaly_q.filter(Anomaly.created_at.between(start_dt, end_dt))
        .order_by(Anomaly.created_at)
        .limit(200)
        .all()
    )

    summary = payload.summary or (
        f"Report covering {date_from.isoformat()} to {date_to.isoformat()}. "
        f"{len(sensor_rows)} sensor readings and {len(anomaly_rows)} detected anomalies "
        f"in range."
    )

    pdf_bytes = generate_report_pdf(
        title=payload.title,
        summary_text=summary,
        sensor_rows=[
            {
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M"),
                "temp_c": r.temp_c, "tds_ppm": r.tds_ppm, "pressure_hpa": r.pressure_hpa,
            }
            for r in sensor_rows
        ],
        anomaly_rows=[
            {
                "created_at": a.created_at.strftime("%Y-%m-%d %H:%M"),
                "anomaly_type": a.anomaly_type, "severity": a.severity, "description": a.description,
            }
            for a in anomaly_rows
        ],
    )

    filename = f"oceanmind-report-{date_from.isoformat()}-to-{date_to.isoformat()}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
