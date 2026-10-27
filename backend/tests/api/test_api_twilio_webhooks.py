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


@pytest.mark.asyncio
async def test_twilio_silence_escalation_ladder(
    async_client: AsyncClient,
    db_session: AsyncSession,
    seed_students: List[Student],
):
    """Verifies 3-tier silence escalation ladder: Soft Reprompt -> Warning -> Graceful Disconnect."""
    script = CallScript(
        name="Silence Test Script",
        category="notice",
        language="en",
        system_prompt="Test prompt",
        opening_message="Hello, this is Nirma University.",
    )
    db_session.add(script)
    await db_session.commit()
    await db_session.refresh(script)

    campaign = CallCampaign(name="Silence Camp", script_id=script.id, scheduled_at=utc_now())
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

    call_sid = "CA_silence_test_sid"

    # Step 1: Answer call to establish Redis session
    answer_payload = {"CallSid": call_sid, "From": "+15005550006", "To": seed_students[0].phone}
    with patch("backend.ai_pipeline.tts.GoogleTTS.synthesize", new_callable=AsyncMock) as mock_tts:
        mock_tts.return_value = "https://calls.nirmauni.ac.in/audio.wav"
        ans_res = await async_client.post(f"/webhook/twilio/answer?task_id={task.id}", data=answer_payload)
        assert ans_res.status_code == 200

    # Step 2: Caller says nothing (empty SpeechResult) -> Tier 1 Soft Reprompt
    silence_payload = {"CallSid": call_sid, "SpeechResult": ""}
    res_tier1 = await async_client.post(f"/webhook/twilio/input?task_id={task.id}", data=silence_payload)
    assert res_tier1.status_code == 200
    assert "Are you still there" in res_tier1.text
    assert "<Gather" in res_tier1.text
    assert 'timeout="5"' in res_tier1.text

    # Step 3: Caller says nothing again -> Tier 2 Final Warning
    res_tier2 = await async_client.post(f"/webhook/twilio/input?task_id={task.id}", data=silence_payload)
    assert res_tier2.status_code == 200
    assert "I didn't hear anything" in res_tier2.text
    assert "<Gather" in res_tier2.text
    assert 'timeout="4"' in res_tier2.text

    # Step 4: Caller stays silent third time -> Tier 3 Polite Disconnect with <Hangup/>
    res_tier3 = await async_client.post(f"/webhook/twilio/input?task_id={task.id}", data=silence_payload)
    assert res_tier3.status_code == 200
    assert "Since I haven't heard from you" in res_tier3.text
    assert "<Hangup" in res_tier3.text

    import asyncio
    await asyncio.sleep(0.1)
    await db_session.refresh(task)
    assert task.status == "failed"
    assert task.outcome == "no_answer"


