import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Users, User, Sparkles, Paperclip, X, PhoneCall, Search, FileText } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useAuth } from '@/lib/auth-context';
import * as api from '@/lib/api-client';
import type { StudentSearchResult, GeneratedScript } from '@/lib/api-client';
import { CallCampaign } from '@/services/api';

interface NewCallViewProps {
  onCallLaunched: (campaign: CallCampaign) => void;
  onNavigateToTelemetry: () => void;
}

const DEPARTMENTS = [
  'Computer Science & Engineering',
  'Information Technology',
  'Mechanical Engineering',
  'Civil Engineering',
  'Institute of Pharmacy',
  'Institute of Management',
];

const LANGUAGES: { value: string; label: string }[] = [
  { value: 'en', label: 'English' },
  { value: 'hi', label: 'Hindi' },
  { value: 'gu', label: 'Gujarati' },
];

type Mode = 'individual' | 'group';

export const NewCallView: React.FC<NewCallViewProps> = ({ onCallLaunched, onNavigateToTelemetry }) => {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';

  const [mode, setMode] = useState<Mode>('individual');

  // Individual-recipient search
  const [studentQuery, setStudentQuery] = useState('');
  const [studentResults, setStudentResults] = useState<StudentSearchResult[]>([]);
  const [selectedStudent, setSelectedStudent] = useState<StudentSearchResult | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const searchDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Group targeting
  const [department, setDepartment] = useState(DEPARTMENTS[0]);
  const [semester, setSemester] = useState<string>('any');

  // The reason, language, optional document
  const [reason, setReason] = useState('');
  const [language, setLanguage] = useState('en');
  const [document, setDocument] = useState<File | null>(null);

  const [generated, setGenerated] = useState<GeneratedScript | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isLaunching, setIsLaunching] = useState(false);

  useEffect(() => {
    if (searchDebounce.current) clearTimeout(searchDebounce.current);
    if (studentQuery.trim().length < 2) {
      setStudentResults([]);
      return;
    }
    setIsSearching(true);
    searchDebounce.current = setTimeout(async () => {
      try {
        const results = await api.searchStudents(studentQuery);
        setStudentResults(results);
      } catch {
        setStudentResults([]);
      } finally {
        setIsSearching(false);
      }
    }, 350);
    return () => { if (searchDebounce.current) clearTimeout(searchDebounce.current); };
  }, [studentQuery]);

  const recipientReady = mode === 'individual' ? !!selectedStudent : !!department;
  const canGenerate = recipientReady && reason.trim().length >= 3;

  const handleGenerate = useCallback(async () => {
    if (!canGenerate) return;
    setIsGenerating(true);
    setGenerated(null);
    try {
      const result = await api.generateScript(reason, language, document);
      setGenerated(result);
    } catch (err) {
      toast.error('Could not write a call script', {
        description: err instanceof api.ApiError ? err.message : 'The backend did not respond.',
      });
    } finally {
      setIsGenerating(false);
    }
  }, [canGenerate, reason, language, document]);

  const handleLaunch = useCallback(async () => {
    if (!generated) return;
    setIsLaunching(true);
    try {
      const scriptName = reason.trim().slice(0, 90);
      const script = await api.createScript({
        name: scriptName,
        language,
        opening_message: generated.opening_message,
        system_prompt: generated.system_prompt,
        category: 'custom',
      });

      const targetFilter =
        mode === 'individual' && selectedStudent
          ? { student_id: selectedStudent.id }
          : { department, ...(semester !== 'any' ? { semester: Number(semester) } : {}) };

      const { campaign, tasksGenerated } = await api.createCampaign({
        name: scriptName || 'Untitled call',
        script_id: script.id,
        target_filter: targetFilter,
        scheduled_at: new Date().toISOString(),
        max_retries: 2,
        retry_delay_min: 45,
      });

      onCallLaunched(campaign);
      toast.success(
        mode === 'individual'
          ? `Calling ${selectedStudent?.name}...`
          : `${tasksGenerated} call${tasksGenerated === 1 ? '' : 's'} queued.`
      );
      setTimeout(onNavigateToTelemetry, 600);

      // Reset for the next call
      setReason('');
      setDocument(null);
      setGenerated(null);
      setSelectedStudent(null);
      setStudentQuery('');
    } catch (err) {
      toast.error('Could not launch the call', {
        description: err instanceof api.ApiError ? err.message : 'The backend did not respond.',
      });
    } finally {
      setIsLaunching(false);
    }
  }, [generated, reason, language, mode, selectedStudent, department, semester, onCallLaunched, onNavigateToTelemetry]);

  return (
    <div className="py-2">
      <div className="max-w-2xl mx-auto space-y-8">

        {/* Masthead */}
        <div className="pb-5 border-b-2 border-navy flex items-end justify-between gap-4">
          <div>
            <span className="font-mono text-[11px] tracking-[.14em] uppercase text-primary font-bold">
              Nirma University · Call Agent
            </span>
            <h1 className="font-serif text-4xl font-bold text-navy mt-1 leading-tight">Start a call</h1>
            <p className="text-navy-soft text-sm mt-1 max-w-md">
              Reach one person or a whole batch. Type the reason — the AI writes its own script and stays on topic.
            </p>
          </div>
        </div>

        {/* Section 1 — Who & why */}
        <section className="bg-paper-raised border border-paperline rounded-2xl shadow-sm p-6 space-y-6">
          <div className="flex items-center gap-3">
            <span className="w-7 h-7 rounded-full bg-primary/10 text-primary font-mono font-bold text-sm flex items-center justify-center shrink-0">1</span>
            <h2 className="font-serif text-xl font-semibold text-navy">Who, and why</h2>
          </div>

          {/* Mode toggle */}
          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => setMode('individual')}
              aria-pressed={mode === 'individual'}
              className={`flex items-center gap-2.5 rounded-xl border-2 px-4 py-3 text-left transition-colors ${
                mode === 'individual' ? 'border-primary bg-primary/5' : 'border-paperline hover:border-paperline-strong'
              }`}
            >
              <User className={`w-5 h-5 ${mode === 'individual' ? 'text-primary' : 'text-navy-mute'}`} />
              <div>
                <div className="text-sm font-semibold text-navy">Call one person</div>
                <div className="text-xs text-navy-mute">Search by name, roll no., or phone</div>
              </div>
            </button>
            <button
              type="button"
              onClick={() => setMode('group')}
              aria-pressed={mode === 'group'}
              className={`flex items-center gap-2.5 rounded-xl border-2 px-4 py-3 text-left transition-colors ${
                mode === 'group' ? 'border-primary bg-primary/5' : 'border-paperline hover:border-paperline-strong'
              }`}
            >
              <Users className={`w-5 h-5 ${mode === 'group' ? 'text-primary' : 'text-navy-mute'}`} />
              <div>
                <div className="text-sm font-semibold text-navy">Call a group</div>
                <div className="text-xs text-navy-mute">Everyone in a department / semester</div>
              </div>
            </button>
          </div>

          {/* Recipient picker */}
          {mode === 'individual' ? (
            <div className="space-y-2">
              <label htmlFor="student-search" className="text-xs font-semibold text-navy-soft">Who are you calling?</label>
              {selectedStudent ? (
                <div className="flex items-center justify-between rounded-lg border border-paperline bg-paper-soft px-3.5 py-2.5">
                  <div>
                    <div className="text-sm font-semibold text-navy">{selectedStudent.name}</div>
                    <div className="text-xs text-navy-mute font-mono">{selectedStudent.roll_number} · {selectedStudent.phone}</div>
                  </div>
                  <button type="button" onClick={() => { setSelectedStudent(null); setStudentQuery(''); }} aria-label="Change recipient" className="text-navy-mute hover:text-navy">
                    <X className="w-4 h-4" />
                  </button>
                </div>
              ) : (
                <div className="relative">
                  <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-navy-mute" />
                  <input
                    id="student-search"
                    value={studentQuery}
                    onChange={(e) => setStudentQuery(e.target.value)}
                    placeholder="e.g. Aarav, 22BCE045, or +9198…"
                    className="w-full pl-9 pr-3 h-10 rounded-lg border border-paperline bg-white text-sm text-navy placeholder:text-navy-mute focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                  />
                  {isSearching && <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-navy-mute">searching…</span>}
                  {studentResults.length > 0 && (
                    <div className="absolute z-10 mt-1 w-full rounded-lg border border-paperline bg-white shadow-lg overflow-hidden">
                      {studentResults.map((s) => (
                        <button
                          key={s.id}
                          type="button"
                          onClick={() => { setSelectedStudent(s); setStudentResults([]); }}
                          className="w-full text-left px-3.5 py-2.5 hover:bg-paper-soft border-b border-paperline last:border-0"
                        >
                          <div className="text-sm font-medium text-navy">{s.name}</div>
                          <div className="text-xs text-navy-mute font-mono">{s.roll_number} · {s.phone} · {s.department ?? '—'}</div>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-navy-soft">Department</label>
                <Select value={department} onValueChange={setDepartment}>
                  <SelectTrigger className="bg-white border-paperline text-navy h-10"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {DEPARTMENTS.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-navy-soft">Semester</label>
                <Select value={semester} onValueChange={setSemester}>
                  <SelectTrigger className="bg-white border-paperline text-navy h-10"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="any">All semesters</SelectItem>
                    {[1, 2, 3, 4, 5, 6, 7, 8].map((s) => <SelectItem key={s} value={String(s)}>Semester {s}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}

          {/* Reason */}
          <div className="space-y-1.5">
            <label htmlFor="reason" className="text-xs font-semibold text-navy-soft">What's this call about?</label>
            <textarea
              id="reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              placeholder="e.g. Remind them their semester 5 tuition fee is due on 15 October, and ask when they plan to pay."
              className="w-full px-3.5 py-2.5 rounded-lg border border-paperline bg-white text-sm text-navy placeholder:text-navy-mute resize-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            />
            <p className="text-[11px] text-navy-mute">Any reason works — the AI writes a script for exactly this, and won't wander onto other topics.</p>
          </div>

          <div className="grid grid-cols-2 gap-3 items-end">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-navy-soft">Language</label>
              <Select value={language} onValueChange={setLanguage}>
                <SelectTrigger className="bg-white border-paperline text-navy h-10"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {LANGUAGES.map((l) => <SelectItem key={l.value} value={l.value}>{l.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-navy-soft">Supporting document <span className="text-navy-mute font-normal">(optional)</span></label>
              {document ? (
                <div className="flex items-center justify-between h-10 px-3 rounded-lg border border-paperline bg-paper-soft text-sm text-navy">
                  <span className="flex items-center gap-1.5 truncate"><FileText className="w-3.5 h-3.5 shrink-0 text-navy-mute" />{document.name}</span>
                  <button type="button" onClick={() => setDocument(null)} aria-label="Remove document" className="text-navy-mute hover:text-navy shrink-0"><X className="w-3.5 h-3.5" /></button>
                </div>
              ) : (
                <label className="flex items-center justify-center gap-1.5 h-10 rounded-lg border border-dashed border-paperline-strong text-xs text-navy-mute cursor-pointer hover:border-primary hover:text-primary transition-colors">
                  <Paperclip className="w-3.5 h-3.5" /> Attach .txt or .pdf
                  <input type="file" accept=".txt,.pdf,.md" className="hidden" onChange={(e) => setDocument(e.target.files?.[0] ?? null)} />
                </label>
              )}
            </div>
          </div>

          <Button
            type="button"
            onClick={handleGenerate}
            disabled={!canGenerate || isGenerating}
            className="w-full bg-navy hover:bg-navy/90 text-white h-11 font-semibold"
          >
            <Sparkles className="w-4 h-4 mr-2" />
            {isGenerating ? 'Writing the script…' : 'Write the call script'}
          </Button>
        </section>

        {/* Section 2 — Preview & launch */}
        {generated && (
          <section className="bg-paper-raised border border-paperline rounded-2xl shadow-sm p-6 space-y-5">
            <div className="flex items-center gap-3">
              <span className="w-7 h-7 rounded-full bg-primary/10 text-primary font-mono font-bold text-sm flex items-center justify-center shrink-0">2</span>
              <h2 className="font-serif text-xl font-semibold text-navy">Preview, then launch</h2>
              {generated.used_document && <Badge variant="mono" className="text-[10px] ml-auto">Used your document</Badge>}
            </div>

            <div className="space-y-1.5">
              <div className="text-[11px] font-mono uppercase tracking-wide text-navy-mute">Opening line</div>
              <div className="rounded-lg border border-gold/40 bg-gold-soft/40 px-4 py-3 text-sm text-navy italic">"{generated.opening_message}"</div>
            </div>
            <div className="space-y-1.5">
              <div className="text-[11px] font-mono uppercase tracking-wide text-navy-mute">What the AI will stick to</div>
              <div className="rounded-lg border border-paperline bg-paper-soft px-4 py-3 text-xs text-navy-soft font-mono leading-relaxed max-h-32 overflow-y-auto">{generated.system_prompt}</div>
            </div>

            <div className="rounded-lg bg-paper-soft border border-paperline px-4 py-3 text-sm text-navy">
              <span className="text-navy-mute">Calling: </span>
              {mode === 'individual' && selectedStudent
                ? <span className="font-semibold">{selectedStudent.name} ({selectedStudent.roll_number})</span>
                : <span className="font-semibold">Everyone active in {department}{semester !== 'any' ? `, Semester ${semester}` : ''}</span>}
            </div>

            {!isAdmin && (
              <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                Launching needs an administrator account — you're signed in as an operator. Ask an admin to launch this.
              </p>
            )}

            <div className="flex gap-3">
              <Button type="button" variant="outline" onClick={handleGenerate} disabled={isGenerating} className="border-paperline-strong text-navy">
                Regenerate
              </Button>
              <Button
                type="button"
                onClick={handleLaunch}
                disabled={!isAdmin || isLaunching}
                className="flex-1 bg-primary hover:bg-primary-hover text-white h-11 font-semibold"
              >
                <PhoneCall className="w-4 h-4 mr-2" />
                {isLaunching ? 'Launching…' : mode === 'individual' ? 'Call now' : 'Launch to the group'}
              </Button>
            </div>
          </section>
        )}
      </div>
    </div>
  );
};

export default NewCallView;
