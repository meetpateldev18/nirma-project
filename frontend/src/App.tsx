import React, { useState, useEffect, useCallback, useMemo, Suspense, lazy } from 'react';
import { Activity, Radio, PhoneCall, FileText, Users } from 'lucide-react';
import { Sidebar, type NavTab } from '@/components/Sidebar';
import { LoginView } from '@/components/LoginView';
import { Toaster } from '@/components/ui/sonner';
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
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

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
    const results = await Promise.all(relevant.map((c) => api.listCampaignTasks(c.id).catch(() => [])));
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
    const socket = api.connectCallEvents(() => {
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
          { id: 'telemetry', label: 'Live calls', icon: Radio, badge: activeCallCount },
          { id: 'campaigns', label: 'New call', icon: PhoneCall },
          { id: 'transcripts', label: 'Transcripts', icon: FileText },
          { id: 'users', label: 'Faculty access', icon: Users },
        ]
      : [
          { id: 'campaigns', label: 'New call', icon: PhoneCall },
          { id: 'transcripts', label: 'My transcripts', icon: FileText },
        ]
  ), [isAdmin, activeCallCount]);

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
      />

      <main id="main-content" tabIndex={-1} className="flex-1 min-w-0 w-full px-3 sm:px-6 lg:px-8 py-4 sm:py-6 lg:py-8 focus:outline-none">
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
                onViewTranscripts={() => setActiveTab('transcripts')}
              />
            )}
            {activeTab === 'telemetry' && isAdmin && <LiveTelemetryView tasks={tasks} onSelectTask={() => {}} />}
            {activeTab === 'campaigns' && (
              <NewCallView
                onCallLaunched={handleCallLaunched}
                onNavigateToTelemetry={() => setActiveTab(isAdmin ? 'telemetry' : 'transcripts')}
              />
            )}
            {activeTab === 'transcripts' && <TranscriptView tasks={tasks} onTaskRetried={handleTaskRetried} />}
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
