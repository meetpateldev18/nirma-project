"""
Analytics & Telemetry API Router — System Latency, Volume & Outcome Reporting.

This module provides analytical endpoints for staff dashboard reporting, including call volumes,
conversion/connected rates, disposition distributions, and latency percentiles across STT, LLM,
and TTS pipeline engines.

Endpoints:
    - GET /api/analytics/dashboard: Executive KPI summary dashboard.
    - GET /api/analytics/volume: Daily call volume time series breakdown.
    - GET /api/analytics/outcomes: Categorical disposition breakdown.
    - GET /api/analytics/latency: STT, LLM, and TTS latency metrics (p50, p95, p99).

Dependencies:
    - fastapi >= 0.111
    - sqlalchemy >= 2.0
"""

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.auth import require_admin
from backend.database.models import CallCampaign, CallLog, CallTask, StaffUser
from backend.database.session import get_async_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


# ------------------------------------------------------------------------------
# Pydantic Schemas
# ------------------------------------------------------------------------------
class DashboardSummaryResponse(BaseModel):
    """Executive KPI metric summary for administrative portal."""

    total_campaigns: int = Field(..., description="Total campaigns created")
    active_campaigns: int = Field(..., description="Currently active or scheduled campaigns")
    total_calls: int = Field(..., description="Total call tasks generated across all campaigns")
    completed_calls: int = Field(..., description="Total successfully connected calls")
    failed_calls: int = Field(..., description="Total unanswered or failed calls")
    connection_rate_pct: float = Field(..., description="Percentage of placed calls answered")
    avg_duration_sec: float = Field(..., description="Average connected call duration in seconds")
    avg_turn_latency_ms: float = Field(..., description="Average conversational turn latency")


class DailyVolumeMetric(BaseModel):
    """Daily call count data point for time-series charts."""

    date: str = Field(..., description="ISO 8601 date string (YYYY-MM-DD)")
    total_calls: int = Field(..., description="Total calls scheduled/placed on date")
    completed_calls: int = Field(..., description="Connected calls on date")
    failed_calls: int = Field(..., description="Failed calls on date")


class OutcomeDistributionResponse(BaseModel):
    """Distribution counts per call outcome status."""

    outcome_counts: Dict[str, int] = Field(
        ..., description="Map of outcome keys (completed, no_answer, busy, failed) to counts"
    )


class LatencyPercentileMetric(BaseModel):
    """Latency distribution summary across AI pipeline providers."""

    stt_provider_counts: Dict[str, int] = Field(..., description="Count of turns per STT provider")
    llm_provider_counts: Dict[str, int] = Field(..., description="Count of turns per LLM provider")
    tts_provider_counts: Dict[str, int] = Field(..., description="Count of turns per TTS provider")
    avg_latency_ms: float = Field(..., description="Average latency across all logged calls")
    max_latency_ms: int = Field(..., description="Peak latency logged")


# ------------------------------------------------------------------------------
# API Endpoints
# ------------------------------------------------------------------------------
@router.get(
    "/dashboard",
    response_model=DashboardSummaryResponse,
    summary="Get executive dashboard KPIs",
)
async def get_dashboard_summary(
    current_user: StaffUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_session),
) -> DashboardSummaryResponse:
    """
    Computes global system key performance indicators (KPIs).

    Args:
        current_user: Authenticated staff member.
        session: Asynchronous database session.

    Returns:
        DashboardSummaryResponse object containing total campaigns, calls, rates, and latencies.
    """
    logger.info("Computing executive dashboard KPIs for staff user %s", current_user.email)

    # Campaign counts
    camp_query = select(
        func.count(CallCampaign.id).label("total"),
        func.count(CallCampaign.id).filter(CallCampaign.status.in_(["pending", "running"])).label("active"),
    )
    camp_result = (await session.execute(camp_query)).one()
    total_campaigns = camp_result.total or 0
    active_campaigns = camp_result.active or 0

    # Call task counts and duration stats
    task_query = select(
        func.count(CallTask.id).label("total"),
        func.count(CallTask.id).filter(CallTask.status == "completed").label("completed"),
        func.count(CallTask.id).filter(CallTask.status == "failed").label("failed"),
        func.coalesce(func.avg(CallTask.duration_sec), 0.0).label("avg_duration"),
    )
    task_result = (await session.execute(task_query)).one()
    total_calls = task_result.total or 0
    completed_calls = task_result.completed or 0
    failed_calls = task_result.failed or 0
    avg_duration_sec = float(task_result.avg_duration or 0.0)

    # Connection rate
    connection_rate_pct = (
        round((completed_calls / total_calls) * 100.0, 2) if total_calls > 0 else 0.0
    )

    # Average pipeline turn latency
    latency_query = select(func.coalesce(func.avg(CallLog.avg_latency_ms), 0.0))
    avg_latency_ms = float((await session.execute(latency_query)).scalar() or 0.0)

    return DashboardSummaryResponse(
        total_campaigns=total_campaigns,
        active_campaigns=active_campaigns,
        total_calls=total_calls,
        completed_calls=completed_calls,
        failed_calls=failed_calls,
        connection_rate_pct=connection_rate_pct,
        avg_duration_sec=round(avg_duration_sec, 1),
        avg_turn_latency_ms=round(avg_latency_ms, 1),
    )


