import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Users, User, Sparkles, Paperclip, X, PhoneCall, Search, FileText, CheckCircle2, ShieldCheck, ArrowRight, RefreshCw, Volume2 } from 'lucide-react';
import { toast } from 'sonner';

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import * as api from '@/lib/api-client';
import type { StudentSearchResult, GeneratedScript } from '@/lib/api-client';
import { CallCampaign } from '@/services/api';

interface NewCallViewProps {
  onCallLaunched: (campaign: CallCampaign) => void;
  onNavigateToTelemetry: () => void;
  systemStatus?: api.SystemStatus | null;
}

const DEPARTMENTS = [
  'Computer Science & Engineering',
  'Information Technology',
  'Mechanical Engineering',
  'Civil Engineering',
  'Institute of Pharmacy',
  'Institute of Management',
];

const LANGUAGES: { value: string; label: string; native: string }[] = [
  { value: 'en', label: 'English', native: 'English (Default)' },
  { value: 'hi', label: 'Hindi', native: 'हिंदी (Devanagari)' },
  { value: 'gu', label: 'Gujarati', native: 'ગુજરાતી (Indic)' },
];

const SUGGESTED_PROMPTS = [
  'Fee payment reminder for upcoming semester registration',
  'Notice regarding mid-semester exam hall ticket collection',
  'Campus placement drive attendance & resume submission notice',
  'Laboratory attendance makeup session schedule notification',
];

type Mode = 'individual' | 'group';

const initialsOf = (name: string) =>
  name.split(' ').map((p) => p[0]).filter(Boolean).slice(0, 2).join('').toUpperCase() || 'ST';

