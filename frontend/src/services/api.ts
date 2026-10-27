/**
 * API Service Client & Telemetry Data Contracts Module.
 *
 * This module defines the complete TypeScript interfaces, data transfer objects (DTOs),
 * and client-side initial seed fixtures for the Nirma Calling Assistant Web Portal.
 * It serves as the single source of truth for all telemetry metrics, campaign scheduling,
 * conversational transcript logging, and carrier task statuses consumed by the dashboard.
 *
 * Architectural Role:
 *     - Establishes strict data schemas mirroring backend Pydantic models (backend/database/models.py).
 *     - Provides resilient offline data fixtures for UI development and fallback when backend is disconnected.
 *     - Coordinates WebSocket telemetry contracts (/ws/calls) and REST endpoints (/api/v1/*).
 *
 * Upstream dependencies:
 *     - Backend FastAPI REST & WebSocket server (backend/main.py)
 * Downstream dependencies:
 *     - frontend/src/App.tsx
 *     - frontend/src/components/DashboardView.tsx
 *     - frontend/src/components/LiveTelemetryView.tsx
 *     - frontend/src/components/CampaignLauncherView.tsx
 *     - frontend/src/components/TranscriptView.tsx
 *
 * @packageDocumentation
 */

// ==============================================================================
// 1. Staff & Identity Schemas
// ==============================================================================

/**
 * Represents an authenticated Nirma University staff member or portal administrator.
 *
 * Roles determine authorization boundaries:
 *  - 'admin': Full clearance to launch, cancel campaigns, edit prompts, and trigger manual retries.
 *  - 'operator': Operational access to monitor live streaming calls and review historical transcripts.
 */
export interface StaffUser {
  /** Unique primary surrogate identifier from backend database. */
  id: number;
  /** Verified institutional email address (e.g., 'operator@nirmauni.ac.in'). */
  email: string;
  /** Full human name of the staff operator. */
  name: string;
  /** Role-based access control level. */
  role: 'admin' | 'operator';
}

// ==============================================================================
// 2. Call Script & Prompt Engineering Schemas
// ==============================================================================

/**
 * Predefined and verified telephony conversation template.
 *
 * Scripts encapsulate the opening spoken greeting and the system persona prompt
 * sent to the local LLM (Qwen-14B) or cloud fallback (Groq LLaMA-3.3-70B).
 */
export interface CallScript {
  /** Unique database identifier. */
  id: number;
  /** Human-readable script name (e.g., 'Semester Fee Payment Reminder (Hindi)'). */
  name: string;
  /** Categorical classification: 'fee_reminder', 'attendance_alert', 'exam_notice'. */
  category: string;
  /** ISO 639-1 language code ('hi' for Hindi, 'gu' for Gujarati, 'en' for English). */
  language: string;
  /**
   * System persona instructions injected into the LLM conversational context.
   * Mandates polite tone, institutional affiliation, and brevity (<35 words).
   */
  system_prompt: string;
  /**
   * First spoken greeting synthesized via TTS and played immediately upon recipient answer.
   * TRAI telecom compliance requires self-identification as an automated AI system in this turn.
   */
  opening_message: string;
}

// ==============================================================================
// 3. Campaign & Task Execution Schemas
// ==============================================================================

/**
 * Outbound batch campaign scheduled by university administrators.
 *
 * Represents an orchestrated sequence of phone calls generated against
 * a targeted student cohort filter (e.g., department, semester, attendance threshold).
 */
export interface CallCampaign {
  /** Unique campaign identifier. */
  id: number;
  /** Campaign title displayed across dashboard and reports. */
  name: string;
  /** Foreign key pointing to the active CallScript template. */
  script_id: number;
  /** JSON criteria used by the Celery dispatcher to select eligible student recipients. */
  target_filter: Record<string, any>;
  /** Target UTC timestamp when the Celery dispatcher begins placing carrier calls. */
  scheduled_at: string;
  /** Maximum number of retry attempts for unanswered or busy calls (default: 2). */
  max_retries: number;
  /** Waiting interval in minutes before triggering an unanswered call retry (default: 45m). */
  retry_delay_min: number;
  /** Real-time execution status of the campaign batch. */
  status: 'pending' | 'running' | 'completed' | 'cancelled';
  /** Total number of student phone calls scheduled in this batch. */
  total_tasks: number;
  /** Number of calls successfully completed and answered. */
  completed_tasks: number;
  /** Number of calls that failed or exhausted retry limits. */
  failed_tasks: number;
}

/**
 * Discrete outbound PSTN phone call placed to an individual student or guardian.
 *
 * Tracks carrier request UUIDs, real-time call states, timing milestones, and live turn snippets.
 */
