"""
Database Session Management Module — Dual Engine Isolation Architecture.

This module provisions database connection lifecycles for two distinct execution models:
1. Asynchronous I/O Layer (FastAPI REST endpoints & Plivo webhooks) via asyncpg.
2. Synchronous Multiprocessing Layer (Celery workers & periodic beat tasks) via psycopg with NullPool.

Architectural Rationale:
    Celery workers run in multiprocessing prefork pools. Sharing a standard connection
    pool across forked processes causes deadlock and corrupted connection states.
    Using `NullPool` for the synchronous engine guarantees that each task opens and closes
    its own discrete connection cleanly.

Dependencies:
    - sqlalchemy[asyncio] >= 2.0
    - asyncpg >= 0.29
    - psycopg >= 3.1
"""

from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from backend.config import settings

# ------------------------------------------------------------------------------
# 1. Asynchronous Engine & Session Factory (FastAPI & Webhooks)
# ------------------------------------------------------------------------------
async_engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=10,  # Optimized for Supabase transaction pooler (port 6543)
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=1800,  # Recycle connections every 30 minutes
    connect_args={
        "statement_cache_size": 0,  # Required for Supabase transaction poolers / PgBouncer
        "server_settings": {"application_name": "nirma_ai_call_agent"},
    },
)

async_session_factory = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# Canonical alias exported for FastAPI dependency and healthcheck probes
AsyncSessionLocal = async_session_factory


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency yielding an isolated asynchronous database session.

    Guarantees session rollback on unhandled exceptions and deterministic
    session closure upon response completion.

    Yields:
        AsyncSession: Active SQLAlchemy async database session.
    """
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def async_session_scope() -> AsyncGenerator[AsyncSession, None]:
    """
    Asynchronous context manager for use outside of FastAPI dependency injection.

    Yields:
        AsyncSession: Active SQLAlchemy async database session.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def set_rls_session_context(
    session: AsyncSession,
    role: str,
    user_id: int | None = None,
    institute_id: int | None = None,
    department_id: int | None = None,
    program_id: int | None = None,
    division_id: int | None = None,
) -> None:
    """Sets PostgreSQL session variables for Gate 2 Row-Level Security (RLS) enforcement."""
    try:
        bind = session.bind or async_engine
        if bind and bind.dialect.name == "postgresql":
            from sqlalchemy import text
            await session.execute(text(f"SET LOCAL app.current_user_role = '{role}';"))
            if institute_id:
                await session.execute(text(f"SET LOCAL app.current_institute_id = '{institute_id}';"))
            if department_id:
                await session.execute(text(f"SET LOCAL app.current_department_id = '{department_id}';"))
            if program_id:
                await session.execute(text(f"SET LOCAL app.current_program_id = '{program_id}';"))
            if division_id:
                await session.execute(text(f"SET LOCAL app.current_division_id = '{division_id}';"))
            if user_id:
                await session.execute(text(f"SET LOCAL app.current_user_id = '{user_id}';"))
    except Exception:
        # Gracefully pass in dialects or environments that don't support custom session variables
        pass


# ------------------------------------------------------------------------------
# 2. Synchronous Engine & Session Factory (Celery Workers & Beat Tasks)
# ------------------------------------------------------------------------------
sync_engine = create_engine(
    settings.sync_database_url,
    echo=settings.debug,
    poolclass=NullPool,  # Critical for Celery fork safety
    pool_pre_ping=True,
    connect_args={"application_name": "nirma_celery_worker"},
)

sync_session_factory = sessionmaker(
    bind=sync_engine,
    class_=Session,
    expire_on_commit=False,
    autoflush=False,
)


@contextmanager
def get_sync_session() -> Generator[Session, None, None]:
    """
    Synchronous context manager for Celery tasks.

    Ensures that every background worker task operates within its own dedicated
    database connection, committing on success and rolling back on failure.

    Yields:
        Session: Active synchronous SQLAlchemy session.
    """
    session = sync_session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
