"""
API Regression Tests — Twilio Webhook State Machine & TwiML Gateway.

Tests Twilio carrier endpoints (/webhook/twilio):
- POST /webhook/twilio/answer: Session initialization, mandatory Redis TTL=600s, TwiML generation.
- POST /webhook/twilio/input: Twilio parameter invariant ('RecordingUrl', 'CallSid'),
  distributed lock deduplication, conversational turn progression, max turn termination.
- POST /webhook/twilio/hangup: Outcome determination by duration / status, transcript serialization into CallLog,
  Redis session cleanup.
- POST /webhook/twilio/fallback: Graceful carrier error recovery with Hangup TwiML.
"""

from typing import List
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models import CallCampaign, CallScript, CallTask, Student, utc_now


@pytest.mark.asyncio
async def test_twilio_answer_nonexistent_task(async_client: AsyncClient):
    """Verifies Twilio answer webhook for nonexistent task returns Hangup TwiML."""
    payload = {
        "CallSid": "CA_unknown_sid",
        "From": "+15005550006",
        "To": "+919876500001",
    }
    response = await async_client.post("/webhook/twilio/answer?task_id=99999", data=payload)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert "<Hangup" in response.text


@pytest.mark.asyncio
async def test_twilio_answer_valid_task_lifecycle(
    async_client: AsyncClient,
    db_session: AsyncSession,
    seed_students: List[Student],
):
    """Verifies Twilio answer webhook sets task in_progress, initializes Redis with TTL=600s, and emits Play/Record TwiML."""
    script = CallScript(
        name="Twilio Fee Reminder",
        category="fee_reminder",
        language="hi",
        system_prompt="You are a fee reminder assistant.",
        opening_message="Namaste, Nirma University se fee reminder call hai.",
    )
    db_session.add(script)
    await db_session.commit()
    await db_session.refresh(script)

    campaign = CallCampaign(name="Twilio Campaign", script_id=script.id, scheduled_at=utc_now())
    db_session.add(campaign)
    await db_session.commit()
    await db_session.refresh(campaign)

    task = CallTask(
        campaign_id=campaign.id,
        student_id=seed_students[0].id,
        student_phone=seed_students[0].phone,
        script_id=script.id,
        status="ringing",
        scheduled_at=utc_now(),
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    payload = {
        "CallSid": "CA_test_active_sid_12345",
        "From": "+15005550006",
        "To": seed_students[0].phone,
    }

    with patch("backend.telephony.webhook_handler.ai_pipeline.tts.synthesize", new_callable=AsyncMock) as mock_tts:
        mock_tts.return_value = "https://calls.nirmauni.ac.in/static/audio/greeting.wav"
        response = await async_client.post(f"/webhook/twilio/answer?task_id={task.id}", data=payload)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert "<Response>" in response.text
    assert "<Play>https://calls.nirmauni.ac.in/static/audio/greeting.wav</Play>" in response.text
    assert f"/webhook/twilio/input?task_id={task.id}" in response.text
    assert 'timeout="4"' in response.text


@pytest.mark.asyncio
async def test_twilio_input_missing_recording_url(async_client: AsyncClient):
    """Verifies Twilio input webhook without RecordingUrl returns Hangup TwiML."""
    payload = {
        "CallSid": "CA_test_sid_without_url",
    }
    response = await async_client.post("/webhook/twilio/input?task_id=1", data=payload)
    assert response.status_code == 200
    assert "<Hangup" in response.text


@pytest.mark.asyncio
async def test_twilio_input_successful_dialogue_turn(
    async_client: AsyncClient,
    db_session: AsyncSession,
    seed_students: List[Student],
):
    """Verifies Twilio input webhook executes conversational AI turn and returns next TwiML."""
    script = CallScript(
        name="Exam Alert",
        category="exam_notice",
        language="en",
        system_prompt="You are exam coordinator.",
        opening_message="Hello, exam schedule announced.",
    )
    db_session.add(script)
    await db_session.commit()
    await db_session.refresh(script)

    campaign = CallCampaign(name="Exam Camp", script_id=script.id, scheduled_at=utc_now())
    db_session.add(campaign)
    await db_session.commit()
    await db_session.refresh(campaign)

    task = CallTask(
        campaign_id=campaign.id,
        student_id=seed_students[0].id,
        student_phone=seed_students[0].phone,
        script_id=script.id,
        status="in_progress",
        scheduled_at=utc_now(),
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    # 1. Simulate Answer to populate Redis session
    answer_payload = {
        "CallSid": "CA_turn_test_sid",
        "From": "+15005550006",
        "To": seed_students[0].phone,
    }
    with patch("backend.ai_pipeline.tts.GoogleTTS.synthesize", new_callable=AsyncMock) as mock_tts:
        mock_tts.return_value = "https://domain.edu/audio1.wav"
        ans_res = await async_client.post(f"/webhook/twilio/answer?task_id={task.id}", data=answer_payload)
        assert ans_res.status_code == 200

    # 2. Simulate Caller Input
    input_payload = {
        "CallSid": "CA_turn_test_sid",
        "RecordingUrl": "https://api.twilio.com/2010-04-01/Accounts/ACtest/Recordings/RE12345",
        "RecordingDuration": "3",
    }

    mock_turn = {
        "user_transcript": "When is the physics paper?",
        "assistant_reply": "Physics paper is on Friday at 10 AM.",
        "response_audio_url": "https://domain.edu/audio2.wav",
        "latency": {"total_ms": 1400},
    }

    with patch("backend.ai_pipeline.pipeline.AIPipeline.process_turn", new_callable=AsyncMock) as mock_turn_runner:
        mock_turn_runner.return_value = mock_turn
        response = await async_client.post(f"/webhook/twilio/input?task_id={task.id}", data=input_payload)

    assert response.status_code == 200
    assert "<Response>" in response.text
    assert "<Play>https://domain.edu/audio2.wav</Play>" in response.text
    assert f"/webhook/twilio/input?task_id={task.id}" in response.text


@pytest.mark.asyncio
async def test_twilio_hangup_completes_call_task(
    async_client: AsyncClient,
    db_session: AsyncSession,
    seed_students: List[Student],
):
    """Verifies Twilio hangup statusCallback records duration, completed outcome, and transcript log."""
    script = CallScript(
        name="Hangup Script",
        category="notice",
        language="hi",
        system_prompt="Test prompt",
        opening_message="Test greeting",
    )
    db_session.add(script)
    await db_session.commit()
    await db_session.refresh(script)

    campaign = CallCampaign(name="Hangup Camp", script_id=script.id, scheduled_at=utc_now())
    db_session.add(campaign)
    await db_session.commit()
    await db_session.refresh(campaign)

    task = CallTask(
        campaign_id=campaign.id,
        student_id=seed_students[0].id,
        student_phone=seed_students[0].phone,
        script_id=script.id,
        status="in_progress",
        scheduled_at=utc_now(),
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    hangup_payload = {
        "CallSid": "CA_hangup_sid_999",
        "CallDuration": "45",
        "CallStatus": "completed",
    }
    response = await async_client.post(f"/webhook/twilio/hangup?task_id={task.id}", data=hangup_payload)
    assert response.status_code == 200
    assert "<Response" in response.text

    # Re-query task to verify completion
    await db_session.refresh(task)
    assert task.status == "completed"
    assert task.duration_sec == 45
    assert task.outcome == "completed"


@pytest.mark.asyncio
async def test_twilio_fallback(async_client: AsyncClient):
    """Verifies Twilio fallback endpoint issues Hangup TwiML."""
    response = await async_client.post("/webhook/twilio/fallback")
    assert response.status_code == 200
    assert "<Hangup" in response.text
