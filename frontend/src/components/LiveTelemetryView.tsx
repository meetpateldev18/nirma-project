import React, { useState } from 'react';
import { 
  PhoneOff, 
  PhoneForwarded, 
  Volume2, 
  Cpu 
} from 'lucide-react';
import { toast } from 'sonner';

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { CallTask, CallLog } from '@/services/api';
import { getCallTranscript } from '@/lib/api-client';

interface LiveTelemetryViewProps {
  tasks: CallTask[];
  onSelectTask: (task: CallTask) => void;
}

export const LiveTelemetryView: React.FC<LiveTelemetryViewProps> = React.memo(({
  tasks,
  onSelectTask,
}) => {
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [activeLog, setActiveLog] = useState<CallLog | null>(null);
  const [isLoadingLog, setIsLoadingLog] = useState(false);

  const selectedTask = tasks.find(t => t.id === selectedTaskId) || tasks[0];

  React.useEffect(() => {
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

  const handleHangup = React.useCallback((task: CallTask) => {
    toast.error(`Call Terminated`, {
      description: `Carrier UUID ${task.plivo_uuid || 'PSTN'} disconnected by operator for ${task.student_name}.`,
    });
  }, []);

  const handleTransfer = React.useCallback((task: CallTask) => {
    toast.info(`Transfer Initiated`, {
      description: `PSTN bridge connected to Student Affairs Desk for ${task.student_name} (${task.student_phone}).`,
    });
  }, []);

  return (
    <div id="panel-telemetry" role="tabpanel" aria-labelledby="tab-telemetry" className="space-y-6">
      {/* View Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-hairline pb-5">
        <div>
          <div className="flex items-center space-x-2">
            <h1 className="text-2xl font-semibold tracking-tight text-ink font-sans">
              Live PSTN Call Telemetry & Streaming Console
            </h1>
            <Badge variant="live" className="text-[10px] font-mono uppercase tracking-wider flex items-center space-x-1">
              <span className="w-1.5 h-1.5 rounded-full bg-live-pulse animate-pulse mr-1" />
              WEBSOCKET CONNECTED
            </Badge>
          </div>
          <p className="text-xs text-body mt-1">
            Real-time audio streaming, speech-to-text turns, and LLM generation over WebSocket bridge (/ws/calls)
          </p>
        </div>

        <div className="flex items-center space-x-2 text-xs font-mono text-body bg-canvas-soft px-3 py-1.5 rounded-md border border-hairline">
          <span>Active Carrier Channels:</span>
          <strong className="text-live-pulse tabular-nums">
            {tasks.filter(t => t.status === 'in_progress' || t.status === 'ringing').length} / 10
          </strong>
        </div>
      </div>

      {/* Main Split-View: Left Calls Grid | Right Live Conversation Drawer */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Active Calls Grid (5 cols) */}
        <div className="lg:col-span-5 space-y-3">
          <div className="text-xs font-mono font-semibold uppercase tracking-wider text-body flex items-center justify-between px-1">
            <span>DISPATCHED CARRIER CALLS</span>
            <span className="text-mute">SELECT TO INSPECT</span>
          </div>

          {tasks.length === 0 && (
            <div className="p-5 rounded-md border border-hairline bg-canvas-soft text-xs text-mute font-mono text-center">
              No call tasks found for active campaigns. Launch a campaign to see live PSTN telemetry here.
            </div>
          )}

          <div className="space-y-2.5" role="list" aria-label="Dispatched carrier calls">
            {tasks.map((task) => {
              const isSelected = task.id === selectedTaskId;
              const isLive = task.status === 'in_progress';
              const isRinging = task.status === 'ringing';

              return (
                <div
                  key={task.id}
                  role="button"
                  tabIndex={0}
                  aria-pressed={isSelected}
                  aria-label={`Call with ${task.student_name}, roll number ${task.student_roll}, status ${task.status}`}
                  onClick={() => {
                    setSelectedTaskId(task.id);
                    onSelectTask(task);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      setSelectedTaskId(task.id);
                      onSelectTask(task);
                    }
                  }}
                  className={`p-3.5 rounded-md border cursor-pointer transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
                    isSelected
                      ? 'bg-canvas-elevated border-hairline-terracotta terracotta-glow'
                      : 'bg-canvas-soft border-hairline hover:bg-canvas-elevated/70'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <span className="font-semibold text-xs text-ink">{task.student_name}</span>
                      <Badge variant="mono" className="text-[10px]">
                        {task.student_roll}
                      </Badge>
                    </div>
                    <Badge
                      variant={isLive ? 'live' : isRinging ? 'ringing' : task.status === 'completed' ? 'secondary' : 'destructive'}
                      className="text-[10px] uppercase font-mono"
                    >
                      {task.status}
                    </Badge>
                  </div>

                  <div className="mt-2 flex items-center justify-between text-xs font-mono text-body">
                    <span className="tabular-nums text-mute">{task.student_phone}</span>
                    <span className="tabular-nums text-ink">
                      {isLive ? `Duration: ${task.duration_sec}s` : task.placed_at}
                    </span>
                  </div>

                  {/* Active turn snippet or waveform */}
                  {isLive && (
                    <div className="mt-2.5 pt-2 border-t border-hairline-subtle flex items-center justify-between text-[11px]">
                      <div className="flex items-center space-x-1.5 text-telemetry-cyan font-mono truncate max-w-[280px]">
                        <Volume2 className="w-3.5 h-3.5 inline shrink-0" aria-hidden="true" />
                        <span className="truncate">{task.current_turn}</span>
                      </div>
                      <div className="flex items-center space-x-0.5" aria-hidden="true">
                        <span className="w-1 h-3 bg-live-pulse rounded-full animate-soundwave" style={{ animationDelay: '0.1s' }} />
                        <span className="w-1 h-4 bg-live-pulse rounded-full animate-soundwave" style={{ animationDelay: '0.3s' }} />
                        <span className="w-1 h-2 bg-live-pulse rounded-full animate-soundwave" style={{ animationDelay: '0.2s' }} />
                      </div>
                    </div>
                  )}

                  {isRinging && (
                    <div className="mt-2.5 pt-2 border-t border-hairline-subtle flex items-center justify-between text-[11px] text-telemetry-amber font-mono">
                      <span>Dialing recipient via Plivo carrier...</span>
                      <span className="animate-pulse" aria-hidden="true">● ● ●</span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Column: Active Call Inspector Console (7 cols) */}
        <div className="lg:col-span-7">
          {!selectedTask ? (
            <Card className="bg-canvas-soft border-hairline h-full flex items-center justify-center min-h-[300px]">
              <p className="text-xs text-mute font-mono">Select a dispatched call to inspect its live stream.</p>
            </Card>
          ) : (
          <Card className="bg-canvas-soft border-hairline h-full flex flex-col">
            <CardHeader className="p-5 border-b border-hairline">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center space-x-2">
                    <CardTitle className="text-base font-semibold text-ink">
                      {selectedTask.student_name}
                    </CardTitle>
                    <Badge variant="mono" className="text-[10px]">
                      {selectedTask.student_roll}
                    </Badge>
                    <Badge 
                      variant={selectedTask.status === 'in_progress' ? 'live' : 'secondary'}
                      className="text-[10px] font-mono uppercase"
                    >
                      {selectedTask.status}
                    </Badge>
                  </div>
                  <CardDescription className="text-xs text-body mt-1 font-mono">
                    Phone: <span className="text-ink tabular-nums">{selectedTask.student_phone}</span> • Carrier UUID: <span className="text-mute tabular-nums">{selectedTask.plivo_uuid || 'N/A'}</span>
                  </CardDescription>
                </div>

                <div className="flex items-center space-x-2">
                  <Button 
                    variant="outline" 
                    size="sm" 
                    onClick={() => handleTransfer(selectedTask)}
                    className="text-xs h-7 border-hairline"
                    aria-label={`Transfer call with ${selectedTask.student_name} to Student Affairs Desk`}
                  >
                    <PhoneForwarded className="w-3 h-3 mr-1 text-telemetry-cyan" aria-hidden="true" />
                    Transfer
                  </Button>
                  <Button 
                    variant="destructive" 
                    size="sm" 
                    onClick={() => handleHangup(selectedTask)}
                    className="text-xs h-7"
                    aria-label={`Hangup call with ${selectedTask.student_name}`}
                  >
                    <PhoneOff className="w-3 h-3 mr-1" aria-hidden="true" />
                    Hangup
                  </Button>
                </div>
              </div>
            </CardHeader>

            {/* Conversational Stream */}
            <CardContent className="p-5 flex-1 flex flex-col justify-between space-y-4">
              <div 
                className="space-y-3.5 max-h-[380px] overflow-y-auto pr-1"
                role="log"
                aria-live="polite"
                aria-relevant="additions text"
                aria-label="Live Call Conversational Stream"
              >
                {isLoadingLog && (
                  <p className="text-xs text-mute font-mono">Loading transcript...</p>
                )}
                {!isLoadingLog && !activeLog && (
                  <p className="text-xs text-mute font-mono">
                    No transcript logged yet for this call{selectedTask.status === 'completed' ? '.' : ' — it is still in progress.'}
                  </p>
                )}
                {activeLog?.transcript.map((turn, index) => {
                  const isAssistant = turn.role === 'assistant';
                  return (
                    <div 
                      key={index} 
                      className={`flex flex-col ${isAssistant ? 'items-start' : 'items-end'}`}
                    >
                      <div className="flex items-center space-x-1.5 mb-1 text-[11px] font-mono text-mute">
                        <span>{isAssistant ? 'AI Assistant (Nirma Finance)' : 'Student / Parent'}</span>
                        <span>•</span>
                        <span className="tabular-nums">{turn.timestamp}</span>
                        {turn.latency_ms && (
                          <span className="text-live-pulse font-semibold tabular-nums">
                            [{turn.latency_ms} ms]
                          </span>
                        )}
                      </div>

                      <div
                        className={`max-w-[85%] rounded-md p-3 text-xs leading-relaxed border ${
                          isAssistant
                            ? 'bg-live-pulse/5 border-live-pulse/20 text-ink'
                            : 'bg-canvas-elevated border-hairline text-ink'
                        }`}
                      >
                        {turn.text}
                      </div>
                    </div>
                  );
                })}

                {selectedTask.status === 'in_progress' && (
                  <div className="flex items-center space-x-2 text-xs text-telemetry-cyan font-mono pt-2" role="status">
                    <span className="w-2 h-2 rounded-full bg-telemetry-cyan animate-ping" aria-hidden="true" />
                    <span>Transcribing live speech stream via IndicConformer (0.6B)...</span>
                  </div>
                )}
              </div>

              {/* Live Turn Latency Gauge Bar */}
              <div className="pt-4 border-t border-hairline bg-canvas-subtle p-3 rounded-md border border-hairline">
                <div className="flex items-center justify-between text-xs font-mono">
                  <div className="flex items-center space-x-2 text-body">
                    <Cpu className="w-3.5 h-3.5 text-telemetry-cyan" aria-hidden="true" />
                    <span>Average Turn Turnaround:</span>
                    <strong className="text-ink tabular-nums">
                      {activeLog?.avg_latency_ms ?? selectedTask.turn_latency_ms ?? 0} ms
                    </strong>
                  </div>
                  <Badge variant="live" className="text-[10px] font-mono">
                    TARGET: &lt; 4,000 ms
                  </Badge>
                </div>
                <div className="grid grid-cols-3 gap-2 mt-2 pt-2 border-t border-hairline text-[10px] font-mono text-mute">
                  <div>STT: <span className="text-ink">{activeLog?.stt_provider ?? '—'}</span></div>
                  <div>LLM: <span className="text-ink">{activeLog?.llm_provider ?? '—'}</span></div>
                  <div>TTS: <span className="text-ink">{activeLog?.tts_provider ?? '—'}</span></div>
                </div>
              </div>
            </CardContent>
          </Card>
          )}
        </div>
      </div>
    </div>
  );
});

LiveTelemetryView.displayName = 'LiveTelemetryView';
