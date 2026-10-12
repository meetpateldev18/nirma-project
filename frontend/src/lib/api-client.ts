/**
 * Backend API Client — REST & WebSocket Transport Layer.
 *
 * Thin fetch wrapper around the FastAPI backend (backend/api/*, backend/websocket/manager.py).
 * Handles JWT bearer attachment, single-flight access-token refresh on 401, and mapping of
 * backend Pydantic response shapes onto the frontend's display-oriented DTOs (services/api.ts).
 *
 * In dev, requests go through the Vite proxy (vite.config.ts) at relative paths so no base
 * URL or CORS configuration is needed; in production these are served from the same origin
 * behind Nginx (docker/nginx), matching the `/api/`, `/auth/`, `/ws/` routing already defined there.
 */

import type { CallCampaign, CallLog, CallScript, CallTask, DailyVolume, DashboardSummary, OutcomeDistribution } from '@/services/api';

const TOKEN_STORAGE_KEY = 'nirma_auth_tokens';

export interface StoredTokens {
  access_token: string;
  refresh_token: string;
  role: 'admin' | 'operator';
  name: string;
}

export function loadStoredTokens(): StoredTokens | null {
  try {
    const raw = localStorage.getItem(TOKEN_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredTokens) : null;
  } catch {
    return null;
  }
}

function saveStoredTokens(tokens: StoredTokens | null) {
  try {
    if (tokens) {
      localStorage.setItem(TOKEN_STORAGE_KEY, JSON.stringify(tokens));
    } else {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
    }
  } catch {
    // Private browsing / storage disabled — session simply won't persist across reloads.
  }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

let refreshInFlight: Promise<boolean> | null = null;

/** Attempts a single token refresh using the stored refresh token. Returns true on success. */
async function tryRefresh(): Promise<boolean> {
  const tokens = loadStoredTokens();
  if (!tokens?.refresh_token) return false;

  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const res = await fetch('/auth/refresh', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: tokens.refresh_token }),
        });
        if (!res.ok) return false;
        const data = await res.json();
        saveStoredTokens({
          access_token: data.access_token,
          refresh_token: data.refresh_token,
          role: data.role,
          name: data.name,
        });
        return true;
      } catch {
        return false;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

async function request<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const tokens = loadStoredTokens();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> | undefined),
  };
  if (tokens?.access_token) {
    headers.Authorization = `Bearer ${tokens.access_token}`;
  }

  const res = await fetch(path, { ...options, headers });

  if (res.status === 401 && retry && tokens?.refresh_token) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      return request<T>(path, options, false);
    }
    saveStoredTokens(null);
    throw new ApiError(401, 'Session expired. Please sign in again.');
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // Non-JSON error body; fall back to statusText.
    }
    throw new ApiError(res.status, typeof detail === 'string' ? detail : JSON.stringify(detail));
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ==============================================================================
// Authentication
// ==============================================================================
export async function login(email: string, password: string): Promise<StoredTokens> {
  const res = await fetch('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    let detail = 'Invalid email or password';
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      // ignore
    }
    throw new ApiError(res.status, detail);
  }
  const data = await res.json();
  const tokens: StoredTokens = {
    access_token: data.access_token,
    refresh_token: data.refresh_token,
    role: data.role,
    name: data.name,
  };
  saveStoredTokens(tokens);
  return tokens;
}

export function logout(): void {
  saveStoredTokens(null);
}

// ==============================================================================
// Response → UI DTO mappers
// ==============================================================================
interface BackendCampaign {
  id: number;
  name: string;
  script_id: number;
  target_filter: Record<string, any>;
  scheduled_at: string;
  max_retries: number;
  retry_delay_min: number;
  status: string;
  task_counts?: Record<string, number> | null;
}

function mapCampaign(c: BackendCampaign): CallCampaign {
  const counts = c.task_counts || {};
  const total = Object.values(counts).reduce((sum, n) => sum + n, 0);
  return {
    id: c.id,
    name: c.name,
    script_id: c.script_id,
    target_filter: c.target_filter,
    scheduled_at: c.scheduled_at,
    max_retries: c.max_retries,
    retry_delay_min: c.retry_delay_min,
    status: c.status as CallCampaign['status'],
    total_tasks: total,
    completed_tasks: counts.completed || 0,
    failed_tasks: (counts.failed || 0) + (counts.cancelled || 0),
  };
}

interface BackendCampaignTask {
  id: number;
  campaign_id: number;
  student_id: number;
  student_name: string;
  student_roll: string;
  student_phone: string;
  script_id: number;
  status: string;
  plivo_uuid: string | null;
  retry_count: number;
  duration_sec: number | null;
  outcome: string | null;
  placed_at: string | null;
}

function mapTask(t: BackendCampaignTask): CallTask {
  return {
    id: t.id,
    campaign_id: t.campaign_id,
    student_id: t.student_id,
    student_name: t.student_name,
    student_roll: t.student_roll,
    student_phone: t.student_phone,
    script_id: t.script_id,
    status: t.status as CallTask['status'],
    plivo_uuid: t.plivo_uuid || undefined,
    retry_count: t.retry_count,
    duration_sec: t.duration_sec ?? undefined,
    outcome: t.outcome || undefined,
    placed_at: t.placed_at || undefined,
  };
}

interface BackendTranscript {
  task_id: number;
  stt_provider: string | null;
  llm_provider: string | null;
  tts_provider: string | null;
  avg_latency_ms: number | null;
  transcript: Array<{ role: string; text: string; timestamp?: string; latency_ms?: number }>;
}

