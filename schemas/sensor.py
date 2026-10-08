from datetime import datetime
from pydantic import BaseModel, Field


class SensorIngestRequest(BaseModel):
    device_id: str = Field(..., examples=["node-001"])
    lat: float
    lon: float
    temp_c: float
    tds_ppm: float
    pressure_hpa: float
    timestamp: datetime | None = None  # if omitted, server sets it


class SensorReadingOut(BaseModel):
    id: str
    device_id: str
    lat: float
    lon: float
    temp_c: float
    tds_ppm: float
    pressure_hpa: float
    created_at: datetime

    class Config:
        from_attributes = True


class SensorIngestResponse(BaseModel):
    status: str
    reading: SensorReadingOut
    anomaly_detected: bool
    severity: str | None = None
