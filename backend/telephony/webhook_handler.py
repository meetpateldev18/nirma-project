"""
Carrier Webhook Handlers Module — Plivo & Twilio Event-Driven Call State Machine.

This module implements the HTTP webhook endpoints triggered by telephony carriers:
1. Plivo Webhooks (/webhook/plivo):
   - POST /webhook/plivo/answer: Triggered when recipient picks up phone.
   - POST /webhook/plivo/input: Triggered when speech recording completes.
   - POST /webhook/plivo/hangup: Triggered upon call disconnection.
   - POST /webhook/plivo/fallback: Triggered on carrier XML error.

2. Twilio Webhooks (/webhook/twilio):
   - POST /webhook/twilio/answer: Triggered when recipient picks up phone.
   - POST /webhook/twilio/input: Triggered when TwiML <Record> completes.
   - POST /webhook/twilio/hangup: Triggered by statusCallback upon call termination.
   - POST /webhook/twilio/fallback: Triggered on TwiML execution error.

CRITICAL TELEPHONY INVARIANTS:
    - Parameter name invariants:
      * Plivo sends 'RecordUrl', 'CallUUID', 'Duration'.
      * Twilio sends 'RecordingUrl', 'CallSid', 'CallDuration', 'CallStatus'.
    - XML generation:
      * Plivo XML uses <Record silence="2" .../> and <Play> tags.
      * Twilio TwiML uses <Record timeout="2" playBeep="false" .../> and <Play> tags.
    - Redis session keys 'call:session:{call_uuid}' MUST maintain explicit TTL=600s.
    - Redis distributed locks 'lock:webhook:turn:{call_uuid}' prevent concurrent duplicate turns.

Dependencies:
    - fastapi >= 0.111
    - redis >= 5.0
    - plivo >= 4.38
    - twilio >= 9.0
"""

import json
import logging
import time
import xml.etree.ElementTree as ET
from typing import Any, Dict, Optional

from fastapi import APIRouter, Form, Query, Response
from sqlalchemy import select
from twilio.twiml.voice_response import VoiceResponse

from backend.ai_pipeline.pipeline import AIPipeline
from backend.config import settings
from backend.database.models import CallLog, CallScript, CallTask
from backend.database.redis_client import redis_manager
from backend.database.session import async_session_scope
from backend.websocket.manager import ws_manager

logger = logging.getLogger(__name__)

# Router instances for Plivo and Twilio carrier webhooks
router = APIRouter(prefix="/webhook/plivo", tags=["Plivo Webhooks"])
twilio_router = APIRouter(prefix="/webhook/twilio", tags=["Twilio Webhooks"])

# Shared Redis client and AI Pipeline
redis_client = redis_manager.get_client()
ai_pipeline = AIPipeline()


# ------------------------------------------------------------------------------
# XML Builders (Plivo XML & Twilio TwiML)
# ------------------------------------------------------------------------------
def _build_plivo_xml_response(
    audio_url: Optional[str] = None,
    action_url: Optional[str] = None,
    hangup: bool = False,
    silence_seconds: int = 2,
) -> str:
    """
    Constructs valid Plivo XML response string.

    Args:
        audio_url: Optional static audio URL to play to the caller.
        action_url: Webhook action URL for the <Record> tag.
        hangup: If True, appends <Hangup/> directive after playing audio.
        silence_seconds: Silence detection threshold in seconds.

    Returns:
        str: Serialized XML document string.
    """
    response_elem = ET.Element("Response")

    if audio_url:
        play_elem = ET.SubElement(response_elem, "Play")
        play_elem.text = audio_url

    if hangup:
        ET.SubElement(response_elem, "Hangup")
    elif action_url:
        ET.SubElement(
            response_elem,
            "Record",
            attrib={
                "action": action_url,
                "maxLength": "30",
                "silence": str(silence_seconds),
                "finishOnKey": "#",
                "redirect": "false",
            },
        )

    return ET.tostring(response_elem, encoding="utf-8", method="xml").decode("utf-8")


def _build_twilio_xml_response(
    audio_url: Optional[str] = None,
    action_url: Optional[str] = None,
    hangup: bool = False,
    silence_seconds: int = 2,
) -> str:
    """
    Constructs valid TwiML XML response string for Twilio voice calls.

    Args:
        audio_url: Optional static audio URL to play to the caller.
        action_url: Webhook action URL for the <Record> tag.
        hangup: If True, appends <Hangup/> directive.
        silence_seconds: Silence detection timeout in seconds (Twilio 'timeout' parameter).

    Returns:
        str: Serialized TwiML XML document string.
    """
    vr = VoiceResponse()

    if audio_url:
        vr.play(audio_url)

    if hangup:
        vr.hangup()
    elif action_url:
        vr.record(
            action=action_url,
            max_length=30,
            timeout=silence_seconds,
            finish_on_key="#",
            play_beep=False,
            method="POST",
        )

    return str(vr)


