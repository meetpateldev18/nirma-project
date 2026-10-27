"""
End-to-End System Workflow Tests — Complete Automated Call Lifecycle.

Tests the full lifecycle of an outbound automated AI call from creation to completion:
1. Student cohort and CallScript creation.
2. Campaign scheduling and automatic task generation via REST API (POST /api/campaigns).
3. Celery background dispatch (place_call_task) transitioning task to 'ringing'.
4. Plivo carrier Answer Webhook (POST /webhook/plivo/answer) activating session in Redis (TTL=600s).
5. Multi-turn AI dialogue progression via Input Webhooks (POST /webhook/plivo/input).
6. Carrier disconnect and Hangup Webhook (POST /webhook/plivo/hangup) calculating outcome,
   persisting full conversational transcript in CallLog, and cleaning Redis memory.
7. Verification of analytical records via REST API (GET /api/calls/{id} and /transcript).
"""

import json
from typing import Dict, List
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.database.models import CallCampaign, CallLog, CallScript, CallTask, Student, utc_now
from backend.scheduler.tasks import place_call_task
import backend.telephony.webhook_handler as wh


@pytest.mark.asyncio
async def test_full_call_lifecycle_from_campaign_to_transcript(
    async_client: AsyncClient,
    admin_headers: Dict[str, str],
    db_session: AsyncSession,
    sync_db_session: Session,
):
    """
    Validates end-to-end integration:
    REST API -> Task Generation -> Celery Dispatch -> Webhooks -> AI Pipeline -> Log Persistence -> API Read.
    """
    # --------------------------------------------------------------------------
    # Step 1: Seed Target Student & Call Script
    # --------------------------------------------------------------------------
    student = Student(
        roll_number="21BCE099",
        name="Vikram Sharma",
        phone="+919876599099",
        department="CS",
        semester=6,
        language_pref="hi",
        is_active=True,
    )
    script = CallScript(
        name="End to End Exam Notice",
        category="notice",
        language="hi",
        system_prompt="You are Nirma Exam Coordinator. Keep responses under 25 words.",
        opening_message="Namaste Vikram, exam schedule has been released.",
    )
    db_session.add_all([student, script])
    await db_session.commit()
    await db_session.refresh(student)
    await db_session.refresh(script)

    # --------------------------------------------------------------------------
    # Step 2: Admin creates campaign via REST API
    # --------------------------------------------------------------------------
    campaign_payload = {
        "name": "Mid-Sem Notice Campaign 2026",
        "script_id": script.id,
        "target_filter": {"department": "CS", "semester": 6},
        "scheduled_at": "2026-10-15T09:30:00Z",
        "max_retries": 2,
        "retry_delay_min": 60,
    }
    create_resp = await async_client.post(
        "/api/campaigns",
        json=campaign_payload,
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    campaign_id = create_resp.json()["id"]

    # Verify task was created in database with 'pending' status
    task_res = await db_session.execute(
        select(CallTask).where(CallTask.campaign_id == campaign_id, CallTask.student_id == student.id)
    )
    task = task_res.scalar_one()
    assert task.status == "pending"
    assert task.student_phone == "+919876599099"
    task_id = task.id

    # --------------------------------------------------------------------------
    # Step 3: Celery worker dispatches call task (transition to 'ringing')
    # --------------------------------------------------------------------------
    # Clear any auto-dispatched call_log so e2e test steps start from pristine state
    await db_session.execute(CallLog.__table__.delete().where(CallLog.task_id == task_id))
    await db_session.commit()

    with patch("backend.scheduler.tasks.get_sync_session") as mock_session_ctx:
        mock_session_ctx.return_value.__enter__.return_value = sync_db_session
        dispatch_status = place_call_task(task_id)
        assert dispatch_status is not None
        assert dispatch_status.startswith("mock_")

    # Refresh task from DB to verify status
    await db_session.refresh(task)
    assert task.status == "ringing"
    assert task.plivo_uuid is not None
    carrier_uuid = task.plivo_uuid

    # --------------------------------------------------------------------------
    # Step 4: Plivo carrier triggers Answer Webhook
    # --------------------------------------------------------------------------
    answer_payload = {
        "CallUUID": carrier_uuid,
        "From": "+917923456789",
        "To": student.phone,
    }
    with patch("backend.telephony.webhook_handler.ai_pipeline.tts.synthesize", new_callable=AsyncMock) as mock_tts:
        mock_tts.return_value = "https://mock.nirmauni.ac.in/audio/opening_greeting.wav"
        ans_resp = await async_client.post(
            f"/webhook/plivo/answer?task_id={task_id}",
            data=answer_payload,
        )
        assert ans_resp.status_code == 200
        assert ans_resp.headers["content-type"].startswith("application/xml")
        assert "<Play>https://mock.nirmauni.ac.in/audio/opening_greeting.wav</Play>" in ans_resp.text
        assert f"/webhook/plivo/input?task_id={task_id}" in ans_resp.text

    # Verify state transitions: status -> 'in_progress', Redis session TTL=600s
    await db_session.refresh(task)
    assert task.status == "in_progress"
    session_key = f"call:session:{carrier_uuid}"
    session_state = await wh.redis_client.hgetall(session_key)
    assert session_state["turn_count"] == "1"
    ttl = await wh.redis_client.ttl(session_key)
    assert ttl == 600

    # --------------------------------------------------------------------------
    # Step 5: Student speaks -> Plivo triggers Input Webhook (Turn 1)
    # --------------------------------------------------------------------------
    input_payload_1 = {
        "CallUUID": carrier_uuid,
        "RecordUrl": "https://api.plivo.com/v1/Recordings/student_turn_1.mp3",
    }
    turn_1_mock = {
        "user_transcript": "Kab se shuru ho rahe hain exams?",
        "assistant_reply": "Exams 25 October se shuru honge.",
        "response_audio_url": "https://mock.nirmauni.ac.in/audio/reply_1.wav",
        "latency": {"total_ms": 1350},
    }
    with patch("backend.telephony.webhook_handler.ai_pipeline.process_turn", new_callable=AsyncMock) as mock_turn:
        mock_turn.return_value = turn_1_mock
        inp_resp_1 = await async_client.post(
            f"/webhook/plivo/input?task_id={task_id}",
            data=input_payload_1,
        )
        assert inp_resp_1.status_code == 200
        assert "<Play>https://mock.nirmauni.ac.in/audio/reply_1.wav</Play>" in inp_resp_1.text
        assert "<Record" in inp_resp_1.text

    # --------------------------------------------------------------------------
    # Step 6: Student concludes -> Plivo triggers Input Webhook (Turn 2, goodbye)
    # --------------------------------------------------------------------------
    input_payload_2 = {
        "CallUUID": carrier_uuid,
        "RecordUrl": "https://api.plivo.com/v1/Recordings/student_turn_2.mp3",
    }
    turn_2_mock = {
        "user_transcript": "Theek hai, dhanyavaad.",
        "assistant_reply": "Aapka swagat hai. Goodbye.",
        "response_audio_url": "https://mock.nirmauni.ac.in/audio/reply_2.wav",
        "latency": {"total_ms": 1200},
    }
    with patch("backend.telephony.webhook_handler.ai_pipeline.process_turn", new_callable=AsyncMock) as mock_turn:
        mock_turn.return_value = turn_2_mock
        inp_resp_2 = await async_client.post(
            f"/webhook/plivo/input?task_id={task_id}",
            data=input_payload_2,
        )
        assert inp_resp_2.status_code == 200
        assert "<Hangup" in inp_resp_2.text  # Disconnected because assistant replied 'Goodbye'

    # --------------------------------------------------------------------------
    # Step 7: Call disconnected -> Plivo triggers Hangup Webhook
    # --------------------------------------------------------------------------
    hangup_payload = {
        "CallUUID": carrier_uuid,
        "Duration": "38",  # 38 seconds connected
    }
    hangup_resp = await async_client.post(
        f"/webhook/plivo/hangup?task_id={task_id}",
        data=hangup_payload,
    )
    assert hangup_resp.status_code == 200
    assert "<Hangup" in hangup_resp.text

    # --------------------------------------------------------------------------
    # Step 8: Assert Persistent State & Database Invariants
    # --------------------------------------------------------------------------
    await db_session.refresh(task)
    assert task.status == "completed"
    assert task.duration_sec == 38
    assert task.outcome == "completed"

    # Verify CallLog transcript
    log_query = select(CallLog).where(CallLog.task_id == task_id)
    log_res = await db_session.execute(log_query)
    call_log = log_res.scalar_one()
    assert len(call_log.transcript) == 5  # Opening + User1 + Assistant1 + User2 + Assistant2
    assert call_log.transcript[1]["content"] == "Kab se shuru ho rahe hain exams?"
    assert call_log.transcript[3]["content"] == "Theek hai, dhanyavaad."

    # Verify Redis session purged
    assert (await wh.redis_client.exists(session_key)) == 0

    # --------------------------------------------------------------------------
    # Step 9: Staff queries REST API for call details and transcript
    # --------------------------------------------------------------------------
    detail_resp = await async_client.get(f"/api/calls/{task_id}", headers=admin_headers)
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()
    assert detail_data["status"] == "completed"
    assert detail_data["duration_sec"] == 38
    assert detail_data["outcome"] == "completed"

    transcript_resp = await async_client.get(f"/api/calls/{task_id}/transcript", headers=admin_headers)
    assert transcript_resp.status_code == 200
    transcript_data = transcript_resp.json()
    assert len(transcript_data["transcript"]) == 5
    assert transcript_data["task_id"] == task_id
    assert transcript_data["stt_provider"] == "indic_conformer"
