"""
scripts/seed_demo_data.py

Seeds a small set of realistic-looking ARGO profiles near the Puri coast
(19.8135, 85.8312 — the demo coordinate used in the blueprint's live demo
script) directly into the local DB and ChromaDB index.

Use this when:
  - You're demoing offline / without a working ERDDAP connection
  - You want deterministic baseline stats so the salt-in-bucket anomaly
    demo reliably triggers (real ERDDAP data near this exact spot may be
    sparse — ARGO floats are open-ocean, so shallow coastal coverage is
    naturally thin, which is the whole premise of this project)

Run from the project root:
    python -m scripts.seed_demo_data
"""
import random
from datetime import date, timedelta

from db.database import SessionLocal, Base, engine
from models.argo_cache import ArgoProfile
from core.embeddings import index_profiles

# Puri coast, Odisha — matches the coordinate used in the blueprint's demo script
DEMO_LAT = 19.8135
DEMO_LON = 85.8312

# Typical pre-monsoon Bay of Bengal surface values near this location
BASE_TEMP_C = 28.5
BASE_SALINITY_PSU = 33.5  # PSU scale; TDS ppm sensor is a rough coastal proxy for this
BASE_PRESSURE_DBAR = 5.0  # near-surface dbar reading (not atmospheric hPa)

N_PROFILES = 24


def make_profile(i: int) -> dict:
    # Small jitter in location (nearby floats, not exact same point) and in
    # values (realistic day-to-day variability) so std dev is non-zero and
    # a salt-spike demo reading clears the sigma threshold convincingly.
    lat = DEMO_LAT + random.uniform(-0.4, 0.4)
    lon = DEMO_LON + random.uniform(-0.4, 0.4)
    profile_date = date.today() - timedelta(days=random.randint(1, 89))

    depth_levels = [5, 10, 20, 50, 100]
    temp_arr = [round(BASE_TEMP_C - 0.02 * d + random.uniform(-0.3, 0.3), 2) for d in depth_levels]
    salinity_arr = [round(BASE_SALINITY_PSU + 0.01 * d + random.uniform(-0.2, 0.2), 2) for d in depth_levels]
    pressure_arr = [round(d * 1.0 + random.uniform(-0.1, 0.1), 2) for d in depth_levels]

    return {
        "wmo_id": f"590{6000 + i}",
        "profile_date": profile_date,
        "lat": lat,
        "lon": lon,
        "depth_arr": depth_levels,
        "temp_arr": temp_arr,
        "salinity_arr": salinity_arr,
        "pressure_arr": pressure_arr,
    }


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = db.query(ArgoProfile).filter(ArgoProfile.wmo_id.like("590%")).count()
        if existing:
            print(f"Demo profiles already present ({existing} rows) — skipping. "
                  f"Delete rows with wmo_id LIKE '590%%' to reseed.")
            return

        created = []
        for i in range(N_PROFILES):
            p = make_profile(i)
            row = ArgoProfile(**p)
            db.add(row)
            created.append(row)
        db.commit()
        for row in created:
            db.refresh(row)

        index_profiles(created)
        print(f"Seeded {len(created)} demo ARGO profiles near Puri coast "
              f"({DEMO_LAT}, {DEMO_LON}) and indexed them into ChromaDB.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
