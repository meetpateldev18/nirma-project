"""
API Contract Tests — Campaign Management Endpoints & Role-Based Access Control.

Tests `/api/campaigns/*`:
- GET /api/campaigns: Pagination, filtering by status, response schemas.
- POST /api/campaigns: Campaign creation, task generation, admin permission check.
- GET /api/campaigns/{id}: Detailed campaign lookup, status breakdown counts.
- PATCH /api/campaigns/{id}/cancel: Campaign cancellation, pending task abort.
"""

from datetime import datetime, timezone
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models import CallCampaign, CallScript, CallTask, utc_now


@pytest.mark.asyncio
async def test_list_campaigns_authenticated_empty(async_client: AsyncClient, operator_headers: dict):
    """Verifies GET /api/campaigns returns empty paginated list when no campaigns exist."""
    response = await async_client.get("/api/campaigns", headers=operator_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["limit"] == 20
    assert data["items"] == []


@pytest.mark.asyncio
async def test_list_campaigns_pagination_and_filtering(
    async_client: AsyncClient,
    admin_headers: dict,
    db_session: AsyncSession,
    seed_script: CallScript,
):
    """Verifies pagination and status filtering on GET /api/campaigns."""
    c1 = CallCampaign(name="Pending Camp", script_id=seed_script.id, scheduled_at=utc_now(), status="pending")
    c2 = CallCampaign(name="Running Camp", script_id=seed_script.id, scheduled_at=utc_now(), status="running")
    c3 = CallCampaign(name="Completed Camp", script_id=seed_script.id, scheduled_at=utc_now(), status="completed")
    db_session.add_all([c1, c2, c3])
    await db_session.commit()

    # Query with status filter
    resp = await async_client.get("/api/campaigns?status=running", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["status"] == "running"
    assert data["items"][0]["name"] == "Running Camp"

    # Query with pagination limit
    resp_limit = await async_client.get("/api/campaigns?limit=2&page=1", headers=admin_headers)
    assert resp_limit.status_code == 200
    assert len(resp_limit.json()["items"]) == 2
    assert resp_limit.json()["total"] == 3


@pytest.mark.asyncio
async def test_list_campaigns_validation_limits(async_client: AsyncClient, operator_headers: dict):
    """Verifies that invalid pagination parameters return HTTP 422."""
    # Page must be >= 1
    resp = await async_client.get("/api/campaigns?page=0", headers=operator_headers)
    assert resp.status_code == 422

    # Limit must be <= 100
    resp = await async_client.get("/api/campaigns?limit=101", headers=operator_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_campaign_admin_success(
    async_client: AsyncClient,
    admin_headers: dict,
    seed_script: CallScript,
    seed_students: list,
):
    """Verifies admin user can create campaign and trigger task generation (201 Created)."""
    payload = {
        "name": "Mid-Semester Fee Notice",
        "script_id": seed_script.id,
        "target_filter": {"department": "CS"},
        "scheduled_at": "2026-10-20T10:00:00Z",
        "max_retries": 2,
        "retry_delay_min": 60,
    }
    response = await async_client.post("/api/campaigns", json=payload, headers=admin_headers)
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "Mid-Semester Fee Notice"
    assert data["script_id"] == seed_script.id
    assert "task_counts" in data
    # Students cohort had 2 active CS students
    assert data["task_counts"]["total"] >= 2


@pytest.mark.asyncio
async def test_create_campaign_operator_allowed(
    async_client: AsyncClient,
    operator_headers: dict,
    seed_script: CallScript,
):
    """Verifies faculty/operator staff member can create scoped campaigns (201 Created)."""
    payload = {
        "name": "Operator Campaign Attempt",
        "script_id": seed_script.id,
        "target_filter": {},
        "scheduled_at": "2026-10-20T10:00:00Z",
    }
    response = await async_client.post("/api/campaigns", json=payload, headers=operator_headers)
    assert response.status_code == 201
    assert response.json()["name"] == "Operator Campaign Attempt"


@pytest.mark.asyncio
async def test_create_campaign_invalid_script_id(async_client: AsyncClient, admin_headers: dict):
    """Verifies that non-existent script_id returns HTTP 400 Bad Request."""
    payload = {
        "name": "Invalid Script Campaign",
        "script_id": 999999,
        "target_filter": {},
        "scheduled_at": "2026-10-20T10:00:00Z",
    }
    response = await async_client.post("/api/campaigns", json=payload, headers=admin_headers)
    assert response.status_code == 400
    assert "callscript" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_campaign_details_and_status_counts(
    async_client: AsyncClient,
    admin_headers: dict,
    db_session: AsyncSession,
    seed_script: CallScript,
    seed_students: list,
):
    """Verifies GET /api/campaigns/{id} returns metadata and task counts grouped by status."""
    campaign = CallCampaign(
        name="Detailed Campaign",
        script_id=seed_script.id,
        scheduled_at=utc_now(),
        status="running",
    )
    db_session.add(campaign)
    await db_session.commit()
    await db_session.refresh(campaign)

    # Add 2 pending tasks, 1 completed task
    t1 = CallTask(campaign_id=campaign.id, student_id=seed_students[0].id, student_phone="+911", script_id=seed_script.id, status="pending", scheduled_at=utc_now())
    t2 = CallTask(campaign_id=campaign.id, student_id=seed_students[1].id, student_phone="+912", script_id=seed_script.id, status="pending", scheduled_at=utc_now())
    t3 = CallTask(campaign_id=campaign.id, student_id=seed_students[2].id, student_phone="+913", script_id=seed_script.id, status="completed", scheduled_at=utc_now())
    db_session.add_all([t1, t2, t3])
    await db_session.commit()

    response = await async_client.get(f"/api/campaigns/{campaign.id}", headers=admin_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == campaign.id
    assert data["task_counts"]["pending"] == 2
    assert data["task_counts"]["completed"] == 1


@pytest.mark.asyncio
async def test_get_campaign_nonexistent_returns_404(async_client: AsyncClient, operator_headers: dict):
    """Verifies GET /api/campaigns/{id} returns 404 for unknown campaign."""
    response = await async_client.get("/api/campaigns/999999", headers=operator_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cancel_campaign_admin_success(
    async_client: AsyncClient,
    admin_headers: dict,
    db_session: AsyncSession,
    seed_script: CallScript,
    seed_students: list,
):
    """Verifies admin user can cancel campaign and marks pending tasks as cancelled."""
    campaign = CallCampaign(
        name="Campaign To Cancel",
        script_id=seed_script.id,
        scheduled_at=utc_now(),
        status="running",
    )
    db_session.add(campaign)
    await db_session.commit()
    await db_session.refresh(campaign)

    task = CallTask(
        campaign_id=campaign.id,
        student_id=seed_students[0].id,
        student_phone="+911",
        script_id=seed_script.id,
        status="pending",
        scheduled_at=utc_now(),
    )
    db_session.add(task)
    await db_session.commit()

    response = await async_client.patch(f"/api/campaigns/{campaign.id}/cancel", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    # Check task status in database
    await db_session.refresh(task)
    assert task.status == "cancelled"
    assert task.outcome == "cancelled"


@pytest.mark.asyncio
async def test_cancel_campaign_operator_forbidden(
    async_client: AsyncClient,
    operator_headers: dict,
    db_session: AsyncSession,
    seed_script: CallScript,
):
    """Verifies operator role cannot cancel a campaign."""
    campaign = CallCampaign(name="Protected Campaign", script_id=seed_script.id, scheduled_at=utc_now())
    db_session.add(campaign)
    await db_session.commit()
    await db_session.refresh(campaign)

    response = await async_client.patch(f"/api/campaigns/{campaign.id}/cancel", headers=operator_headers)
    assert response.status_code == 403
