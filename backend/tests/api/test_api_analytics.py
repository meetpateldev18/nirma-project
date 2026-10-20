"""
API Regression Tests — Analytics & Telemetry Router.

Tests `backend.api.analytics`:
- GET /api/analytics/dashboard: KPI metrics, zero-division guards, active counts.
- GET /api/analytics/volume: Daily call volume aggregation and day parameter limits.
- GET /api/analytics/outcomes: Categorical outcome disposition distributions.
- GET /api/analytics/latency: STT/LLM/TTS provider telemetry and latency percentiles.
- Authentication and authorization boundaries for analytical data access.
"""

import datetime
from typing import Dict, List
from httpx import AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models import CallCampaign, CallLog, CallScript, CallTask, Student, utc_now


@pytest.mark.asyncio
async def test_get_dashboard_unauthenticated(async_client: AsyncClient):
    """Verifies unauthenticated requests to dashboard analytics are rejected with 401."""
    response = await async_client.get("/api/analytics/dashboard")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_dashboard_forbidden_for_operator(
    async_client: AsyncClient,
    operator_headers: Dict[str, str],
):
    """Verifies operators/faculty are blocked from viewing global analytics (403)."""
    response = await async_client.get("/api/analytics/dashboard", headers=operator_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_dashboard_empty_db_returns_zeros(
    async_client: AsyncClient,
    admin_headers: Dict[str, str],
):
    """Verifies dashboard KPIs return clean zero values when no campaigns/calls exist."""
    response = await async_client.get("/api/analytics/dashboard", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()

    assert data["total_campaigns"] == 0
    assert data["active_campaigns"] == 0
    assert data["total_calls"] == 0
    assert data["completed_calls"] == 0
    assert data["failed_calls"] == 0
    assert data["connection_rate_pct"] == 0.0
    assert data["avg_duration_sec"] == 0.0
    assert data["avg_turn_latency_ms"] == 0.0


@pytest.mark.asyncio
async def test_get_dashboard_computes_kpis(
    async_client: AsyncClient,
    admin_headers: Dict[str, str],
    db_session: AsyncSession,
    seed_students: List[Student],
):
    """Verifies dashboard accurately aggregates campaigns, completion rates, and average duration."""
    # Seed script
    script = CallScript(
        name="Dashboard Script",
        category="notice",
        language="en",
        system_prompt="Prompt",
        opening_message="Hello",
    )
    db_session.add(script)
    await db_session.commit()
    await db_session.refresh(script)

    # Seed 2 campaigns (1 running, 1 completed)
    c1 = CallCampaign(name="Active Campaign", script_id=script.id, status="running", scheduled_at=utc_now())
    c2 = CallCampaign(name="Finished Campaign", script_id=script.id, status="completed", scheduled_at=utc_now())
    db_session.add_all([c1, c2])
    await db_session.commit()
    await db_session.refresh(c1)
    await db_session.refresh(c2)

    # Seed 4 tasks: 2 completed (durations 60s, 120s), 1 failed, 1 pending
    t1 = CallTask(
        campaign_id=c1.id,
        student_id=seed_students[0].id,
        student_phone=seed_students[0].phone,
        script_id=script.id,
        status="completed",
        duration_sec=60,
        scheduled_at=utc_now(),
    )
    t2 = CallTask(
        campaign_id=c1.id,
        student_id=seed_students[1].id,
        student_phone=seed_students[1].phone,
        script_id=script.id,
        status="completed",
        duration_sec=120,
        scheduled_at=utc_now(),
    )
    t3 = CallTask(
        campaign_id=c2.id,
        student_id=seed_students[2].id,
        student_phone=seed_students[2].phone,
        script_id=script.id,
        status="failed",
        duration_sec=0,
        scheduled_at=utc_now(),
    )
    t4 = CallTask(
        campaign_id=c2.id,
        student_id=seed_students[3].id,
        student_phone=seed_students[3].phone,
        script_id=script.id,
        status="pending",
        duration_sec=0,
        scheduled_at=utc_now(),
    )
    db_session.add_all([t1, t2, t3, t4])
    await db_session.commit()
    await db_session.refresh(t1)

    # Seed CallLog with latency
    log = CallLog(
        task_id=t1.id,
        avg_latency_ms=1200,
        max_latency_ms=1500,
        stt_provider="indic_conformer",
        llm_provider="ollama_qwen",
        tts_provider="indicf5",
    )
    db_session.add(log)
    await db_session.commit()

    response = await async_client.get("/api/analytics/dashboard", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()

    assert data["total_campaigns"] == 2
    assert data["active_campaigns"] == 1
    assert data["total_calls"] == 4
    assert data["completed_calls"] == 2
    assert data["failed_calls"] == 1
    # connection_rate = 2/4 = 50.0%
    assert data["connection_rate_pct"] == 50.0
    # avg_duration = (60 + 120 + 0 + 0) / 4 = 45.0s
    assert data["avg_duration_sec"] == 45.0
    assert data["avg_turn_latency_ms"] == 1200.0


@pytest.mark.asyncio
async def test_get_volume_unauthenticated(async_client: AsyncClient):
    """Verifies unauthenticated access to daily volume is rejected."""
    response = await async_client.get("/api/analytics/volume")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_volume_with_data(
    async_client: AsyncClient,
    admin_headers: Dict[str, str],
    db_session: AsyncSession,
    seed_students: List[Student],
):
    """Verifies volume time-series groups calls by calendar date accurately."""
    script = CallScript(
        name="Test Script",
        category="notice",
        language="en",
        system_prompt="System Prompt",
        opening_message="Opening Message",
    )
    db_session.add(script)
    await db_session.commit()
    await db_session.refresh(script)

    campaign = CallCampaign(name="Vol Campaign", script_id=script.id, scheduled_at=utc_now())
    db_session.add(campaign)
    await db_session.commit()
    await db_session.refresh(campaign)

    t1 = CallTask(
        campaign_id=campaign.id,
        student_id=seed_students[0].id,
        student_phone=seed_students[0].phone,
        script_id=script.id,
        status="completed",
        scheduled_at=utc_now(),
    )
    db_session.add(t1)
    await db_session.commit()

    response = await async_client.get("/api/analytics/volume?days=7", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()

    assert isinstance(data, list)
    assert len(data) >= 1
    today_metric = data[-1]
    assert "date" in today_metric
    assert today_metric["total_calls"] >= 1
    assert today_metric["completed_calls"] >= 1


@pytest.mark.asyncio
async def test_get_outcomes_unauthenticated(async_client: AsyncClient):
    """Verifies unauthenticated access to outcome distribution is rejected."""
    response = await async_client.get("/api/analytics/outcomes")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_outcomes_distribution(
    async_client: AsyncClient,
    admin_headers: Dict[str, str],
    db_session: AsyncSession,
    seed_students: List[Student],
):
    """Verifies outcome distribution returns exact counts mapped per disposition key."""
    script = CallScript(
        name="Outcome Script",
        category="notice",
        language="en",
        system_prompt="Prompt",
        opening_message="Hello",
    )
    db_session.add(script)
    await db_session.commit()
    await db_session.refresh(script)

    campaign = CallCampaign(name="Outcome Campaign", script_id=script.id, scheduled_at=utc_now())
    db_session.add(campaign)
    await db_session.commit()
    await db_session.refresh(campaign)

    t1 = CallTask(
        campaign_id=campaign.id,
        student_id=seed_students[0].id,
        student_phone=seed_students[0].phone,
        script_id=script.id,
        status="completed",
        outcome="answered",
        scheduled_at=utc_now(),
    )
    t2 = CallTask(
        campaign_id=campaign.id,
        student_id=seed_students[1].id,
        student_phone=seed_students[1].phone,
        script_id=script.id,
        status="failed",
        outcome="no_answer",
        scheduled_at=utc_now(),
    )
    db_session.add_all([t1, t2])
    await db_session.commit()

    response = await async_client.get("/api/analytics/outcomes", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()

    assert "outcome_counts" in data
    assert data["outcome_counts"].get("answered") == 1
    assert data["outcome_counts"].get("no_answer") == 1


@pytest.mark.asyncio
async def test_get_latency_metrics(
    async_client: AsyncClient,
    admin_headers: Dict[str, str],
    db_session: AsyncSession,
    seed_students: List[Student],
):
    """Verifies AI latency metrics calculate provider distributions and overall averages."""
    script = CallScript(
        name="Latency Script",
        category="notice",
        language="en",
        system_prompt="Prompt",
        opening_message="Hello",
    )
    db_session.add(script)
    await db_session.commit()
    await db_session.refresh(script)

    campaign = CallCampaign(name="Latency Campaign", script_id=script.id, scheduled_at=utc_now())
    db_session.add(campaign)
    await db_session.commit()
    await db_session.refresh(campaign)

    task1 = CallTask(
        campaign_id=campaign.id,
        student_id=seed_students[0].id,
        student_phone=seed_students[0].phone,
        script_id=script.id,
        status="completed",
        scheduled_at=utc_now(),
    )
    task2 = CallTask(
        campaign_id=campaign.id,
        student_id=seed_students[1].id,
        student_phone=seed_students[1].phone,
        script_id=script.id,
        status="completed",
        scheduled_at=utc_now(),
    )
    db_session.add_all([task1, task2])
    await db_session.commit()
    await db_session.refresh(task1)
    await db_session.refresh(task2)

    log1 = CallLog(
        task_id=task1.id,
        avg_latency_ms=1000,
        max_latency_ms=1400,
        stt_provider="indic_conformer",
        llm_provider="ollama_qwen",
        tts_provider="indicf5",
    )
    log2 = CallLog(
        task_id=task2.id,
        avg_latency_ms=1600,
        max_latency_ms=2200,
        stt_provider="sarvam",
        llm_provider="groq",
        tts_provider="gtts",
    )
    db_session.add_all([log1, log2])
    await db_session.commit()

    response = await async_client.get("/api/analytics/latency", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()

    assert data["stt_provider_counts"]["indic_conformer"] == 1
    assert data["stt_provider_counts"]["sarvam"] == 1
    assert data["llm_provider_counts"]["ollama_qwen"] == 1
    assert data["llm_provider_counts"]["groq"] == 1
    assert data["tts_provider_counts"]["indicf5"] == 1
    assert data["tts_provider_counts"]["gtts"] == 1

    # avg_latency = (1000 + 1600) / 2 = 1300.0
    assert data["avg_latency_ms"] == 1300.0
    assert data["max_latency_ms"] == 2200
