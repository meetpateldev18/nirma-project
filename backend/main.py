"""
Application Main Entrypoint — FastAPI ASGI Server & Route Aggregator.

This module initializes the core FastAPI web application for the Nirma Calling Assistant.
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
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, Any
from pydantic import BaseModel, Field

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from backend.api.academic import router as academic_router
from backend.api.analytics import router as analytics_router
from backend.api.auth import router as auth_router
from backend.api.calls import router as calls_router
from backend.api.campaigns import router as campaigns_router
from backend.api.students import router as students_router
from backend.config import settings
from backend.database.session import AsyncSessionLocal
from backend.telephony.webhook_handler import (
    router as webhook_router,
    twilio_router as twilio_webhook_router,
)
from backend.websocket.manager import router as ws_router

# Configure root logger
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("backend.main")


async def _active_call_watchdog() -> None:
    """
    Background worker that polls carrier status every 3 seconds for active calls
    (ringing or in_progress) to catch completions when carriers do not deliver
    hangup webhooks (e.g. Twilio Free Trial parameter restrictions or abrupt user disconnects).
    """
    from datetime import datetime, timezone
    from sqlalchemy import select
    from backend.telephony.factory import get_telephony_adapter
    from backend.telephony.webhook_handler import _execute_call_hangup
    from backend.database.session import async_session_scope
    from backend.database.models import CallTask

    logger.info("Active call watchdog worker started (polling interval: 1s).")
    while True:
        try:
            await asyncio.sleep(1.0)
            async with async_session_scope() as session:
                res = await session.execute(
                    select(CallTask).where(
                        CallTask.status.in_(["ringing", "in_progress"]),
                        CallTask.plivo_uuid.is_not(None),
                    )
                )
                active_tasks = res.scalars().all()
                if not active_tasks:
                    continue

                adapter = get_telephony_adapter(settings.telephony_provider)
                for task in active_tasks:
                    call_uuid = task.plivo_uuid
                    if not call_uuid or call_uuid.startswith("mock_"):
                        continue

                    try:
                        carrier_status = await adapter.get_call_status(call_uuid)
                    except Exception as poll_err:
                        logger.warning("Watchdog poll failed for %s: %s", call_uuid, poll_err)
                        continue

                    normalized_status = carrier_status.strip().lower().replace("-", "_")
                    if normalized_status in ["completed", "busy", "no_answer", "failed", "canceled"]:
                        logger.info(
                            "Watchdog: Carrier reported call SID %s as '%s' (Task ID: %d). Finalizing hangup.",
                            call_uuid,
                            carrier_status,
                            task.id,
                        )
                        duration_sec = task.duration_sec or 0
                        if task.answered_at:
                            duration_sec = max(1, int((datetime.now(timezone.utc) - task.answered_at).total_seconds()))

                        await _execute_call_hangup(
                            task_id=task.id,
                            call_uuid=call_uuid,
                            duration=duration_sec,
                            carrier=settings.telephony_provider,
                            call_status=carrier_status,
                        )
        except asyncio.CancelledError:
            logger.info("Active call watchdog worker stopped.")
            break
        except Exception as exc:
            logger.warning("Active call watchdog encountered an error: %s", exc)


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

    # Launch active call watchdog monitor
    watchdog_task = asyncio.create_task(_active_call_watchdog())

    try:
        yield
    finally:
        watchdog_task.cancel()
        try:
            await watchdog_task
        except asyncio.CancelledError:
            pass

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
app.include_router(academic_router)
app.include_router(campaigns_router)
app.include_router(calls_router)
app.include_router(students_router)
app.include_router(analytics_router)
app.include_router(webhook_router)
app.include_router(twilio_webhook_router)
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


class SystemStatusResponse(BaseModel):
    """Dynamic operational telemetry for PSTN carrier, LLM inference, STT/TTS pipeline, and TRAI compliance."""

    pstn_status: str = Field(..., description="'active' | 'dummy' | 'error'")
    pstn_label: str = Field(..., description="Display label for PSTN gateway")
    pstn_caller_id: str = Field(..., description="Configured caller ID")
    llm_provider: str = Field(..., description="'ollama' | 'gemini' | 'groq' | 'fallback'")
    llm_label: str = Field(..., description="Display label for active LLM")
    llm_model: str = Field(..., description="Active LLM model name")
    stt_provider: str = Field(default="sarvam", description="Active speech recognition provider")
    stt_label: str = Field(default="Sarvam AI", description="Display label for active STT")
    tts_provider: str = Field(default="gemini", description="Active speech synthesis provider")
    tts_label: str = Field(default="Gemini Flash Audio", description="Display label for active TTS")
    audio_codec: str = Field(default="Twilio G.711u", description="Carrier audio stream format")
    trai_window: str = Field(default="09:00 - 21:00 IST", description="Mandated calling window")
    trai_is_open: bool = Field(..., description="Whether currently within window")
    trai_status: str = Field(..., description="'Active' | 'Deferred'")
    current_ist: str = Field(..., description="Current time in IST")


@app.get("/api/system/status", response_model=SystemStatusResponse, tags=["Health"])
async def get_system_status() -> SystemStatusResponse:
    """
    Returns live dynamic operational telemetry across PSTN gateway, LLM inference, STT/TTS engines, and TRAI regulatory window.
    """
    import zoneinfo
    from datetime import datetime
    import httpx
    from backend.scheduler.tasks import is_within_trai_calling_window

    # 1. Determine Active PSTN Carrier Gateway Status (Plivo vs Twilio, Sandbox vs Live)
    carrier_provider = settings.telephony_provider.strip().lower()
    if carrier_provider == "twilio":
        is_dummy = (
            not settings.twilio_account_sid
            or settings.twilio_account_sid.lower() in ("your_twilio_account_sid", "mock", "", "none")
            or not settings.twilio_auth_token
            or settings.twilio_auth_token.lower() in ("your_twilio_auth_token", "mock", "", "none")
            or not settings.twilio_account_sid.lower().startswith("ac")
        )
        pstn_status = "dummy" if is_dummy else "active"
        pstn_label = "Twilio Sandbox" if is_dummy else "Twilio Active"
        pstn_caller_id = settings.twilio_caller_id
        audio_codec = "Twilio G.711u (8kHz / μ-law)"
    else:
        is_dummy = (
            not settings.plivo_auth_id
            or settings.plivo_auth_id.lower() in ("your_plivo_auth_id", "mock", "", "none")
            or not settings.plivo_auth_token
            or settings.plivo_auth_token.lower() in ("your_plivo_auth_token", "mock", "", "none")
        )
        pstn_status = "dummy" if is_dummy else "active"
        pstn_label = "Plivo Sandbox" if is_dummy else "Plivo Active"
        pstn_caller_id = settings.plivo_caller_id
        audio_codec = "Plivo PCM (16kHz / Dual-Channel)"

    # 2. Determine LLM Provider (Probe Local Ollama vs Gemini vs Groq vs Fallback)
    ollama_online = False
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(0.2, connect=0.15)) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            if resp.status_code == 200:
                ollama_online = True
    except Exception:
        ollama_online = False

    if ollama_online:
        llm_provider = "ollama"
        llm_model = settings.ollama_model
        llm_label = f"Ollama GPU: {settings.ollama_model}"
    elif settings.gemini_api_key and not settings.gemini_api_key.startswith("your_"):
        llm_provider = "gemini"
        llm_model = settings.gemini_model
        llm_label = f"Gemini Flash: {settings.gemini_model}"
    elif settings.groq_api_key and not settings.groq_api_key.startswith("your_"):
        llm_provider = "groq"
        llm_model = "qwen/qwen3.8-27b"
        llm_label = "Groq Cloud"
    else:
        llm_provider = "fallback"
        llm_model = "deterministic"
        llm_label = "Deterministic Fallback"

    # 3. Determine STT Provider (Sarvam AI Cloud vs IndicConformer Local)
    if settings.sarvam_api_key and not settings.sarvam_api_key.startswith("your_"):
        stt_provider = "sarvam"
        stt_label = "Sarvam AI (saaras:v4)"
    elif os.path.exists(settings.indic_conformer_model_path or ""):
        stt_provider = "indic_conformer"
        stt_label = "IndicConformer (0.6B Local)"
    else:
        stt_provider = "sarvam" if settings.sarvam_api_key else "indic_conformer"
        stt_label = "Sarvam AI Cloud" if settings.sarvam_api_key else "IndicConformer (0.6B)"

    # 4. Determine TTS Provider (Gemini TTS vs IndicF5 Local vs Google TTS)
    if settings.gemini_api_key and not settings.gemini_api_key.startswith("your_"):
        tts_provider = "gemini"
        tts_label = "Gemini Flash Audio"
    elif os.path.exists(settings.indic_f5_model_path or ""):
        tts_provider = "indicf5"
        tts_label = "IndicF5 (Local GPU)"
    else:
        tts_provider = "gtts"
        tts_label = "Google Cloud TTS (gTTS)"

    # 5. Determine TRAI Calling Window Status
    trai_open = is_within_trai_calling_window()
    tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    now_ist = datetime.now(tz).strftime("%H:%M IST")

    return SystemStatusResponse(
        pstn_status=pstn_status,
        pstn_label=pstn_label,
        pstn_caller_id=pstn_caller_id,
        llm_provider=llm_provider,
        llm_label=llm_label,
        llm_model=llm_model,
        stt_provider=stt_provider,
        stt_label=stt_label,
        tts_provider=tts_provider,
        tts_label=tts_label,
        audio_codec=audio_codec,
        trai_window="09:00 - 21:00 IST",
        trai_is_open=trai_open,
        trai_status="Active" if trai_open else "Deferred",
        current_ist=now_ist,
    )
