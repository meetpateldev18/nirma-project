# Nirma University AI Call Agent — System Memory Bank & Living Technical Reference
# File: docs/SYSTEM_MEMORY.md
# Classification: Central Architecture, State & Implementation Memory

This document serves as the persistent, single-source-of-truth technical memory for the Nirma University AI Call Agent. Any agent or engineer working in this codebase can rely on this document for precise operational context, schema specifications, concurrency locks, hardware budgets, and known technical debt.

---

## 1. System Identity & Architectural Blueprint

### 1.1 Purpose & Mission
An enterprise-grade, automated multilingual outbound voice calling system developed for Nirma University to deliver administrative notifications (fee reminders, exam notices, attendance warnings, campus placements, and event alerts) to students across Gujarat and India.

### 1.2 Core Technology Matrix
| Layer | Technologies | Role / Justification |
| :--- | :--- | :--- |
| **API & Webhook Engine** | FastAPI (Python 3.11/3.15), Uvicorn | High-throughput asynchronous ASGI server for REST API and Plivo webhooks. |
| **Database & ORM** | PostgreSQL 15+, SQLAlchemy 2.0, AsyncPG / Psycopg | Relational state storage with async FastAPI access and sync Celery worker access. |
| **Task Queue & Scheduler** | Celery 5.4, Celery Beat, Redis 7 (or Upstash) | Background queue for non-blocking carrier dialing and cron-style batch polling. |
| **Telephony Gateway** | Plivo Cloud Telephony API (Twilio standby) | PSTN signaling, call dispatch, and `<Record>` / `<Play>` XML execution. |
| **Speech-to-Text (STT)** | IndicConformer 0.60B (NeMo) -> Sarvam AI (`saaras:v4`) | Multilingual ASR for English, Hindi, and Gujarati with cloud failover. |
| **Language Reasoning (LLM)** | Qwen-14B (Ollama Q4_K_M) -> Groq API (`llama-3.3-70b`) | Concise conversational reasoning restricted to <= 30 words per turn. |
| **Text-to-Speech (TTS)** | IndicF5 0.40B Acoustic -> Google TTS (gTTS) | Natural speech synthesis served statically via Nginx audio cache. |
| **Frontend Dashboard** | React 19, Vite, Tailwind CSS v4, Radix UI / Shadcn | Single-page operator application with light paper/navy theme and live WebSockets. |
| **Target Infrastructure** | Nirma Supercomputer (Ubuntu 22.04 LTS, RTX 3090/4090 24GB) | Headless deployment managed exclusively over SSH with NVIDIA GPU passthrough. |

---

## 2. End-to-End System Topology & Data Flow

