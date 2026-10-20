"""
Campaign Management API Router — Outbound Campaign CRUD & Task Generation.

This module provides endpoints for scheduling, monitoring, and cancelling batch outbound call campaigns.

Endpoints:
    - GET /api/campaigns: Paginated list of campaigns with status counts.
    - POST /api/campaigns: Creates campaign and generates call tasks (Admin required).
    - GET /api/campaigns/{id}: Campaign details and status breakdown.
    - PATCH /api/campaigns/{id}/cancel: Cancels pending campaign tasks (Admin required).
    - GET /api/campaigns/{id}/tasks: Paginated call task breakdown.

Dependencies:
    - fastapi >= 0.111
    - sqlalchemy >= 2.0
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.ai_pipeline.script_writer import build_opening_message, extract_document_text, generate_system_prompt
from backend.api.auth import get_current_user, require_admin
from backend.database.models import CallCampaign, CallScript, CallTask, StaffUser, utc_now
from backend.database.session import get_async_session, get_sync_session
from backend.scheduler.campaign_runner import CampaignRunner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/campaigns", tags=["Campaigns"])


# ------------------------------------------------------------------------------
# Pydantic Schemas
# ------------------------------------------------------------------------------
class CampaignCreateRequest(BaseModel):
    """Payload for creating a new outbound call campaign."""

    name: str = Field(..., example="BTech 2026 Semester Fee Reminder")
    script_id: int = Field(..., example=1)
    target_filter: Dict[str, Any] = Field(
        default_factory=dict, example={"department": "CS", "semester": 4}
    )
    scheduled_at: datetime = Field(..., example="2026-10-15T10:00:00Z")
    max_retries: int = Field(default=2, ge=0, le=5)
    retry_delay_min: int = Field(default=60, ge=5, le=1440)


class CampaignResponse(BaseModel):
    """Public campaign data representation."""

    id: int
    name: str
    script_id: int
    target_filter: Dict[str, Any]
    scheduled_at: datetime
    max_retries: int
    retry_delay_min: int
    status: str
    created_by: Optional[int]
    created_at: datetime
    task_counts: Optional[Dict[str, int]] = None


class PaginatedCampaigns(BaseModel):
    """Paginated list wrapper for campaigns."""

    total: int
    page: int
    limit: int
    items: List[CampaignResponse]


class CallScriptResponse(BaseModel):
    """Public call script template representation for campaign authoring."""

    id: int
    name: str
    category: str
    language: str
    system_prompt: str
    opening_message: str
    is_active: bool


class CampaignTaskResponse(BaseModel):
    """Call task row enriched with student identity for live monitoring views."""

    id: int
    campaign_id: int
    student_id: int
    student_name: str
    student_roll: str
    student_phone: str
    script_id: int
    status: str
    plivo_uuid: Optional[str]
    retry_count: int
    duration_sec: Optional[int]
    outcome: Optional[str]
    placed_at: Optional[datetime]


class PaginatedCampaignTasks(BaseModel):
    """Paginated list wrapper for a campaign's call tasks."""

    total: int
    page: int
    limit: int
    items: List[CampaignTaskResponse]


class GeneratedScriptResponse(BaseModel):
    """Ephemeral, not-yet-persisted script generated from a free-text call reason."""

    opening_message: str
    system_prompt: str
    used_document: bool


class ScriptCreateRequest(BaseModel):
    """Payload to persist a (typically LLM-generated) call script as a CallScript row."""

    name: str = Field(..., max_length=100)
    language: str = Field(..., pattern="^(en|hi|gu)$")
    opening_message: str
    system_prompt: str
    category: str = Field(default="custom", max_length=50)


# ------------------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------------------
@router.get("", response_model=PaginatedCampaigns)
async def list_campaigns(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    session: AsyncSession = Depends(get_async_session),
    current_user: StaffUser = Depends(get_current_user),
) -> PaginatedCampaigns:
    """Returns a paginated list of campaigns filtered by status."""
    query = select(CallCampaign)
    if current_user.role != "admin":
        query = query.where(CallCampaign.created_by == current_user.id)
    if status_filter:
        query = query.where(CallCampaign.status == status_filter)

    # Count total
    count_stmt = select(func.count()).select_from(query.subquery())
    total_res = await session.execute(count_stmt)
    total = total_res.scalar_one()

    # Paginate
    query = query.order_by(CallCampaign.created_at.desc()).offset((page - 1) * limit).limit(limit)
    res = await session.execute(query)
    campaigns = res.scalars().all()

    items = [CampaignResponse.model_validate(c, from_attributes=True) for c in campaigns]
    return PaginatedCampaigns(total=total, page=page, limit=limit, items=items)


