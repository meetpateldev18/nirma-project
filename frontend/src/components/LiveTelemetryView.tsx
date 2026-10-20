/**
 * Unified Live Telemetry & Conversational Transcripts View.
 *
 * Combines real-time PSTN carrier channel monitoring (10 concurrent channels),
 * live voice turn streaming, active call supervision (Transfer Desk, Hang Up),
 * interactive audio playback, re-dial dispatching, and turn-by-turn conversational
 * transcripts into a single mission-control interface.
 */

import React, { useState, useMemo, useCallback, useEffect } from 'react';
import {
  PhoneOff,
  PhoneForwarded,
  Volume2,
  Cpu,
  Radio,
  Search,
  ShieldCheck,
  RotateCcw,
  Play,
  Pause,
  VolumeX,
  FileText,
  ArrowLeft,
  Copy,
  CheckCircle2,
  AlertCircle,
  Phone,
  Server,
  Clock
} from 'lucide-react';
import { toast } from 'sonner';

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { CallTask, CallLog } from '@/services/api';
import { useAuth } from '@/lib/auth-context';
import {
  getCallTranscript,
  hangupCall,
  transferCall,
  retryCallTask,
  connectCallEvents,
  SystemStatus
} from '@/lib/api-client';
import { ConversationalTranscript } from '@/components/ConversationalTranscript';
import {
  CALL_STATUS_FILTERS,
  getCallStatusLabel,
  getCallStatusBadgeVariant
} from '@/lib/call-status';

interface LiveTelemetryViewProps {
  tasks: CallTask[];
  onSelectTask?: (task: CallTask) => void;
  onTaskRetried?: () => void;
  systemStatus?: SystemStatus | null;
}

const initialsOf = (name: string) =>
  name.split(' ').map((p) => p[0]).filter(Boolean).slice(0, 2).join('').toUpperCase() || 'ST';

const formatDateTimeIST = (isoStr?: string | null): string => {
  if (!isoStr) return 'N/A';
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return isoStr;
    return d.toLocaleString('en-IN', {
      timeZone: 'Asia/Kolkata',
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
    });
  } catch {
    return isoStr;
  }
};

const formatTimeIST = (isoStr?: string | null): string => {
  if (!isoStr) return '';
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return '';
    return d.toLocaleTimeString('en-IN', {
      timeZone: 'Asia/Kolkata',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    });
  } catch {
    return '';
  }
};

