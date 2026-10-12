import React, { useState } from 'react';
import { Search, Play, Pause, RotateCcw, Phone, Bot, User, ArrowLeft } from 'lucide-react';
import { toast } from 'sonner';

import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { type CallTask, CallLog } from '@/services/api';
import { useAuth } from '@/lib/auth-context';
import { getCallTranscript, retryCallTask } from '@/lib/api-client';

interface TranscriptViewProps {
  tasks: CallTask[];
  onTaskRetried: () => void;
}

const initialsOf = (name: string) =>
  name.split(' ').map((p) => p[0]).filter(Boolean).slice(0, 2).join('').toUpperCase() || '?';

const AVATAR_TONES = ['bg-rose-100 text-rose-700', 'bg-amber-100 text-amber-700', 'bg-emerald-100 text-emerald-700', 'bg-sky-100 text-sky-700', 'bg-violet-100 text-violet-700'];
const toneFor = (id: number) => AVATAR_TONES[id % AVATAR_TONES.length];

const Avatar: React.FC<{ name: string; id: number; size?: string }> = ({ name, id, size = 'w-11 h-11 text-sm' }) => (
  <div className={`${size} rounded-full flex items-center justify-center font-semibold shrink-0 ${toneFor(id)}`}>{initialsOf(name)}</div>
);

const STATUS_LABEL: Record<string, string> = {
  completed: 'Completed',
  in_progress: 'Ongoing',
  ringing: 'Ringing',
  pending: 'Waiting',
  failed: 'Failed',
  cancelled: 'Cancelled',
};

const StatusPill: React.FC<{ status: string }> = ({ status }) => {
  const tone =
    status === 'completed' ? 'bg-emerald-50 text-emerald-700'
    : status === 'in_progress' ? 'bg-amber-50 text-amber-700'
    : status === 'failed' ? 'bg-red-50 text-red-600'
    : 'bg-canvas-elevated text-body';
  return <span className={`px-3 py-1 rounded-full text-xs font-medium ${tone}`}>{STATUS_LABEL[status] ?? status}</span>;
};

