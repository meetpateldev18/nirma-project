import React, { useState } from 'react';
import { 
  Search, 
  Play, 
  Pause, 
  RotateCcw, 
  Volume2, 
  User, 
  Bot
} from 'lucide-react';
import { toast } from 'sonner';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { 
  Table, 
  TableBody, 
  TableCell, 
  TableHead, 
  TableHeader, 
  TableRow 
} from '@/components/ui/table';
import { type CallTask, CallLog } from '@/services/api';
import { getCallTranscript, retryCallTask } from '@/lib/api-client';

interface TranscriptViewProps {
  tasks: CallTask[];
  onTaskRetried: () => void;
}

export const TranscriptView: React.FC<TranscriptViewProps> = React.memo(({ tasks, onTaskRetried }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1);
  const [activeLog, setActiveLog] = useState<CallLog | null>(null);
  const [isLoadingLog, setIsLoadingLog] = useState(false);

  const filteredTasks = React.useMemo(() => {
    const term = searchTerm.toLowerCase().trim();
    if (!term) return tasks;
    return tasks.filter(task =>
      task.student_name.toLowerCase().includes(term) ||
      task.student_roll.toLowerCase().includes(term) ||
      task.student_phone.includes(term)
    );
  }, [tasks, searchTerm]);

  const selectedTask = React.useMemo(() => {
    return tasks.find(t => t.id === selectedTaskId) || tasks[0];
  }, [tasks, selectedTaskId]);

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

  const togglePlayAudio = React.useCallback(() => {
    if (!selectedTask) return;
    setIsPlaying(prev => {
      const nextState = !prev;
      if (nextState) {
        toast.info(`Playing call recording for ${selectedTask.student_name}`, {
          description: `Source: audio archive (${selectedTask.duration_sec ?? 0}s connected duration)`
        });
      }
      return nextState;
    });
  }, [selectedTask]);

  const handleManualRetry = React.useCallback((task: CallTask) => {
    toast.promise(retryCallTask(task.id), {
      loading: `Queueing manual PSTN retry for ${task.student_phone}...`,
      success: () => {
        onTaskRetried();
        return `Call task #${task.id} reset to pending. Carrier dial dispatched.`;
      },
      error: (err) => (err instanceof Error ? err.message : 'Failed to reset task'),
    });
  }, [onTaskRetried]);

  return (
    <div id="panel-transcripts" role="tabpanel" aria-labelledby="tab-transcripts" className="space-y-6">
      {/* View Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-hairline pb-5">
        <div>
          <div className="flex items-center space-x-2">
            <h1 className="text-2xl font-semibold tracking-tight text-ink font-sans">
              Conversation Transcripts & Audio Inspector
            </h1>
            <Badge variant="mono" className="text-[10px]">
              AUDIT COMPLIANT
            </Badge>
          </div>
          <p className="text-xs text-body mt-1">
            Review multi-turn speech transcripts, provider attribution, and conversational latencies for all completed calls
          </p>
        </div>

        {/* Search Input */}
        <div className="relative w-full sm:w-72">
          <label htmlFor="transcript-search-input" className="sr-only">
            Search call archive by student name, roll number, or phone number
          </label>
          <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-mute" aria-hidden="true" />
          <Input 
            id="transcript-search-input"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search roll, name, or phone..."
            className="pl-9 bg-canvas-soft border-hairline text-xs"
          />
        </div>
      </div>

      {/* Main Grid: Left Tasks Table (5 cols) | Right Transcript & Audio Console (7 cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Call Records Table */}
        <div className="lg:col-span-5">
          <Card className="bg-canvas-soft border-hairline overflow-hidden">
            <CardHeader className="p-4 border-b border-hairline">
              <div className="flex items-center justify-between">
                <CardTitle className="text-xs font-mono font-semibold uppercase tracking-wider text-body">
                  CALL LOG ARCHIVE
                </CardTitle>
                <Badge variant="mono" className="text-[10px] tabular-nums">
                  {filteredTasks.length} Records
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <caption className="sr-only">Historical Outbound Call Logs Archive</caption>
                <TableHeader>
                  <TableRow>
                    <TableHead scope="col">STUDENT</TableHead>
                    <TableHead scope="col">STATUS</TableHead>
                    <TableHead scope="col" className="text-right">DURATION</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredTasks.map((task) => {
                    const isSelected = task.id === selectedTaskId;
                    return (
                      <TableRow 
                        key={task.id}
                        tabIndex={0}
                        role="button"
                        aria-pressed={isSelected}
                        aria-label={`Select call log for ${task.student_name}, roll ${task.student_roll}`}
                        onClick={() => setSelectedTaskId(task.id)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            setSelectedTaskId(task.id);
                          }
                        }}
                        className={`cursor-pointer transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
                          isSelected 
                            ? 'bg-canvas-elevated border-l-2 border-l-primary' 
                            : 'hover:bg-canvas-elevated/40'
                        }`}
                      >
                        <TableCell className="py-3">
                          <div className="font-semibold text-xs text-ink">{task.student_name}</div>
                          <div className="text-[11px] font-mono text-mute tabular-nums">{task.student_roll} • {task.student_phone}</div>
                        </TableCell>
                        <TableCell className="py-3">
                          <Badge 
                            variant={
                              task.status === 'completed' ? 'secondary' : 
                              task.status === 'in_progress' ? 'live' : 
                              task.status === 'ringing' ? 'ringing' : 'destructive'
                            }
                            className="text-[10px] font-mono uppercase"
                          >
                            {task.outcome || task.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs tabular-nums text-ink py-3">
                          {task.duration_sec ? `${task.duration_sec}s` : '0s'}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </div>

        {/* Right Column: Audio Player & Turn-by-Turn Transcript */}
        <div className="lg:col-span-7 space-y-5">
          {!selectedTask ? (
            <Card className="bg-canvas-soft border-hairline flex items-center justify-center min-h-[300px]">
              <p className="text-xs text-mute font-mono">No call records yet. Launch a campaign to generate call logs.</p>
            </Card>
          ) : (
          <>
          {/* Audio Player Card */}
          <Card className="bg-canvas-elevated border-hairline-strong shadow-lg">
            <CardContent className="p-5 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-semibold text-ink">{selectedTask.student_name}</div>
                  <div className="text-xs text-mute font-mono">
                    Call Record #{selectedTask.id} • Plivo UUID: {selectedTask.plivo_uuid}
                  </div>
                </div>

                {selectedTask.status === 'failed' && (
                  <Button 
                    variant="outline" 
                    size="sm"
                    onClick={() => handleManualRetry(selectedTask)}
                    className="border-primary/40 text-primary hover:bg-primary/10 text-xs h-7"
                  >
                    <RotateCcw className="w-3 h-3 mr-1" />
                    Retry Call
                  </Button>
                )}
              </div>

              {/* Waveform & Timeline Slider */}
              <div className="p-3.5 rounded-md bg-canvas-soft border border-hairline space-y-3">
                <div className="flex items-center justify-between text-xs font-mono text-mute">
                  <div className="flex items-center space-x-1.5 text-ink">
                    <Volume2 className="w-3.5 h-3.5 text-primary" />
                    <span>Carrier Audio Track (8kHz mono)</span>
                  </div>
                  <div className="tabular-nums">
                    00:00 / 00:{String(selectedTask.duration_sec ?? 0).padStart(2, '0')}
                  </div>
                </div>

                {/* Animated Waveform Visualization */}
                <div className="h-8 flex items-center justify-between space-x-1 px-1">
                  {Array.from({ length: 36 }).map((_, i) => {
                    const heights = [6, 12, 18, 24, 10, 16, 28, 20, 8, 14, 22, 16, 26, 12, 18, 8];
                    const height = heights[i % heights.length];
                    const isPassed = i < 14;
                    return (
                      <div 
                        key={i} 
                        className={`w-1 rounded-full transition-all ${
                          isPassed ? 'bg-primary' : 'bg-canvas-elevated'
                        }`} 
                        style={{ height: `${height}px` }} 
                      />
                    );
                  })}
                </div>

                {/* Audio Controls */}
                <div className="flex items-center justify-between pt-1">
                  <div className="flex items-center space-x-2">
                    <Button 
                      variant="default" 
                      size="sm" 
                      onClick={togglePlayAudio}
                      aria-label={isPlaying ? "Pause call recording" : "Play call recording"}
                      className="h-8 px-3 rounded-full bg-primary"
                    >
                      {isPlaying ? <Pause className="w-3.5 h-3.5 mr-1" aria-hidden="true" /> : <Play className="w-3.5 h-3.5 mr-1" aria-hidden="true" />}
                      <span>{isPlaying ? 'Pause' : 'Play Audio'}</span>
                    </Button>
                  </div>

                  <div className="flex items-center space-x-1" role="group" aria-label="Audio Playback Speed">
                    {[1, 1.25, 1.5].map((speed) => (
                      <button
                        key={speed}
                        type="button"
                        aria-pressed={playbackSpeed === speed}
                        aria-label={`${speed}x speed`}
                        onClick={() => setPlaybackSpeed(speed)}
                        className={`px-2 py-0.5 rounded text-[10px] font-mono border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
                          playbackSpeed === speed 
                            ? 'bg-primary text-white border-primary shadow-sm' 
                            : 'bg-canvas-elevated text-mute border-hairline hover:text-ink'
                        }`}
                      >
                        {speed}x
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* AI Engine Attribution Card */}
              <div className="grid grid-cols-3 gap-2.5 p-3 rounded-md bg-canvas-soft border border-hairline text-xs font-mono">
                <div>
                  <div className="text-[10px] text-mute uppercase">STT Engine</div>
                  <div className="text-ink font-semibold truncate">{activeLog?.stt_provider ?? '—'}</div>
                </div>
                <div>
                  <div className="text-[10px] text-mute uppercase">LLM Engine</div>
                  <div className="text-ink font-semibold truncate">{activeLog?.llm_provider ?? '—'}</div>
                </div>
                <div>
                  <div className="text-[10px] text-mute uppercase">TTS Engine</div>
                  <div className="text-ink font-semibold truncate">{activeLog?.tts_provider ?? '—'}</div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Full Turn Dialogue Bubble Stream */}
          <Card className="bg-canvas-soft border-hairline">
            <CardHeader className="p-4 border-b border-hairline">
              <div className="flex items-center justify-between">
                <CardTitle className="text-xs font-mono font-semibold uppercase tracking-wider text-body">
                  FULL MULTI-TURN TRANSCRIPT
                </CardTitle>
                <span className="text-xs font-mono text-mute">
                  Average Turn Latency: <strong className="text-live-pulse tabular-nums">{activeLog?.avg_latency_ms ?? 0} ms</strong>
                </span>
              </div>
            </CardHeader>
            <CardContent className="p-5 space-y-4 max-h-[420px] overflow-y-auto" role="log" aria-label="Conversation turn-by-turn dialogue history">
              {isLoadingLog && <p className="text-xs text-mute font-mono">Loading transcript...</p>}
              {!isLoadingLog && !activeLog && (
                <p className="text-xs text-mute font-mono">No transcript recorded for this call.</p>
              )}
              {activeLog?.transcript.map((turn, index) => {
                const isAssistant = turn.role === 'assistant';
                return (
                  <div 
                    key={index} 
                    className={`flex flex-col ${isAssistant ? 'items-start' : 'items-end'}`}
                  >
                    <div className="flex items-center space-x-1.5 mb-1 text-[11px] font-mono text-mute">
                      <span className="flex items-center space-x-1 text-ink font-medium">
                        {isAssistant ? (
                          <>
                            <Bot className="w-3 h-3 text-primary inline" aria-hidden="true" />
                            <span>AI Caller (Nirma University)</span>
                          </>
                        ) : (
                          <>
                            <User className="w-3 h-3 text-telemetry-cyan inline" aria-hidden="true" />
                            <span>Recipient Speech</span>
                          </>
                        )}
                      </span>
                      <span>•</span>
                      <span className="tabular-nums">{turn.timestamp}</span>
                      {turn.latency_ms && (
                        <span className="text-live-pulse font-semibold tabular-nums">
                          [{turn.latency_ms} ms turnaround]
                        </span>
                      )}
                    </div>

                    <div
                      className={`max-w-[85%] rounded-md p-3.5 text-xs leading-relaxed border ${
                        isAssistant
                          ? 'bg-live-pulse/5 border-live-pulse/20 text-ink shadow-sm'
                          : 'bg-canvas-elevated border-hairline text-ink'
                      }`}
                    >
                      {turn.text}
                    </div>
                  </div>
                );
              })}
            </CardContent>
          </Card>
          </>
          )}
        </div>
      </div>
    </div>
  );
});

TranscriptView.displayName = 'TranscriptView';
