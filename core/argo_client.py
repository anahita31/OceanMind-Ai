"""
Wrapper around the Ifremer ERDDAP ARGO endpoint.

NOTE (per project blueprint): never call ERDDAP on a per-user-request basis.
Sync happens once on startup and then nightly via APScheduler — everything
the API serves comes from the local `argo_cache` table.
"""
from datetime import date, datetime, timedelta, timezone
import logging

import httpx
from sqlalchemy.orm import Session

from config import settings
from models.argo_cache import ArgoProfile

logger = logging.getLogger("oceanmind.argo_client")


def _build_erddap_url() -> str:
    """
    Builds an ERDDAP tabledap query for the configured Indian Ocean bounding
    box and lookback window. Requests the core profile variables needed to
    reconstruct depth/temp/salinity/pressure arrays per float.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=settings.ARGO_SYNC_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    fields = "platform_number,time,latitude,longitude,pres,temp,psal"
    constraints = (
        f"&latitude>={settings.ARGO_LAT_MIN}&latitude<={settings.ARGO_LAT_MAX}"
        f"&longitude>={settings.ARGO_LON_MIN}&longitude<={settings.ARGO_LON_MAX}"
        f"&time>={since}"
    )
    return f"{settings.ARGO_BASE_URL}.json?{fields}{constraints}"


async def fetch_argo_profiles() -> list[dict]:
    """
    Fetches raw ARGO rows from ERDDAP and groups them into per-float,
    per-day profiles (one row per depth level in the source data).
    Returns a list of dicts ready to be stored as ArgoProfile rows.
    """
    url = _build_erddap_url()
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:
        logger.warning("ARGO ERDDAP fetch failed (%s) — skipping this sync cycle", exc)
        return []

    rows = payload.get("table", {}).get("rows", [])
    columns = payload.get("table", {}).get("columnNames", [])
    col_idx = {name: i for i, name in enumerate(columns)}

    # Group rows into profiles keyed by (float_id, date). Depth, temperature,
    # and salinity are appended together per row so the three arrays stay
    # index-aligned — a row missing one field gets `None` in that array's
    # slot rather than being silently skipped, which would otherwise shift
    # every later index out of alignment (e.g. pairing one row's temperature
    # with a different row's depth). A row with no `pres` value is skipped
    # entirely for this profile, since without it there's no depth to anchor
    # the other readings to.
    grouped: dict[tuple, dict] = {}
    for row in rows:
        wmo_id = str(row[col_idx["platform_number"]])
        ts = row[col_idx["time"]]
        profile_date = ts.split("T")[0] if isinstance(ts, str) else str(ts)
        key = (wmo_id, profile_date)

        pres = row[col_idx["pres"]] if "pres" in col_idx else None
        if pres is None:
            continue  # no depth reference — can't place this row in the profile

        if key not in grouped:
            grouped[key] = {
                "wmo_id": wmo_id,
                "profile_date": profile_date,
                "lat": row[col_idx["latitude"]],
                "lon": row[col_idx["longitude"]],
                "depth_arr": [],
                "temp_arr": [],
                "salinity_arr": [],
                "pressure_arr": [],
            }

        temp = row[col_idx["temp"]] if "temp" in col_idx else None
        psal = row[col_idx["psal"]] if "psal" in col_idx else None

        grouped[key]["depth_arr"].append(pres)
        grouped[key]["pressure_arr"].append(pres)
        grouped[key]["temp_arr"].append(temp)     # None if this row didn't report it
        grouped[key]["salinity_arr"].append(psal)  # None if this row didn't report it

    return list(grouped.values())


def store_profiles(db: Session, profiles: list[dict]) -> int:
    """Upserts profiles into argo_cache. Returns count stored."""
    count = 0
    for p in profiles:
        try:
            profile_date = datetime.strptime(p["profile_date"], "%Y-%m-%d").date()
        except ValueError:
            continue

        exists = (
            db.query(ArgoProfile)
            .filter(ArgoProfile.wmo_id == p["wmo_id"], ArgoProfile.profile_date == profile_date)
            .first()
        )
        if exists:
            continue

        db.add(
            ArgoProfile(
                wmo_id=p["wmo_id"],
                profile_date=profile_date,
                lat=p["lat"],
                lon=p["lon"],
                depth_arr=p["depth_arr"],
                temp_arr=p["temp_arr"],
                salinity_arr=p["salinity_arr"],
                pressure_arr=p["pressure_arr"],
            )
        )
        count += 1

    db.commit()
    logger.info("ARGO sync: stored %d new profiles", count)
    return count


async def sync_argo_data(db: Session) -> int:
    """Full sync cycle: fetch from ERDDAP, store new profiles. Safe to call repeatedly."""
    profiles = await fetch_argo_profiles()
    if not profiles:
        return 0
    return store_profiles(db, profiles)