```mermaid
flowchart TD
    subgraph Telecom & Carrier Network
        StudentPhone[Student PSTN Mobile Device]
        PlivoCarrier[Plivo PSTN Cloud Telephony]
    end

    subgraph Nirma Supercomputer / Institutional Host
        NginxProxy[Nginx Reverse Proxy & TLS Termination]

        subgraph ASGI Web Tier
            FastAPIServer[FastAPI Web Application]
            AuthRouter[JWT Authentication & RBAC]
            CampaignRouter[Campaign & Script API]
            WebhookRouter[Plivo Webhook State Machine]
            WSManager[WebSocket Connection Pool]
        end

        subgraph Background Processing Tier
            CeleryBeat[Celery Beat Scheduler (30s Tick)]
            CeleryWorker[Celery Sync Multiprocessing Workers]
        end

        subgraph Persistence & Shared State Tier
            PostgresDB[(PostgreSQL 15 / Supabase)]
            RedisCache[(Redis 7 / Upstash Cache & Locks)]
            AudioCache[(Local Audio Cache Directory /static/audio)]
        end

        subgraph AI Inference Pipeline
            IndicConformer[Primary STT: IndicConformer 0.60B]
            OllamaLLM[Primary LLM: Qwen-14B via Ollama]
            IndicF5TTS[Primary TTS: IndicF5 Acoustic Engine]
        end
    end

    subgraph External Cloud Fallbacks
        SarvamCloud[Sarvam AI saaras:v4 STT]
        GroqCloud[Groq Cloud LLaMA-3.3-70B LLM]
        GoogleCloudTTS[Google Cloud gTTS]
    end

    subgraph Staff User Interface
        StaffBrowser[Staff / Admin Browser Dashboard]
    end

    %% Dialing Lifecycle
    StaffBrowser -->|POST /api/campaigns| CampaignRouter
    CampaignRouter -->|Inserts Campaign & Tasks| PostgresDB
    CeleryBeat -->|Every 30s: Query Due Tasks| PostgresDB
    CeleryBeat -->|Dispatches Task ID| CeleryWorker
    CeleryWorker -->|Direct Sync REST Dial| PlivoCarrier
    PlivoCarrier -->|PSTN Dial| StudentPhone

    %% Conversational Turn Lifecycle
    StudentPhone -->|Voice Answer| PlivoCarrier
    PlivoCarrier -->|POST /webhook/plivo/answer| NginxProxy
    NginxProxy --> WebhookRouter
    WebhookRouter -->|Initialize Session TTL=600s| RedisCache
    WebhookRouter -->|Return Opening XML Play + Record| PlivoCarrier
    StudentPhone -->|Speaks Response| PlivoCarrier
    PlivoCarrier -->|POST /webhook/plivo/input RecordUrl| WebhookRouter
    WebhookRouter -->|Lock turn:call_uuid| RedisCache
    WebhookRouter --> IndicConformer
    IndicConformer -.->|On Failure / Timeout| SarvamCloud
    WebhookRouter --> OllamaLLM
    OllamaLLM -.->|On Failure / Timeout| GroqCloud
    WebhookRouter --> IndicF5TTS
    IndicF5TTS -.->|On Failure / Missing Weights| GoogleCloudTTS
    WebhookRouter -->|Return XML Play Response + Record| PlivoCarrier
    WebhookRouter -->|Broadcast Live Metrics| WSManager
    WSManager -->|WebSocket /ws/calls| StaffBrowser

    %% Disconnection Lifecycle
    StudentPhone -->|Call Ends| PlivoCarrier
    PlivoCarrier -->|POST /webhook/plivo/hangup| WebhookRouter
    WebhookRouter -->|Persist Transcript & Outcome| PostgresDB
    WebhookRouter -->|Delete Session Key| RedisCache
```

---

## 3. Database Schema & Data Dictionary (PostgreSQL 15)

### 3.1 `staff_users`
Stores administrative operators and faculty members with hashed passwords.
- `id` (INTEGER, PK, Autoincrement)
- `email` (VARCHAR(100), UNIQUE, INDEX)
- `name` (VARCHAR(100), NOT NULL)
- `role` (VARCHAR(20), NOT NULL, default `'operator'`) — `'admin'` or `'operator'`
- `password_hash` (VARCHAR(255), NOT NULL) — Bcrypt hashed string
- `is_active` (BOOLEAN, NOT NULL, default `TRUE`)
- `created_at` (TIMESTAMPTZ, NOT NULL, default `utc_now`)

### 3.2 `students`
Student profiles, academic cohorts, and language preferences.
- `id` (INTEGER, PK, Autoincrement)
- `roll_number` (VARCHAR(20), UNIQUE, INDEX) — e.g. `'21BCE001'`
- `name` (VARCHAR(100), NOT NULL)
- `phone` (VARCHAR(15), NOT NULL, INDEX) — E.164 format (e.g. `'+918866241204'`)
- `alt_phone` (VARCHAR(15), NULLABLE)
- `language_pref` (VARCHAR(10), NOT NULL, default `'hi'`) — `'hi'`, `'gu'`, `'en'`
- `department` (VARCHAR(50), NULLABLE) — e.g. `'Computer Science & Engineering'`
- `semester` (INTEGER, NULLABLE) — 1 through 8
- `whatsapp_number` (VARCHAR(15), NULLABLE)
- `is_active` (BOOLEAN, NOT NULL, default `TRUE`)
- `created_at` (TIMESTAMPTZ, default `utc_now`)
- `updated_at` (TIMESTAMPTZ, default `utc_now`, auto-updating)
- *Compound Indexes*: `idx_students_phone`, `idx_students_dept_sem_active (department, semester, is_active)`