export const TranscriptView: React.FC<TranscriptViewProps> = React.memo(({ tasks, onTaskRetried }) => {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [activeLog, setActiveLog] = useState<CallLog | null>(null);
  const [isLoadingLog, setIsLoadingLog] = useState(false);

  const filteredTasks = React.useMemo(() => {
    const term = searchTerm.toLowerCase().trim();
    if (!term) return tasks;
    return tasks.filter((t) =>
      t.student_name.toLowerCase().includes(term) ||
      t.student_roll.toLowerCase().includes(term) ||
      t.student_phone.includes(term)
    );
  }, [tasks, searchTerm]);

  const selectedTask = React.useMemo(() => tasks.find((t) => t.id === selectedTaskId), [tasks, selectedTaskId]);

  // On wide screens something is always open; on phones the list shows first.
  const detailTask = selectedTask ?? (typeof window !== 'undefined' && window.innerWidth >= 1024 ? tasks[0] : undefined);

  React.useEffect(() => {
    if (!detailTask) {
      setActiveLog(null);
      return;
    }
    let cancelled = false;
    setIsLoadingLog(true);
    getCallTranscript(detailTask.id)
      .then((log) => { if (!cancelled) setActiveLog(log); })
      .catch(() => { if (!cancelled) setActiveLog(null); })
      .finally(() => { if (!cancelled) setIsLoadingLog(false); });
    return () => { cancelled = true; };
  }, [detailTask?.id]);

  const handleManualRetry = React.useCallback((task: CallTask) => {
    toast.promise(retryCallTask(task.id), {
      loading: 'Queueing the call again…',
      success: () => { onTaskRetried(); return 'Call queued again.'; },
      error: (err) => (err instanceof Error ? err.message : 'Could not retry'),
    });
  }, [onTaskRetried]);

  const showDetailOnMobile = !!selectedTask;
  const duration = detailTask?.duration_sec ?? 0;
  const mmss = `${Math.floor(duration / 60)}:${String(duration % 60).padStart(2, '0')}`;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[minmax(280px,360px)_1fr] gap-4 lg:gap-6 lg:h-[calc(100vh-4rem)]">
      {/* Left: call list */}
      <Card className={`${showDetailOnMobile ? 'hidden lg:flex' : 'flex'} flex-col p-4 sm:p-5 min-h-0`}>
        <h1 className="text-2xl font-semibold text-ink">Transcripts</h1>
        <div className="relative mt-4">
          <Search className="w-4 h-4 absolute left-3.5 top-3 text-mute" aria-hidden="true" />
          <label htmlFor="transcript-search" className="sr-only">Search calls</label>
          <Input
            id="transcript-search"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search"
            className="pl-10"
          />
        </div>

        <ul className="mt-3 flex-1 overflow-y-auto -mx-2 divide-y divide-hairline">
          {filteredTasks.length === 0 && (
            <li className="px-3 py-8 text-center text-sm text-mute">No calls yet.</li>
          )}
          {filteredTasks.map((t) => {
            const active = t.id === detailTask?.id;
            return (
              <li key={t.id}>
                <button
                  type="button"
                  onClick={() => setSelectedTaskId(t.id)}
                  aria-pressed={active}
                  className={`w-full flex items-center gap-3 px-3 py-3 text-left transition-colors rounded-xl ${active ? 'bg-emerald-50' : 'hover:bg-canvas-elevated'}`}
                >
                  <Avatar name={t.student_name} id={t.student_id} />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-ink truncate">{t.student_name}</div>
                    <div className="text-xs text-mute truncate">{t.student_roll}</div>
                  </div>
                  <span className={`w-2 h-2 rounded-full shrink-0 ${t.status === 'completed' ? 'bg-emerald-500' : t.status === 'failed' ? 'bg-red-500' : 'bg-amber-400'}`} aria-label={STATUS_LABEL[t.status] ?? t.status} />
                </button>
              </li>
            );
          })}
        </ul>
      </Card>

      {/* Right: detail */}
      <div className={`${showDetailOnMobile ? 'flex' : 'hidden lg:flex'} flex-col gap-4 min-h-0 lg:overflow-y-auto`}>
        {!detailTask ? (
          <Card className="flex-1 flex items-center justify-center min-h-[300px] text-sm text-mute">
            Pick a call to read its transcript.
          </Card>
        ) : (
          <>
            <Card className="p-4 sm:p-6">
              <button
                type="button"
                onClick={() => setSelectedTaskId(null)}
                className="lg:hidden mb-3 inline-flex items-center gap-1.5 text-sm text-primary"
              >
                <ArrowLeft className="w-4 h-4" /> All calls
              </button>
              <div className="flex flex-wrap items-center gap-4">
                <Avatar name={detailTask.student_name} id={detailTask.student_id} size="w-16 h-16 text-xl" />
                <div className="min-w-0 flex-1">
                  <h2 className="text-2xl font-semibold text-ink truncate">{detailTask.student_name}</h2>
                  <div className="text-body text-sm mt-0.5">{detailTask.student_phone}</div>
                </div>
                {isAdmin && detailTask.status === 'failed' && (
                  <Button onClick={() => handleManualRetry(detailTask)} className="bg-live-pulse hover:bg-live-pulse-soft">
                    <RotateCcw className="w-4 h-4 mr-1.5" /> Call again
                  </Button>
                )}
              </div>
              <dl className="mt-5 grid grid-cols-[88px_1fr] gap-y-2 text-sm">
                <dt className="text-body">Roll no.</dt><dd className="text-ink">{detailTask.student_roll}</dd>
                <dt className="text-body">Status</dt><dd><StatusPill status={detailTask.status} /></dd>
                <dt className="text-body">Length</dt><dd className="text-ink">{mmss}</dd>
              </dl>
            </Card>

            <Card className="p-4 sm:p-5">
              <div className="flex items-center gap-4">
                <button
                  type="button"
                  onClick={() => {
                    setIsPlaying((p) => !p);
                    toast.info('Audio playback is not connected yet.');
                  }}
                  aria-label={isPlaying ? 'Pause recording' : 'Play recording'}
                  className="w-10 h-10 rounded-full bg-primary text-white flex items-center justify-center shrink-0"
                >
                  {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
                </button>
                <div className="flex-1">
                  <div className="h-1.5 rounded-full bg-canvas-elevated" />
                  <div className="flex justify-between text-xs text-body mt-1.5 tabular-nums"><span>0:00</span><span>{mmss}</span></div>
                </div>
              </div>
            </Card>

            <h3 className="text-lg font-semibold text-ink px-1 mt-1">Conversation</h3>
            {isLoadingLog && <p className="text-sm text-mute px-1">Loading…</p>}
            {!isLoadingLog && !activeLog && <p className="text-sm text-mute px-1">No transcript was recorded for this call.</p>}
            {activeLog?.transcript.map((turn, i) => {
              const ai = turn.role === 'assistant';
              return (
                <Card key={i} className="p-4 sm:p-5">
                  <div className="flex items-start gap-3">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${ai ? 'bg-primary/10 text-primary' : 'bg-sky-100 text-sky-700'}`}>
                      {ai ? <Bot className="w-4 h-4" /> : <User className="w-4 h-4" />}
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm text-ink leading-relaxed">{turn.text}</p>
                      <div className="mt-2 flex items-center gap-3 text-xs text-mute">
                        <span>{ai ? 'AI caller' : 'Student'}</span>
                        <span className="tabular-nums">{turn.timestamp}</span>
                      </div>
                    </div>
                  </div>
                </Card>
              );
            })}
            {detailTask.status === 'completed' && !activeLog && !isLoadingLog && (
              <Card className="p-4 text-sm text-mute flex items-center gap-2"><Phone className="w-4 h-4" />Call finished with no spoken text.</Card>
            )}
          </>
        )}
      </div>
    </div>
  );
});

TranscriptView.displayName = 'TranscriptView';
