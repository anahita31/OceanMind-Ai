import uuid
from datetime import datetime, date, timezone

from sqlalchemy import String, Float, Date, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ArgoProfile(Base):
    """
    A cached ARGO float profile. depth/temp/salinity/pressure arrays are stored
    as JSON so this works identically on SQLite (dev) and Postgres (prod) —
    Postgres users can migrate to native ARRAY columns later if needed.
    """

    __tablename__ = "argo_cache"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    wmo_id: Mapped[str] = mapped_column(String(20), index=True)
    profile_date: Mapped[date] = mapped_column(Date, index=True)
    lat: Mapped[float] = mapped_column(Float, index=True)
    lon: Mapped[float] = mapped_column(Float, index=True)
    depth_arr: Mapped[list] = mapped_column(JSON, default=list)
    temp_arr: Mapped[list] = mapped_column(JSON, default=list)
    salinity_arr: Mapped[list] = mapped_column(JSON, default=list)
    pressure_arr: Mapped[list] = mapped_column(JSON, default=list)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
