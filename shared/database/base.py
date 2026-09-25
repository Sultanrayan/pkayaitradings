"""SQLAlchemy async engine and session management."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from shared.config import Settings, get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def create_engine(settings: Settings | None = None, *, echo: bool = False) -> AsyncEngine:
    """Build an async SQLAlchemy engine from settings."""
    settings = settings or get_settings()
    return create_async_engine(
        settings.postgres_url,
        echo=echo,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Return a session factory bound to ``engine``."""
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Provide a transactional session scope.

    Commits on success and rolls back on error.
    """
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def init_models(engine: AsyncEngine) -> None:
    """Create all tables (development convenience; use Alembic in production)."""
    from shared.database import models  # noqa: F401 - register mappers

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
