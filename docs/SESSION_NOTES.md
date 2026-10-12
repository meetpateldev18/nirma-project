# Engineering Session Notes — Nirma AI Call Agent

**Date:** 2026-10-11 → 2026-10-12
**Participant:** Meet Patel, working with Claude (Sonnet 5)
**Scope:** Audit the existing project, fix what was broken, rebuild the staff frontend against the real backend, add a free-text "reason-driven" call flow with LLM-generated scripts, and re-theme the whole app to a light design.

This is a narrative summary of the session's work and decisions — not a literal chat transcript (that isn't something that can be exported programmatically) — written so any collaborator can see what changed, why, and what's still open.

---

## 1. Starting point — audit of the cloned repo

Cloned fresh from `github.com/urvagandhi/nirma-ai-call-agent`. Findings:

- **Backend was solid**: FastAPI + Celery + PostgreSQL + Redis, 159 automated tests, all passing once the missing test dependencies (`pytest`, `pytest-asyncio`, `aiosqlite`, `greenlet`) were installed — none of these were declared in `requirements.txt`.
- **Frontend could not build at all.** `.gitignore` had a bare `lib/` pattern intended for Python build artifacts, which also matched `frontend/src/lib/` — so the shadcn `cn()` helper (`utils.ts`) was never committed. Every UI primitive imports from it.
- **Frontend had zero backend integration.** Every view read from hardcoded mock arrays in `services/api.ts`. No login screen existed; the header had a hardcoded staff name.
- Two endpoints referenced in the backend's own docstrings (`GET /api/campaigns/scripts`, `GET /api/campaigns/{id}/tasks`) didn't actually exist.
- The local TTS engine (`IndicF5TTS._sync_synthesize`) was an empty stub — logs a message, writes no audio.
- Celery's default `prefork` worker pool crashes under this machine's Python 3.14 / macOS combination (a `billiard` compatibility issue, not an app bug) — fixed locally by running with `--pool=solo`.

Full detail on this pass is in the **"Mission Control Readout"** artifact published mid-session (a plain-English + technical status report with an architecture diagram and a severity-ranked gap list).

## 2. Making the frontend real

- Fixed the `.gitignore` collision (scoped the Python-only entries to the repo root) and restored `src/lib/utils.ts`.
- Found and fixed a second, more subtle bug: a custom Tailwind `spacing` scale (`sm`, `md`, `lg`...) silently collided with Tailwind's built-in `max-w-*` scale, making every `max-w-sm`/`max-w-lg` in the app render a few pixels wide instead of its real size (this broke the shared `Dialog` component's default width on narrow viewports). Removed the unused, colliding scale.
- Added the two missing endpoints (`backend/api/campaigns.py`).
- Built a real auth layer: `frontend/src/lib/api-client.ts` (typed fetch client, JWT handling with auto-refresh-on-401, WebSocket connector), `frontend/src/lib/auth-context.tsx`, `frontend/src/components/LoginView.tsx`.
- Wired Dashboard, Live Telemetry, Campaign Launcher, and Transcripts to real REST/WebSocket data, replacing every mock fixture (later deleted entirely from `services/api.ts`).
- Stood up the full local stack (Docker Postgres/Redis, `uvicorn`, Celery worker + beat, Vite dev server), seeded an admin user and five demo students, and verified the complete flow — login → dashboard → launch a campaign → live telemetry → transcripts — in a real headless Chrome session via Playwright, not just by reading code.

## 3. "New Call" — reason-driven calling instead of fixed templates

Request: support both individual and batch calling from one focused flow; replace the fixed 6-template dropdown with a free-text reason that an LLM turns into the actual call script; make a document attachment optional context, never required.

Built:

- `backend/ai_pipeline/script_writer.py` — the opening line (mandatory AI self-disclosure, for TRAI compliance) is always built deterministically, language-aware, so it can never be dropped by a flaky model. The system prompt that keeps the AI on-topic is written by the existing `FallbackLLM` chain (local Ollama → Groq Cloud), with a deterministic template as a last-resort fallback if neither is reachable — verified live: with no real Ollama/Groq credentials configured, the chain correctly tried both, failed both, and fell through to the deterministic script without crashing.
- `POST /api/campaigns/generate-script` — multipart endpoint, optional `.txt`/`.pdf` upload (text extracted via `pypdf`, best-effort, failures swallowed since the document is always optional).
- `POST /api/campaigns/scripts` — persists a generated script as a normal `CallScript` row so the existing campaign-creation path needs no changes.
- `backend/api/students.py` — new search endpoint (`GET /api/students/search`) for the "call one person" flow.
- `CampaignRunner` extended to match a single `student_id` directly, bypassing department/semester filters — this is what makes an "individual call" just a one-recipient campaign under the hood.
- `frontend/src/components/NewCallView.tsx` replaced `CampaignLauncherView.tsx` entirely: a two-section flow (who & why → preview & launch), individual-vs-group toggle, live student search, free-text reason, language picker, optional file attach, and a preview of the exact opening line and system prompt before anything is dispatched.
- Verified both paths end-to-end: an individual call matched exactly the one selected student; a group call against "Computer Science & Engineering" matched exactly the 4 seeded students in that department.