### 3.3 `call_scripts`
Reusable conversational script templates with initial greetings and system prompts.
- `id` (INTEGER, PK, Autoincrement)
- `name` (VARCHAR(100), NOT NULL)
- `category` (VARCHAR(50), NOT NULL, INDEX) — e.g. `'fee_reminder'`, `'exam_notice'`, `'custom'`
- `language` (VARCHAR(10), NOT NULL) — `'hi'`, `'gu'`, `'en'`
- `system_prompt` (TEXT, NOT NULL) — Core behavioral constraint for LLM
- `opening_message` (TEXT, NOT NULL) — Synthesized opening line with mandatory AI disclosure
- `is_active` (BOOLEAN, NOT NULL, default `TRUE`)
- `created_by` (INTEGER, FK `staff_users.id`, NULLABLE)
- `created_at` (TIMESTAMPTZ, default `utc_now`)

### 3.4 `call_campaigns`
Batch and individual outbound call campaigns scheduled by staff.
- `id` (INTEGER, PK, Autoincrement)
- `name` (VARCHAR(100), NOT NULL)
- `script_id` (INTEGER, FK `call_scripts.id`, NOT NULL)
- `target_filter` (JSONB, NOT NULL, default `{}`) — Filter criteria (e.g. `{"department": "CS", "semester": 6}` or `{"student_id": 42}`)
- `scheduled_at` (TIMESTAMPTZ, NOT NULL, INDEX)
- `max_retries` (INTEGER, NOT NULL, default 2)
- `retry_delay_min` (INTEGER, NOT NULL, default 60)
- `status` (VARCHAR(20), NOT NULL, default `'pending'`, INDEX) — `'pending'`, `'running'`, `'completed'`, `'cancelled'`
- `created_by` (INTEGER, FK `staff_users.id`, NULLABLE)
- `created_at` (TIMESTAMPTZ, default `utc_now`)

### 3.5 `call_tasks`
Individual outbound phone calls queued and dispatched to students.
- `id` (INTEGER, PK, Autoincrement)
- `campaign_id` (INTEGER, FK `call_campaigns.id`, NOT NULL, INDEX)
- `student_id` (INTEGER, FK `students.id`, NOT NULL, INDEX)
- `student_phone` (VARCHAR(15), NOT NULL)
- `script_id` (INTEGER, FK `call_scripts.id`, NOT NULL)
- `status` (VARCHAR(20), NOT NULL, default `'pending'`, INDEX) — `'pending'`, `'ringing'`, `'in_progress'`, `'completed'`, `'failed'`, `'cancelled'`
- `plivo_uuid` (VARCHAR(50), NULLABLE, INDEX) — Carrier UUID
- `retry_count` (INTEGER, NOT NULL, default 0)
- `scheduled_at` (TIMESTAMPTZ, NOT NULL, INDEX)
- `placed_at` (TIMESTAMPTZ, NULLABLE)
- `answered_at` (TIMESTAMPTZ, NULLABLE)
- `ended_at` (TIMESTAMPTZ, NULLABLE)
- `duration_sec` (INTEGER, NULLABLE)
- `outcome` (VARCHAR(30), NULLABLE) — `'completed'`, `'no_answer'`, `'busy'`, `'failed'`
- `created_at` (TIMESTAMPTZ, default `utc_now`)
- *Partial Index*: `idx_call_tasks_pending_scheduled` on `scheduled_at WHERE status = 'pending'`

