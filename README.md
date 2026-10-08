# OceanMind AI — Backend

FastAPI backend for **OceanMind AI** (SIH25040, Ministry of Earth Sciences): ARGO ocean
data + a live coastal sensor node + a RAG chatbot + statistical anomaly detection.

## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:
- `GROQ_API_KEY` — get a free key at https://console.groq.com/keys. Without it, the
  chatbot endpoint still runs and returns a clear "not configured" message instead of
  crashing, so the rest of the app (sensor ingest, dashboard, anomalies) works standalone.
- Everything else has a sensible default — SQLite locally, no other services required.

## Run

```bash
uvicorn main:app --reload --port 8000
```

Visit `http://localhost:8000/docs` for interactive Swagger docs of every endpoint.

On startup the app creates all tables and tries one ARGO ERDDAP sync. If you're offline
or ERDDAP is unreachable, that sync just logs a warning and skips — it will not crash
the app, and the nightly cron (02:00) will retry automatically once online.

## Seeding demo data (recommended before your first demo)

Real-time ARGO coverage directly at a specific coastal point is often thin — floats are
open-ocean by design, which is the whole reason this project's hardware node exists. For
a reliable anomaly-detection demo (e.g. the salt-in-bucket script), seed some realistic
baseline profiles near the Puri coast demo coordinate:

```bash
python -m scripts.seed_demo_data
```

This inserts ~24 profiles into `argo_cache` and indexes them into ChromaDB, so
`GET /api/anomaly/active` and the chatbot both have a real baseline to reason against.

## Project layout

```
main.py              FastAPI app, lifespan startup (DB init, ARGO sync, scheduler)
config.py             Settings loaded from .env
api/routes/           chat.py, sensor.py, argo.py, anomaly.py, report.py
api/deps.py            shared DB session dependency
core/
  argo_client.py       ERDDAP fetch + cache
  anomaly_engine.py     mean/std baseline comparison, severity classification
  rag_pipeline.py       Groq chat completion + audience classification
  embeddings.py          ChromaDB indexing/retrieval for RAG
  report_gen.py          PDF report builder (reportlab)
  ws_manager.py           WebSocket broadcast for live dashboard updates
models/                SQLAlchemy models: sensor, conversation, argo_cache, anomaly
schemas/                Pydantic request/response models
services/                 business logic used by routes
scripts/seed_demo_data.py  offline demo-data seeder
```

## Key endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/sensor/ingest` | Push a reading from the Arduino/Pi Python bridge |
| GET | `/api/sensor/latest` | Latest N readings for the dashboard |
| WS | `/api/sensor/stream` | Live push to the dashboard as readings arrive |
| POST | `/api/chat/message` | Chatbot — ARGO + live sensor + anomaly context |
| GET | `/api/argo/profiles` | Query cached ARGO profiles by bounding box |
| GET | `/api/anomaly/active` | Unresolved anomalies for the alert banner/feed |
| POST | `/api/report/generate` | Streams a PDF report for a date range |
| GET | `/api/health` | DB / ChromaDB / ARGO cache status |

## Connecting the hardware

The Python serial bridge (Phase 1, Arduino via USB) or the standalone Pi (Phase 2) both
just need to `POST` JSON matching `schemas.sensor.SensorIngestRequest` to
`/api/sensor/ingest`. Nothing else in the backend needs to know which phase you're on.

## Notes

- SQLite is the default and is genuinely fine for the hackathon timeline — swap
  `DATABASE_URL` for a Postgres/Supabase URL for the finals deployment with zero code
  changes (SQLAlchemy handles both).
- `argo_cache` arrays are stored as JSON so this works identically on SQLite and
  Postgres. Migrate to native Postgres `ARRAY` columns later if you want, it's optional.
- The anomaly engine deliberately does *not* use ML — mean ± 2σ / 3σ, plus a rate check
  for pressure. Per the blueprint: simple statistics win here, and it's explainable to
  judges in one sentence.
- Set `SENSOR_API_KEY` in `.env` and send it as `X-API-Key` on `/api/sensor/ingest`
  before deploying publicly, so readings can't be spoofed by anyone who finds the URL.
  Left blank by default so local/demo use needs no extra setup.

### Anomaly baselines — why temperature, salinity, and pressure aren't all compared the same way

- **Temperature** is compared against nearby ARGO floats' *surface-only* readings
  (≤ `BASELINE_SURFACE_DEPTH_M`, default 15m). Celsius is the same physical quantity in
  both datasets, and filtering to surface depths avoids diluting the baseline with ARGO's
  deep (100m+) samples, which the coastal node never measures.
- **Salinity (TDS proxy)** is compared against the *sensor node's own rolling history*,
  not ARGO. ARGO's `PSAL` is lab-grade conductivity salinity in PSU; a cheap gravity TDS
  sensor reads ppm on a different scale. Converting one to the other needs calibration
  against a known-salinity sample — without that, a direct ARGO comparison produces a
  sigma value that looks precise but isn't measuring anything real.
- **Pressure** is also compared against the node's own history (rate of change, hPa/hour)
  plus an absolute `<1000hPa` threshold — not ARGO. ARGO's `PRES` is water pressure
  through the depth profile (dbar), which is a different physical quantity from the
  BMP280's sea-level atmospheric pressure (hPa), even though the hardware table pairs
  them as if they were equivalent.
- Both self-baselines fail safe: no anomaly is raised until a device has at least
  `SELF_BASELINE_MIN_READINGS` (default 5) prior readings to compare against.