## 4. Visual design — light theme, first for "New Call," then app-wide

Given a reference (an IMS Ahmedabad report screenshot: navy serif headlines, warm accent, white cards on light grey), `NewCallView` was built with its own light palette (`paper`/`navy`/`paperline`/`gold` Tailwind tokens, Source Serif 4 for headlines) as a deliberate "light island" inside the otherwise-dark app shell.

Follow-up request: extend that light theme to the whole application. Since every component already used semantic Tailwind tokens (`bg-canvas-*`, `text-ink`, `text-body`, `border-hairline`) rather than literal colors, the re-theme was done centrally in `tailwind.config.js` rather than file-by-file:

- Flipped `canvas`, `ink`, `body`, `mute`, `hairline` from the dark "mission control" values to a light paper/navy hierarchy.
- **Deepened every semantic status color** (live/amber/cyan/violet/rose, and the queued/ringing/completed/failed/busy/dnd state colors) — their original values were tuned for a dark background and would fail WCAG AA contrast as text on white (e.g. the original emerald green was ~2.5:1 on white; now ~4.9:1).
- Fixed the handful of spots that weren't token-driven: `index.html`/`index.css` hardcoded dark values, the chart tooltips in `DashboardView.tsx`, and the `sonner` toast library's own `theme="dark"` flag.
- Removed `NewCallView`'s now-redundant light-island wrapper, since the whole page around it is light now too.
- Verified all four tabs visually via full-page screenshots.

## 5. Current state — what's verified working right now

- 159/159 backend tests passing.
- Frontend builds and type-checks clean.
- Full login → campaign → telemetry → transcript loop verified in a real browser, both for individual and group recipients.
- The LLM fallback chain (Ollama → Groq → deterministic template) verified working under real failure conditions (neither configured).
- TRAI 9 AM–9 PM IST calling-window enforcement verified working live (Celery correctly deferred dispatch outside the window).
- Plivo telephony runs in its built-in sandbox mode (fake `mock_...` call UUIDs) since no real Plivo account is configured — by design, so none of this testing has placed a real, billed phone call.

## 6. Known gaps — not fixed this session, worth tracking

| Gap | Where |
|---|---|
| Local TTS (IndicF5) is still an empty stub | `backend/ai_pipeline/tts.py` |
| No Plivo webhook signature verification, despite `AGENTS.md` mandating it | `backend/telephony/webhook_handler.py` |
| Campaign filter mismatch: frontend can send multiple semesters, backend only matches one | `backend/scheduler/campaign_runner.py` |
| No CSV student-import endpoint (student data only exists via direct DB insert) | — |
| "Transfer" / "Hangup" buttons in Live Telemetry are UI-only, no backend endpoint | `frontend/src/components/LiveTelemetryView.tsx` |
| MinIO referenced in `.env.example`/docs but never wired into the actual stack | — |
| No CI pipeline, no frontend test suite | — |
| Not yet deployed to the real Nirma HPC node / institutional domain | — |
| No real Plivo/Sarvam/Groq credentials or downloaded model weights | — |

## 7. How to run it locally

```bash
cd nirma-ai-call-agent
docker compose up -d postgres redis
python -m backend.seeds            # creates tables, seeds admin + call script templates
uvicorn backend.main:app --port 8000 &
celery -A backend.scheduler.celery_app worker --pool=solo &   # --pool=solo needed on macOS/py3.14
celery -A backend.scheduler.celery_app beat &
cd frontend && npm install && npm run dev
```

Open `http://localhost:3000`, sign in with `admin@nirmauni.ac.in` / `Admin@Nirma2026` (from `backend/seeds.py`).

## 8. Setting up real Plivo telephony (summary — see chat for full detail)

1. Create a Plivo account, get an Auth ID/Token, rent an Indian DID number.
2. **India TRAI DLT registration is required** before bulk/automated voice calling to Indian numbers is legal — a paperwork step on the university's side, not a code change.
3. Put real credentials in `.env` (`PLIVO_AUTH_ID`, `PLIVO_AUTH_TOKEN`, `PLIVO_CALLER_ID`) — `PlivoAdapter` automatically stops faking calls once these look real.
4. Plivo's webhooks need a **publicly reachable** `BASE_URL` — `localhost` doesn't work. Use `ngrok` for local testing; the real Nirma domain once deployed.
5. Before testing with real credentials, edit the hardcoded test number in `scripts/verify_credentials.py` to your own phone — as shipped it dials a placeholder number.
