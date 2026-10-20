"""
API Contract Tests — Call Tasks, Conversation Transcripts & Manual Retry Endpoints.

Tests `/api/calls/*`:
- GET /api/calls/{task_id}: Call task metadata, carrier state, timestamps, duration.
- GET /api/calls/{task_id}/transcript: Full multi-turn conversation logs and AI latency telemetry.
- POST /api/calls/{task_id}/retry: Manual task reset, admin authorization enforcement, retry increment.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models import CallCampaign, CallLog, CallScript, CallTask, Student, utc_now


@pytest.fixture
async def seeded_call_task(
    db_session: AsyncSession,
    seed_script: CallScript,
    seed_students: list,
    seed_users: dict,
) -> CallTask:
    """Seeds a persistent campaign and call task with an attached transcript log."""
    campaign = CallCampaign(
        name="Seeded Calls Campaign",
        script_id=seed_script.id,
        scheduled_at=utc_now(),
        status="running",
        created_by=seed_users["operator"].id,
    )
    db_session.add(campaign)
    await db_session.commit()
    await db_session.refresh(campaign)

    student = seed_students[0]
    task = CallTask(
        campaign_id=campaign.id,
        student_id=student.id,
        student_phone=student.phone,
        script_id=seed_script.id,
        status="completed",
        plivo_uuid="call-uuid-9876",
        retry_count=1,
        scheduled_at=utc_now(),
        duration_sec=42,
        outcome="completed",
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    call_log = CallLog(
        task_id=task.id,
        transcript=[
            {"role": "assistant", "content": "Namaste, fee payment baaki hai."},
            {"role": "user", "content": "Haan, main kal kar dunga."},
            {"role": "assistant", "content": "Dhanyavaad, have a good day."},
        ],
        stt_provider="indic_conformer",
        llm_provider="qwen3",
        tts_provider="indicf5",
        avg_latency_ms=1820,
        max_latency_ms=2100,
        error_log=[],
    )
    db_session.add(call_log)
    await db_session.commit()
    await db_session.refresh(call_log)

    return task


@pytest.mark.asyncio
async def test_get_call_task_success(
    async_client: AsyncClient,
    operator_headers: dict,
    seeded_call_task: CallTask,
):
    """Verifies GET /api/calls/{task_id} returns detailed task status and timing breakdown."""
    response = await async_client.get(f"/api/calls/{seeded_call_task.id}", headers=operator_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == seeded_call_task.id
    assert data["status"] == "completed"
    assert data["student_phone"] == seeded_call_task.student_phone
    assert data["duration_sec"] == 42
    assert data["outcome"] == "completed"
    assert data["plivo_uuid"] == "call-uuid-9876"


@pytest.mark.asyncio
async def test_get_call_task_not_found(async_client: AsyncClient, operator_headers: dict):
    """Verifies GET /api/calls/{task_id} returns HTTP 404 for non-existent task IDs."""
    response = await async_client.get("/api/calls/999999", headers=operator_headers)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_call_transcript_success(
    async_client: AsyncClient,
    operator_headers: dict,
    seeded_call_task: CallTask,
):
    """Verifies GET /api/calls/{task_id}/transcript returns conversation history and latency stats."""
    response = await async_client.get(
        f"/api/calls/{seeded_call_task.id}/transcript",
        headers=operator_headers,
    )
    assert response.status_code == 200

    data = response.json()
    assert data["task_id"] == seeded_call_task.id
    assert len(data["transcript"]) == 3
    assert data["transcript"][0]["role"] == "assistant"
    assert data["stt_provider"] == "indic_conformer"
    assert data["llm_provider"] == "qwen3"
    assert data["tts_provider"] == "indicf5"
    assert data["avg_latency_ms"] == 1820


@pytest.mark.asyncio
async def test_get_call_transcript_not_found(
    async_client: AsyncClient,
    operator_headers: dict,
    db_session: AsyncSession,
    seed_script: CallScript,
    seed_students: list,
    seed_users: dict,
):
    """Verifies GET /api/calls/{task_id}/transcript returns HTTP 404 when CallLog record does not exist."""
    # Create task without log
    campaign = CallCampaign(
        name="No Log Camp",
        script_id=seed_script.id,
        scheduled_at=utc_now(),
        created_by=seed_users["operator"].id,
    )
    db_session.add(campaign)
    await db_session.commit()
    await db_session.refresh(campaign)

    task = CallTask(
        campaign_id=campaign.id,
        student_id=seed_students[0].id,
        student_phone=seed_students[0].phone,
        script_id=seed_script.id,
        status="pending",
        scheduled_at=utc_now(),
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    response = await async_client.get(f"/api/calls/{task.id}/transcript", headers=operator_headers)
    assert response.status_code == 404
    assert "transcript not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_retry_call_task_admin_success(
    async_client: AsyncClient,
    admin_headers: dict,
    seeded_call_task: CallTask,
    db_session: AsyncSession,
):
    """Verifies admin user can manually trigger call task retry (resets to pending, increments retry_count)."""
    initial_retry_count = seeded_call_task.retry_count

    response = await async_client.post(
        f"/api/calls/{seeded_call_task.id}/retry",
        headers=admin_headers,
    )
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "pending"
    assert data["outcome"] is None
    assert data["retry_count"] == initial_retry_count + 1

    # Verify state in database
    await db_session.refresh(seeded_call_task)
    assert seeded_call_task.status == "pending"
    assert seeded_call_task.outcome is None
    assert seeded_call_task.retry_count == initial_retry_count + 1


@pytest.mark.asyncio
async def test_retry_call_task_operator_forbidden(
    async_client: AsyncClient,
    operator_headers: dict,
    seeded_call_task: CallTask,
):
    """Verifies operator role cannot manually trigger call task retries."""
    response = await async_client.post(
        f"/api/calls/{seeded_call_task.id}/retry",
        headers=operator_headers,
    )
    assert response.status_code == 403
    assert "administrator" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_retry_call_task_not_found(async_client: AsyncClient, admin_headers: dict):
    """Verifies retry on non-existent task ID returns HTTP 404."""
    response = await async_client.post("/api/calls/999999/retry", headers=admin_headers)
    assert response.status_code == 404