def _build_carrier_xml(
    carrier: str,
    audio_url: Optional[str] = None,
    action_url: Optional[str] = None,
    hangup: bool = False,
    silence_seconds: int = 2,
) -> str:
    """Helper to dispatch XML generation to the appropriate carrier dialect."""
    if carrier.lower() == "twilio":
        return _build_twilio_xml_response(
            audio_url=audio_url,
            action_url=action_url,
            hangup=hangup,
            silence_seconds=silence_seconds,
        )
    return _build_plivo_xml_response(
        audio_url=audio_url,
        action_url=action_url,
        hangup=hangup,
        silence_seconds=silence_seconds,
    )


# ------------------------------------------------------------------------------
# Core Telephony State Machine Operations
# ------------------------------------------------------------------------------
async def _execute_call_answer(
    task_id: Optional[int],
    call_uuid: str,
    from_number: str,
    to_number: str,
    carrier: str,
) -> Response:
    """
    Shared call answer handler for both Plivo and Twilio carriers.

    Supports both queued database campaign calls and ad-hoc/inbound testing calls.
    Sets status to 'in_progress', synthesizes opening greeting, initializes Redis
    call session with TTL=600s, and emits carrier-specific XML.
    """
    task_id_int = task_id or 0
    logger.info(
        "[%s] Answer Webhook -> TaskID: %d, CallUUID/SID: %s, From: %s, To: %s",
        carrier.upper(),
        task_id_int,
        call_uuid,
        from_number,
        to_number,
    )

    # 1. Fetch task and script details from database if task_id provided
    row = None
    if task_id_int > 0:
        async with async_session_scope() as session:
            result = await session.execute(
                select(CallTask, CallScript)
                .join(CallScript, CallTask.script_id == CallScript.id)
                .where(CallTask.id == task_id_int)
            )
            row = result.first()
            if not row:
                logger.error(
                    "[%s] CallTask ID %d not found in database for answer webhook.",
                    carrier.upper(),
                    task_id_int,
                )
                xml_resp = _build_carrier_xml(carrier=carrier, hangup=True)
                return Response(content=xml_resp, media_type="application/xml")

            task, script = row
            task.status = "in_progress"
            task.plivo_uuid = call_uuid  # Stores carrier CallUUID / CallSid
            task.answered_at = task.answered_at or task.created_at

    if row:
        task, script = row
        opening_text = script.opening_message
        language = script.language or "en"
        system_prompt = script.system_prompt
    else:
        logger.info("[%s] Inbound ad-hoc test call detected (CallUUID: %s). Using dynamic Gemini voice assistant.", carrier.upper(), call_uuid)
        opening_text = "Namaste! This is the Nirma University AI voice assistant powered by Google Gemini. How may I assist you today?"
        language = "en"
        system_prompt = (
            "You are an intelligent, polite AI voice representative of Nirma University. "
            "Answer questions about admissions, exams, campus events, or fees concisely in 1 to 2 short sentences (under 30 words). "
            "Never use markdown, bullet points, or asterisks. This is an active voice call."
        )

    # 2. Synthesize initial opening message audio URL via TTS
    opening_audio_url = await ai_pipeline.tts.synthesize(text=opening_text, language=language)

    # 3. Store in-flight session context in Redis (TTL=600 seconds)
    session_key = f"call:session:{call_uuid}"
    session_data = {
        "task_id": str(task_id_int),
        "call_uuid": call_uuid,
        "carrier": carrier,
        "system_prompt": system_prompt,
        "opening_message": opening_text,
        "lang": language,
        "turn_count": "1",
        "history": json.dumps([{"role": "assistant", "content": opening_text}]),
        "start_time": str(time.time()),
    }

    # Batch session initialization and TTL into a single atomic network round-trip
    async with redis_client.pipeline(transaction=True) as pipe:
        pipe.hset(session_key, mapping=session_data)
        pipe.expire(session_key, 600)  # Mandatory 600s TTL
        await pipe.execute()
    logger.info("Initialized Redis call session key '%s' with TTL=600s (carrier: %s)", session_key, carrier)

    # 4. Broadcast live status update to WebSocket clients
    await ws_manager.broadcast(
        "call_status",
        {
            "task_id": task_id_int,
            "call_uuid": call_uuid,
            "carrier": carrier,
            "status": "in_progress",
            "lang": language,
            "from_number": from_number,
            "to_number": to_number,
        },
    )

    # 5. Construct carrier-specific XML response
    input_action_url = settings.build_webhook_url(f"/webhook/{carrier}/input?task_id={task_id_int}")
    xml_content = _build_carrier_xml(
        carrier=carrier,
        audio_url=opening_audio_url,
        action_url=input_action_url,
        silence_seconds=2,
    )

    return Response(content=xml_content, media_type="application/xml")