export interface CallTask {
  /** Unique database task identifier. */
  id: number;
  /** Foreign key referencing the parent CallCampaign batch. */
  campaign_id: number;
  /** Foreign key referencing the student recipient profile. */
  student_id: number;
  /** Full student name from university ERP. */
  student_name: string;
  /** Unique university enrollment roll number (e.g., '22BCE045'). */
  student_roll: string;
  /** Target recipient phone number in E.164 international format (+91...). */
  student_phone: string;
  /** Script template identifier utilized for this call session. */
  script_id: number;
  /**
   * Real-time telephony state:
   *  - 'pending': Queued in Redis awaiting Celery rate limiter dispatch.
   *  - 'ringing': Carrier signaled outbound ringing on Indian PSTN network.
   *  - 'in_progress': Call answered; audio stream and turn processing active.
   *  - 'completed': Call terminated normally after conversation resolution.
   *  - 'failed': Call rejected, carrier timeout, or busy without answer.
   */
  status: 'pending' | 'ringing' | 'in_progress' | 'completed' | 'failed' | 'busy' | 'no_answer' | 'cancelled';
  /** Unique carrier request identifier assigned by telephony gateway (Plivo CallUUID / Twilio CallSid). */
  plivo_uuid?: string;
  /** Current retry attempt count for this specific recipient. */
  retry_count: number;
  /** Total connected conversational duration in seconds. */
  duration_sec?: number;
  /** Final carrier disposition: 'completed', 'no_answer', 'busy', 'failed'. */
  outcome?: string;
  /** Human-readable relative timestamp indicating when the call was dialed. */
  placed_at?: string;
  /** ISO timestamp when recipient answered the call. */
  answered_at?: string;
  /** Real-time conversational turn snippet streaming over WebSocket for active monitoring. */
  current_turn?: string;
  /** Turn turnaround latency in milliseconds for the latest exchange (<4,000ms SLA target). */
  turn_latency_ms?: number;
  /** Parent campaign title or topic summary. */
  campaign_name?: string;
  /** Script name or category. */
  script_name?: string;
  /** Brief summary or reason explaining what the call is about. */
  summary?: string;
}

// ==============================================================================
// 4. Conversation Transcript & Telemetry Schemas
// ==============================================================================

/**
 * Individual conversational dialogue turn between the AI agent and the human recipient.
 */
export interface TranscriptTurn {
  /** Turn speaker attribution: 'assistant' (AI agent) or 'user' (student/parent). */
  role: 'assistant' | 'user' | 'system';
  /** Clean textual transcript of the speech utterance. */
  text: string;
  /** Time of day when the utterance was logged (HH:MM:SS format). */
  timestamp?: string;
  /** Latency in milliseconds taken to process and synthesize this specific turn. */
  latency_ms?: number;
}

/**
 * Comprehensive historical audit record of a completed or failed phone call.
 *
 * Stores the full multi-turn transcript array, provider attribution tags,
 * turn turnaround latency metrics, and persistent MinIO/S3 audio recording URL.
 */
export interface CallLog {
  /** Unique database identifier. */
  id: number;
  /** Foreign key linking back to the originating CallTask. */
  task_id: number;
  /** Chronological array of conversational turns. */
  transcript: TranscriptTurn[];
  /** Name of speech recognition engine utilized ('IndicConformer (0.6B)' | 'Sarvam AI'). */
  stt_provider: string;
  /** Name of language model engine utilized ('Qwen-14B (Ollama Q4)' | 'Gemini Flash' | 'Groq Cloud'). */
  llm_provider: string;
  /** Name of speech synthesis engine utilized ('IndicF5 (Local)' | 'Google Cloud TTS'). */
  tts_provider: string;
  /** Mean turnaround latency across all turns in milliseconds. */
  avg_latency_ms: number;
  /** Peak turnaround latency observed in milliseconds. */
  max_latency_ms: number;
  /** Fully qualified HTTPS URL to the recorded carrier audio WAV file. */
  audio_url?: string;
}

// ==============================================================================
// 5. Analytical Dashboard KPI Schemas
// ==============================================================================

/**
 * Executive KPI summary metrics displayed on the primary mission control dashboard.
 */
export interface DashboardSummary {
  /** Cumulative count of all campaigns created. */
  total_campaigns: number;
  /** Count of campaigns currently in 'running' or 'pending' state. */
  active_campaigns: number;
  /** Total calls dialed across the system lifetime. */
  total_calls: number;
  /** Number of calls successfully connected and answered. */
  completed_calls: number;
  /** Number of calls that failed, timed out, or encountered carrier errors. */
  failed_calls: number;
  /** Percentage of dialed calls that connected successfully (e.g., 94.2%). */
  connection_rate_pct: number;
  /** Average duration in seconds of answered phone calls. */
  avg_duration_sec: number;
  /** Average end-to-end turn turnaround latency across all AI pipeline engines. */
  avg_turn_latency_ms: number;
}

/**
 * Time-series data point representing call volume grouped by calendar day.
 */
export interface DailyVolume {
  /** Formatted calendar date label (e.g., 'Oct 08'). */
  date: string;
  /** Total calls dialed on this date. */
  total_calls: number;
  /** Connected and answered calls on this date. */
  completed_calls: number;
  /** Unanswered or failed calls on this date. */
  failed_calls: number;
}

/**
 * Distribution breakdown of final carrier call outcomes.
 */
export interface OutcomeDistribution {
  /** Mapping of disposition keys ('completed', 'no_answer', 'busy', 'failed') to counts. */
  outcome_counts: Record<string, number>;
}

/**
 * Technical latency and provider distribution telemetry for engineering monitoring.
 */
export interface LatencyMetric {
  /** Turn counts grouped by speech recognition engine. */
  stt_provider_counts: Record<string, number>;
  /** Turn counts grouped by language model engine. */
  llm_provider_counts: Record<string, number>;
  /** Turn counts grouped by speech synthesis engine. */
  tts_provider_counts: Record<string, number>;
  /** System-wide average turn latency in milliseconds. */
  avg_latency_ms: number;
  /** System-wide peak turnaround latency logged in milliseconds. */
  max_latency_ms: number;
}
