"""
Compares each new coastal sensor reading against two different baselines,
chosen per-parameter because they aren't all comparable to ARGO in the
same way:

  - TEMPERATURE: compared against nearby ARGO floats' *surface-only*
    temperature history. Temperature in Celsius is the same physical
    quantity in both datasets, so this comparison is valid.

  - SALINITY (TDS proxy) and PRESSURE: compared against the sensor
    node's own rolling history instead of ARGO. Neither has a valid
    ARGO equivalent to diff against:
      * ARGO's PSAL is lab-grade conductivity salinity (PSU) — a cheap
        gravity TDS sensor's ppm reading is not on the same scale and
        is not directly convertible without calibration against a known
        sample, so comparing it to an ARGO PSU mean/std would be
        comparing different units and produce a meaningless sigma.
      * ARGO's PRES is *water* pressure through the depth profile
        (dbar) — physically different from the BMP280's *atmospheric*
        pressure (hPa). These are not the same quantity even though
        the original hardware table pairs them.

For Phase 1 (college demo) this is deliberately simple statistics
(mean +/- N sigma, plus a rate check for pressure) rather than a trained
model — per the blueprint, "simple statistics win here."
"""
import math
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import asc, desc

from config import settings
from models.argo_cache import ArgoProfile
from models.anomaly import Anomaly
from models.sensor import SensorReading


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _stats(vals: list[float]) -> tuple[float, float]:
    if not vals:
        return 0.0, 0.0
    arr = np.array(vals, dtype=float)
    return float(arr.mean()), float(arr.std() or 1e-6)  # avoid div-by-zero


@dataclass
class ArgoTempBaseline:
    temp_mean: float
    temp_std: float
    n_profiles: int


def get_argo_temp_baseline(db: Session, lat: float, lon: float, radius_km: float | None = None) -> ArgoTempBaseline | None:
    """
    Pulls nearby ARGO profiles and computes surface-only temperature
    mean/std. Returns None if there isn't enough nearby ARGO history to
    judge against (fails safe — no anomaly claims without a real baseline).

    Depth-filtered to <= settings.BASELINE_SURFACE_DEPTH_M: the coastal
    node reads at the surface, so mixing in deep ARGO levels (100m+) would
    bias the baseline with water that isn't comparable to what the node
    is actually measuring.
    """
    radius_km = radius_km or settings.ANOMALY_RADIUS_KM

    # Coarse bounding-box pre-filter (~1 degree ~ 111km) before exact haversine check
    deg_pad = radius_km / 111.0
    candidates = (
        db.query(ArgoProfile)
        .filter(
            ArgoProfile.lat.between(lat - deg_pad, lat + deg_pad),
            ArgoProfile.lon.between(lon - deg_pad, lon + deg_pad),
        )
        .all()
    )
    nearby = [p for p in candidates if _haversine_km(lat, lon, p.lat, p.lon) <= radius_km]
    if not nearby:
        return None

    surface_temps: list[float] = []
    for p in nearby:
        depths = p.depth_arr or []
        temps = p.temp_arr or []
        # depth_arr and temp_arr are index-aligned (one entry per sampled
        # depth level) — only keep the levels at or above the surface cutoff.
        for depth, temp in zip(depths, temps):
            if depth is not None and temp is not None and depth <= settings.BASELINE_SURFACE_DEPTH_M:
                surface_temps.append(temp)

    if not surface_temps:
        return None

    t_mean, t_std = _stats(surface_temps)
    return ArgoTempBaseline(temp_mean=t_mean, temp_std=t_std, n_profiles=len(nearby))


@dataclass
class SelfBaseline:
    mean: float
    std: float
    n_readings: int


def get_self_baseline(db: Session, device_id: str, field: str, exclude_id: str | None = None) -> SelfBaseline | None:
    """
    Rolling mean/std of a device's own past readings for the given field
    ("tds_ppm" or "pressure_hpa"). Returns None until at least
    SELF_BASELINE_MIN_READINGS are available (fail safe, same philosophy
    as the ARGO baseline).
    """
    q = db.query(SensorReading).filter(SensorReading.device_id == device_id)
    if exclude_id:
        q = q.filter(SensorReading.id != exclude_id)
    rows = q.order_by(desc(SensorReading.created_at)).limit(settings.SELF_BASELINE_WINDOW).all()

    if len(rows) < settings.SELF_BASELINE_MIN_READINGS:
        return None

    vals = [getattr(r, field) for r in rows]
    mean, std = _stats(vals)
    return SelfBaseline(mean=mean, std=std, n_readings=len(rows))


def get_previous_reading(db: Session, device_id: str, exclude_id: str | None = None) -> SensorReading | None:
    q = db.query(SensorReading).filter(SensorReading.device_id == device_id)
    if exclude_id:
        q = q.filter(SensorReading.id != exclude_id)
    return q.order_by(desc(SensorReading.created_at)).first()


def _severity(deviation_sigma: float) -> str:
    if deviation_sigma >= settings.ANOMALY_SIGMA_HIGH:
        return "HIGH"
    if deviation_sigma >= settings.ANOMALY_SIGMA_MEDIUM:
        return "MEDIUM"
    return "LOW"


