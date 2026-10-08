from datetime import date

from sqlalchemy.orm import Session

from models.argo_cache import ArgoProfile


def query_profiles(
    db: Session,
    lat_min: float, lat_max: float, lon_min: float, lon_max: float,
    date_from: date | None = None, date_to: date | None = None,
    limit: int = 200,
) -> list[ArgoProfile]:
    q = db.query(ArgoProfile).filter(
        ArgoProfile.lat.between(lat_min, lat_max),
        ArgoProfile.lon.between(lon_min, lon_max),
    )
    if date_from:
        q = q.filter(ArgoProfile.profile_date >= date_from)
    if date_to:
        q = q.filter(ArgoProfile.profile_date <= date_to)
    return q.order_by(ArgoProfile.profile_date.desc()).limit(limit).all()


def get_float_profiles(db: Session, wmo_id: str) -> list[ArgoProfile]:
    return (
        db.query(ArgoProfile)
        .filter(ArgoProfile.wmo_id == wmo_id)
        .order_by(ArgoProfile.profile_date.desc())
        .all()
    )
