"""Database engine, session factory, and initialization utilities."""

from __future__ import annotations

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.models.base import Base

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _build_engine_url(raw_url: str) -> str:
    """Normalise the DATABASE_URL so it uses the correct async driver.

    * ``sqlite:///...``   → ``sqlite+aiosqlite:///...``
    * ``postgresql://...`` → ``postgresql+asyncpg://...``
    * Already-async URLs are returned unchanged.
    """
    if raw_url.startswith("sqlite:///"):
        return raw_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return raw_url


def get_engine() -> AsyncEngine:
    """Return the singleton async engine, creating it on first call."""
    global _engine
    if _engine is None:
        settings = get_settings()
        url = _build_engine_url(settings.DATABASE_URL)

        connect_args: dict = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
            # Ensure parent directory exists for SQLite database files
            db_path = url.split("sqlite+aiosqlite:///")[-1].split("?")[0]
            if db_path and db_path != ":memory:":
                import os
                parent_dir = os.path.dirname(db_path)
                if parent_dir:
                    os.makedirs(parent_dir, exist_ok=True)

        _engine = create_async_engine(
            url,
            echo=settings.LOG_LEVEL.upper() == "DEBUG",
            connect_args=connect_args,
            pool_pre_ping=True,
        )
        logger.info("Database engine created for %s", url.split("@")[-1] if "@" in url else url)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the singleton session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session.

    Usage::

        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create all tables that don't yet exist.

    Called during application startup via the FastAPI lifespan handler.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables verified / created.")


async def close_db() -> None:
    """Dispose of the engine connection pool.

    Called during application shutdown.
    """
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database engine disposed.")
