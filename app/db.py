# backend/app/db.py
"""
Database engine — supports both SQLite (standalone) and PostgreSQL (Railway/cloud).

Set SENTRIBID_DB_URL in .env:
  SQLite:     sqlite:///./sentribid.db
  PostgreSQL: postgresql://user:pass@host:5432/dbname
  Railway:    $DATABASE_URL (auto-provided)
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase


class Base(DeclarativeBase):
    pass


def _get_db_url() -> str:
    """Resolve database URL from environment. Railway provides DATABASE_URL."""
    url = os.getenv("SENTRIBID_DB_URL", "") or os.getenv("DATABASE_URL", "")
    if not url:
        url = "sqlite:///./sentribid.db"
    # Railway sometimes gives postgres:// instead of postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def make_engine():
    url = _get_db_url()
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    return create_engine(url, connect_args=connect_args, pool_pre_ping=True)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