async def _execute_call_input(
    task_id: int,
    call_uuid: str,
    raw_record_url: Optional[str],
    carrier: str,
) -> Response:
    """
    Shared call input handler for both Plivo and Twilio carriers.

    Processes caller speech recording through the AI cascade (STT -> LLM -> TTS),
    updates conversation history in Redis, checks hangup conditions, and returns
    carrier XML with the next synthesised response and <Record> tag.
    """
    if not raw_record_url:
        logger.error(
            "[%s] Missing audio recording URL in input webhook for CallUUID %s",
            carrier.upper(),
            call_uuid,
        )
        xml_resp = _build_carrier_xml(carrier=carrier, hangup=True)
        return Response(content=xml_resp, media_type="application/xml")

    # In Twilio, ensure URL points directly to .wav container if no file extension is present
    actual_record_url = raw_record_url
    if carrier.lower() == "twilio" and not actual_record_url.endswith((".wav", ".mp3")):
        actual_record_url = f"{actual_record_url}.wav"

    logger.info(
        "[%s] Input Webhook -> TaskID: %d, CallUUID: %s, RecordURL: %s",
        carrier.upper(),
        task_id,
        call_uuid,
        actual_record_url,
    )

    # Acquire distributed lock with unique token to deduplicate concurrent webhook callbacks
    lock_key = f"webhook:turn:{call_uuid}"
    lock_acquired, lock_token = await redis_manager.acquire_lock(lock_key, ttl_seconds=15)
    if not lock_acquired:
        logger.warning(
            "[%s] Duplicate/concurrent input webhook for CallUUID %s ignored.",
            carrier.upper(),
            call_uuid,
        )
        return Response(content="<Response/>", media_type="application/xml")

    try:
        # 1. Load Redis session context
        session_key = f"call:session:{call_uuid}"
        session_data = await redis_client.hgetall(session_key)

        if not session_data:
            logger.warning(
                "[%s] Redis session key '%s' expired or missing. Terminating call.",
                carrier.upper(),
                session_key,
            )
            xml_resp = _build_carrier_xml(carrier=carrier, hangup=True)
            return Response(content=xml_resp, media_type="application/xml")

        # Reconstitute context dictionary
        history_list = json.loads(session_data.get("history", "[]"))
        turn_count = int(session_data.get("turn_count", "1")) + 1
        lang = session_data.get("lang", "hi")
        system_prompt = session_data.get("system_prompt", "")

        context: Dict[str, Any] = {
            "task_id": task_id,
            "call_uuid": call_uuid,
            "carrier": carrier,
            "system_prompt": system_prompt,
            "history": history_list,
            "lang": lang,
            "turn": turn_count,
            "latency_log": [],
        }

        # 2. Run cascaded AI pipeline turn (STT -> LLM -> TTS)
        try:
            turn_result = await ai_pipeline.process_turn(
                audio_url=actual_record_url,
                context=context,
            )
            user_transcript = turn_result["user_transcript"]
            assistant_reply = turn_result["assistant_reply"]
            response_audio_url = turn_result["response_audio_url"]
        except Exception as exc:
            logger.error(
                "[%s] AI pipeline turn failure for task %d: %s",
                carrier.upper(),
                task_id,
                exc,
                exc_info=True,
            )
            response_audio_url = await ai_pipeline.tts.synthesize(
                "Main aapki baat samajh nahi paya. Kripya punah prayas karen.", lang
            )
            assistant_reply = "Main aapki baat samajh nahi paya."
            user_transcript = ""

        # 3. Update history and turn count in Redis via atomic pipeline
        if user_transcript:
            history_list.append({"role": "user", "content": user_transcript})
        history_list.append({"role": "assistant", "content": assistant_reply})

        async with redis_client.pipeline(transaction=True) as pipe:
            pipe.hset(
                session_key,
                mapping={
                    "history": json.dumps(history_list),
                    "turn_count": str(turn_count),
                },
            )
            pipe.expire(session_key, 600)  # Refresh 600s TTL
            await pipe.execute()
    finally:
        await redis_manager.release_lock(lock_key, lock_token)

    # 4. Check call termination criteria (max 10 turns or explicit goodbye)
    should_hangup = turn_count >= 10 or any(
        kw in assistant_reply.lower() for kw in ["goodbye", "dhanyavaad", "alvida", "thank you"]
    )

    input_action_url = settings.build_webhook_url(f"/webhook/{carrier}/input?task_id={task_id}")
    xml_content = _build_carrier_xml(
        carrier=carrier,
        audio_url=response_audio_url,
        action_url=input_action_url if not should_hangup else None,
        hangup=should_hangup,
        silence_seconds=2,
    )

    # Broadcast turn dialogue and latency metrics to connected dashboard operators
    turn_latency = 1800
    if "turn_result" in locals() and isinstance(turn_result, dict):
        turn_latency = turn_result.get("latency", {}).get("total_ms", 1800)

    await ws_manager.broadcast(
        "transcript_turn",
        {
            "task_id": task_id,
            "call_uuid": call_uuid,
            "carrier": carrier,
            "turn": turn_count,
            "user_transcript": user_transcript,
            "assistant_reply": assistant_reply,
            "latency_ms": turn_latency,
        },
    )

    return Response(content=xml_content, media_type="application/xml")


