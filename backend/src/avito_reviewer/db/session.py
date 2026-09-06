"""Engine and session factory.

No Alembic here on purpose: the hackathon shape has three tables and no data
worth migrating yet (`docs/handover-backend.md`'s TODO list already says so under
"Инфраструктура"). Startup runs `Base.metadata.create_all` and that is the
whole migration story until there is a schema worth versioning.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from avito_reviewer.config import DatabaseConfig

from .models import Base


def make_engine(config: DatabaseConfig) -> AsyncEngine:
    return create_async_engine(config.dsn, echo=config.echo, pool_pre_ping=True)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_models(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def session_dependency(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: one session per request, from the app-wide sessionmaker."""
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with sessionmaker() as session:
        yield session