export const NewCallView: React.FC<NewCallViewProps> = ({ onCallLaunched, onNavigateToTelemetry, systemStatus }) => {
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
    }, 300);
    return () => {
      if (searchDebounce.current) clearTimeout(searchDebounce.current);
    };
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
      toast.success('Call script generated successfully', {
        description: 'Review the opening greeting and prompt below before launching.',
      });
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
      const scriptName = reason.trim().slice(0, 90) || 'Automated Outreach';
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
        name: scriptName,
        script_id: script.id,
        target_filter: targetFilter,
        scheduled_at: new Date().toISOString(),
        max_retries: 2,
        retry_delay_min: 45,
      });

      onCallLaunched(campaign);
      toast.success(
        mode === 'individual'
          ? `Dispatched call to ${selectedStudent?.name}`
          : `Campaign queued with ${tasksGenerated} recipient${tasksGenerated === 1 ? '' : 's'}`,
        {
          description: 'Switching to Live Telemetry console...',
        }
      );
      setTimeout(onNavigateToTelemetry, 600);

      // Reset state for subsequent call
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
    <div className="space-y-6">
      {/* Main Studio Grid: Left Configurator (7 cols) | Right Voice Studio Preview (5 cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Form & Targeting (7 cols) */}
        <div className="lg:col-span-7 space-y-6">
          {/* Step 1: Target Audience */}
          <Card>
            <CardHeader className="p-5 pb-3 border-b border-hairline flex flex-row items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded-full bg-primary/10 text-primary font-bold text-xs flex items-center justify-center shrink-0">
                  1
                </div>
                <div>
                  <CardTitle className="text-sm font-bold text-ink">Target Recipient</CardTitle>
                  <CardDescription className="text-xs text-body">Choose individual student or cohort</CardDescription>
                </div>
              </div>
              <Badge variant="outline" className="text-[10px] font-mono">
                {mode === 'individual' ? 'Single Call' : 'Batch Campaign'}
              </Badge>
            </CardHeader>

            <CardContent className="p-5 space-y-5">
              {/* Segmented Mode Switcher */}
              <div className="grid grid-cols-2 gap-2 p-1 rounded-xl bg-canvas-elevated border border-hairline">
                <button
                  type="button"
                  onClick={() => setMode('individual')}
                  className={`flex items-center justify-center gap-2 py-2.5 px-3 rounded-lg text-xs font-semibold transition-all ${
                    mode === 'individual'
                      ? 'bg-white text-ink shadow-sm'
                      : 'text-body hover:text-ink'
                  }`}
                >
                  <User className="w-4 h-4" />
                  <span>Individual Student</span>
                </button>
                <button
                  type="button"
                  onClick={() => setMode('group')}
                  className={`flex items-center justify-center gap-2 py-2.5 px-3 rounded-lg text-xs font-semibold transition-all ${
                    mode === 'group'
                      ? 'bg-white text-ink shadow-sm'
                      : 'text-body hover:text-ink'
                  }`}
                >
                  <Users className="w-4 h-4" />
                  <span>Department Cohort</span>
                </button>
              </div>

              {/* Recipient Input depending on mode */}
              {mode === 'individual' ? (
                <div className="space-y-2">
                  <label htmlFor="student-search" className="text-xs font-semibold text-body">
                    Search Student Directory
                  </label>
                  {selectedStudent ? (
                    <div className="flex items-center justify-between rounded-xl border border-hairline bg-canvas-elevated p-3.5">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-full bg-primary text-white font-semibold flex items-center justify-center text-sm shadow-sm">
                          {initialsOf(selectedStudent.name)}
                        </div>
                        <div>
                          <div className="text-sm font-semibold text-ink flex items-center gap-2">
                            <span>{selectedStudent.name}</span>
                            <Badge variant="secondary" className="text-[10px]">
                              {selectedStudent.department ?? 'Active'}
                            </Badge>
                          </div>
                          <div className="text-xs text-mute font-mono mt-0.5">
                            Roll: <span className="text-ink">{selectedStudent.roll_number}</span> • Tel: <span className="text-ink tabular-nums">{selectedStudent.phone}</span>
                          </div>
                        </div>
                      </div>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setSelectedStudent(null);
                          setStudentQuery('');
                        }}
                        className="h-8 text-xs text-mute hover:text-ink"
                      >
                        <X className="w-4 h-4 mr-1" /> Change
                      </Button>
                    </div>
                  ) : (
                    <div className="relative">
                      <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-mute" />
                      <input
                        id="student-search"
                        value={studentQuery}
                        onChange={(e) => setStudentQuery(e.target.value)}
                        placeholder="Search student by name, roll number (e.g. 22BCE045), or phone..."
                        className="w-full pl-10 pr-10 h-10 rounded-xl border border-hairline-strong bg-white text-sm text-ink placeholder:text-mute focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
                      />
                      {isSearching && (
                        <span className="absolute right-3.5 top-1/2 -translate-y-1/2 text-xs text-mute font-mono">
                          Searching...
                        </span>
                      )}
                      {studentResults.length > 0 && (
                        <div className="absolute z-20 mt-1.5 w-full rounded-xl border border-hairline bg-white shadow-xl max-h-56 overflow-y-auto">
                          {studentResults.map((s) => (
                            <button
                              key={s.id}
                              type="button"
                              onClick={() => {
                                setSelectedStudent(s);
                                setStudentResults([]);
                              }}
                              className="w-full text-left px-4 py-2.5 hover:bg-canvas-elevated flex items-center justify-between border-b border-hairline-subtle last:border-0 transition-colors"
                            >
                              <div className="flex items-center gap-2.5">
                                <div className="w-8 h-8 rounded-full bg-canvas-elevated text-ink font-semibold flex items-center justify-center text-xs">
                                  {initialsOf(s.name)}
                                </div>
                                <div>
                                  <div className="text-xs font-semibold text-ink">{s.name}</div>
                                  <div className="text-[11px] text-mute font-mono">
                                    {s.roll_number} • {s.department ?? 'N/A'}
                                  </div>
                                </div>
                              </div>
                              <span className="text-xs font-mono text-body tabular-nums">{s.phone}</span>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-body">Academic Department</label>
                    <Select value={department} onValueChange={setDepartment}>
                      <SelectTrigger className="bg-white border-hairline text-ink h-10 rounded-xl">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {DEPARTMENTS.map((d) => (
                          <SelectItem key={d} value={d}>
                            {d}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-body">Target Semester</label>
                    <Select value={semester} onValueChange={setSemester}>
                      <SelectTrigger className="bg-white border-hairline text-ink h-10 rounded-xl">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="any">All Semesters (Entire Department)</SelectItem>
                        {[1, 2, 3, 4, 5, 6, 7, 8].map((s) => (
                          <SelectItem key={s} value={String(s)}>
                            Semester {s}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Step 2: Reason & Content */}
          <Card>
            <CardHeader className="p-5 pb-3 border-b border-hairline flex flex-row items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded-full bg-primary/10 text-primary font-bold text-xs flex items-center justify-center shrink-0">
                  2
                </div>
                <div>
                  <CardTitle className="text-sm font-bold text-ink">Call Intent & Context</CardTitle>
                  <CardDescription className="text-xs text-body">Natural language purpose for the voice agent</CardDescription>
                </div>
              </div>
              <span className="text-xs font-mono text-mute">{reason.length} chars</span>
            </CardHeader>

            <CardContent className="p-5 space-y-4">
              <div className="space-y-2">
                <label htmlFor="reason" className="text-xs font-semibold text-body">
                  What is the purpose of this call?
                </label>
                <textarea
                  id="reason"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  rows={3}
                  placeholder="e.g. Remind them their Semester 5 tuition fee payment is pending, and ask if they need assistance with the bank gateway..."
                  className="w-full px-3.5 py-2.5 rounded-xl border border-hairline-strong bg-white text-sm text-ink placeholder:text-mute resize-none focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary leading-relaxed"
                />
              </div>

              {/* Quick suggestion prompt chips */}
              <div className="space-y-1.5">
                <span className="text-[11px] font-semibold text-mute uppercase font-mono tracking-wider">
                  Quick Templates:
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {SUGGESTED_PROMPTS.map((prompt, idx) => (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => setReason(prompt)}
                      className="text-left text-[11px] px-2.5 py-1 rounded-full bg-canvas-elevated hover:bg-primary/10 hover:text-primary text-body border border-hairline transition-colors"
                    >
                      {prompt.slice(0, 36)}...
                    </button>
                  ))}
                </div>
              </div>

              {/* Language Selector & File Upload */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-body">Spoken Language</label>
                  <Select value={language} onValueChange={setLanguage}>
                    <SelectTrigger className="bg-white border-hairline text-ink h-10 rounded-xl">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {LANGUAGES.map((l) => (
                        <SelectItem key={l.value} value={l.value}>
                          {l.native}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-body">
                    Official Circular / PDF <span className="text-mute font-normal">(Optional)</span>
                  </label>
                  {document ? (
                    <div className="flex items-center justify-between h-10 px-3 rounded-xl border border-hairline bg-canvas-elevated text-xs text-ink">
                      <span className="flex items-center gap-1.5 truncate">
                        <FileText className="w-4 h-4 text-primary shrink-0" />
                        <span className="truncate">{document.name}</span>
                      </span>
                      <button
                        type="button"
                        onClick={() => setDocument(null)}
                        aria-label="Remove attached document"
                        className="text-mute hover:text-ink ml-2"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ) : (
                    <label className="flex items-center justify-center gap-2 h-10 rounded-xl border border-dashed border-hairline-strong bg-canvas-elevated/40 hover:bg-canvas-elevated text-xs text-body hover:text-ink cursor-pointer transition-colors">
                      <Paperclip className="w-3.5 h-3.5 text-mute" />
                      <span>Attach .txt or .pdf</span>
                      <input
                        type="file"
                        accept=".txt,.pdf,.md"
                        className="hidden"
                        onChange={(e) => setDocument(e.target.files?.[0] ?? null)}
                      />
                    </label>
                  )}
                </div>
              </div>

              {/* Generate AI Script Action */}
              <div className="pt-2">
                <Button
                  type="button"
                  onClick={handleGenerate}
                  disabled={!canGenerate || isGenerating}
                  className="w-full h-11 rounded-full bg-primary hover:bg-primary-hover text-white text-xs font-semibold shadow-sm transition-all"
                >
                  <Sparkles className={`w-4 h-4 mr-2 ${isGenerating ? 'animate-spin' : ''}`} />
                  {isGenerating ? 'Synthesizing voice prompt via LLM...' : 'Generate AI Voice Script'}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right Column: AI Script Preview & Launch Inspector (5 cols) */}
        <div className="lg:col-span-5 space-y-6">
          <Card className="h-full flex flex-col justify-between">
            <CardHeader className="p-5 pb-3 border-b border-hairline flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-sm font-bold text-ink">Calling Assistant Preview</CardTitle>
                <CardDescription className="text-xs text-body">
                  Simulated PSTN spoken output & prompt constraints
                </CardDescription>
              </div>
              <Badge variant={generated ? 'live' : 'secondary'} className="text-[10px] font-mono uppercase">
                {generated ? 'Ready to Dial' : 'Waiting for Input'}
              </Badge>
            </CardHeader>

            <CardContent className="p-5 flex-1 flex flex-col justify-between space-y-4">
              {!generated ? (
                <div className="flex-1 flex flex-col items-center justify-center text-center p-6 space-y-3 min-h-[320px]">
                  <div className="w-12 h-12 rounded-2xl bg-primary/10 text-primary flex items-center justify-center">
                    <Volume2 className="w-6 h-6" />
                  </div>
                  <div className="space-y-1">
                    <h3 className="text-sm font-semibold text-ink">No Script Generated Yet</h3>
                    <p className="text-xs text-mute max-w-xs leading-relaxed">
                      Select a recipient and describe the call objective on the left. The AI will formulate the conversational greeting and instructions.
                    </p>
                  </div>
                  <div className="pt-2 text-[11px] font-mono text-mute flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-live-pulse" />
                    <span>{systemStatus?.llm_label || 'Gemini Flash'} Ready</span>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  {/* Opening Line Card */}
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-[11px] font-mono uppercase tracking-wider text-body">
                      <span className="flex items-center gap-1 text-telemetry-amber font-semibold">
                        <ShieldCheck className="w-3.5 h-3.5" />
                        TRAI Regulatory Opening Line
                      </span>
                      <span className="text-mute font-mono">Spoken First</span>
                    </div>
                    <div className="rounded-xl border border-telemetry-amber/20 bg-telemetry-amber/5 p-3.5 text-xs text-ink leading-relaxed font-sans italic border-l-4 border-l-telemetry-amber">
                      "{generated.opening_message}"
                    </div>
                  </div>

                  {/* System Prompt Context */}
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-[11px] font-mono uppercase tracking-wider text-body">
                      <span>Conversational Context (Max 35 Words)</span>
                      <span className="text-mute font-mono">{systemStatus?.llm_model || 'Gemini Flash'} Locked</span>
                    </div>
                    <div className="rounded-xl border border-hairline bg-canvas-elevated p-3.5 text-xs text-body font-mono leading-relaxed max-h-40 overflow-y-auto">
                      {generated.system_prompt}
                    </div>
                  </div>

                  {/* Calling Target Summary */}
                  <div className="p-3 rounded-xl bg-canvas-elevated border border-hairline flex items-center justify-between text-xs font-mono">
                    <span className="text-mute">Recipient:</span>
                    <strong className="text-ink truncate max-w-[200px]">
                      {mode === 'individual' && selectedStudent
                        ? `${selectedStudent.name} (${selectedStudent.roll_number})`
                        : `${department} (${semester === 'any' ? 'All' : `Sem ${semester}`})`}
                    </strong>
                  </div>

                  {/* Regenerate & Launch CTAs */}
                  <div className="pt-2 flex flex-col sm:flex-row gap-2.5">
                    <Button
                      type="button"
                      variant="outline"
                      onClick={handleGenerate}
                      disabled={isGenerating}
                      className="h-11 rounded-full px-4 text-xs font-medium"
                    >
                      <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${isGenerating ? 'animate-spin' : ''}`} />
                      Regenerate
                    </Button>
                    <Button
                      type="button"
                      onClick={handleLaunch}
                      disabled={isLaunching}
                      className="flex-1 h-11 rounded-full bg-live-pulse hover:bg-live-pulse/90 text-white text-xs font-semibold shadow-md active:scale-[0.98] transition-all"
                    >
                      <PhoneCall className="w-4 h-4 mr-2" />
                      {isLaunching
                        ? 'Dispatching PSTN Call...'
                        : mode === 'individual'
                        ? 'Dial Student Now'
                        : 'Launch Cohort Campaign'}
                    </Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default NewCallView;