async def _execute_call_hangup(
    task_id: int,
    call_uuid: str,
    duration: int,
    carrier: str,
    call_status: Optional[str] = None,
) -> Response:
    """
    Shared call hangup handler for both Plivo and Twilio carriers.

    Updates task duration and outcome in PostgreSQL, persists the conversational
    transcript in CallLog, removes Redis in-flight session, and broadcasts completion.
    """
    logger.info(
        "[%s] Hangup Webhook -> TaskID: %d, CallUUID: %s, Duration: %ds, Status: %s",
        carrier.upper(),
        task_id,
        call_uuid,
        duration,
        call_status,
    )

    session_key = f"call:session:{call_uuid}"
    session_data = await redis_client.hgetall(session_key)
    history_list = json.loads(session_data.get("history", "[]")) if session_data else []

    # Calculate final outcome based on duration and optional carrier call status
    if duration > 5:
        computed_outcome = "completed"
    elif call_status:
        # Standardize carrier status: 'busy', 'no-answer', 'failed', 'canceled'
        normalized_status = call_status.strip().lower().replace("-", "_")
        computed_outcome = normalized_status if normalized_status in ["busy", "failed", "no_answer", "canceled"] else "no_answer"
    else:
        computed_outcome = "no_answer"

    # Update database records
    async with async_session_scope() as session:
        task_res = await session.execute(select(CallTask).where(CallTask.id == task_id))
        task = task_res.scalar_one_or_none()

        if task:
            task.status = "completed" if computed_outcome == "completed" else "failed"
            task.duration_sec = duration
            task.outcome = computed_outcome
            task.ended_at = task.ended_at or task.created_at

            # Save full transcript log
            log_res = await session.execute(select(CallLog).where(CallLog.task_id == task_id))
            call_log = log_res.scalar_one_or_none()
            if not call_log:
                call_log = CallLog(
                    task_id=task_id,
                    transcript=history_list,
                    stt_provider="indic_conformer",
                    llm_provider="qwen3",
                    tts_provider="indicf5",
                    avg_latency_ms=1800,
                )
                session.add(call_log)
            else:
                call_log.transcript = history_list

    # Delete Redis session context
    await redis_client.delete(session_key)

    # Broadcast call termination status to WebSocket clients
    await ws_manager.broadcast(
        "call_status",
        {
            "task_id": task_id,
            "call_uuid": call_uuid,
            "carrier": carrier,
            "status": "completed" if computed_outcome == "completed" else "failed",
            "duration_sec": duration,
            "outcome": computed_outcome,
        },
    )

    if carrier.lower() == "twilio":
        return Response(content="<Response/>", media_type="application/xml")

    xml_content = _build_plivo_xml_response(hangup=True)
    return Response(content=xml_content, media_type="application/xml")


