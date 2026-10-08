from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ArgoProfileOut(BaseModel):
    id: str
    wmo_id: str
    profile_date: date
    lat: float
    lon: float

    # ARGO data can contain null/missing measurements
    depth_arr: list[float | None]
    temp_arr: list[float | None]
    salinity_arr: list[float | None]
    pressure_arr: list[float | None]

    fetched_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ArgoProfileQuery(BaseModel):
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float

    date_from: date | None = None
    date_to: date | None = None