### 3.6 `call_logs`
Operational conversational audit log with complete turns and provider metrics.
- `id` (INTEGER, PK, Autoincrement)
- `task_id` (INTEGER, FK `call_tasks.id`, UNIQUE, NOT NULL, INDEX)
- `transcript` (JSONB, NOT NULL, default `[]`) — Array of turns `[{"role": "user"|"assistant", "content": "..."}]`
- `stt_provider` (VARCHAR(20), NULLABLE) — `'indic_conformer'` | `'sarvam'`
- `llm_provider` (VARCHAR(20), NULLABLE) — `'qwen3'` | `'groq'`
- `tts_provider` (VARCHAR(20), NULLABLE) — `'indicf5'` | `'gtts'`
- `avg_latency_ms` (INTEGER, NULLABLE)
- `max_latency_ms` (INTEGER, NULLABLE)
- `error_log` (JSONB, NOT NULL, default `[]`)
- `created_at` (TIMESTAMPTZ, default `utc_now`)

---

## 4. Telephony & Webhook Mechanics (Plivo & Twilio Dual-Carrier Architecture)

### 4.1 Carrier Resolution & Factory Protocol
Carrier selection is fully dynamic and parameterized via `settings.telephony_provider` (`'plivo'` or `'twilio'`):
- **Factory Resolver**: `get_telephony_adapter(provider=None)` in [`backend/telephony/factory.py`](file:///Users/urvagandhi/Developer/College/nirma-ai-call-agent/backend/telephony/factory.py) dynamically instantiates the correct concrete adapter (`PlivoAdapter` or `TwilioAdapter`).
- **Dynamic Webhook Binding**: `settings.get_carrier_webhook_urls(task_id)` automatically generates `/webhook/plivo/*` or `/webhook/twilio/*` URLs.
- **Dynamic System Status**: `GET /api/system/status` automatically probes whether Plivo or Twilio is active, verifies sandbox vs live credentials, and displays the appropriate caller ID in the sidebar.

### 4.2 Parameter & XML Invariants
| Carrier | Call Identifier | Audio Recording Parameter | Silence Attribute | XML Format |
| :--- | :--- | :--- | :--- | :--- |
| **Plivo** | `CallUUID` | `RecordUrl` (defensive fallback to `RecordingUrl`) | `silence="2"` | Plivo XML (`<Play>`, `<Record>`, `<Hangup>`) |
| **Twilio** | `CallSid` | `RecordingUrl` (auto-appends `.wav` for direct PCM) | `timeout="2"` | TwiML via `VoiceResponse` (`<Play>`, `<Record>`, `<Hangup>`) |

### 4.3 Authenticated Media Retrieval
Twilio enforces HTTP Basic Auth on recording media endpoints (`api.twilio.com`) when account media protection is active. [`backend/ai_pipeline/stt.py`](file:///Users/urvagandhi/Developer/College/nirma-ai-call-agent/backend/ai_pipeline/stt.py) includes `_get_audio_download_auth()` which automatically attaches `(account_sid, auth_token)` when downloading caller audio from Twilio, preventing 401 Unauthorized errors during ASR transcription.

### 4.4 Concurrency & Execution Separation
1. **Celery Worker Execution (`place_call_sync`)**:
   - Celery multiprocessing worker processes execute carrier REST SDK calls synchronously directly.
   - Eliminates redundant `asyncio.run()` event loops inside prefork worker tasks.
2. **FastAPI Webhook & REST Execution (`place_call`)**:
   - Carrier SDK calls are non-blocking inside FastAPI async routes via `await asyncio.to_thread(...)`.

### 4.5 Redis State & Distributed Lock Protocol
- **Call Session Key**: `call:session:{call_uuid}` (HASH)
  - `TTL = 600 seconds` (mandatory, refreshed on every turn).
  - Fields: `task_id`, `call_uuid`, `carrier`, `system_prompt`, `opening_message`, `lang`, `turn_count`, `history`, `start_time`.
- **Turn Lock Key**: `lock:webhook:turn:{call_uuid}` (STRING)
  - `TTL = 15 seconds`.
  - Acquired via `SET NX EX`. Released atomically via Lua script checking lock token.
- **Batch Dispatcher Lock**: `lock:dispatcher:batch` (STRING)
  - `TTL = 25 seconds`. Prevents overlapping Celery Beat ticks.

---

## 5. AI Pipeline & Latency Budgets

### 5.1 Strict Turn Budget (< 4,000 ms)
| Sub-Pipeline | Target Budget | Fallback Trigger | Primary Engine | Fallback Engine |
| :--- | :--- | :--- | :--- | :--- |
| **STT (ASR)** | < 1,200 ms | Timeout > 2.0s or Exception | IndicConformer 0.60B (NeMo) | Sarvam AI (`saaras:v4`) |
| **LLM Reasoning** | < 1,800 ms | Timeout > 3.5s or Exception | Qwen-14B (Ollama Q4_K_M) | Groq Cloud (`llama-3.3-70b`) |
| **TTS Synthesis** | < 600 ms | Timeout > 2.5s or Exception | IndicF5 Acoustic Engine | Google Cloud gTTS |
| **Transport & Overhead** | < 400 ms | Fixed buffer | Nginx Static Audio Cache | MinIO Object Store |

### 5.2 Conversational UX Constraints
- **Word Limit**: <= 30 words per turn (maximum 2 short sentences).
- **Prohibited Formatting**: Zero markdown symbols, bold text, asterisks, bullet points, or numbered lists in synthesized voice answers.
- **Context Pruning**: Prompt conversational history is truncated to the last 6 messages (3 turns) to preserve sub-second time-to-first-token (TTFT).

### 5.3 VRAM Hardware Allocation (RTX 3090/4090 24GB)
- IndicConformer 0.60B: ~1.5 GB
- Qwen-14B 4-bit Quantized: ~9.2 GB
- TTS Acoustic Engine: ~2.0 GB
- CUDA Runtime & KV Buffers: ~2.5 GB
- **Total Committed VRAM**: ~15.2 GB (Safely fits inside 24 GB card; will crash on an 8 GB card).

---

## 6. Regulatory & Compliance Safeguards (TRAI / India)

1. **Permitted Calling Window**: Outbound calls can strictly be placed between **09:00:00 and 21:00:00 IST** (`Asia/Kolkata`). Celery Beat dispatcher checks `is_within_trai_calling_window()` and defers tasks outside this window.
2. **Mandatory AI Disclosure**: In compliance with TRAI regulations and consumer protection directives, the opening sentence of every script template must identify the caller as an automated AI system of Nirma University.
3. **Reason-Driven Determinism**: In `backend/ai_pipeline/script_writer.py`, opening lines are built deterministically from approved templates to prevent flaky models from omitting self-disclosure.
4. **PII Masking**: Transcripts transmitted to external cloud APIs must not expose sensitive student financial data.

---

## 7. Frontend Architecture & Design Tokens

### 7.1 Visual System & Semantic Tokens (Light Paper/Navy)
Derived from institutional print aesthetics (IMS Ahmedabad / Nirma University):
- `bg-canvas`: Light paper surface (`#F8F9FA` / `#FFFFFF`)
- `text-ink`: Deep navy primary typography (`#0A192F` / `#1E293B`)
- `text-body`: Muted slate body typography (`#475569`)
- `text-mute`: Subtle metadata font (`#64748B`)
- `border-hairline`: Subdued divider line (`rgba(0, 0, 0, 0.08)`)
- `brand-terracotta`: Accent primary (`#E06D3B`, hover `#F08252`)
- `live-emerald`: Live connected calls (`#059669` - contrast adjusted for light background)
- `trai-amber`: Regulatory pending status (`#D97706`)

### 7.2 Component Architecture & Invariants
- Built with **Radix UI** primitives and **Shadcn UI** conventions (`@/components/ui/*`).
- **No in-house primitive components**: Standard buttons, dialogs, selects, inputs, badges, tabs, and tables.
- **Sonner Toast**: `<Toaster />` mounted once at root in `App.tsx`.
- **Tabular Numerics**: `tabular-nums` enforced on all live metrics, counters, and phone numbers.
- **Role-Based Views**:
  - `Admin`: Full navigation (Overview Dashboard, Live Calls Telemetry, New Call, Transcripts, Faculty Access).
  - `Operator / Faculty`: Focused navigation (New Call, My Transcripts).

---

## 8. Remote Supercomputer (HPC) & SSH Deployment Runbook

### 8.1 SSH Deployment Protocol
1. Production target is the Nirma University Supercomputer node accessed exclusively over **SSH**.
2. Deployment command:
   ```bash
   ssh nirma_admin@hpc.nirmauni.ac.in
   cd /opt/nirma-ai-call-agent
   bash scripts/deploy_supercomputer.sh
   ```
3. The deployment script:
   - Validates `.env` presence.
   - Verifies NVIDIA GPU visibility via `nvidia-smi`.
   - Pulls latest git commits.
   - Executes `docker compose build && docker compose up -d`.
   - Waits for Postgres readiness and runs `alembic upgrade head` and `python -m backend.seeds`.
   - Pulls Ollama model `qwen:14b`.
   - Validates `/health` endpoint probe.

### 8.2 Institutional Domain Binding
- Nirma University provisions an institutional domain (e.g. `https://calls.nirmauni.ac.in`).
- Reverse proxy (Nginx) terminates TLS and routes:
  - `/` -> Frontend static build
  - `/api/` -> FastAPI backend
  - `/auth/` -> Authentication router
  - `/ws/` -> WebSocket connection manager (with `Upgrade` headers)
  - `/webhook/` -> Plivo webhook handler
  - `/static/audio/` -> Static audio cache directory

---

## 9. Technical Debt, Known Gaps & Action Items

| Item | Component | Current State | Production Resolution Path |
| :--- | :--- | :--- | :--- |
| **1. IndicF5 TTS Stub** | `backend/ai_pipeline/tts.py` | `_sync_synthesize` is an empty stub that raises `FileNotFoundError` or returns without writing WAV bytes. Currently falls over to `GoogleTTS` (gTTS). | Implement PyTorch IndicF5 checkpoint inference or integrate fast Kokoro-ONNX / Parler-TTS. |
| **2. Plivo Webhook Signatures** | `backend/telephony/webhook_handler.py` | Webhooks validate parameters but do not currently verify `X-Plivo-Signature-V3`. | Add FastAPI middleware or dependency verifying HMAC-SHA256 signature using `settings.plivo_auth_token`. |
| **3. Twilio Adapter Implementation** | `backend/telephony/` | **RESOLVED & COMPLETE**. Full `TwilioAdapter`, `get_telephony_adapter()` factory, authenticated audio fetching, and `/webhook/twilio/*` TwiML state machine active. | Complete with 14 automated regression test cases. |
| **4. Multi-Semester Matching** | `backend/scheduler/campaign_runner.py` | Matches a single integer semester; frontend can send arrays. | Update filter logic to support `semester in target_filter["semesters"]`. |
| **5. Live Call Action Endpoints** | `backend/api/calls.py` & UI | "Transfer" and "Hangup" buttons in `LiveTelemetryView.tsx` are UI-only. | Add `POST /api/calls/{id}/hangup` calling `adapter.hangup_call(task.plivo_uuid)`. |
| **6. CSV Student Import** | `backend/api/students.py` | No bulk CSV import endpoint exists. | Implement `POST /api/students/import` accepting CSV with roll, name, phone, dept, sem, lang. |
| **7. MinIO Object Storage** | Infrastructure | MinIO is referenced in `.env.example` but audio is currently served from local disk. | Add MinIO/S3 storage backend for audio archive persistence across container rebuilds. |

---

## 10. Verification & Test Commands

### 10.1 Running Backend Pytest Suite
```bash
source .venv/bin/activate
pytest -v
# 174 passed in ~2.4 seconds
```

### 10.2 Building & Linting Frontend
```bash
cd frontend
npm run lint    # oxlint: 0 errors
npm run build   # tsc -b && vite build: clean production bundle
```

### 10.3 Validating Live Cloud Credentials
```bash
python scripts/verify_credentials.py
```
Checks Groq Cloud LLM, Sarvam AI STT, Supabase PostgreSQL, Upstash Redis, and Plivo sandbox.
