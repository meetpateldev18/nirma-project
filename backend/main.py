"""
Application Main Entrypoint — FastAPI ASGI Server & Route Aggregator.

This module initializes the core FastAPI web application for the Nirma University AI Call Agent.
It mounts CORS middleware, provisions static audio file serving, binds all REST/WebSocket routers,
and configures application lifecycle hooks for database connection validation.

Upstream dependencies:
    - backend.config.settings
    - backend.database.session
    - backend.api.*
    - backend.telephony.webhook_handler
    - backend.websocket.manager

Downstream dependencies:
    - uvicorn / gunicorn ASGI web server
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from backend.api.analytics import router as analytics_router
from backend.api.auth import router as auth_router
from backend.api.calls import router as calls_router
from backend.api.campaigns import router as campaigns_router
from backend.api.students import router as students_router
from backend.config import settings
from backend.database.session import AsyncSessionLocal
from backend.telephony.webhook_handler import router as webhook_router
from backend.websocket.manager import router as ws_router

# Configure root logger
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("backend.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan context manager handling startup and shutdown events.

    Args:
        app: FastAPI application instance.
    """
    logger.info("Initializing %s (%s environment)...", settings.app_name, settings.app_env)

    # Guarantee audio cache directory exists
    os.makedirs(settings.audio_cache_dir, exist_ok=True)
    logger.info("Audio cache directory provisioned at: %s", settings.audio_cache_dir)

    # Validate database connectivity
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        logger.info("Database connection successfully established and verified.")
    except Exception as exc:
        logger.error("Database connectivity check failed during startup: %s", str(exc))

    yield

    logger.info("Shutting down %s...", settings.app_name)
    try:
        from backend.database.redis_client import redis_manager
        await redis_manager.close()

        from backend.database.session import async_engine
        await async_engine.dispose()
        logger.info("Redis and database connection pools successfully disposed.")
    except Exception as exc:
        logger.warning("Error during resource shutdown disposal: %s", str(exc))


# Create core FastAPI application instance
app = FastAPI(
    title=settings.app_name,
    description="Enterprise Multi-Lingual Automated PSTN Outbound Calling System for Nirma University",
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

# ------------------------------------------------------------------------------
# CORS Middleware Configuration
# ------------------------------------------------------------------------------
origins = [origin.strip() for origin in settings.allowed_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------------------
# Static File Audio Mount
# ------------------------------------------------------------------------------
os.makedirs(settings.audio_cache_dir, exist_ok=True)
app.mount(
    "/static/audio",
    StaticFiles(directory=settings.audio_cache_dir),
    name="static_audio",
)

# ------------------------------------------------------------------------------
# Router Bindings
# ------------------------------------------------------------------------------
app.include_router(auth_router)
app.include_router(campaigns_router)
app.include_router(calls_router)
app.include_router(students_router)
app.include_router(analytics_router)
app.include_router(webhook_router)
app.include_router(ws_router)


# ------------------------------------------------------------------------------
# Health & Status Endpoints
# ------------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, str]:
    """
    Service health check probe used by Docker and Nginx reverse proxy.

    Returns:
        JSON response with system status, environment, and database health.
    """
    db_status = "healthy"
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        logger.error("Health check DB probe failure: %s", str(exc))
        db_status = "unhealthy"

    return {
        "status": "online" if db_status == "healthy" else "degraded",
        "app_name": settings.app_name,
        "environment": settings.app_env,
        "database": db_status,
        "base_url": settings.base_url,
    }