# ------------------------------------------------------------------------------
# 1. Plivo Webhook Endpoints (/webhook/plivo)
# ------------------------------------------------------------------------------
@router.post("/answer")
async def handle_plivo_answer(
    task_id: int = Query(..., description="Internal CallTask primary key"),
    call_uuid: str = Form(..., alias="CallUUID"),
    from_number: str = Form(..., alias="From"),
    to_number: str = Form(..., alias="To"),
) -> Response:
    """Triggered by Plivo when the student answers an outbound call."""
    return await _execute_call_answer(
        task_id=task_id,
        call_uuid=call_uuid,
        from_number=from_number,
        to_number=to_number,
        carrier="plivo",
    )


@router.post("/input")
async def handle_plivo_input(
    task_id: int = Query(..., description="Internal CallTask primary key"),
    call_uuid: str = Form(..., alias="CallUUID"),
    record_url: Optional[str] = Form(None, alias="RecordUrl"),
    recording_url: Optional[str] = Form(None, alias="RecordingUrl"),
) -> Response:
    """
    Triggered by Plivo when student finishes speaking.
    PLIVO PARAMETER INVARIANT: Reads 'RecordUrl' (with fallback to 'RecordingUrl').
    """
    actual_url = record_url or recording_url
    return await _execute_call_input(
        task_id=task_id,
        call_uuid=call_uuid,
        raw_record_url=actual_url,
        carrier="plivo",
    )


@router.post("/hangup")
async def handle_plivo_hangup(
    task_id: int = Query(..., description="Internal CallTask primary key"),
    call_uuid: str = Form(..., alias="CallUUID"),
    duration: int = Form(0, alias="Duration"),
) -> Response:
    """Triggered by Plivo when the call disconnects."""
    return await _execute_call_hangup(
        task_id=task_id,
        call_uuid=call_uuid,
        duration=duration,
        carrier="plivo",
    )


@router.post("/fallback")
async def handle_plivo_fallback() -> Response:
    """Triggered by Plivo on XML execution error; ensures graceful call hangup."""
    logger.error("Plivo Webhook Fallback triggered due to XML parsing or carrier routing failure.")
    xml_content = _build_plivo_xml_response(hangup=True)
    return Response(content=xml_content, media_type="application/xml")


# ------------------------------------------------------------------------------
# 2. Twilio Webhook Endpoints (/webhook/twilio)
# ------------------------------------------------------------------------------
@twilio_router.post("/answer")
async def handle_twilio_answer(
    task_id: Optional[int] = Query(None, description="Internal CallTask primary key"),
    call_sid: str = Form(..., alias="CallSid"),
    from_number: str = Form(..., alias="From"),
    to_number: str = Form(..., alias="To"),
) -> Response:
    """Triggered by Twilio when the student answers an outbound call or when an inbound test call is placed."""
    return await _execute_call_answer(
        task_id=task_id,
        call_uuid=call_sid,
        from_number=from_number,
        to_number=to_number,
        carrier="twilio",
    )


@twilio_router.post("/input")
async def handle_twilio_input(
    task_id: Optional[int] = Query(None, description="Internal CallTask primary key"),
    call_sid: str = Form(..., alias="CallSid"),
    recording_url: Optional[str] = Form(None, alias="RecordingUrl"),
) -> Response:
    """
    Triggered by Twilio when caller finishes speaking following a <Record> directive.
    TWILIO PARAMETER INVARIANT: Reads 'RecordingUrl' (e.g. https://api.twilio.com/.../Recordings/RE...).
    """
    return await _execute_call_input(
        task_id=task_id,
        call_uuid=call_sid,
        raw_record_url=recording_url,
        carrier="twilio",
    )


@twilio_router.post("/hangup")
async def handle_twilio_hangup(
    task_id: Optional[int] = Query(None, description="Internal CallTask primary key"),
    call_sid: str = Form(..., alias="CallSid"),
    call_duration: Optional[int] = Form(None, alias="CallDuration"),
    duration: int = Form(0, alias="Duration"),
    call_status: Optional[str] = Form(None, alias="CallStatus"),
) -> Response:
    """Triggered by Twilio statusCallback upon call completion."""
    actual_duration = call_duration if call_duration is not None else duration
    return await _execute_call_hangup(
        task_id=task_id,
        call_uuid=call_sid,
        duration=actual_duration,
        carrier="twilio",
        call_status=call_status,
    )


@twilio_router.post("/fallback")
async def handle_twilio_fallback() -> Response:
    """Triggered by Twilio on TwiML error; terminates call safely."""
    logger.error("Twilio Webhook Fallback triggered due to TwiML execution error.")
    xml_content = _build_twilio_xml_response(hangup=True)
    return Response(content=xml_content, media_type="application/xml")
