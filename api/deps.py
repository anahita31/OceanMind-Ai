"""Shared FastAPI dependencies (DB session, etc.)."""
from db.database import get_db  # re-exported for convenient `from api.deps import get_db`

__all__ = ["get_db"]