@pytest.mark.asyncio
async def test_twilio_silence_reset_when_user_speaks(
    async_client: AsyncClient,
    db_session: AsyncSession,
    seed_students: List[Student],
):
    """Verifies that an active user speech utterance resets the silence escalation counter to 0."""
    script = CallScript(
        name="Reset Silence Script",
        category="notice",
        language="en",
        system_prompt="Test assistant.",
        opening_message="Hello from Nirma University.",
    )
    db_session.add(script)
    await db_session.commit()
    await db_session.refresh(script)

    campaign = CallCampaign(name="Reset Camp", script_id=script.id, scheduled_at=utc_now())
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

    call_sid = "CA_reset_silence_sid"

    # 1. Answer call
    answer_payload = {"CallSid": call_sid, "From": "+15005550006", "To": seed_students[0].phone}
    with patch("backend.ai_pipeline.tts.GoogleTTS.synthesize", new_callable=AsyncMock) as mock_tts:
        mock_tts.return_value = "https://calls.nirmauni.ac.in/audio.wav"
        await async_client.post(f"/webhook/twilio/answer?task_id={task.id}", data=answer_payload)

    # 2. Trigger Tier 1 silence
    silence_payload = {"CallSid": call_sid, "SpeechResult": ""}
    res_tier1 = await async_client.post(f"/webhook/twilio/input?task_id={task.id}", data=silence_payload)
    assert "Are you still there" in res_tier1.text

    # 3. Caller speaks!
    speech_payload = {"CallSid": call_sid, "SpeechResult": "Yes I am here, tell me about admissions."}
    with patch("backend.ai_pipeline.llm.FallbackLLM.generate", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = "Admissions are open until next Friday."
        res_speech = await async_client.post(f"/webhook/twilio/input?task_id={task.id}", data=speech_payload)
    assert res_speech.status_code == 200
    assert "Admissions are open" in res_speech.text

    # 4. Now if caller stays silent again, it starts back at Tier 1 Soft Reprompt (not Tier 2!)
    res_next_silence = await async_client.post(f"/webhook/twilio/input?task_id={task.id}", data=silence_payload)
    assert "Are you still there" in res_next_silence.text


@pytest.mark.asyncio
async def test_twilio_slow_llm_triggers_filler_and_redirect_flow(
    async_client: AsyncClient,
    db_session: AsyncSession,
    seed_students: List[Student],
):
    """Verifies that slow LLM inference triggers localized filler <Say> + <Redirect> to prevent carrier timeout."""
    import asyncio

    script = CallScript(
        name="Slow LLM Script",
        category="notice",
        language="en",
        system_prompt="Test assistant.",
        opening_message="Hello from Nirma University.",
    )
    db_session.add(script)
    await db_session.commit()
    await db_session.refresh(script)

    campaign = CallCampaign(name="Slow Camp", script_id=script.id, scheduled_at=utc_now())
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

    call_sid = "CA_slow_llm_sid_999"

    # 1. Answer call
    answer_payload = {"CallSid": call_sid, "From": "+15005550006", "To": seed_students[0].phone}
    with patch("backend.ai_pipeline.tts.GoogleTTS.synthesize", new_callable=AsyncMock) as mock_tts:
        mock_tts.return_value = "https://calls.nirmauni.ac.in/audio.wav"
        await async_client.post(f"/webhook/twilio/answer?task_id={task.id}", data=answer_payload)

    # 2. Simulate slow LLM (takes 2.8s, exceeding 2.0s fast-path deadline)
    async def _mock_slow_llm(*args, **kwargs):
        await asyncio.sleep(2.3)
        return "Here is your detailed examination result."

    speech_payload = {"CallSid": call_sid, "SpeechResult": "What is my grade in mathematics?"}
    with patch("backend.ai_pipeline.llm.FallbackLLM.generate", side_effect=_mock_slow_llm):
        res_input = await async_client.post(f"/webhook/twilio/input?task_id={task.id}", data=speech_payload)

    # Must return immediate TwiML with filler and <Redirect>
    assert res_input.status_code == 200
    assert "Please give me a moment while I check that for you" in res_input.text
    assert "<Redirect" in res_input.text
    assert f"/webhook/twilio/continue?task_id={task.id}" in res_input.text

    # Allow the background worker to finish saving the pending response in Redis
    await asyncio.sleep(0.5)

    # 3. Simulate Twilio following the <Redirect> to /webhook/twilio/continue
    continue_payload = {"CallSid": call_sid, "turn": "2"}
    res_continue = await async_client.post(f"/webhook/twilio/continue?task_id={task.id}&turn=2&call_uuid={call_sid}", data=continue_payload)

    assert res_continue.status_code == 200
    assert "Here is your detailed examination result" in res_continue.text
    assert "<Gather" in res_continue.text


@pytest.mark.asyncio
async def test_twilio_multilingual_filler_gujarati(
    async_client: AsyncClient,
    db_session: AsyncSession,
    seed_students: List[Student],
):
    """Verifies that Gujarati call sessions play native Gujarati filler prompt when LLM is slow."""
    import asyncio

    script = CallScript(
        name="Gujarati Notice",
        category="notice",
        language="gu",
        system_prompt="તમે નિર્મા યુનિવર્સિટીના સહાયક છો.",
        opening_message="નમસ્તે, નિર્મા યુનિવર્સિટીમાં આપનું સ્વાગત છે.",
    )
    db_session.add(script)
    await db_session.commit()
    await db_session.refresh(script)

    campaign = CallCampaign(name="Guj Camp", script_id=script.id, scheduled_at=utc_now())
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

    call_sid = "CA_gujarati_sid_123"

    # 1. Answer call
    answer_payload = {"CallSid": call_sid, "From": "+15005550006", "To": seed_students[0].phone}
    with patch("backend.ai_pipeline.tts.GoogleTTS.synthesize", new_callable=AsyncMock) as mock_tts:
        mock_tts.return_value = "https://calls.nirmauni.ac.in/audio.wav"
        await async_client.post(f"/webhook/twilio/answer?task_id={task.id}", data=answer_payload)

    # 2. Slow LLM in Gujarati
    async def _mock_slow_llm(*args, **kwargs):
        await asyncio.sleep(2.3)
        return "પરીક્ષા આવતા સોમવારે શરૂ થશે."

    speech_payload = {"CallSid": call_sid, "SpeechResult": "પરીક્ષા ક્યારે છે?"}
    with patch("backend.ai_pipeline.llm.FallbackLLM.generate", side_effect=_mock_slow_llm):
        res_input = await async_client.post(f"/webhook/twilio/input?task_id={task.id}", data=speech_payload)

    assert res_input.status_code == 200
    assert "કૃપા કરીને થોડીવાર રાહ જુઓ, હું માહિતી ચકાસી રહ્યો છું." in res_input.text
    assert "<Redirect" in res_input.text