function mapTranscript(t: BackendTranscript): CallLog {
  return {
    id: t.task_id,
    task_id: t.task_id,
    stt_provider: t.stt_provider || 'unknown',
    llm_provider: t.llm_provider || 'unknown',
    tts_provider: t.tts_provider || 'unknown',
    avg_latency_ms: t.avg_latency_ms || 0,
    max_latency_ms: t.avg_latency_ms || 0,
    transcript: t.transcript.map((turn) => ({
      role: turn.role as 'assistant' | 'user' | 'system',
      text: turn.text,
      timestamp: turn.timestamp,
      latency_ms: turn.latency_ms,
    })),
  };
}

// ==============================================================================
// Campaigns & Scripts
// ==============================================================================
export async function listCampaigns(): Promise<CallCampaign[]> {
  const data = await request<{ items: BackendCampaign[] }>('/api/campaigns?limit=100');
  return data.items.map(mapCampaign);
}

export interface CreateCampaignPayload {
  name: string;
  script_id: number;
  target_filter: Record<string, any>;
  scheduled_at: string;
  max_retries: number;
  retry_delay_min: number;
}

export async function createCampaign(payload: CreateCampaignPayload): Promise<{ campaign: CallCampaign; tasksGenerated: number }> {
  const data = await request<BackendCampaign>('/api/campaigns', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return { campaign: mapCampaign(data), tasksGenerated: data.task_counts?.total ?? 0 };
}

export interface GeneratedScript {
  opening_message: string;
  system_prompt: string;
  used_document: boolean;
}

/** Writes a topic-locked call script from a free-text reason (and optional document), via the LLM. */
export async function generateScript(reason: string, language: string, document?: File | null): Promise<GeneratedScript> {
  const tokens = loadStoredTokens();
  const form = new FormData();
  form.append('reason', reason);
  form.append('language', language);
  if (document) form.append('document', document);

  const res = await fetch('/api/campaigns/generate-script', {
    method: 'POST',
    headers: tokens?.access_token ? { Authorization: `Bearer ${tokens.access_token}` } : {},
    body: form,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      // ignore
    }
    throw new ApiError(res.status, typeof detail === 'string' ? detail : 'Could not generate a call script.');
  }
  return res.json();
}

export interface CreateScriptPayload {
  name: string;
  language: string;
  opening_message: string;
  system_prompt: string;
  category?: string;
}

/** Persists a (typically just-generated) call script as a reusable CallScript row. */
export async function createScript(payload: CreateScriptPayload): Promise<CallScript> {
  return request<CallScript>('/api/campaigns/scripts', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export interface StudentSearchResult {
  id: number;
  name: string;
  roll_number: string;
  phone: string;
  department: string | null;
  semester: number | null;
}

/** Searches active students by name, roll number, or phone — for the "call one person" flow. */
export async function searchStudents(query: string): Promise<StudentSearchResult[]> {
  if (query.trim().length < 2) return [];
  return request<StudentSearchResult[]>(`/api/students/search?q=${encodeURIComponent(query.trim())}`);
}

export async function listScripts(): Promise<CallScript[]> {
  const data = await request<Array<{ id: number; name: string; category: string; language: string; system_prompt: string; opening_message: string }>>(
    '/api/campaigns/scripts'
  );
  return data;
}

export async function listCampaignTasks(campaignId: number): Promise<CallTask[]> {
  const data = await request<{ items: BackendCampaignTask[] }>(`/api/campaigns/${campaignId}/tasks?limit=200`);
  return data.items.map(mapTask);
}

// ==============================================================================
// Calls & Transcripts
// ==============================================================================
export async function getCallTranscript(taskId: number): Promise<CallLog | null> {
  try {
    const data = await request<BackendTranscript>(`/api/calls/${taskId}/transcript`);
    return mapTranscript(data);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

export async function retryCallTask(taskId: number): Promise<void> {
  await request(`/api/calls/${taskId}/retry`, { method: 'POST' });
}

// ==============================================================================
// Analytics
// ==============================================================================
export async function getDashboardSummary(): Promise<DashboardSummary> {
  return request<DashboardSummary>('/api/analytics/dashboard');
}

export async function getDailyVolume(days = 7): Promise<DailyVolume[]> {
  return request<DailyVolume[]>(`/api/analytics/volume?days=${days}`);
}

export async function getOutcomeDistribution(): Promise<OutcomeDistribution> {
  return request<OutcomeDistribution>('/api/analytics/outcomes');
}

// ==============================================================================
// Real-time WebSocket
// ==============================================================================
export interface CallEventEnvelope {
  event: string;
  timestamp: string;
  data: Record<string, any>;
}

/** Opens the authenticated live telemetry socket at /ws/calls. Caller owns the returned socket's lifecycle. */
export function connectCallEvents(onEvent: (envelope: CallEventEnvelope) => void): WebSocket | null {
  const tokens = loadStoredTokens();
  if (!tokens?.access_token) return null;

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const socket = new WebSocket(`${protocol}//${window.location.host}/ws/calls?token=${encodeURIComponent(tokens.access_token)}`);

  socket.onmessage = (ev) => {
    try {
      onEvent(JSON.parse(ev.data));
    } catch {
      // Ignore malformed frames (e.g. keep-alive pings echoed as text).
    }
  };

  return socket;
}
