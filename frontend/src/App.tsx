import React, { useState, useEffect, useCallback, useMemo, Suspense, lazy } from 'react';
import { Activity, Radio, PhoneCall, FileText, Users, Clock, ShieldCheck } from 'lucide-react';
import { Sidebar, type NavTab } from '@/components/Sidebar';
import { LoginView } from '@/components/LoginView';
import { Toaster } from '@/components/ui/sonner';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/lib/auth-context';
import * as api from '@/lib/api-client';
import {
  CallCampaign,
  CallTask,
  DashboardSummary,
  DailyVolume,
  OutcomeDistribution,
} from '@/services/api';

const DashboardView = lazy(() => import('@/components/DashboardView').then(m => ({ default: m.DashboardView })));
const LiveTelemetryView = lazy(() => import('@/components/LiveTelemetryView').then(m => ({ default: m.LiveTelemetryView })));
const NewCallView = lazy(() => import('@/components/NewCallView').then(m => ({ default: m.NewCallView })));
const TranscriptView = lazy(() => import('@/components/TranscriptView').then(m => ({ default: m.TranscriptView })));
const UsersView = lazy(() => import('@/components/UsersView').then(m => ({ default: m.UsersView })));

type TabId = 'dashboard' | 'telemetry' | 'campaigns' | 'transcripts' | 'users';

const ViewFallback = () => (
  <div className="flex items-center justify-center min-h-[360px]">
    <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
  </div>
);

