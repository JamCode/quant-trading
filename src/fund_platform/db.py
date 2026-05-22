"""SQLAlchemy engine (MySQL via PyMySQL)."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    from fund_platform.settings import database_url

    return create_engine(
        database_url(),
        pool_pre_ping=True,
        pool_recycle=3600,
        future=True,
    )
