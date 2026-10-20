"""
Call Task API Router — Task Status, Transcript Viewer & Manual Retries.

This module provides endpoints for viewing call status, inspecting conversation transcripts,
and triggering manual call retries.

Endpoints:
    - GET /api/calls/{task_id}: Call task status and timing breakdown.
    - GET /api/calls/{task_id}/transcript: Full conversation transcript log.
    - POST /api/calls/{task_id}/retry: Manually resets failed task to pending (Admin required).

Dependencies:
    - fastapi >= 0.111
    - sqlalchemy >= 2.0
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.api.auth import get_current_user, require_admin
from backend.database.redis_client import redis_manager
from backend.config import settings
from backend.database.models import CallCampaign, CallLog, CallTask, StaffUser, utc_now
from backend.database.session import get_async_session
from backend.telephony.factory import get_telephony_adapter
from backend.websocket.manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/calls", tags=["Calls"])


# ------------------------------------------------------------------------------
# Pydantic Schemas
# ------------------------------------------------------------------------------
class CallTaskDetailResponse(BaseModel):
    """Detailed response model for a single call task."""

    id: int
    campaign_id: int
    student_id: int
    student_phone: str
    script_id: int
    status: str
    plivo_uuid: Optional[str]
    retry_count: int
    scheduled_at: datetime
    placed_at: Optional[datetime]
    answered_at: Optional[datetime]
    ended_at: Optional[datetime]
    duration_sec: Optional[int]
    outcome: Optional[str]
    created_at: datetime
    campaign_name: Optional[str] = None
    script_name: Optional[str] = None
    summary: Optional[str] = None


class CallTranscriptResponse(BaseModel):
    """Conversation transcript response model."""

    task_id: int
    stt_provider: Optional[str]
    llm_provider: Optional[str]
    tts_provider: Optional[str]
    avg_latency_ms: Optional[int]
    transcript: List[Dict[str, Any]]
    error_log: List[Dict[str, Any]]


# ------------------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------------------
async def _assert_task_access(session: AsyncSession, task_id: int, user: StaffUser) -> None:
    """Non-admin staff may only open calls belonging to campaigns they created."""
    if user.role == "admin":
        return
    res = await session.execute(
        select(CallCampaign.created_by)
        .join(CallTask, CallTask.campaign_id == CallCampaign.id)
        .where(CallTask.id == task_id)
    )
    if res.scalar_one_or_none() != user.id:
        raise HTTPException(status_code=404, detail="Call task not found.")


@router.get("/{task_id}", response_model=CallTaskDetailResponse)
async def get_call_task(
    task_id: int,
    session: AsyncSession = Depends(get_async_session),
    current_user: StaffUser = Depends(get_current_user),
) -> CallTaskDetailResponse:
    """Returns timing and state breakdown for a specific CallTask."""
    await _assert_task_access(session, task_id, current_user)
    res = await session.execute(
        select(CallTask)
        .options(selectinload(CallTask.campaign), selectinload(CallTask.script))
        .where(CallTask.id == task_id)
    )
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Call task not found.")
    detail = CallTaskDetailResponse.model_validate(task, from_attributes=True)
    if task.campaign:
        detail.campaign_name = task.campaign.name
        detail.summary = task.campaign.name
    if task.script:
        detail.script_name = task.script.name
        if not detail.summary:
            detail.summary = task.script.name
    return detail


@router.get("/{task_id}/transcript", response_model=CallTranscriptResponse)
async def get_call_transcript(
    task_id: int,
    session: AsyncSession = Depends(get_async_session),
    current_user: StaffUser = Depends(get_current_user),
) -> CallTranscriptResponse:
    """
    Returns the full conversation transcript and real-time AI telemetry for a call task.
    Supports in-flight live streaming from Redis and historical persistence from PostgreSQL.
    """
    await _assert_task_access(session, task_id, current_user)
    
    # 1. Fetch persistent log from DB if it exists
    res = await session.execute(select(CallLog).where(CallLog.task_id == task_id))
    log = res.scalar_one_or_none()

    # 2. Fetch task to check for active in-flight session in Redis
    task_res = await session.execute(select(CallTask).where(CallTask.id == task_id))
    task = task_res.scalar_one_or_none()

    # 3. Check if active session exists in Redis
    live_history = []
    if task and task.plivo_uuid:
        try:
            import json
            redis_client = await redis_manager.get_client()
            session_data = await redis_client.hgetall(f"call:session:{task.plivo_uuid}")
            if session_data and session_data.get("history"):
                live_history = json.loads(session_data.get("history", "[]"))
        except Exception as redis_err:
            logger.warning("Failed to query live Redis transcript for task %d: %s", task_id, redis_err)

    # 4. If we have live in-flight history, combine with historical logs if any
    if live_history:
        prior_turns = (log.transcript if log and isinstance(log.transcript, list) else [])
        combined = []
        if prior_turns:
            combined.extend(prior_turns)
            combined.append({
                "role": "system",
                "content": f"--- Active Re-dial (Attempt #{(task.retry_count or 0) + 1}) ---",
                "timestamp": utc_now().strftime("%H:%M:%S"),
                "latency_ms": 0,
            })
        combined.extend(live_history)

        normalized_turns = [
            {
                "role": turn.get("role", "system"),
                "text": turn.get("content") or turn.get("text", ""),
                "content": turn.get("content") or turn.get("text", ""),
                "timestamp": turn.get("timestamp"),
                "latency_ms": turn.get("latency_ms"),
            }
            for turn in combined
        ]
        latencies = [t.get("latency_ms") for t in normalized_turns if t.get("latency_ms") and t.get("latency_ms") > 0]
        avg_lat = int(sum(latencies) / len(latencies)) if latencies else 0

        return CallTranscriptResponse(
            task_id=task_id,
            stt_provider="twilio_gather" if settings.telephony_provider == "twilio" else "indic_conformer",
            llm_provider="groq" if settings.groq_api_key else "gemini",
            tts_provider="gtts",
            avg_latency_ms=avg_lat or 1500,
            transcript=normalized_turns,
            error_log=[],
        )

    if not log:
        raise HTTPException(status_code=404, detail="Transcript not found for this task.")

    normalized_turns = [
        {
            "role": turn.get("role", "system"),
            "text": turn.get("content") or turn.get("text", ""),
            "content": turn.get("content") or turn.get("text", ""),
            "timestamp": turn.get("timestamp"),
            "latency_ms": turn.get("latency_ms"),
        }
        for turn in (log.transcript if isinstance(log.transcript, list) else [])
    ]
    latencies = [t.get("latency_ms") for t in normalized_turns if t.get("latency_ms") and t.get("latency_ms") > 0]
    avg_lat = int(sum(latencies) / len(latencies)) if latencies else (log.avg_latency_ms or 0)

    return CallTranscriptResponse(
        task_id=log.task_id,
        stt_provider=log.stt_provider,
        llm_provider=log.llm_provider,
        tts_provider=log.tts_provider,
        avg_latency_ms=avg_lat,
        transcript=normalized_turns,
        error_log=log.error_log if isinstance(log.error_log, list) else [],
    )


@router.post("/{task_id}/retry", response_model=CallTaskDetailResponse)
async def retry_call_task(
    task_id: int,
    session: AsyncSession = Depends(get_async_session),
    current_user: StaffUser = Depends(require_admin),
) -> CallTaskDetailResponse:
    """
    Manually resets a failed, completed, or no-answer task to pending and dispatches
    an immediate outbound PSTN call via telephony adapter (Admin required).
    Resets active call duration and answered timestamp to ensure independent timing.
    """
    res = await session.execute(select(CallTask).where(CallTask.id == task_id))
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Call task not found.")

    task.status = "pending"
    task.outcome = None
    task.scheduled_at = utc_now()
    task.placed_at = None
    task.answered_at = None
    task.ended_at = None
    task.duration_sec = 0
    task.retry_count += 1
    await session.commit()
    await session.refresh(task)

    logger.info("Manual retry triggered for Task ID %d by admin %s", task_id, current_user.email)

    # Broadcast initial queued state to WebSocket clients
    try:
        await ws_manager.broadcast(
            "call_status",
            {
                "task_id": task.id,
                "status": "pending",
                "campaign_id": task.campaign_id,
                "retry_count": task.retry_count,
            },
        )
    except Exception as ws_err:
        logger.warning("Failed to broadcast retry status for task %d: %s", task_id, ws_err)

    # Immediately trigger call placement via telephony adapter in background thread
    async def _async_dispatch_retry(t_id: int) -> None:
        from backend.scheduler.tasks import place_call_task
        try:
            call_uuid = await asyncio.to_thread(place_call_task, t_id)
            if call_uuid:
                await ws_manager.broadcast(
                    "call_status",
                    {
                        "task_id": t_id,
                        "status": "ringing",
                        "call_uuid": call_uuid,
                    },
                )
        except Exception as exc:
            logger.error("Error dispatching manual retry for task %d: %s", t_id, exc)

    asyncio.create_task(_async_dispatch_retry(task.id))

    return CallTaskDetailResponse.model_validate(task, from_attributes=True)


@router.post("/{task_id}/hangup", response_model=CallTaskDetailResponse)
async def hangup_call_task(
    task_id: int,
    session: AsyncSession = Depends(get_async_session),
    current_user: StaffUser = Depends(get_current_user),
) -> CallTaskDetailResponse:
    """
    Terminates an active PSTN carrier call programmatically.

    Instructs carrier REST API to drop the live call, marks task completed
    with outcome 'operator_hangup', and cleans up Redis session state.
    """
    await _assert_task_access(session, task_id, current_user)
    res = await session.execute(select(CallTask).where(CallTask.id == task_id))
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Call task not found.")

    carrier = settings.telephony_provider.strip().lower()
    adapter = get_telephony_adapter(carrier)

    if task.plivo_uuid:
        try:
            await adapter.hangup_call(task.plivo_uuid)
        except Exception as exc:
            logger.warning("Carrier hangup API exception for task %d (UUID %s): %s", task_id, task.plivo_uuid, exc)

    now = utc_now()
    task.status = "completed"
    task.outcome = "operator_hangup"
    task.ended_at = now
    if task.answered_at:
        task.duration_sec = max(1, int((now - task.answered_at).total_seconds()))

    await session.commit()
    await session.refresh(task)

    # Clean up Redis session context
    if task.plivo_uuid:
        try:
            r = await redis_manager.get_client()
            await r.delete(f"call:session:{task.plivo_uuid}")
        except Exception:
            pass

    # Broadcast real-time call termination to dashboard clients
    await ws_manager.broadcast(
        "call_status",
        {
            "task_id": task.id,
            "call_uuid": task.plivo_uuid or "",
            "carrier": carrier,
            "status": "completed",
            "outcome": "operator_hangup",
            "duration_sec": task.duration_sec or 0,
        },
    )

    logger.info("CallTask ID %d terminated by %s (Outcome: operator_hangup)", task_id, current_user.email)
    return CallTaskDetailResponse.model_validate(task, from_attributes=True)


@router.post("/{task_id}/transfer", response_model=CallTaskDetailResponse)
async def transfer_call_task(
    task_id: int,
    desk_number: str = Query("+917971606000", description="Destination desk phone number in E.164 format"),
    session: AsyncSession = Depends(get_async_session),
    current_user: StaffUser = Depends(get_current_user),
) -> CallTaskDetailResponse:
    """
    Transfers an in-progress call to a student affairs / department help desk phone number.
    """
    await _assert_task_access(session, task_id, current_user)
    res = await session.execute(select(CallTask).where(CallTask.id == task_id))
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Call task not found.")

    carrier = settings.telephony_provider.strip().lower()
    adapter = get_telephony_adapter(carrier)

    if task.plivo_uuid:
        try:
            await adapter.transfer_call(task.plivo_uuid, desk_number=desk_number)
        except Exception as exc:
            logger.warning("Carrier transfer API exception for task %d: %s", task_id, exc)

    now = utc_now()
    task.status = "completed"
    task.outcome = "transferred"
    task.ended_at = now
    if task.answered_at:
        task.duration_sec = max(1, int((now - task.answered_at).total_seconds()))

    await session.commit()
    await session.refresh(task)

    # Broadcast real-time call transfer to dashboard clients
    await ws_manager.broadcast(
        "call_status",
        {
            "task_id": task.id,
            "call_uuid": task.plivo_uuid or "",
            "carrier": carrier,
            "status": "completed",
            "outcome": "transferred",
            "duration_sec": task.duration_sec or 0,
        },
    )

    logger.info("CallTask ID %d transferred to %s by %s", task_id, desk_number, current_user.email)
    return CallTaskDetailResponse.model_validate(task, from_attributes=True)
