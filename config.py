"""
Central application configuration.
Reads from .env via pydantic-settings. Import `settings` anywhere you need config.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database — falls back to local SQLite if not set, so the project runs
    # with zero external setup for a first demo.
    DATABASE_URL: str = "sqlite:///./oceanmind.db"

    # LLM
    GROQ_API_KEY: str = ""
    CHAT_MODEL: str = "llama-3.3-70b-versatile"
    CLASSIFIER_MODEL: str = "llama-3.1-8b-instant"

    # Vector store
    CHROMA_PERSIST_DIR: str = "./chroma_data"

    # ARGO
    ARGO_BASE_URL: str = "https://erddap.ifremer.fr/erddap/tabledap/ArgoFloats"
    ARGO_LAT_MIN: float = 0
    ARGO_LAT_MAX: float = 25
    ARGO_LON_MIN: float = 60
    ARGO_LON_MAX: float = 100
    ARGO_SYNC_DAYS: int = 90

    # App
    SECRET_KEY: str = "change_me_in_production"
    FRONTEND_ORIGIN: str = "http://localhost:3000"

    # Anomaly thresholds (in std deviations)
    ANOMALY_SIGMA_MEDIUM: float = 2.0
    ANOMALY_SIGMA_HIGH: float = 3.0
    ANOMALY_RADIUS_KM: float = 50.0

    # Only compare against ARGO depth levels at or above this depth (metres).
    # The coastal sensor node reads at the surface — mixing in ARGO's deep
    # (e.g. 100m+) levels would bias the baseline with water that isn't
    # comparable to what the node is actually measuring.
    BASELINE_SURFACE_DEPTH_M: float = 15.0

    # TDS (ppm) and atmospheric pressure (hPa) have no valid ARGO equivalent
    # to compare against: ARGO's PSAL is lab-grade conductivity salinity on
    # a different scale than a cheap gravity TDS sensor's ppm reading, and
    # ARGO's PRES is water pressure through the depth profile (dbar) — not
    # the BMP280's sea-level atmospheric pressure (hPa). Comparing either
    # directly against an ARGO-derived mean/std would be comparing different
    # physical quantities. Both are instead judged against the sensor
    # node's own rolling history (self-baseline) — see anomaly_engine.py.
    SELF_BASELINE_WINDOW: int = 20  # how many past readings to build the rolling baseline from
    SELF_BASELINE_MIN_READINGS: int = 5  # fail safe — no anomaly claims until we have this many

    # A pressure drop faster than this (hPa/hour) is flagged regardless of
    # the self-baseline sigma comparison — rapid drops matter more than
    # slow drift for storm/cyclone early warning.
    PRESSURE_DROP_RATE_HPA_PER_HR: float = 1.0

    # Optional shared-secret header required on POST /api/sensor/ingest.
    # Leave blank for local/demo use (no auth enforced). Set it before
    # exposing the ingest endpoint on a public deployment, so readings
    # can't be spoofed by anyone who finds the URL.
    SENSOR_API_KEY: str = ""


settings = Settings()
