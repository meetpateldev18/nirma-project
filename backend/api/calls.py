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

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.auth import get_current_user, require_admin
from backend.database.models import CallCampaign, CallLog, CallTask, StaffUser, utc_now
from backend.database.session import get_async_session

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
    res = await session.execute(select(CallTask).where(CallTask.id == task_id))
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Call task not found.")
    return CallTaskDetailResponse.model_validate(task, from_attributes=True)


@router.get("/{task_id}/transcript", response_model=CallTranscriptResponse)
async def get_call_transcript(
    task_id: int,
    session: AsyncSession = Depends(get_async_session),
    current_user: StaffUser = Depends(get_current_user),
) -> CallTranscriptResponse:
    """Returns the full conversation transcript and AI telemetry for a call task."""
    await _assert_task_access(session, task_id, current_user)
    res = await session.execute(select(CallLog).where(CallLog.task_id == task_id))
    log = res.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Transcript not found for this task.")
    return CallTranscriptResponse.model_validate(log, from_attributes=True)


@router.post("/{task_id}/retry", response_model=CallTaskDetailResponse)
async def retry_call_task(
    task_id: int,
    session: AsyncSession = Depends(get_async_session),
    current_user: StaffUser = Depends(require_admin),
) -> CallTaskDetailResponse:
    """Manually resets a failed or no-answer task to pending for immediate execution (Admin required)."""
    res = await session.execute(select(CallTask).where(CallTask.id == task_id))
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Call task not found.")

    task.status = "pending"
    task.outcome = None
    task.scheduled_at = utc_now()
    task.retry_count += 1
    await session.commit()
    await session.refresh(task)

    logger.info("Manual retry triggered for Task ID %d by admin %s", task_id, current_user.email)
    return CallTaskDetailResponse.model_validate(task, from_attributes=True)
