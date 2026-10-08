from fastapi import APIRouter, Depends, Header, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from config import settings
from api.deps import get_db
from schemas.sensor import SensorIngestRequest, SensorIngestResponse, SensorReadingOut
from services.sensor_service import ingest_reading, get_latest_readings
from core.ws_manager import manager

router = APIRouter(prefix="/api/sensor", tags=["sensor"])


def _check_sensor_api_key(x_api_key: str | None):
    """
    No-op when SENSOR_API_KEY is unset (default) so local/demo use needs no
    setup. Set SENSOR_API_KEY in .env before exposing /ingest publicly, so
    readings can't be spoofed by anyone who finds the URL.
    """
    if settings.SENSOR_API_KEY and x_api_key != settings.SENSOR_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


@router.post("/ingest", response_model=SensorIngestResponse)
async def ingest(
    payload: SensorIngestRequest,
    db: Session = Depends(get_db),
    x_api_key: str | None = Header(default=None),
):
    """Ingests a reading from the Arduino/Pi node (via the Python serial bridge)."""
    _check_sensor_api_key(x_api_key)
    reading, anomalies = ingest_reading(
        db,
        device_id=payload.device_id, lat=payload.lat, lon=payload.lon,
        temp_c=payload.temp_c, tds_ppm=payload.tds_ppm, pressure_hpa=payload.pressure_hpa,
        timestamp=payload.timestamp,
    )

    reading_out = SensorReadingOut.model_validate(reading)

    # Push to any connected dashboards in real time
    await manager.broadcast({
        "type": "sensor_reading",
        "reading": reading_out.model_dump(mode="json"),
        "anomalies": [{"type": a.anomaly_type, "severity": a.severity, "description": a.description} for a in anomalies],
    })

    return SensorIngestResponse(
        status="ok",
        reading=reading_out,
        anomaly_detected=bool(anomalies),
        severity=max((a.severity for a in anomalies), default=None,
                     key=lambda s: {"LOW": 0, "MEDIUM": 1, "HIGH": 2}.get(s, 0)) if anomalies else None,
    )


@router.get("/latest", response_model=list[SensorReadingOut])
def latest(device_id: str | None = None, n: int = 50, db: Session = Depends(get_db)):
    readings = get_latest_readings(db, device_id=device_id, limit=n)
    return [SensorReadingOut.model_validate(r) for r in readings]


@router.websocket("/stream")
async def stream(ws: WebSocket):
    """Frontend connects here on dashboard load; receives new readings as they arrive."""
    await manager.connect(ws)
    try:
        while True:
            # Client isn't expected to send anything; this just keeps the connection open.
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
