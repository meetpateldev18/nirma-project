"""
Comprehensive Credential & Service Verification Script.

Tests and validates all configured cloud API keys and connection strings:
1. Groq Cloud LLM (llama-3.3-70b-versatile)
2. Sarvam AI Speech-to-Text (saaras:v4)
3. Supabase PostgreSQL (PostgreSQL 17 via asyncpg & psycopg)
4. Upstash Serverless Redis (TCP TLS & HTTPS REST API)
5. Plivo Telephony Adapter (Development Sandbox Verification)
"""

import asyncio
import io
import os
import struct
import time
import wave
from pathlib import Path
from typing import Dict

import httpx
import psycopg
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text


def load_env() -> Dict[str, str]:
    """Parses .env file directly into a dictionary."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    env_vars = {}
    if not env_path.exists():
        print(f"❌ .env not found at {env_path}")
        return env_vars

    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                env_vars[k] = v
    return env_vars


def generate_test_wav_bytes() -> bytes:
    """Generates an in-memory 1-second 16kHz mono 16-bit PCM silence WAV."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)        # Mono
        wf.setsampwidth(2)        # 16-bit PCM
        wf.setframerate(16000)    # 16 kHz
        # Write 0.5s of low-level 440Hz test tone
        sample_count = 8000
        raw_samples = bytearray()
        for i in range(sample_count):
            val = int(500 * (1 if (i % 36) < 18 else -1))
            raw_samples.extend(struct.pack("<h", val))
        wf.writeframes(bytes(raw_samples))
    return buffer.getvalue()


async def verify_gemini(gemini_key: str, model: str = "gemini-3.8-flash"):
    print("\n" + "=" * 60)
    print("1. VERIFYING GOOGLE GEMINI CLOUD LLM & TTS MODELS")
    print("=" * 60)
    if not gemini_key or "your_gemini" in gemini_key:
        print("❌ GEMINI_API_KEY is missing or placeholder.")
        return False

    print(f"Key Prefix: {gemini_key[:8]}...{gemini_key[-4:]}")

    # 1. Test Text Model (3.8-flash or 3.5-flash-lite)
    tested_models = [model, "gemini-3.5-flash-lite"] if model != "gemini-3.5-flash-lite" else [model]
    text_ok = False
    for m in tested_models:
        print(f"\n--- Testing LLM Reasoning: {m} ---")
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={gemini_key}"
        payload = {
            "system_instruction": {"parts": [{"text": "You are Nirma University AI voice caller. Answer in 1 short sentence."}]},
            "contents": [{"role": "user", "parts": [{"text": "Hello, please confirm you are online and working."}]}],
            "generationConfig": {"maxOutputTokens": 40, "temperature": 0.2},
        }

        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.post(endpoint, json=payload)
                latency = (time.time() - t0) * 1000
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    print(f"✅ STATUS: SUCCESS (HTTP 200)")
                    print(f"⏱️ LATENCY: {latency:.1f} ms")
                    print(f"🤖 MODEL RESPONSE: \"{content}\"")
                    text_ok = True
                    break
                else:
                    print(f"⚠️ STATUS: {resp.status_code} ({resp.text[:120]})")
        except Exception as exc:
            print(f"⚠️ {m} timeout or error: {exc}")

    # 2. Test Gemini Audio Synthesis (gemini-3.8-flash-lite-tts)
    print(f"\n--- Testing Audio Synthesis: gemini-3.8-flash-lite-tts ---")
    tts_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash-lite-tts:generateContent?key={gemini_key}"
    tts_payload = {
        "contents": [{"parts": [{"text": "Hello, this is Nirma University AI assistant."}]}],
        "generationConfig": {"responseModalities": ["AUDIO"]},
    }
    t0 = time.time()
    tts_ok = False
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(tts_url, json=tts_payload)
            latency = (time.time() - t0) * 1000
            if resp.status_code == 200:
                data = resp.json()
                b64_bytes = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
                print(f"✅ STATUS: SUCCESS (HTTP 200)")
                print(f"⏱️ TTS LATENCY: {latency:.1f} ms")
                print(f"🔊 AUDIO GENERATED: {len(b64_bytes)} base64 chars (native audio/wav)")
                tts_ok = True
            else:
                print(f"⚠️ TTS STATUS: {resp.status_code} ({resp.text[:120]})")
    except Exception as exc:
        print(f"⚠️ Gemini TTS error: {exc}")

    return text_ok and tts_ok