@router.post("", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CampaignCreateRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: StaffUser = Depends(get_current_user),
) -> CampaignResponse:
    """Creates a campaign and generates CallTask records for matching students."""
    # Verify script exists
    script_res = await session.execute(select(CallScript).where(CallScript.id == payload.script_id))
    script = script_res.scalar_one_or_none()
    if not script or not script.is_active:
        raise HTTPException(status_code=400, detail="Invalid or inactive CallScript ID.")

    campaign = CallCampaign(
        name=payload.name,
        script_id=payload.script_id,
        target_filter=payload.target_filter,
        scheduled_at=payload.scheduled_at,
        max_retries=payload.max_retries,
        retry_delay_min=payload.retry_delay_min,
        status="pending",
        created_by=current_user.id,
    )
    session.add(campaign)
    await session.commit()
    await session.refresh(campaign)

    # Generate task rows synchronously via NullPool engine
    def _sync_generate_tasks():
        with get_sync_session() as sync_db:
            return CampaignRunner.generate_tasks_for_campaign(campaign.id, sync_db)

    task_count = await session.run_sync(lambda _: _sync_generate_tasks())
    logger.info("Campaign ID %d created by %s. Generated %d tasks.", campaign.id, current_user.email, task_count)

    # Automatically dispatch tasks immediately so call dials without delay
    if task_count > 0:
        def _sync_auto_dispatch():
            from backend.scheduler.tasks import place_call_task
            with get_sync_session() as sync_db:
                due_tasks = sync_db.query(CallTask).filter(
                    CallTask.campaign_id == campaign.id,
                    CallTask.status == "pending"
                ).all()
                for dt in due_tasks:
                    try:
                        place_call_task(dt.id)
                    except Exception as err:
                        logger.error("Auto-dispatch error for task %d: %s", dt.id, err)

        asyncio.create_task(asyncio.to_thread(_sync_auto_dispatch))

    response = CampaignResponse.model_validate(campaign, from_attributes=True)
    response.task_counts = {"total": task_count, "pending": task_count}
    return response


@router.post("/generate-script", response_model=GeneratedScriptResponse)
async def generate_script(
    reason: str = Form(..., min_length=3, max_length=500),
    language: str = Form(..., pattern="^(en|hi|gu)$"),
    document: Optional[UploadFile] = File(default=None),
    current_user: StaffUser = Depends(get_current_user),
) -> GeneratedScriptResponse:
    """
    Writes a topic-locked call script from a free-text reason instead of a fixed template.

    The AI-disclosure opening line is built deterministically (never left to the LLM);
    the system prompt that keeps the assistant on-topic for the whole call is written by
    the configured LLM (local Ollama, falling back to Groq), with a deterministic
    template standing in if neither is reachable. An attached document is optional —
    its extracted text (best effort; silently ignored if extraction fails) is given to
    the LLM as extra context, never as a requirement.
    """
    document_text: Optional[str] = None
    if document is not None:
        raw_bytes = await document.read()
        document_text = extract_document_text(document.filename or "", raw_bytes)

    opening_message = build_opening_message(reason, language)
    system_prompt = await generate_system_prompt(reason, language, document_text)

    return GeneratedScriptResponse(
        opening_message=opening_message,
        system_prompt=system_prompt,
        used_document=document_text is not None,
    )


@router.post("/scripts", response_model=CallScriptResponse, status_code=status.HTTP_201_CREATED)
async def create_script(
    payload: ScriptCreateRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: StaffUser = Depends(get_current_user),
) -> CallScriptResponse:
    """Persists a call script (typically one just generated from a free-text reason)."""
    script = CallScript(
        name=payload.name,
        category=payload.category,
        language=payload.language,
        system_prompt=payload.system_prompt,
        opening_message=payload.opening_message,
        is_active=True,
        created_by=current_user.id,
    )
    session.add(script)
    await session.commit()
    await session.refresh(script)
    return CallScriptResponse.model_validate(script, from_attributes=True)


