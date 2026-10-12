import React, { useState, useEffect, useCallback, Suspense, lazy } from 'react';
import { Header } from '@/components/Header';
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

const ViewFallback = () => (
  <div className="flex items-center justify-center min-h-[480px]">
    <div className="flex flex-col items-center space-y-3 p-6 glass-panel rounded-lg border border-hairline">
      <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      <span className="text-xs font-mono text-mute tracking-wider uppercase">Loading View Telemetry...</span>
    </div>
  </div>
);

function AuthenticatedApp() {
  const { user, logout } = useAuth();
  const [activeTab, setActiveTab] = useState<'dashboard' | 'telemetry' | 'campaigns' | 'transcripts'>('dashboard');

  const [campaigns, setCampaigns] = useState<CallCampaign[]>([]);
  const [tasks, setTasks] = useState<CallTask[]>([]);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [volume, setVolume] = useState<DailyVolume[]>([]);
  const [outcomes, setOutcomes] = useState<OutcomeDistribution | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refreshAnalytics = useCallback(async () => {
    const [summaryData, volumeData, outcomesData] = await Promise.all([
      api.getDashboardSummary(),
      api.getDailyVolume(7),
      api.getOutcomeDistribution(),
    ]);
    setSummary(summaryData);
    setVolume(volumeData);
    setOutcomes(outcomesData);
  }, []);

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

  // Initial data load
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
          setLoadError(err instanceof api.ApiError ? err.message : 'Unable to reach the AI Call Agent backend.');
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [refreshAnalytics, refreshTasks]);

  // Live telemetry: reconcile task state whenever the backend broadcasts a call event.
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

  const handleLaunchNewCampaign = useCallback(() => setActiveTab('campaigns'), []);
  const handleViewTranscripts = useCallback(() => setActiveTab('transcripts'), []);
  const handleNavigateToTelemetry = useCallback(() => setActiveTab('telemetry'), []);
  const handleTabChange = useCallback((tab: string) => setActiveTab(tab as any), []);

  const activeCallCount = React.useMemo(() => {
    return tasks.filter(t => t.status === 'in_progress' || t.status === 'ringing').length;
  }, [tasks]);

  return (
    <div className="min-h-screen bg-canvas text-ink flex flex-col font-sans antialiased selection:bg-primary selection:text-white">
      <Toaster position="top-right" richColors />

      <Header
        activeTab={activeTab}
        setActiveTab={handleTabChange}
        activeCallCount={activeCallCount}
        userName={user?.name ?? 'Staff'}
        userRole={user?.role ?? 'operator'}
        onLogout={logout}
      />

      <main id="main-content" tabIndex={-1} className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 focus:outline-none">
        {isLoading ? (
          <ViewFallback />
        ) : loadError ? (
          <div className="flex flex-col items-center justify-center min-h-[400px] space-y-3 text-center">
            <p className="text-sm text-ink font-medium">Could not load telemetry from the backend</p>
            <p className="text-xs text-mute font-mono max-w-md">{loadError}</p>
            <p className="text-xs text-mute">Confirm the FastAPI backend is running at <code className="font-mono">:8000</code> and reachable via the dev proxy.</p>
          </div>
        ) : (
          <Suspense fallback={<ViewFallback />}>
            {activeTab === 'dashboard' && (
              <DashboardView
                campaigns={campaigns}
                summary={summary}
                volume={volume}
                outcomes={outcomes}
                onLaunchNewCampaign={handleLaunchNewCampaign}
                onViewTranscripts={handleViewTranscripts}
              />
            )}

            {activeTab === 'telemetry' && (
              <LiveTelemetryView
                tasks={tasks}
                onSelectTask={() => {}}
              />
            )}

            {activeTab === 'campaigns' && (
              <NewCallView
                onCallLaunched={handleCallLaunched}
                onNavigateToTelemetry={handleNavigateToTelemetry}
              />
            )}

            {activeTab === 'transcripts' && (
              <TranscriptView tasks={tasks} onTaskRetried={handleTaskRetried} />
            )}
          </Suspense>
        )}
      </main>

      <footer className="border-t border-hairline bg-canvas-subtle py-4 mt-auto">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between text-xs text-mute font-mono gap-2">
          <div>
            Nirma University • High-Performance Computing (HPC) AI Telephony Platform
          </div>
          <div className="flex items-center space-x-4">
            <span>TRAI Window: Active (09:00 - 21:00 IST)</span>
          </div>
        </div>
      </footer>
    </div>
  );
}

export function App() {
  const { isAuthenticated } = useAuth();
  return isAuthenticated ? <AuthenticatedApp /> : <LoginView />;
}

export default App;