def detect_anomalies(db: Session, reading: SensorReading) -> list[Anomaly]:
    """
    Runs the reading against the appropriate baseline per parameter and
    stores any anomaly records found. Returns the list of newly created
    Anomaly rows.
    """
    found: list[Anomaly] = []

    # --- Temperature: ARGO surface baseline (valid unit match) ---
    argo_baseline = get_argo_temp_baseline(db, reading.lat, reading.lon)
    is_temp_spike = False
    temp_sigma = 0.0
    if argo_baseline is not None:
        temp_sigma = (reading.temp_c - argo_baseline.temp_mean) / argo_baseline.temp_std
        is_temp_spike = temp_sigma >= settings.ANOMALY_SIGMA_MEDIUM

    # --- Salinity (TDS proxy): device's own rolling history ---
    sal_self = get_self_baseline(db, reading.device_id, "tds_ppm", exclude_id=reading.id)
    is_sal_drop = is_sal_spike = False
    sal_sigma = 0.0
    if sal_self is not None:
        sal_sigma = (reading.tds_ppm - sal_self.mean) / sal_self.std
        is_sal_drop = sal_sigma <= -settings.ANOMALY_SIGMA_MEDIUM
        is_sal_spike = sal_sigma >= settings.ANOMALY_SIGMA_MEDIUM

    # Compound anomaly: temp spike + salinity drop together = pre-cyclone signature
    if is_temp_spike and is_sal_drop:
        found.append(
            Anomaly(
                sensor_reading_id=reading.id,
                anomaly_type="COMPOUND",
                severity="HIGH",
                description=(
                    f"Combined temperature spike and salinity-proxy drop detected — "
                    f"temperature {temp_sigma:.1f}sigma above the ARGO surface baseline "
                    f"with a simultaneous salinity-proxy drop ({abs(sal_sigma):.1f}sigma "
                    f"below this node's own recent readings). This pattern may be "
                    f"consistent with conditions associated with pre-cyclone systems "
                    f"and requires further validation."
                ),
            )
        )
    else:
        if is_temp_spike:
            sev = _severity(temp_sigma)
            found.append(
                Anomaly(
                    sensor_reading_id=reading.id,
                    anomaly_type="TEMP_SPIKE",
                    severity=sev,
                    description=(
                        f"Water temperature {reading.temp_c:.1f}C is {temp_sigma:.1f}sigma above the "
                        f"ARGO surface baseline ({argo_baseline.temp_mean:.1f}C, n={argo_baseline.n_profiles} "
                        f"nearby profiles)"
                        + (" — coral bleaching risk elevated." if sev == "HIGH" else " for this location.")
                    ),
                )
            )
        if is_sal_drop:
            found.append(
                Anomaly(
                    sensor_reading_id=reading.id,
                    anomaly_type="SALINITY_DROP",
                    severity=_severity(abs(sal_sigma)),
                    description=(
                        f"Salinity proxy (TDS {reading.tds_ppm:.0f}ppm) is {abs(sal_sigma):.1f}sigma below "
                        f"this node's own recent average ({sal_self.mean:.0f}ppm) — possible freshwater "
                        f"influx (river discharge or pre-monsoon dilution pattern)."
                    ),
                )
            )
        if is_sal_spike:
            found.append(
                Anomaly(
                    sensor_reading_id=reading.id,
                    anomaly_type="SALINITY_SPIKE",
                    severity=_severity(sal_sigma),
                    description=(
                        f"Salinity proxy (TDS {reading.tds_ppm:.0f}ppm) is {sal_sigma:.1f}sigma above "
                        f"this node's own recent average ({sal_self.mean:.0f}ppm) — possible evaporation "
                        f"anomaly or upwelling."
                    ),
                )
            )

    # --- Pressure: rate of drop (own history) + absolute low-pressure threshold ---
    prev = get_previous_reading(db, reading.device_id, exclude_id=reading.id)
    drop_rate_hpa_hr = None
    if prev is not None:
        prev_time = prev.created_at
        cur_time = reading.created_at or datetime.now(timezone.utc)
        if prev_time.tzinfo is None:
            prev_time = prev_time.replace(tzinfo=timezone.utc)
        if cur_time.tzinfo is None:
            cur_time = cur_time.replace(tzinfo=timezone.utc)
        hours_elapsed = max((cur_time - prev_time).total_seconds() / 3600.0, 1e-6)
        drop_rate_hpa_hr = (prev.pressure_hpa - reading.pressure_hpa) / hours_elapsed

    is_rapid_drop = drop_rate_hpa_hr is not None and drop_rate_hpa_hr >= settings.PRESSURE_DROP_RATE_HPA_PER_HR
    is_low_absolute = reading.pressure_hpa < 1000

    # Both conditions required together, per the blueprint's B7 spec
    # ("pressure < 1000 hPa + rapid drop rate"). Absolute-only would flag
    # an ordinary slow seasonal dip below 1000hPa as a HIGH alert; requiring
    # the rate check too keeps this specific to an actually developing system.
    is_pressure_anomaly = is_low_absolute and is_rapid_drop

    if is_pressure_anomaly:
        found.append(
            Anomaly(
                sensor_reading_id=reading.id,
                anomaly_type="PRESSURE_DROP",
                severity="HIGH",
                description=(
                    f"Atmospheric pressure {reading.pressure_hpa:.1f}hPa is below 1000hPa "
                    f"and falling at {drop_rate_hpa_hr:.2f}hPa/hr — monitor for a developing "
                    f"low pressure system."
                ),
            )
        )

    for a in found:
        db.add(a)
    if found:
        db.commit()
        for a in found:
            db.refresh(a)

    return found