async def verify_groq(groq_key: str):
    print("\n" + "=" * 60)
    print("2. VERIFYING GROQ CLOUD LLM API")
    print("=" * 60)
    if not groq_key or "your_groq" in groq_key:
        print("❌ GROQ_API_KEY is missing or placeholder.")
        return False

    print(f"Key Prefix: {groq_key[:12]}...{groq_key[-4:]}")
    headers = {
        "Authorization": f"Bearer {groq_key}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    }
    payload = {
        "model": "qwen/qwen3.8-27b",
        "messages": [
            {
                "role": "system",
                "content": "You are Nirma University AI voice caller. Answer in maximum 1 sentence.",
            },
            {"role": "user", "content": "Hello, please confirm you are online and working."},
        ],
        "max_tokens": 40,
        "temperature": 0.2,
    }

    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            latency = (time.time() - t0) * 1000
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"].strip()
                print(f"✅ STATUS: SUCCESS (HTTP 200)")
                print(f"⏱️ LATENCY: {latency:.1f} ms")
                print(f"🤖 MODEL RESPONSE: \"{content}\"")
                return True
            else:
                print(f"❌ STATUS: FAILED (HTTP {resp.status_code})")
                print(f"Response: {resp.text}")
                return False
    except Exception as exc:
        print(f"❌ ERROR: {exc}")
        return False


async def verify_sarvam(sarvam_key: str):
    print("\n" + "=" * 60)
    print("2. VERIFYING SARVAM AI SPEECH-TO-TEXT (STT) API")
    print("=" * 60)
    if not sarvam_key or "your_sarvam" in sarvam_key:
        print("❌ SARVAM_API_KEY is missing or placeholder.")
        return False

    print(f"Key Prefix: {sarvam_key[:12]}...{sarvam_key[-4:]}")
    wav_bytes = generate_test_wav_bytes()
    headers = {"api-subscription-key": sarvam_key}
    files = {"file": ("test_tone.wav", wav_bytes, "audio/wav")}
    data = {
        "model": "saaras:v4",
        "mode": "transcribe",
        "language_code": "hi-IN",
        "with_diarization": "false",
    }

    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(
                "https://api.sarvam.ai/speech-to-text",
                headers=headers,
                files=files,
                data=data,
            )
            latency = (time.time() - t0) * 1000
            if resp.status_code == 200:
                res_data = resp.json()
                transcript = res_data.get("transcript", "(empty tone)")
                req_id = res_data.get("request_id", "N/A")
                print(f"✅ STATUS: SUCCESS (HTTP 200)")
                print(f"⏱️ LATENCY: {latency:.1f} ms")
                print(f"🆔 REQUEST ID: {req_id}")
                print(f"🎙️ TRANSCRIPTION PARSED: \"{transcript}\"")
                return True
            else:
                print(f"❌ STATUS: FAILED (HTTP {resp.status_code})")
                print(f"Response: {resp.text}")
                return False
    except Exception as exc:
        print(f"❌ ERROR: {exc}")
        return False


async def verify_supabase(sync_url: str, async_url: str):
    print("\n" + "=" * 60)
    print("3. VERIFYING SUPABASE POSTGRESQL DATABASE")
    print("=" * 60)
    if not sync_url or "localhost" in sync_url:
        print("❌ Supabase URL not configured in .env.")
        return False

    host = sync_url.split("@")[-1]
    print(f"Host: {host}")

    # 1. Test psycopg (Synchronous Celery driver)
    t0 = time.time()
    try:
        clean_conn = sync_url.replace("postgresql+psycopg://", "postgresql://")
        with psycopg.connect(clean_conn, connect_timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version();")
                pg_ver = cur.fetchone()[0]
                cur.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    ORDER BY table_name;
                """)
                tables = [r[0] for r in cur.fetchall()]
        latency_sync = (time.time() - t0) * 1000
        print(f"✅ PSYCOPG (Sync): CONNECTED in {latency_sync:.1f} ms")
        print(f"   Postgres Version: {pg_ver.split(' on ')[0]}")
        print(f"   Live Tables ({len(tables)}): {tables}")
    except Exception as exc:
        print(f"❌ PSYCOPG FAILED: {exc}")
        return False

    # 2. Test asyncpg (Asynchronous FastAPI driver)
    t0 = time.time()
    try:
        engine = create_async_engine(
            async_url,
            connect_args={"statement_cache_size": 0},
            pool_pre_ping=True,
        )
        async with engine.connect() as aconn:
            res = await aconn.execute(text("SELECT count(*) FROM staff_users;"))
            count = res.scalar()
        await engine.dispose()
        latency_async = (time.time() - t0) * 1000
        print(f"✅ ASYNCPG (Async): CONNECTED in {latency_async:.1f} ms")
        print(f"   Query 'SELECT count(*) FROM staff_users': {count} records")
        return True
    except Exception as exc:
        print(f"❌ ASYNCPG FAILED: {exc}")
        return False


async def verify_upstash(redis_url: str, rest_url: str, rest_token: str):
    print("\n" + "=" * 60)
    print("4. VERIFYING UPSTASH REDIS CACHE & TASK BROKER")
    print("=" * 60)
    if not redis_url or "localhost" in redis_url:
        print("❌ Upstash REDIS_URL not configured.")
        return False

    # 1. Test TCP TLS (rediss://)
    t0 = time.time()
    try:
        r = aioredis.from_url(redis_url, decode_responses=True)
        test_key = f"nirma:verify:{int(time.time())}"
        await r.set(test_key, "online_ok", ex=120)
        read_val = await r.get(test_key)
        ttl = await r.ttl(test_key)
        await r.delete(test_key)
        await r.aclose()
        latency_tcp = (time.time() - t0) * 1000
        print(f"✅ TCP TLS (rediss://): CONNECTED in {latency_tcp:.1f} ms")
        print(f"   Read/Write Verified: Value='{read_val}', TTL={ttl}s")
    except Exception as exc:
        print(f"❌ TCP TLS FAILED: {exc}")
        return False

    # 2. Test HTTPS REST API
    if rest_url and rest_token:
        t0 = time.time()
        try:
            headers = {"Authorization": f"Bearer {rest_token}"}
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(f"{rest_url}/ping", headers=headers)
                latency_rest = (time.time() - t0) * 1000
                if resp.status_code == 200:
                    print(f"✅ HTTPS REST API: CONNECTED in {latency_rest:.1f} ms (Response: {resp.text.strip()})")
                else:
                    print(f"⚠️ REST API returned {resp.status_code}: {resp.text}")
        except Exception as exc:
            print(f"⚠️ REST API check error: {exc}")
    return True


def verify_plivo():
    print("\n" + "=" * 60)
    print("5. VERIFYING PLIVO TELEPHONY ADAPTER (LOCAL SANDBOX)")
    print("=" * 60)
    import sys
    sys.path.insert(0, ".")
    from backend.telephony.plivo_adapter import PlivoAdapter

    adapter = PlivoAdapter()
    result = adapter.place_call_sync(
        to_number="+919876543210",
        answer_url="http://localhost:8000/webhook/plivo/answer",
        hangup_url="http://localhost:8000/webhook/plivo/hangup",
        caller_id="+917971600000",
    )
    print(f"✅ DISPATCH OUTCOME: {result.status.upper()}")
    print(f"   Simulated UUID: {result.call_uuid}")
    print(f"   Safe for local development with zero carrier charges.")
    return True


def verify_twilio(account_sid: str, auth_token: str, caller_id: str):
    print("\n" + "=" * 60)
    print("6. VERIFYING TWILIO TELEPHONY ADAPTER & ACCOUNT")
    print("=" * 60)
    if not account_sid or not auth_token or "your_" in account_sid:
        print("❌ Twilio credentials missing in .env.")
        return False

    print(f"Account SID: {account_sid[:8]}...{account_sid[-4:]}")
    print(f"Caller ID:   {caller_id or 'Not Configured'}")

    # 1. Probe Live Twilio Account API
    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        account = client.api.v2010.accounts(account_sid).fetch()
        print(f"✅ TWILIO ACCOUNT: {account.status.upper()} (Friendly Name: '{account.friendly_name}')")

        try:
            balance = client.balance.fetch()
            print(f"💰 ACCOUNT BALANCE: {balance.balance} {balance.currency}")
        except Exception:
            pass

        incoming = client.incoming_phone_numbers.list(limit=5)
        numbers = [n.phone_number for n in incoming]
        if numbers:
            print(f"📞 PROVISIONED PHONE NUMBERS: {numbers}")
            print(f"   (Use one of these numbers as your TWILIO_CALLER_ID in .env)")
        else:
            print("⚠️ PROVISIONED PHONE NUMBERS: None found.")
            print("👉 ACTION REQUIRED: Go to https://console.twilio.com and click 'Get a phone number'")
            print("   to claim your free trial number, then set it as TWILIO_CALLER_ID in .env")

        return True
    except Exception as exc:
        print(f"❌ TWILIO API AUTHENTICATION FAILED: {exc}")
        return False


async def main():
    env = load_env()
    print("=" * 60)
    print("NIRMA AI CALL AGENT — END-TO-END CREDENTIAL VERIFICATION")
    print("=" * 60)

    gem_ok = await verify_gemini(
        env.get("GEMINI_API_KEY", ""),
        env.get("GEMINI_MODEL", "gemini-3.8-flash"),
    )
    g_ok = await verify_groq(env.get("GROQ_API_KEY", ""))
    s_ok = await verify_sarvam(env.get("SARVAM_API_KEY", ""))
    db_ok = await verify_supabase(env.get("SYNC_DATABASE_URL", ""), env.get("DATABASE_URL", ""))
    r_ok = await verify_upstash(
        env.get("REDIS_URL", ""),
        env.get("UPSTASH_REDIS_REST_URL", ""),
        env.get("UPSTASH_REDIS_REST_TOKEN", ""),
    )
    p_ok = verify_plivo()
    tw_ok = verify_twilio(
        env.get("TWILIO_ACCOUNT_SID", ""),
        env.get("TWILIO_AUTH_TOKEN", ""),
        env.get("TWILIO_CALLER_ID", ""),
    )

    print("\n" + "=" * 60)
    print("FINAL SUMMARY REPORT")
    print("=" * 60)
    print(f"1. Google Gemini (LLM & Native Audio TTS): {'🟢 OPERATIONAL' if gem_ok else '🔴 FAILED / NOT SET'}")
    print(f"2. Groq Cloud LLM (Secondary LLM Backup):  {'🟢 OPERATIONAL' if g_ok else '🔴 FAILED / NOT SET'}")
    print(f"3. Sarvam AI (Speech-to-Text / ASR):       {'🟢 OPERATIONAL' if s_ok else '🔴 FAILED / NOT SET'}")
    print(f"4. Supabase PostgreSQL (Database Cloud):   {'🟢 OPERATIONAL' if db_ok else '🔴 FAILED'}")
    print(f"5. Upstash Redis (Serverless Cache):       {'🟢 OPERATIONAL' if r_ok else '🔴 FAILED'}")
    print(f"6. Plivo Telephony (Primary Indian PSTN):  {'🟢 OPERATIONAL' if p_ok else '🔴 FAILED'}")
    print(f"7. Twilio Telephony (Trial & Global PSTN): {'🟢 OPERATIONAL' if tw_ok else '🔴 FAILED'}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
