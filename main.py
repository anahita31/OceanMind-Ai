"""
OceanMind AI Backend
FastAPI application entry point.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import settings
from db.init_db import init_db
from db.database import SessionLocal
from core.argo_client import sync_argo_data
from core.embeddings import index_profiles
from models.argo_cache import ArgoProfile

from api.routes import chat, sensor, argo, anomaly, report, auth


# ---------------------------------------------------------
# Logging
# ---------------------------------------------------------

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("oceanmind.main")


# ---------------------------------------------------------
# Scheduler
# ---------------------------------------------------------

scheduler = AsyncIOScheduler()


# ---------------------------------------------------------
# ARGO Sync + Index
# ---------------------------------------------------------

async def run_argo_sync_and_index():
    """
    Fetch new ARGO profiles, store them in the database,
    and index the latest profiles into ChromaDB.
    """

    db = SessionLocal()

    try:
        stored_count = await sync_argo_data(db)

        if stored_count:
            recent = (
                db.query(ArgoProfile)
                .order_by(ArgoProfile.fetched_at.desc())
                .limit(stored_count)
                .all()
            )

            index_profiles(recent)

            logger.info(
                "ARGO sync + index cycle complete: %d new profiles",
                stored_count,
            )

    except Exception:
        logger.exception("ARGO sync + index cycle failed")

    finally:
        db.close()


# ---------------------------------------------------------
# Application Lifespan
# ---------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):

    # Create database tables
    init_db()

    logger.info("Database tables ready")

    # Initial ARGO sync
    try:
        await run_argo_sync_and_index()
    except Exception:
        logger.exception("Initial ARGO sync failed")

    # Nightly ARGO refresh
    scheduler.add_job(
        run_argo_sync_and_index,
        "cron",
        hour=2,
        minute=0,
        id="argo_nightly_sync",
        replace_existing=True,
    )

    scheduler.start()

    logger.info(
        "APScheduler started - nightly ARGO sync scheduled for 02:00"
    )

    yield

    # Shutdown scheduler
    scheduler.shutdown(wait=False)

    logger.info("APScheduler stopped")


# ---------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------

app = FastAPI(
    title="OceanMind AI",
    description=(
        "Intelligent Ocean Data Discovery & Coastal "
        "Extension Platform - SIH25040"
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------
# CORS
# ---------------------------------------------------------

app.add_middleware(
    CORSMiddleware,

    # Frontend development URLs
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],
)


# ---------------------------------------------------------
# API Routers
# ---------------------------------------------------------

app.include_router(auth.router)

app.include_router(chat.router)

app.include_router(sensor.router)

app.include_router(argo.router)

app.include_router(anomaly.router)

app.include_router(report.router)


# ---------------------------------------------------------
# Health Check
# ---------------------------------------------------------

@app.get("/api/health", tags=["health"])
def health():

    from db.database import SessionLocal as _Session
    from core.embeddings import get_collection

    status = {
        "status": "ok",
        "db": "ok",
        "chromadb": "ok",
        "argo_cache": "ok",
    }

    # Database check
    db = _Session()

    try:
        count = db.query(ArgoProfile).count()

        status["argo_cache_profiles"] = count

    except Exception as exc:

        status["db"] = f"error: {exc}"

        status["status"] = "degraded"

    finally:

        db.close()

    # ChromaDB check
    try:

        col = get_collection()

        status["chromadb_documents"] = col.count()

    except Exception as exc:

        status["chromadb"] = f"error: {exc}"

        status["status"] = "degraded"

    return status


# ---------------------------------------------------------
# Root
# ---------------------------------------------------------

@app.get("/", tags=["health"])
def root():

    return {
        "name": "OceanMind AI",
        "tagline": "Ask the Ocean. Discover the Future.",
        "docs": "/docs",
    }