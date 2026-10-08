"""
Creates all tables on startup.
"""

from db.database import Base, engine

# Import every model so they register on Base.metadata
from models import sensor, conversation, argo_cache, anomaly, user


def init_db():
    Base.metadata.create_all(bind=engine)