export const LiveTelemetryView: React.FC<LiveTelemetryViewProps> = React.memo(({
  tasks,
  onSelectTask,
  onTaskRetried,
  systemStatus,
}) => {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';

  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [activeLog, setActiveLog] = useState<CallLog | null>(null);
  const [isLoadingLog, setIsLoadingLog] = useState(false);
  const [isHangingUp, setIsHangingUp] = useState(false);
  const [isTransferring, setIsTransferring] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [currentTime, setCurrentTime] = useState<number>(Date.now());
  const [localTaskOverrides, setLocalTaskOverrides] = useState<Record<number, Partial<CallTask>>>({});

  // Audio recording player state (for completed calls)
  const [isPlaying, setIsPlaying] = useState(false);
  const [playProgressSec, setPlayProgressSec] = useState<number>(0);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1);

  // Ticking timer for real-time live duration counter
  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const mergedTasks = useMemo(() => {
    return tasks.map((t) => {
      const ov = localTaskOverrides[t.id];
      return ov ? { ...t, ...ov } : t;
    });
  }, [tasks, localTaskOverrides]);

  const selectedTask = useMemo(() => {
    if (selectedTaskId) {
      return mergedTasks.find((t) => t.id === selectedTaskId) || mergedTasks[0];
    }
    return mergedTasks[0];
  }, [mergedTasks, selectedTaskId]);

  const showDetailOnMobile = !!selectedTaskId;

  // Fetch full transcript whenever selected task changes
  useEffect(() => {
    if (!selectedTask) {
      setActiveLog(null);
      return;
    }
    let cancelled = false;
    setIsLoadingLog(true);
    getCallTranscript(selectedTask.id)
      .then((log) => { if (!cancelled) setActiveLog(log); })
      .catch(() => { if (!cancelled) setActiveLog(null); })
      .finally(() => { if (!cancelled) setIsLoadingLog(false); });
    return () => { cancelled = true; };
  }, [selectedTask?.id]);

  // Reset audio playback whenever selected task changes
  useEffect(() => {
    setIsPlaying(false);
    setPlayProgressSec(0);
  }, [selectedTask?.id]);

  // Real-time fail-safe poller for active calls (1.5s interval during in_progress/ringing)
  useEffect(() => {
    if (!selectedTask || (selectedTask.status !== 'in_progress' && selectedTask.status !== 'ringing')) {
      return;
    }
    const interval = setInterval(() => {
      getCallTranscript(selectedTask.id)
        .then((log) => {
          if (log) setActiveLog(log);
        })
        .catch(() => {});
    }, 1500);
    return () => clearInterval(interval);
  }, [selectedTask?.id, selectedTask?.status]);

  const duration = selectedTask?.duration_sec ?? 0;
  const mmss = `${Math.floor(duration / 60)}:${String(duration % 60).padStart(2, '0')}`;
  const progressMmss = `${Math.floor(playProgressSec / 60)}:${String(playProgressSec % 60).padStart(2, '0')}`;

  // Ticking timer for audio playback scrubber
  useEffect(() => {
    if (!isPlaying || !duration || duration <= 0) {
      return;
    }
    const interval = setInterval(() => {
      setPlayProgressSec((prev) => {
        if (prev + 1 >= duration) {
          setIsPlaying(false);
          return duration;
        }
        return prev + 1;
      });
    }, 1000 / playbackSpeed);
    return () => clearInterval(interval);
  }, [isPlaying, duration, playbackSpeed]);

  // Real-time live transcript and call event listener (Persistent WebSocket)
  useEffect(() => {
    const socket = connectCallEvents((envelope) => {
      if (envelope.event === 'transcript_turn') {
        const payload = envelope.data as any;
        if (payload?.task_id) {
          setActiveLog((prev) => {
            if (prev && prev.task_id !== payload.task_id) return prev;
            const existing = prev ? [...prev.transcript] : [];
            const timestamp = new Date().toLocaleTimeString('en-IN', { hour12: false });
            if (payload.user_transcript) {
              const last = existing[existing.length - 1];
              if (!last || last.role !== 'user' || (last.text !== payload.user_transcript && (last as any).content !== payload.user_transcript)) {
                existing.push({
                  role: 'user',
                  text: payload.user_transcript,
                  content: payload.user_transcript,
                  timestamp,
                } as any);
              }
            }
            if (payload.assistant_reply) {
              const last = existing[existing.length - 1];
              if (!last || last.role !== 'assistant' || (last.text !== payload.assistant_reply && (last as any).content !== payload.assistant_reply)) {
                existing.push({
                  role: 'assistant',
                  text: payload.assistant_reply,
                  content: payload.assistant_reply,
                  timestamp,
                  latency_ms: payload.latency_ms,
                } as any);
              }
            }
            return {
              id: prev?.id || 0,
              task_id: payload.task_id,
              transcript: existing,
              stt_provider: prev?.stt_provider || systemStatus?.stt_label || 'Twilio Gather',
              llm_provider: prev?.llm_provider || systemStatus?.llm_label || 'Groq Cloud',
              tts_provider: prev?.tts_provider || systemStatus?.tts_label || 'Google TTS',
              avg_latency_ms: payload.latency_ms || prev?.avg_latency_ms || 1500,
              max_latency_ms: Math.max(prev?.max_latency_ms || 0, payload.latency_ms || 0),
            };
          });

          // Immediately reflect latest audio exchange on the corresponding left task card
          setLocalTaskOverrides((prev) => ({
            ...prev,
            [payload.task_id]: {
              ...(prev[payload.task_id] || {}),
              current_turn: payload.assistant_reply || payload.user_transcript || prev[payload.task_id]?.current_turn,
              turn_latency_ms: payload.latency_ms ?? prev[payload.task_id]?.turn_latency_ms,
            },
          }));
        }
      } else if (envelope.event === 'call_status') {
        const payload = envelope.data as any;
        if (payload?.task_id) {
          // Immediately update task in local state for instantaneous 0ms visual feedback
          setLocalTaskOverrides((prev) => ({
            ...prev,
            [payload.task_id]: {
              ...(prev[payload.task_id] || {}),
              status: payload.status,
              duration_sec: payload.duration_sec ?? prev[payload.task_id]?.duration_sec,
              plivo_uuid: payload.call_uuid ?? prev[payload.task_id]?.plivo_uuid,
            },
          }));

          getCallTranscript(payload.task_id)
            .then((log) => {
              if (log) setActiveLog(log);
            })
            .catch(() => {});
        }
      }
    });

    return () => {
      socket?.close();
    };
  }, [systemStatus]);

  const handleHangup = useCallback(async (task: CallTask) => {
    setIsHangingUp(true);
    try {
      await hangupCall(task.id);
      toast.success('Call Terminated', {
        description: `Carrier Call ID ${task.plivo_uuid || 'PSTN'} disconnected for ${task.student_name}.`,
      });
    } catch (err: any) {
      toast.error('Hangup Failed', {
        description: err?.message || 'Could not disconnect the active call.',
      });
    } finally {
      setIsHangingUp(false);
    }
  }, []);

  const handleTransfer = useCallback(async (task: CallTask) => {
    setIsTransferring(true);
    try {
      await transferCall(task.id);
      toast.success('Transfer Connected', {
        description: `PSTN bridge connected to Student Help Desk for ${task.student_name} (${task.student_phone}).`,
      });
    } catch (err: any) {
      toast.error('Transfer Failed', {
        description: err?.message || 'Could not transfer the active call.',
      });
    } finally {
      setIsTransferring(false);
    }
  }, []);

  const handleManualRetry = useCallback((task: CallTask) => {
    setIsRetrying(true);
    toast.promise(
      retryCallTask(task.id)
        .then(() => {
          onTaskRetried?.();
        })
        .finally(() => {
          setIsRetrying(false);
        }),
      {
        loading: `Connecting carrier & re-dialing ${task.student_name}...`,
        success: `Outbound carrier re-dial initiated! Dialing ${task.student_phone}...`,
        error: (err) => (err instanceof Error ? err.message : 'Could not re-dial call'),
      }
    );
  }, [onTaskRetried]);

  const filteredTasks = useMemo(() => {
    const q = searchQuery.toLowerCase();
    return mergedTasks.filter((t) => {
      const matchesSearch =
        t.student_name.toLowerCase().includes(q) ||
        t.student_roll.toLowerCase().includes(q) ||
        t.student_phone.includes(searchQuery) ||
        (t.summary && t.summary.toLowerCase().includes(q)) ||
        (t.campaign_name && t.campaign_name.toLowerCase().includes(q)) ||
        (t.script_name && t.script_name.toLowerCase().includes(q));

      if (!matchesSearch) return false;
      if (statusFilter === 'all') return true;
      if (statusFilter === 'completed') return t.status === 'completed';
      if (statusFilter === 'failed') return t.status === 'failed' || t.status === 'busy' || t.status === 'no_answer' || t.status === 'cancelled';
      if (statusFilter === 'active') return t.status === 'in_progress' || t.status === 'ringing';
      return true;
    });
  }, [mergedTasks, searchQuery, statusFilter]);

  const activeChannelCount = mergedTasks.filter(t => t.status === 'in_progress' || t.status === 'ringing').length;

  return (
    <div id="panel-telemetry" role="tabpanel" aria-labelledby="tab-telemetry" className="space-y-6">
      {/* Split-View: Left Calls Feed (5 cols) | Right Live Stream & Transcripts Console (7 cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 min-h-[640px]">
        {/* Left Column: Dispatched Carrier Calls (5 cols) */}
        <div className={`lg:col-span-5 ${showDetailOnMobile ? 'hidden lg:block' : 'block'} space-y-4`}>
          <Card className="flex flex-col h-full">
            <CardHeader className="p-4 sm:p-5 pb-3 border-b border-hairline space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <CardTitle className="text-sm font-bold text-ink">Calls & Transcripts</CardTitle>
                  <Badge variant="live" className="text-[10px] font-mono">
                    {activeChannelCount} / 10 Channels
                  </Badge>
                </div>
                <Badge variant="mono" className="text-[10px]">
                  {filteredTasks.length} Calls
                </Badge>
              </div>

              {/* Search Bar */}
              <div className="relative">
                <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-mute" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search by student name, roll number, or phone..."
                  className="w-full pl-9 pr-3 h-8 rounded-lg border border-hairline-strong bg-white text-xs text-ink placeholder:text-mute focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
                />
              </div>

              {/* Status Filter Chips */}
              <div className="flex items-center gap-1.5 overflow-x-auto pb-0.5">
                {CALL_STATUS_FILTERS.map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    onClick={() => setStatusFilter(f.id)}
                    className={`text-[11px] font-medium px-2.5 py-1 rounded-full whitespace-nowrap transition-colors ${statusFilter === f.id
                        ? 'bg-primary text-white shadow-xs'
                        : 'bg-canvas-elevated hover:bg-canvas-elevated/80 text-body border border-hairline'
                      }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </CardHeader>

            <CardContent className="p-3 max-h-[640px] overflow-y-auto space-y-2">
              {filteredTasks.length === 0 ? (
                <div className="p-8 text-center text-xs text-mute font-mono">
                  No matching calls found. Launch a campaign or adjust search criteria.
                </div>
              ) : (
                filteredTasks.map((task) => {
                  const isSelected = task.id === selectedTask?.id;
                  const isLive = task.status === 'in_progress';
                  const isRinging = task.status === 'ringing';

                  return (
                    <div
                      key={task.id}
                      role="button"
                      tabIndex={0}
                      aria-pressed={isSelected}
                      onClick={() => {
                        setSelectedTaskId(task.id);
                        onSelectTask?.(task);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          setSelectedTaskId(task.id);
                          onSelectTask?.(task);
                        }
                      }}
                      className={`p-3.5 rounded-xl border cursor-pointer transition-all ${isSelected
                          ? 'bg-primary/5 border-primary shadow-xs'
                          : 'bg-white border-hairline hover:bg-canvas-elevated/60'
                        }`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2.5 min-w-0">
                          <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold shrink-0 ${task.status === 'completed'
                              ? 'bg-live-pulse/10 text-live-pulse'
                              : isLive
                                ? 'bg-live-pulse text-white'
                                : isRinging
                                  ? 'bg-telemetry-amber text-white'
                                  : task.status === 'failed' || task.status === 'busy'
                                    ? 'bg-state-failed/10 text-state-failed'
                                    : 'bg-canvas-elevated text-body'
                            }`}>
                            {initialsOf(task.student_name)}
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="text-xs font-semibold text-ink line-clamp-1">{task.student_name}</div>
                            <div className="text-[10px] text-mute font-mono truncate">
                              Roll: {task.student_roll}
                            </div>
                          </div>
                        </div>

                        <Badge
                          variant={getCallStatusBadgeVariant(task.status)}
                          className="text-[10px] font-mono uppercase shrink-0"
                        >
                          {isLive && <span className="w-1.5 h-1.5 rounded-full bg-live-pulse mr-1 animate-pulse" />}
                          {getCallStatusLabel(task.status)}
                        </Badge>
                      </div>

                      {/* Call Purpose / Reason Summary */}
                      {(task.summary || task.campaign_name || task.script_name) && (
                        <div className="mt-2 px-2.5 py-1.5 rounded-lg bg-canvas-subtle/80 border border-hairline-subtle flex items-start gap-1.5 text-[11px] text-body leading-snug">
                          <FileText className="w-3.5 h-3.5 text-primary shrink-0 mt-0.5" />
                          <span className="line-clamp-2 font-normal text-ink/90">
                            {task.summary || task.campaign_name || task.script_name}
                          </span>
                        </div>
                      )}

                      <div className="mt-2.5 pt-2 border-t border-hairline-subtle flex items-center justify-between text-[11px] font-mono">
                        <span className="text-mute tabular-nums flex items-center gap-1">
                          <Phone className="w-3 h-3 text-mute/70 shrink-0" />
                          <span>{task.student_phone}</span>
                        </span>
                        <span className="text-ink font-medium tabular-nums">
                          {isLive
                            ? `Duration: ${task.duration_sec ?? (task.answered_at ? Math.max(0, Math.floor((currentTime - new Date(task.answered_at).getTime()) / 1000)) : 0)}s`
                            : (task.duration_sec ? `${task.duration_sec}s` : (formatTimeIST(task.placed_at) || 'Queued'))}
                        </span>
                      </div>

                      {/* Active turn equalizer simulation */}
                      {isLive && (
                        <div className="mt-2 pt-2 border-t border-hairline-subtle flex items-center justify-between text-[11px]">
                          <span className="text-telemetry-cyan font-mono truncate max-w-[200px] flex items-center gap-1">
                            <Volume2 className="w-3.5 h-3.5 shrink-0" />
                            <span className="truncate">{task.current_turn || 'Streaming audio...'}</span>
                          </span>
                          <div className="flex items-center gap-0.5">
                            <span className="w-1 h-3 bg-live-pulse rounded-full animate-soundwave" style={{ animationDelay: '0.1s' }} />
                            <span className="w-1 h-4 bg-live-pulse rounded-full animate-soundwave" style={{ animationDelay: '0.3s' }} />
                            <span className="w-1 h-2 bg-live-pulse rounded-full animate-soundwave" style={{ animationDelay: '0.2s' }} />
                          </div>
                        </div>
                      )}

                      {isRinging && (
                        <div className="mt-2 pt-2 border-t border-hairline-subtle flex items-center justify-between text-[11px] text-telemetry-amber font-mono">
                          <span>Connecting to telecom carrier...</span>
                          <span className="animate-pulse">● ● ●</span>
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right Column: Live Call Inspector & Transcript Console (7 cols) */}
        <div className={`lg:col-span-7 ${showDetailOnMobile ? 'block' : 'hidden lg:block'} space-y-4`}>
          {!selectedTask ? (
            <Card className="h-full flex flex-col items-center justify-center p-8 text-center min-h-[460px]">
              <Radio className="w-10 h-10 text-mute/50 mb-3" />
              <h3 className="text-sm font-semibold text-ink">No Call Record Selected</h3>
              <p className="text-xs text-mute font-mono mt-1 max-w-sm">
                Select a call from the left directory to monitor live telemetry, inspect audio playback, and read conversational transcripts.
              </p>
            </Card>
          ) : (
            <div className="space-y-4">
              {/* Call Control & Metadata Banner Card */}
              <Card>
                <CardHeader className="p-4 sm:p-5 border-b border-hairline">
                  {showDetailOnMobile && (
                    <button
                      type="button"
                      onClick={() => setSelectedTaskId(null)}
                      className="lg:hidden mb-3 inline-flex items-center gap-1.5 text-xs text-primary font-semibold"
                    >
                      <ArrowLeft className="w-3.5 h-3.5" /> Back to call directory
                    </button>
                  )}

                  <div className="flex flex-col xl:flex-row xl:items-start justify-between gap-4">
                    {/* Student Identity Block */}
                    <div className="flex items-start gap-3.5 min-w-0 flex-1">
                      <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-primary/15 to-primary/5 text-primary border border-primary/20 flex items-center justify-center font-bold text-base shrink-0 shadow-xs">
                        {initialsOf(selectedTask.student_name)}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <h2 className="text-base sm:text-lg font-bold text-ink tracking-tight">
                            {selectedTask.student_name}
                          </h2>
                          <Badge variant="mono" className="text-xs px-2 py-0.5">
                            {selectedTask.student_roll}
                          </Badge>
                          <Badge
                            variant={getCallStatusBadgeVariant(selectedTask.status)}
                            className="text-xs font-mono uppercase px-2.5 py-0.5"
                          >
                            {selectedTask.status === 'in_progress' && (
                              <span className="w-1.5 h-1.5 rounded-full bg-live-pulse mr-1.5 animate-pulse" />
                            )}
                            {getCallStatusLabel(selectedTask.status)}
                          </Badge>
                        </div>

                        {/* Clean Sub-header Metadata Strip - Wrap-friendly, Never Truncated */}
                        <div className="flex flex-wrap items-center gap-y-1.5 gap-x-3 text-xs font-mono text-body mt-2 pt-1 border-t border-hairline/60">
                          <span className="flex items-center gap-1.5 text-ink font-medium">
                            <Phone className="w-3.5 h-3.5 text-mute" />
                            <span className="tabular-nums">{selectedTask.student_phone}</span>
                          </span>
                          {/* <span className="text-hairline-strong">•</span>
                          <span className="flex items-center gap-1.5 text-mute">
                            <Server className="w-3.5 h-3.5 text-mute" />
                            <span>{systemStatus?.pstn_label || (selectedTask.plivo_uuid?.startsWith('CA') ? 'Twilio Voice Gateway' : 'Carrier PSTN')}</span>
                          </span> */}
                          {selectedTask.placed_at && (
                            <>
                              <span className="text-hairline-strong">•</span>
                              <span className="flex items-center gap-1.5 text-mute" title={selectedTask.placed_at}>
                                <Clock className="w-3.5 h-3.5 text-mute" />
                                <span className="tabular-nums">
                                  Placed: {formatDateTimeIST(selectedTask.placed_at)}
                                </span>
                              </span>
                            </>
                          )}
                        </div>

                        {/* Call Purpose / Reason Summary */}
                        {(selectedTask.summary || selectedTask.campaign_name || selectedTask.script_name) && (
                          <div className="mt-2.5 px-3 py-1.5 rounded-lg bg-canvas-subtle/80 border border-hairline-subtle flex items-center gap-2 text-xs text-body">
                            <FileText className="w-3.5 h-3.5 text-primary shrink-0" />
                            <span className="text-mute font-mono text-[10px] uppercase tracking-wider shrink-0">Purpose:</span>
                            <span className="font-medium text-ink truncate">
                              {selectedTask.summary || selectedTask.campaign_name || selectedTask.script_name}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Operational Control Buttons / Call Disposition Badge */}
                    <div className="flex items-center gap-2 shrink-0 self-start xl:self-center">
                      {selectedTask.status === 'in_progress' ? (
                        <>
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={isTransferring}
                            onClick={() => handleTransfer(selectedTask)}
                            className="h-8 rounded-full px-3.5 text-xs font-medium border-hairline hover:bg-canvas-elevated"
                          >
                            <PhoneForwarded className="w-3.5 h-3.5 mr-1.5 text-telemetry-cyan" />
                            {isTransferring ? 'Transferring...' : 'Transfer Desk'}
                          </Button>
                          <Button
                            variant="destructive"
                            size="sm"
                            disabled={isHangingUp}
                            onClick={() => handleHangup(selectedTask)}
                            className="h-8 rounded-full px-3.5 text-xs font-medium"
                          >
                            <PhoneOff className="w-3.5 h-3.5 mr-1.5" />
                            {isHangingUp ? 'Hanging up...' : 'Hang Up'}
                          </Button>
                        </>
                      ) : selectedTask.status === 'ringing' ? (
                        <Button
                          variant="destructive"
                          size="sm"
                          disabled={isHangingUp}
                          onClick={() => handleHangup(selectedTask)}
                          className="h-8 rounded-full px-3.5 text-xs font-medium"
                        >
                          <PhoneOff className="w-3.5 h-3.5 mr-1.5" />
                          Cancel Call
                        </Button>
                      ) : (
                        <div className="flex flex-wrap items-center gap-2">
                          {isAdmin && (
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={isRetrying}
                              onClick={() => handleManualRetry(selectedTask)}
                              className="h-8 rounded-full px-3.5 text-xs font-medium border-primary/30 hover:border-primary hover:bg-primary/5 text-ink shadow-xs disabled:opacity-50"
                            >
                              <RotateCcw className={`w-3.5 h-3.5 mr-1.5 text-primary ${isRetrying ? 'animate-spin' : ''}`} />
                              {isRetrying ? 'Dialing...' : 'Re-dial Call'}
                            </Button>
                          )}
                          {selectedTask.status === 'completed' && (
                            <Badge variant="outline" className="h-8 rounded-full px-3 text-xs font-mono text-emerald-700 bg-emerald-50 border-emerald-200 flex items-center gap-1.5">
                              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                              <span>Resolved • {selectedTask.duration_sec ?? 0}s</span>
                            </Badge>
                          )}
                          {selectedTask.status === 'pending' && (
                            <Badge variant="outline" className="h-8 rounded-full px-3 text-xs font-mono text-amber-700 bg-amber-50 border-amber-200 flex items-center gap-1.5">
                              <Clock className="w-3.5 h-3.5 text-amber-600 animate-spin" />
                              <span>Queued for Dialing</span>
                            </Badge>
                          )}
                          {(selectedTask.status === 'failed' || selectedTask.status === 'busy' || selectedTask.status === 'no_answer') && (
                            <Badge variant="outline" className="h-8 rounded-full px-3 text-xs font-mono text-rose-700 bg-rose-50 border-rose-200 flex items-center gap-1.5">
                              <AlertCircle className="w-3.5 h-3.5 text-rose-600" />
                              <span>{getCallStatusLabel(selectedTask.status)}</span>
                            </Badge>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </CardHeader>

                {/* Telemetry Summary: 3 Metrics Cards + Full-Width Carrier UUID Panel */}
                <CardContent className="p-4 sm:p-5 space-y-3 bg-canvas-elevated/40 text-xs font-mono border-t border-hairline">
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    {/* 1. Call Duration */}
                    <div className="p-3.5 rounded-xl bg-white border border-hairline shadow-xs">
                      <div className="flex items-center justify-between text-mute text-[10px] uppercase tracking-wider mb-1 font-semibold">
                        <span>Call Duration</span>
                        <Clock className="w-3.5 h-3.5 text-mute" />
                      </div>
                      <div className="text-base font-bold text-ink tabular-nums">
                        {selectedTask.status === 'in_progress'
                          ? `${selectedTask.duration_sec ?? (selectedTask.answered_at ? Math.max(0, Math.floor((currentTime - new Date(selectedTask.answered_at).getTime()) / 1000)) : 0)}s (Live)`
                          : mmss}
                      </div>
                      <div className="text-[10px] text-mute mt-0.5 tabular-nums">
                        {selectedTask.duration_sec ? `${selectedTask.duration_sec}s total elapsed` : '0 seconds'}
                      </div>
                    </div>

                    {/* 2. Dial Attempts */}
                    <div className="p-3.5 rounded-xl bg-white border border-hairline shadow-xs">
                      <div className="flex items-center justify-between text-mute text-[10px] uppercase tracking-wider mb-1 font-semibold">
                        <span>Dial Attempts</span>
                        <RotateCcw className="w-3.5 h-3.5 text-mute" />
                      </div>
                      <div className="text-base font-bold text-ink tabular-nums">
                        Attempt #{(selectedTask.retry_count ?? 0) + 1}
                      </div>
                      <div className="text-[10px] text-mute mt-0.5">
                        {(selectedTask.retry_count ?? 0) === 0 ? (
                          'Initial call • 0 retries'
                        ) : (selectedTask.retry_count ?? 0) <= 2 ? (
                          `${selectedTask.retry_count} / 2 auto-retries used`
                        ) : (
                          <span className="text-telemetry-amber font-semibold">
                            {selectedTask.retry_count} retries • Manual override
                          </span>
                        )}
                      </div>
                    </div>

                    {/* 3. STT ASR Engine */}
                    <div className="p-3.5 rounded-xl bg-white border border-hairline shadow-xs">
                      <div className="flex items-center justify-between text-mute text-[10px] uppercase tracking-wider mb-1 font-semibold">
                        <span>STT ASR Engine</span>
                        <Volume2 className="w-3.5 h-3.5 text-mute" />
                      </div>
                      <div className="text-base font-bold text-ink truncate" title={activeLog?.stt_provider ?? 'twilio_gather'}>
                        {activeLog?.stt_provider ?? (selectedTask.plivo_uuid?.startsWith('CA') ? 'twilio_gather' : 'indic_conformer')}
                      </div>
                      <div className="text-[10px] text-mute mt-0.5">
                        Speech recognition pipeline
                      </div>
                    </div>
                  </div>

                  {/* Dedicated Full-Width Carrier UUID / SID Panel — 100% VISIBLE, NO TRUNCATION */}
                  <div className="p-3.5 rounded-xl bg-white border border-hairline shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="text-[10px] text-mute uppercase tracking-wider font-semibold mb-1 flex items-center gap-1.5">
                        <Server className="w-3 h-3 text-mute" />
                        <span>Carrier Telephony SID / UUID</span>
                      </div>
                      <div className="font-mono text-xs sm:text-sm font-bold text-ink break-all select-all tracking-wide">
                        {selectedTask.plivo_uuid || 'PSTN-Local-Carrier-Pending'}
                      </div>
                    </div>
                    {selectedTask.plivo_uuid && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          navigator.clipboard.writeText(selectedTask.plivo_uuid || '');
                          toast.success('Carrier UUID copied to clipboard');
                        }}
                        className="h-8 rounded-full px-3 text-xs shrink-0 border-hairline hover:bg-canvas-elevated flex items-center gap-1.5 self-start sm:self-center"
                      >
                        <Copy className="w-3.5 h-3.5 text-mute" />
                        <span>Copy UUID</span>
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>

              {/* Audio Deck: Live Waveform Equalizer when live, or Interactive Audio Playback when completed */}
              {selectedTask.status === 'in_progress' ? (
                <Card>
                  <CardContent className="p-4 sm:p-5 flex items-center justify-between border border-live-pulse/20 bg-live-pulse/5 rounded-xl">
                    <div className="flex items-center gap-2 text-xs font-mono text-live-pulse">
                      <Volume2 className="w-4 h-4 animate-pulse" />
                      <span>Live {systemStatus?.audio_codec || '16kHz PCM Carrier Stream'}</span>
                    </div>
                    <div className="flex items-center gap-1">
                      {[6, 12, 18, 10, 16, 22, 14, 8, 20, 12, 16, 10, 24, 18, 14, 8].map((h, i) => (
                        <span
                          key={i}
                          className="w-1 bg-live-pulse rounded-full animate-soundwave"
                          style={{
                            height: `${h}px`,
                            animationDelay: `${(i * 0.1) % 0.8}s`,
                          }}
                        />
                      ))}
                    </div>
                  </CardContent>
                </Card>
              ) : duration === 0 ? (
                <Card>
                  <CardContent className="p-4 sm:p-5 flex items-center gap-3 text-xs font-mono text-mute bg-canvas-elevated/40">
                    <VolumeX className="w-4 h-4 text-mute shrink-0" />
                    <span>No audio recording available for this call session (Call Duration: 0:00).</span>
                  </CardContent>
                </Card>
              ) : (
                <Card className="overflow-hidden">
                  <CardContent className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div className="flex items-center gap-3.5 w-full sm:w-auto flex-1">
                      <button
                        type="button"
                        onClick={() => {
                          setIsPlaying((p) => !p);
                          toast.info(isPlaying ? 'Audio playback paused' : 'Playing synthesized carrier audio stream');
                        }}
                        aria-label={isPlaying ? 'Pause audio' : 'Play audio'}
                        className="w-11 h-11 rounded-full bg-primary hover:bg-primary-hover text-white flex items-center justify-center shrink-0 shadow-sm transition-transform active:scale-95 cursor-pointer"
                      >
                        {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
                      </button>
                      <div className="flex-1 min-w-[200px]">
                        <div
                          onClick={(e) => {
                            if (duration <= 0) return;
                            const rect = e.currentTarget.getBoundingClientRect();
                            const clickX = e.clientX - rect.left;
                            const pct = Math.max(0, Math.min(1, clickX / rect.width));
                            setPlayProgressSec(Math.round(pct * duration));
                          }}
                          className="h-2.5 rounded-full bg-canvas-elevated overflow-hidden border border-hairline relative cursor-pointer group"
                        >
                          <div
                            className="h-full bg-primary rounded-full transition-all duration-150"
                            style={{ width: `${duration > 0 ? (playProgressSec / duration) * 100 : 0}%` }}
                          />
                        </div>
                        <div className="flex justify-between text-xs text-mute font-mono mt-1.5 tabular-nums">
                          <span className="font-semibold text-ink">{progressMmss}</span>
                          <span className="text-mute">{mmss}</span>
                        </div>
                      </div>
                    </div>

                    {/* Playback speed selector */}
                    <div className="flex items-center gap-1.5 shrink-0 self-end sm:self-center">
                      {[1, 1.25, 1.5].map((spd) => (
                        <button
                          key={spd}
                          type="button"
                          onClick={() => setPlaybackSpeed(spd)}
                          className={`px-3 py-1 rounded-full text-xs font-mono font-medium transition-colors cursor-pointer ${playbackSpeed === spd
                              ? 'bg-primary text-white shadow-xs'
                              : 'bg-canvas-elevated text-body hover:text-ink border border-hairline'
                            }`}
                        >
                          {spd}x
                        </button>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Conversational Transcript Card */}
              <ConversationalTranscript
                activeLog={activeLog}
                isLoadingLog={isLoadingLog}
                studentName={selectedTask.student_name}
                isLive={selectedTask.status === 'in_progress'}
                systemStatus={systemStatus}
                maxHeightClass="max-h-[360px]"
              />

              {/* Turnaround Latency Health & Provider Telemetry Card */}
              <Card>
                <CardContent className="p-4 space-y-3">
                  <div className="p-3.5 rounded-xl bg-canvas-elevated border border-hairline flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs font-mono">
                    <div className="flex items-center gap-2 text-body">
                      <Cpu className="w-4 h-4 text-telemetry-cyan" />
                      <span>Average Turn Latency:</span>
                      <strong className="text-ink font-bold tabular-nums">
                        {activeLog?.avg_latency_ms ?? selectedTask.turn_latency_ms ?? 0} ms
                      </strong>
                    </div>
                    <Badge variant="live" className="text-[10px] font-mono">
                      Latency Budget &lt; 4,000 ms
                    </Badge>
                  </div>

                  {/* Pipeline Provider Chips */}
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-[11px] font-mono text-mute">
                    <div className="p-2 rounded-lg bg-canvas-elevated border border-hairline">
                      <span className="text-mute block text-[10px]">ASR (STT):</span>
                      <strong className="text-ink">{activeLog?.stt_provider ?? systemStatus?.stt_label ?? 'Sarvam AI'}</strong>
                    </div>
                    <div className="p-2 rounded-lg bg-canvas-elevated border border-hairline">
                      <span className="text-mute block text-[10px]">LLM:</span>
                      <strong className="text-ink">{activeLog?.llm_provider ?? systemStatus?.llm_label ?? 'Gemini Flash'}</strong>
                    </div>
                    <div className="p-2 rounded-lg bg-canvas-elevated border border-hairline">
                      <span className="text-mute block text-[10px]">TTS:</span>
                      <strong className="text-ink">{activeLog?.tts_provider ?? systemStatus?.tts_label ?? 'Gemini Flash Audio'}</strong>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </div>
      </div>
    </div>
  );
});

LiveTelemetryView.displayName = 'LiveTelemetryView';
export default LiveTelemetryView;
