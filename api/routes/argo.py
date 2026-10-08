from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.deps import get_db
from schemas.argo import ArgoProfileOut
from services.argo_service import query_profiles, get_float_profiles

router = APIRouter(prefix="/api/argo", tags=["argo"])


@router.get("/profiles", response_model=list[ArgoProfileOut])
def profiles(
    lat_min: float = Query(..., description="Southern bound of bounding box"),
    lat_max: float = Query(..., description="Northern bound of bounding box"),
    lon_min: float = Query(..., description="Western bound of bounding box"),
    lon_max: float = Query(..., description="Eastern bound of bounding box"),
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    """Query cached ARGO profiles by lat/lon bounding box and optional date range."""
    rows = query_profiles(db, lat_min, lat_max, lon_min, lon_max, date_from, date_to, limit)
    return [ArgoProfileOut.model_validate(r) for r in rows]


@router.get("/float/{wmo_id}", response_model=list[ArgoProfileOut])
def float_profiles(wmo_id: str, db: Session = Depends(get_db)):
    """All cached profiles for a specific ARGO float, by WMO ID, most recent first."""
    rows = get_float_profiles(db, wmo_id)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No cached profiles found for float {wmo_id}")
    return [ArgoProfileOut.model_validate(r) for r in rows]
