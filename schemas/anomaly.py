from datetime import datetime
from pydantic import BaseModel


class AnomalyOut(BaseModel):
    id: str
    sensor_reading_id: str
    anomaly_type: str
    severity: str
    description: str
    resolved: bool
    created_at: datetime

    class Config:
        from_attributes = True