@router.get("/scripts", response_model=List[CallScriptResponse])
async def list_scripts(
    session: AsyncSession = Depends(get_async_session),
    current_user: StaffUser = Depends(get_current_user),
) -> List[CallScriptResponse]:
    """Returns all active call script templates available for campaign authoring."""
    res = await session.execute(
        select(CallScript).where(CallScript.is_active.is_(True)).order_by(CallScript.name)
    )
    scripts = res.scalars().all()
    return [CallScriptResponse.model_validate(s, from_attributes=True) for s in scripts]


@router.get("/{campaign_id}/tasks", response_model=PaginatedCampaignTasks)
async def list_campaign_tasks(
    campaign_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_async_session),
    current_user: StaffUser = Depends(get_current_user),
) -> PaginatedCampaignTasks:
    """Returns a paginated, student-enriched breakdown of a campaign's call tasks."""
    campaign_res = await session.execute(select(CallCampaign).where(CallCampaign.id == campaign_id))
    owned = campaign_res.scalar_one_or_none()
    if not owned or (current_user.role != "admin" and owned.created_by != current_user.id):
        raise HTTPException(status_code=404, detail="Campaign not found.")

    count_stmt = select(func.count()).select_from(
        select(CallTask.id).where(CallTask.campaign_id == campaign_id).subquery()
    )
    total = (await session.execute(count_stmt)).scalar_one()

    query = (
        select(CallTask)
        .options(selectinload(CallTask.student))
        .where(CallTask.campaign_id == campaign_id)
        .order_by(CallTask.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    res = await session.execute(query)
    tasks = res.scalars().all()

    items = [
        CampaignTaskResponse(
            id=t.id,
            campaign_id=t.campaign_id,
            student_id=t.student_id,
            student_name=t.student.name if t.student else "Unknown",
            student_roll=t.student.roll_number if t.student else "N/A",
            student_phone=t.student_phone,
            script_id=t.script_id,
            status=t.status,
            plivo_uuid=t.plivo_uuid,
            retry_count=t.retry_count,
            duration_sec=t.duration_sec,
            outcome=t.outcome,
            placed_at=t.placed_at,
        )
        for t in tasks
    ]
    return PaginatedCampaignTasks(total=total, page=page, limit=limit, items=items)


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: int,
    session: AsyncSession = Depends(get_async_session),
    current_user: StaffUser = Depends(get_current_user),
) -> CampaignResponse:
    """Returns detailed campaign metadata and task status summary."""
    res = await session.execute(select(CallCampaign).where(CallCampaign.id == campaign_id))
    campaign = res.scalar_one_or_none()
    if not campaign or (current_user.role != "admin" and campaign.created_by != current_user.id):
        raise HTTPException(status_code=404, detail="Campaign not found.")

    # Calculate status counts
    count_stmt = (
        select(CallTask.status, func.count(CallTask.id))
        .where(CallTask.campaign_id == campaign_id)
        .group_by(CallTask.status)
    )
    count_res = await session.execute(count_stmt)
    status_counts = {row[0]: row[1] for row in count_res.all()}

    response = CampaignResponse.model_validate(campaign, from_attributes=True)
    response.task_counts = status_counts
    return response


@router.patch("/{campaign_id}/cancel", response_model=CampaignResponse)
async def cancel_campaign(
    campaign_id: int,
    session: AsyncSession = Depends(get_async_session),
    current_user: StaffUser = Depends(require_admin),
) -> CampaignResponse:
    """Cancels a pending/running campaign and updates pending tasks to 'cancelled' (Admin required)."""
    res = await session.execute(select(CallCampaign).where(CallCampaign.id == campaign_id))
    campaign = res.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    campaign.status = "cancelled"

    # Cancel pending tasks
    await session.execute(
        update(CallTask)
        .where(CallTask.campaign_id == campaign_id, CallTask.status.in_(["pending", "ringing"]))
        .values(status="cancelled", outcome="cancelled")
    )
    await session.commit()
    await session.refresh(campaign)

    logger.info("Campaign ID %d cancelled by %s", campaign_id, current_user.email)
    return CampaignResponse.model_validate(campaign, from_attributes=True)
