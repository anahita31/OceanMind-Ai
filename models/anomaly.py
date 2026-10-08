import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Anomaly(Base):
    __tablename__ = "anomalies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    sensor_reading_id: Mapped[str] = mapped_column(String(36), ForeignKey("sensor_readings.id"))
    anomaly_type: Mapped[str] = mapped_column(String(50))  # TEMP_SPIKE / SALINITY_DROP / etc.
    severity: Mapped[str] = mapped_column(String(10))  # LOW / MEDIUM / HIGH
    description: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