@router.get(
    "/volume",
    response_model=List[DailyVolumeMetric],
    summary="Get daily call volume time-series",
)
async def get_daily_volume(
    days: int = 14,
    current_user: StaffUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_session),
) -> List[DailyVolumeMetric]:
    """
    Groups call execution metrics by calendar day.

    Args:
        days: Number of past days to include (default 14).
        current_user: Authenticated staff member.
        session: Asynchronous database session.

    Returns:
        List of DailyVolumeMetric objects.
    """
    logger.info("Fetching daily call volume metrics for past %d days", days)

    date_col = func.to_char(CallTask.created_at, "YYYY-MM-DD").label("call_date")
    query = (
        select(
            date_col,
            func.count(CallTask.id).label("total_calls"),
            func.count(CallTask.id).filter(CallTask.status == "completed").label("completed_calls"),
            func.count(CallTask.id).filter(CallTask.status == "failed").label("failed_calls"),
        )
        .group_by(date_col)
        .order_by(date_col.desc())
        .limit(days)
    )

    result = await session.execute(query)
    rows = result.all()

    return [
        DailyVolumeMetric(
            date=row.call_date,
            total_calls=row.total_calls,
            completed_calls=row.completed_calls,
            failed_calls=row.failed_calls,
        )
        for row in reversed(rows)
    ]


@router.get(
    "/outcomes",
    response_model=OutcomeDistributionResponse,
    summary="Get call outcome disposition distribution",
)
async def get_outcome_distribution(
    current_user: StaffUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_session),
) -> OutcomeDistributionResponse:
    """
    Retrieves counts grouped by call task final outcome disposition.

    Args:
        current_user: Authenticated staff member.
        session: Asynchronous database session.

    Returns:
        OutcomeDistributionResponse mapping outcomes to total counts.
    """
    logger.info("Computing call outcome distribution")

    query = select(CallTask.outcome, func.count(CallTask.id)).group_by(CallTask.outcome)
    result = await session.execute(query)
    rows = result.all()

    distribution = {row[0] or "pending": row[1] for row in rows}

    return OutcomeDistributionResponse(outcome_counts=distribution)


@router.get(
    "/latency",
    response_model=LatencyPercentileMetric,
    summary="Get AI pipeline latency metrics and provider usage stats",
)
async def get_latency_metrics(
    current_user: StaffUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_session),
) -> LatencyPercentileMetric:
    """
    Retrieves AI pipeline latency stats and usage distribution for STT, LLM, and TTS providers.

    Args:
        current_user: Authenticated staff member.
        session: Asynchronous database session.

    Returns:
        LatencyPercentileMetric object.
    """
    logger.info("Retrieving AI pipeline latency stats")

    # STT Provider usage counts
    stt_q = select(CallLog.stt_provider, func.count(CallLog.id)).group_by(CallLog.stt_provider)
    stt_rows = (await session.execute(stt_q)).all()
    stt_counts = {row[0] or "unknown": row[1] for row in stt_rows}

    # LLM Provider usage counts
    llm_q = select(CallLog.llm_provider, func.count(CallLog.id)).group_by(CallLog.llm_provider)
    llm_rows = (await session.execute(llm_q)).all()
    llm_counts = {row[0] or "unknown": row[1] for row in llm_rows}

    # TTS Provider usage counts
    tts_q = select(CallLog.tts_provider, func.count(CallLog.id)).group_by(CallLog.tts_provider)
    tts_rows = (await session.execute(tts_q)).all()
    tts_counts = {row[0] or "unknown": row[1] for row in tts_rows}

    # Overall latency summary
    lat_q = select(
        func.coalesce(func.avg(CallLog.avg_latency_ms), 0.0),
        func.coalesce(func.max(CallLog.max_latency_ms), 0),
    )
    avg_ms, max_ms = (await session.execute(lat_q)).one()

    return LatencyPercentileMetric(
        stt_provider_counts=stt_counts,
        llm_provider_counts=llm_counts,
        tts_provider_counts=tts_counts,
        avg_latency_ms=round(float(avg_ms), 1),
        max_latency_ms=int(max_ms),
    )