function AuthenticatedApp() {
  const { user, logout } = useAuth();
  const isAdmin = user?.role === 'admin';
  // Faculty (operator) accounts only get the call form and their own transcripts.
  const [activeTab, setActiveTab] = useState<TabId>(isAdmin ? 'dashboard' : 'campaigns');

  const [campaigns, setCampaigns] = useState<CallCampaign[]>([]);
  const [tasks, setTasks] = useState<CallTask[]>([]);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [volume, setVolume] = useState<DailyVolume[]>([]);
  const [outcomes, setOutcomes] = useState<OutcomeDistribution | null>(null);
  const [systemStatus, setSystemStatus] = useState<api.SystemStatus | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const loadStatus = () => {
      api.getSystemStatus()
        .then((data) => { if (!cancelled) setSystemStatus(data); })
        .catch(() => {});
    };
    loadStatus();
    const timer = setInterval(loadStatus, 15000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const refreshAnalytics = useCallback(async () => {
    if (!isAdmin) return;
    const [summaryData, volumeData, outcomesData] = await Promise.all([
      api.getDashboardSummary(),
      api.getDailyVolume(7),
      api.getOutcomeDistribution(),
    ]);
    setSummary(summaryData);
    setVolume(volumeData);
    setOutcomes(outcomesData);
  }, [isAdmin]);

  const refreshTasks = useCallback(async (campaignList: CallCampaign[]) => {
    const relevant = campaignList.filter((c) => c.status === 'running' || c.status === 'pending' || c.status === 'completed');
    const results = await Promise.all(
      relevant.map(async (c) => {
        const cTasks = await api.listCampaignTasks(c.id).catch(() => []);
        return cTasks.map((t) => ({
          ...t,
          campaign_name: t.campaign_name || c.name,
          summary: t.summary || t.campaign_name || c.name,
        }));
      })
    );
    setTasks(results.flat());
  }, []);

  const refreshCampaigns = useCallback(async () => {
    const data = await api.listCampaigns();
    setCampaigns(data);
    await refreshTasks(data);
  }, [refreshTasks]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setIsLoading(true);
      setLoadError(null);
      try {
        const campaignsData = await api.listCampaigns();
        if (cancelled) return;
        setCampaigns(campaignsData);
        await Promise.all([refreshAnalytics(), refreshTasks(campaignsData)]);
      } catch (err) {
        if (!cancelled) {
          setLoadError(err instanceof api.ApiError ? err.message : 'Unable to reach the server.');
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [refreshAnalytics, refreshTasks]);

  // Live updates: refresh whenever the backend reports a call event.
  useEffect(() => {
    const socket = api.connectCallEvents((envelope) => {
      if (envelope.event === 'call_status') {
        const payload = envelope.data as any;
        if (payload?.task_id) {
          setTasks((prev) =>
            prev.map((t) =>
              t.id === payload.task_id
                ? {
                    ...t,
                    status: payload.status,
                    duration_sec: payload.duration_sec ?? t.duration_sec,
                    plivo_uuid: payload.call_uuid ?? t.plivo_uuid,
                  }
                : t
            )
          );
        }
      }
      refreshCampaigns();
      refreshAnalytics();
    });
    return () => socket?.close();
  }, [refreshCampaigns, refreshAnalytics]);

  const handleCallLaunched = useCallback((newCampaign: CallCampaign) => {
    setCampaigns(prev => [newCampaign, ...prev]);
    refreshTasks([newCampaign, ...campaigns]);
    refreshAnalytics();
  }, [campaigns, refreshTasks, refreshAnalytics]);

  const handleTaskRetried = useCallback(() => {
    refreshCampaigns();
    refreshAnalytics();
  }, [refreshCampaigns, refreshAnalytics]);

  const activeCallCount = useMemo(
    () => tasks.filter(t => t.status === 'in_progress' || t.status === 'ringing').length,
    [tasks]
  );

  const tabs = useMemo<NavTab[]>(() => (
    isAdmin
      ? [
          { id: 'dashboard', label: 'Overview', icon: Activity },
          { id: 'telemetry', label: 'Calls & Transcripts', icon: Radio, badge: activeCallCount },
          { id: 'campaigns', label: 'New call', icon: PhoneCall },
          { id: 'users', label: 'Faculty access', icon: Users },
        ]
      : [
          { id: 'telemetry', label: 'Calls & Transcripts', icon: Radio, badge: activeCallCount },
          { id: 'campaigns', label: 'New call', icon: PhoneCall },
        ]
  ), [isAdmin, activeCallCount]);

  // Live clock formatted in Indian Standard Time (IST)
  const [istTime, setIstTime] = useState<string>('');
  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setIstTime(now.toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true, hour: '2-digit', minute: '2-digit', second: '2-digit' }));
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  const activeTabMeta = useMemo(() => {
    switch (activeTab) {
      case 'dashboard':
        return { label: 'Overview', desc: 'Real-time outbound campaign analytics, KPI trends, and call volume' };
      case 'telemetry':
      case 'transcripts':
        return { label: 'Calls & Transcripts', desc: 'Real-time PSTN carrier channel monitor (10 channels), live audio waveforms, and conversational transcripts' };
      case 'users':
        return { label: 'Faculty Access Control', desc: 'Manage departmental faculty permissions and operator access accounts' };
      default:
        return { label: 'Dashboard', desc: 'Nirma Calling Assistant • High-Performance Computing Platform' };
    }
  }, [activeTab]);

  return (
    <div className="min-h-screen bg-canvas text-ink flex flex-col lg:flex-row font-sans antialiased">
      <Toaster position="top-right" richColors />

      <Sidebar
        tabs={tabs}
        activeTab={activeTab}
        setActiveTab={(t) => setActiveTab(t as TabId)}
        userName={user?.name ?? 'Staff'}
        userRole={user?.role ?? 'operator'}
        onLogout={logout}
        systemStatus={systemStatus}
      />

      <main id="main-content" tabIndex={-1} className="flex-1 min-w-0 w-full px-4 sm:px-6 lg:px-8 py-5 sm:py-6 lg:py-7 focus:outline-none flex flex-col">
        {/* Top Header Bar */}
        <header className="bg-white rounded-2xl border border-hairline shadow-[0_1px_3px_rgba(15,23,42,0.04)] px-5 py-3.5 mb-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="space-y-0.5">
            <div className="flex items-center gap-2 text-[11px] font-mono text-mute tracking-wide uppercase">
              <span>HPC Mission Control</span>
              <span className="text-hairline-strong">/</span>
              <span className="text-primary font-semibold">{activeTabMeta.label}</span>
            </div>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-ink font-sans">
              {activeTabMeta.label}
            </h1>
            <p className="text-xs text-body line-clamp-1">
              {activeTabMeta.desc}
            </p>
          </div>

          {/* Right Status & Actions Telemetry */}
          <div className="flex flex-wrap items-center gap-2.5">
            {/* Live IST Clock */}
            <div className="hidden md:flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-canvas-elevated border border-hairline text-xs font-mono text-ink">
              <span className="w-1.5 h-1.5 rounded-full bg-telemetry-cyan animate-pulse" />
              <span className="tabular-nums font-medium">{istTime || 'IST Active'}</span>
            </div>

            {/* Active Live Calls Count */}
            {activeCallCount > 0 && activeTab !== 'telemetry' && (
              <button
                type="button"
                onClick={() => setActiveTab('telemetry')}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-live-pulse/10 border border-live-pulse/30 text-live-pulse text-xs font-medium hover:bg-live-pulse/20 transition-colors"
              >
                <span className="w-2 h-2 rounded-full bg-live-pulse animate-ping" />
                <span className="tabular-nums font-semibold">{activeCallCount} Live Call{activeCallCount === 1 ? '' : 's'}</span>
              </button>
            )}

            {/* Tab Contextual Actions */}
            {activeTab === 'dashboard' && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setActiveTab('telemetry')}
                  className="h-8 rounded-full px-3.5 text-xs border-hairline text-body hover:text-ink"
                >
                  <Clock className="w-3.5 h-3.5 mr-1.5 text-mute" />
                  Call History
                </Button>
                <Button
                  size="sm"
                  onClick={() => setActiveTab('campaigns')}
                  className="h-8 rounded-full px-4 text-xs font-semibold bg-primary hover:bg-primary-hover shadow-sm"
                >
                  <PhoneCall className="w-3.5 h-3.5 mr-1.5" />
                  New Call
                </Button>
              </>
            )}

            {activeTab === 'campaigns' && (
              <div className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-live-pulse/10 border border-live-pulse/20 text-xs font-mono text-live-pulse">
                <ShieldCheck className="w-3.5 h-3.5" />
                <span className="font-medium">TRAI 09:00 - 21:00 Regulated</span>
              </div>
            )}

            {(activeTab === 'telemetry' || activeTab === 'transcripts' || activeTab === 'users') && (
              <Button
                size="sm"
                onClick={() => setActiveTab('campaigns')}
                className="h-8 rounded-full px-4 text-xs font-semibold bg-primary hover:bg-primary-hover shadow-sm"
              >
                <PhoneCall className="w-3.5 h-3.5 mr-1.5" />
                New Call
              </Button>
            )}
          </div>
        </header>

        {isLoading ? (
          <ViewFallback />
        ) : loadError ? (
          <div className="flex flex-col items-center justify-center min-h-[320px] space-y-2 text-center">
            <p className="text-sm text-ink font-medium">Could not load data</p>
            <p className="text-xs text-mute max-w-md">{loadError}</p>
          </div>
        ) : (
          <Suspense fallback={<ViewFallback />}>
            {activeTab === 'dashboard' && isAdmin && (
              <DashboardView
                campaigns={campaigns}
                summary={summary}
                volume={volume}
                outcomes={outcomes}
                onLaunchNewCampaign={() => setActiveTab('campaigns')}
                onViewTranscripts={() => setActiveTab('telemetry')}
              />
            )}
            {(activeTab === 'telemetry' || activeTab === 'transcripts') && (
              <LiveTelemetryView 
                tasks={tasks} 
                onSelectTask={() => {}} 
                onTaskRetried={handleTaskRetried}
                systemStatus={systemStatus} 
              />
            )}
            {activeTab === 'campaigns' && (
              <NewCallView
                onCallLaunched={handleCallLaunched}
                onNavigateToTelemetry={() => setActiveTab('telemetry')}
                systemStatus={systemStatus}
              />
            )}
            {activeTab === 'users' && isAdmin && <UsersView />}
          </Suspense>
        )}
      </main>
    </div>
  );
}

export function App() {
  const { isAuthenticated } = useAuth();
  return isAuthenticated ? <AuthenticatedApp /> : <LoginView />;
}

export default App;
