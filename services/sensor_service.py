from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import desc

from models.sensor import SensorReading
from core.anomaly_engine import detect_anomalies


def ingest_reading(db: Session, device_id: str, lat: float, lon: float,
                    temp_c: float, tds_ppm: float, pressure_hpa: float,
                    timestamp: datetime | None = None) -> tuple[SensorReading, list]:
    """
    timestamp: the reading's own capture time from the Arduino/Pi bridge, if
    supplied. Used as created_at instead of server-arrival time, so the
    pressure drop-rate calculation in the anomaly engine reflects when the
    reading was actually taken — not when it happened to reach the network,
    which matters if the bridge buffers or retries.
    """
    reading = SensorReading(
        device_id=device_id, lat=lat, lon=lon,
        temp_c=temp_c, tds_ppm=tds_ppm, pressure_hpa=pressure_hpa,
    )
    if timestamp is not None:
        reading.created_at = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)
    db.add(reading)
    db.commit()
    db.refresh(reading)

    anomalies = detect_anomalies(db, reading)
    return reading, anomalies


def get_latest_readings(db: Session, device_id: str | None = None, limit: int = 50) -> list[SensorReading]:
    q = db.query(SensorReading)
    if device_id:
        q = q.filter(SensorReading.device_id == device_id)
    return q.order_by(desc(SensorReading.created_at)).limit(limit).all()
