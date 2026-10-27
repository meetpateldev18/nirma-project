/**
 * Conversational Transcript Component.
 *
 * Renders turn-by-turn spoken dialogue between the Nirma Calling Assistant
 * and the student recipient, with latency benchmarks, carrier speech bubbles,
 * role-specific avatars, live transcribing indicator, and clipboard export.
 *
 * Used uniformly across Live Telemetry and Historical Transcripts views.
 */

import React, { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import { 
  Bot, 
  User, 
  Copy, 
  Check, 
  Clock, 
  Phone 
} from 'lucide-react';
import { toast } from 'sonner';

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { type CallLog } from '@/services/api';
import { type SystemStatus } from '@/lib/api-client';

export interface ConversationalTranscriptProps {
  /** Call log data containing transcript turns and provider telemetry */
  activeLog: CallLog | null;
  /** Whether transcript turn logs are currently being fetched */
  isLoadingLog?: boolean;
  /** Full student name for the human caller speech bubbles */
  studentName?: string;
  /** Whether the call is actively in-flight (enables live pulse indicator and auto-scroll) */
  isLive?: boolean;
  /** Telemetry system status for displaying active STT/LLM engine names */
  systemStatus?: SystemStatus | null;
  /** Optional custom CSS classes for the card container */
  className?: string;
  /** Max height Tailwind class for the scrollable turns container */
  maxHeightClass?: string;
  /** Custom empty state message */
  emptyMessage?: string;
}

export const ConversationalTranscript: React.FC<ConversationalTranscriptProps> = React.memo(({
  activeLog,
  isLoadingLog = false,
  studentName = 'Student',
  isLive = false,
  systemStatus,
  className = '',
  maxHeightClass = 'max-h-[460px]',
  emptyMessage,
}) => {
  const [copied, setCopied] = useState(false);
  const turnsEndRef = useRef<HTMLDivElement>(null);

  // Filter out system prompt turns if any were captured in history
  const spokenTurns = useMemo(() => {
    if (!activeLog || !Array.isArray(activeLog.transcript)) return [];
    return activeLog.transcript.filter((turn) => turn.role === 'assistant' || turn.role === 'user');
  }, [activeLog?.transcript]);

  const handleCopyTranscript = useCallback(() => {
    if (spokenTurns.length === 0) return;
    const formatted = spokenTurns
      .map((t) => {
        const speaker = t.role === 'assistant' ? 'Nirma Calling Assistant' : studentName;
        const time = t.timestamp ? `[${t.timestamp}] ` : '';
        const latency = t.latency_ms ? ` (${t.latency_ms}ms)` : '';
        const text = t.text || (t as any).content || '';
        return `${time}${speaker}${latency}:\n${text}`;
      })
      .join('\n\n');

    navigator.clipboard.writeText(formatted);
    setCopied(true);
    toast.success('Transcript copied to clipboard');
    setTimeout(() => setCopied(false), 2000);
  }, [spokenTurns, studentName]);

  // Smooth auto-scroll to the latest turn as speech streams in during live calls
  useEffect(() => {
    if (isLive && turnsEndRef.current) {
      turnsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [spokenTurns.length, isLive]);

  const hasTurns = spokenTurns.length > 0;

  return (
    <Card className={className}>
      <CardHeader className="p-4 sm:p-5 pb-3 border-b border-hairline flex flex-row items-center justify-between">
        <div>
          <CardTitle className="text-sm font-bold text-ink">Conversational Transcript</CardTitle>
          <CardDescription className="text-xs text-body">
            Turn-by-turn spoken dialogue with latency benchmarks
          </CardDescription>
        </div>
        {hasTurns && (
          <Button
            variant="outline"
            size="sm"
            onClick={handleCopyTranscript}
            className="h-8 rounded-full px-3 text-xs"
          >
            {copied ? <Check className="w-3.5 h-3.5 mr-1 text-live-pulse" /> : <Copy className="w-3.5 h-3.5 mr-1" />}
            {copied ? 'Copied' : 'Copy All'}
          </Button>
        )}
      </CardHeader>

      <CardContent className={`p-4 sm:p-5 space-y-4 ${maxHeightClass} overflow-y-auto`}>
        {isLoadingLog && (
          <div className="flex items-center justify-center p-8 text-xs text-mute font-mono">
            <Clock className="w-4 h-4 mr-2 animate-spin" />
            {isLive ? 'Fetching live speech transcript turn logs...' : 'Loading conversational turns from backend database...'}
          </div>
        )}

        {!isLoadingLog && !hasTurns && (
          <div className="p-8 text-center text-xs text-mute font-mono space-y-2">
            <Phone className="w-6 h-6 mx-auto text-mute/50" />
            <p>{emptyMessage || 'No spoken turns recorded for this call session.'}</p>
            <p className="text-[11px] text-mute/70">
              {isLive
                ? 'Call is connecting or awaiting caller speech. Utterances will appear live.'
                : 'The call may have ended before connection or without speech exchanged.'}
            </p>
          </div>
        )}

        {spokenTurns.map((turn, index) => {
          const isAssistant = turn.role === 'assistant';
          const text = turn.text || (turn as any).content || '';

          return (
            <div
              key={index}
              className={`flex gap-3 ${isAssistant ? 'flex-row' : 'flex-row-reverse'}`}
            >
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-xs shrink-0 ${
                  isAssistant
                    ? 'bg-primary/10 text-primary'
                    : 'bg-canvas-elevated text-ink'
                }`}
              >
                {isAssistant ? <Bot className="w-4 h-4" /> : <User className="w-4 h-4" />}
              </div>

              <div className={`max-w-[80%] space-y-1 ${isAssistant ? 'text-left' : 'text-right'}`}>
                <div
                  className={`flex items-center gap-1.5 text-[10px] font-mono text-mute px-1 ${
                    isAssistant ? 'justify-start' : 'justify-end'
                  }`}
                >
                  {isAssistant ? (
                    <>
                      <span className="font-semibold text-body">Nirma Calling Assistant</span>
                      {turn.timestamp && (
                        <>
                          <span>•</span>
                          <span className="tabular-nums">{turn.timestamp}</span>
                        </>
                      )}
                      {turn.latency_ms && (
                        <span className="text-live-pulse font-semibold tabular-nums">
                          [{turn.latency_ms}ms]
                        </span>
                      )}
                    </>
                  ) : (
                    <>
                      {turn.latency_ms && (
                        <span className="text-live-pulse font-semibold tabular-nums">
                          [{turn.latency_ms}ms]
                        </span>
                      )}
                      {turn.timestamp && (
                        <>
                          <span className="tabular-nums">{turn.timestamp}</span>
                          <span>•</span>
                        </>
                      )}
                      <span className="font-semibold text-body">{studentName}</span>
                    </>
                  )}
                </div>

                <div
                  className={`p-3.5 rounded-2xl text-xs sm:text-sm leading-relaxed border shadow-xs text-left ${
                    isAssistant
                      ? 'bg-primary/5 border-primary/20 text-ink rounded-tl-sm'
                      : 'bg-white border-hairline text-ink rounded-tr-sm'
                  }`}
                >
                  {text}
                </div>
              </div>
            </div>
          );
        })}

        {isLive && (
          <div className="flex items-center gap-2 text-xs text-telemetry-cyan font-mono pt-2" role="status">
            <span className="w-2 h-2 rounded-full bg-telemetry-cyan animate-ping" />
            <span>Transcribing live speech stream via {systemStatus?.stt_label || 'IndicConformer (0.6B)'}...</span>
          </div>
        )}
        <div ref={turnsEndRef} />
      </CardContent>
    </Card>
  );
});

ConversationalTranscript.displayName = 'ConversationalTranscript';
export default ConversationalTranscript;
