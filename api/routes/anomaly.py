from datetime import date, datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from api.deps import get_db
from schemas.anomaly import AnomalyOut
from models.anomaly import Anomaly

router = APIRouter(prefix="/api/anomaly", tags=["anomaly"])


@router.get("/active", response_model=list[AnomalyOut])
def active(db: Session = Depends(get_db)):
    """All unresolved anomalies, most recent first — powers the dashboard alert feed."""
    rows = (
        db.query(Anomaly)
        .filter(Anomaly.resolved.is_(False))
        .order_by(desc(Anomaly.created_at))
        .all()
    )
    return [AnomalyOut.model_validate(r) for r in rows]


@router.get("/history", response_model=list[AnomalyOut])
def history(
    severity: str | None = Query(None, description="Filter by LOW / MEDIUM / HIGH"),
    anomaly_type: str | None = Query(None, description="Filter by anomaly type, e.g. TEMP_SPIKE"),
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    """Historical anomaly records with optional filters."""
    q = db.query(Anomaly)
    if severity:
        q = q.filter(Anomaly.severity == severity.upper())
    if anomaly_type:
        q = q.filter(Anomaly.anomaly_type == anomaly_type.upper())
    if date_from:
        q = q.filter(Anomaly.created_at >= datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc))
    if date_to:
        q = q.filter(
            Anomaly.created_at <= datetime.combine(date_to, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1)
        )
    rows = q.order_by(desc(Anomaly.created_at)).limit(limit).all()
    return [AnomalyOut.model_validate(r) for r in rows]
