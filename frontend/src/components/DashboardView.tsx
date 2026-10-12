import React from 'react';
import { 
  PhoneCall, 
  PhoneForwarded, 
  Clock, 
  Zap, 
  TrendingUp, 
  CheckCircle2
} from 'lucide-react';
import { 
  ResponsiveContainer, 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  Tooltip, 
  PieChart, 
  Pie, 
  Cell
} from 'recharts';

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Progress } from '@/components/ui/progress';
import { CallCampaign, DashboardSummary, DailyVolume, OutcomeDistribution } from '@/services/api';

interface DashboardViewProps {
  campaigns: CallCampaign[];
  summary: DashboardSummary | null;
  volume: DailyVolume[];
  outcomes: OutcomeDistribution | null;
  onLaunchNewCampaign: () => void;
  onViewTranscripts: () => void;
}

const OUTCOME_COLORS: Record<string, string> = {
  completed: '#10B981',
  no_answer: '#F59E0B',
  busy: '#A855F7',
  failed: '#EF4444',
  cancelled: '#64748B',
  pending: '#06B6D4',
};

const OUTCOME_LABELS: Record<string, string> = {
  completed: 'Completed & Answered',
  no_answer: 'No Answer / Timeout',
  busy: 'User Busy / Rejected',
  failed: 'Carrier Error / Failed',
  cancelled: 'Cancelled',
  pending: 'Pending Dispatch',
};

export const DashboardView: React.FC<DashboardViewProps> = React.memo(({
  campaigns,
  summary,
  volume,
  outcomes,
  onLaunchNewCampaign,
  onViewTranscripts,
}) => {
  const totalCalls = summary?.total_calls ?? 0;
  const connectionRate = (summary?.connection_rate_pct ?? 0).toFixed(1);
  const avgDuration = summary?.avg_duration_sec ?? 0;
  const avgTurnLatencySec = ((summary?.avg_turn_latency_ms ?? 0) / 1000).toFixed(2);

  const dispositionData = React.useMemo(() => {
    const counts = outcomes?.outcome_counts ?? {};
    return Object.entries(counts).map(([key, value]) => ({
      name: OUTCOME_LABELS[key] || key,
      value,
      color: OUTCOME_COLORS[key] || '#64748B',
    }));
  }, [outcomes]);

  const dailyVolumeData = React.useMemo(
    () => volume.map((v) => ({ date: v.date, placed: v.total_calls, completed: v.completed_calls, failed: v.failed_calls })),
    [volume]
  );

  return (
    <div id="panel-dashboard" role="tabpanel" aria-labelledby="tab-dashboard" className="space-y-6">
      {/* Top Banner & Quick Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-hairline pb-5">
        <div>
          <div className="flex items-center space-x-2">
            <h1 className="text-2xl font-semibold tracking-tight text-ink font-sans">
              Operational Telemetry & Performance Overview
            </h1>
            <Badge variant="live" className="text-[10px] font-mono uppercase tracking-wider">
              LIVE HPC STREAM
            </Badge>
          </div>
          <p className="text-xs text-body mt-1">
            Real-time automated outbound PSTN calls dialed from Nirma University Supercomputer node
          </p>
        </div>

        <div className="flex items-center space-x-2.5">
          <Button variant="outline" size="default" onClick={onViewTranscripts}>
            <Clock className="w-3.5 h-3.5 mr-1.5 text-body" />
            Inspect Call Logs
          </Button>
          <Button variant="default" size="default" onClick={onLaunchNewCampaign}>
            <PhoneCall className="w-3.5 h-3.5 mr-1.5" />
            Launch Batch Campaign
          </Button>
        </div>
      </div>

      {/* KPI Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Calls */}
        <Card className="bg-canvas-soft border-hairline">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <span className="font-mono text-[11px] font-semibold uppercase tracking-wider text-body">
                TOTAL CALLS DIALED
              </span>
              <PhoneForwarded className="w-4 h-4 text-primary" />
            </div>
            <div className="mt-2 flex items-baseline space-x-2">
              <span className="text-3xl font-semibold tracking-tight text-ink tabular-nums font-sans">
                {totalCalls.toLocaleString()}
              </span>
              <span className="text-xs text-live-pulse font-mono flex items-center">
                <TrendingUp className="w-3 h-3 mr-0.5 inline" /> {summary?.active_campaigns ?? 0} active
              </span>
            </div>
            <p className="text-[11px] text-mute mt-1 font-mono">
              Across {summary?.total_campaigns ?? 0} total campaigns
            </p>
          </CardContent>
        </Card>

        {/* Delivery / Connection Rate */}
        <Card className="bg-canvas-soft border-hairline">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <span className="font-mono text-[11px] font-semibold uppercase tracking-wider text-body">
                CONNECTION RATE
              </span>
              <CheckCircle2 className="w-4 h-4 text-live-pulse" />
            </div>
            <div className="mt-2 flex items-baseline space-x-2">
              <span className="text-3xl font-semibold tracking-tight text-ink tabular-nums font-sans">
                {connectionRate}%
              </span>
              <span className="text-xs text-live-pulse font-mono">
                TRAI Compliant
              </span>
            </div>
            <div className="mt-2">
              <Progress value={parseFloat(connectionRate)} className="h-1 bg-canvas-elevated" />
            </div>
          </CardContent>
        </Card>

        {/* Average Call Duration */}
        <Card className="bg-canvas-soft border-hairline">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <span className="font-mono text-[11px] font-semibold uppercase tracking-wider text-body">
                AVG CALL DURATION
              </span>
              <Clock className="w-4 h-4 text-telemetry-cyan" />
            </div>
            <div className="mt-2 flex items-baseline space-x-2">
              <span className="text-3xl font-semibold tracking-tight text-ink tabular-nums font-sans">
                {avgDuration.toFixed(1)}s
              </span>
            </div>
            <p className="text-[11px] text-mute mt-1 font-mono">
              Across {summary?.completed_calls ?? 0} connected calls
            </p>
          </CardContent>
        </Card>

        {/* Turnaround Latency */}
        <Card className="bg-canvas-soft border-hairline">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <span className="font-mono text-[11px] font-semibold uppercase tracking-wider text-body">
                AVG TURN LATENCY
              </span>
              <Zap className="w-4 h-4 text-telemetry-amber" />
            </div>
            <div className="mt-2 flex items-baseline space-x-2">
              <span className="text-3xl font-semibold tracking-tight text-live-pulse tabular-nums font-sans">
                {avgTurnLatencySec}s
              </span>
              <span className="text-[11px] text-live-pulse font-mono px-1.5 py-0.5 rounded bg-live-pulse/10 border border-live-pulse/20">
                BUDGET &lt; 4.0s
              </span>
            </div>
            <p className="text-[11px] text-mute mt-1 font-mono">
              STT → LLM → TTS cascade average
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Main Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Daily Call Volume Time-Series */}
        <Card className="lg:col-span-2 bg-canvas-soft border-hairline">
          <CardHeader className="p-5 pb-2">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-sm font-semibold text-ink">Daily Outbound Call Volume</CardTitle>
                <CardDescription className="text-xs text-body mt-0.5">
                  Placed vs connected carrier calls across the past 7 days
                </CardDescription>
              </div>
              <div className="flex items-center space-x-3 text-xs font-mono">
                <span className="flex items-center text-primary">
                  <span className="w-2.5 h-2.5 rounded-full bg-primary inline-block mr-1.5" />
                  Dialed Calls
                </span>
                <span className="flex items-center text-live-pulse">
                  <span className="w-2.5 h-2.5 rounded-full bg-live-pulse inline-block mr-1.5" />
                  Answered
                </span>
              </div>
            </div>
          </CardHeader>
          <CardContent className="p-5 pt-3">
            <div className="h-[260px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={dailyVolumeData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorPlaced" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#E06D3B" stopOpacity={0.35}/>
                      <stop offset="95%" stopColor="#E06D3B" stopOpacity={0}/>
                    </linearGradient>
                    <linearGradient id="colorCompleted" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10B981" stopOpacity={0.35}/>
                      <stop offset="95%" stopColor="#10B981" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="date" stroke="#64748B" fontSize={11} tickLine={false} axisLine={false} />
                  <YAxis stroke="#64748B" fontSize={11} tickLine={false} axisLine={false} />
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: '#FFFFFF', 
                      borderColor: 'rgba(15,23,42,0.12)', 
                      borderRadius: '6px',
                      color: '#16254D',
                      fontSize: '12px',
                      fontFamily: 'Inter'
                    }} 
                  />
                  <Area type="monotone" dataKey="placed" stroke="#E06D3B" strokeWidth={2} fillOpacity={1} fill="url(#colorPlaced)" />
                  <Area type="monotone" dataKey="completed" stroke="#10B981" strokeWidth={2} fillOpacity={1} fill="url(#colorCompleted)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Disposition Breakdown Donut */}
        <Card className="bg-canvas-soft border-hairline">
          <CardHeader className="p-5 pb-2">
            <CardTitle className="text-sm font-semibold text-ink">Call Disposition Breakdown</CardTitle>
            <CardDescription className="text-xs text-body mt-0.5">
              Telecom carrier delivery status distribution
            </CardDescription>
          </CardHeader>
          <CardContent className="p-5 pt-3">
            <div className="h-[180px] w-full flex items-center justify-center">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={dispositionData}
                    innerRadius={55}
                    outerRadius={80}
                    paddingAngle={4}
                    dataKey="value"
                  >
                    {dispositionData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: '#FFFFFF', 
                      borderColor: 'rgba(15,23,42,0.12)', 
                      borderRadius: '6px',
                      color: '#16254D',
                      fontSize: '11px' 
                    }} 
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-4 space-y-2 text-xs font-mono">
              {dispositionData.map((item) => (
                <div key={item.name} className="flex items-center justify-between text-body">
                  <div className="flex items-center space-x-2">
                    <span className="w-2 h-2 rounded-full" style={{ backgroundColor: item.color }} />
                    <span className="truncate max-w-[150px]">{item.name}</span>
                  </div>
                  <span className="text-ink font-semibold tabular-nums">{item.value.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Latency Pipeline Breakdown & Active Campaigns */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Latency Summary Card */}
        <Card className="bg-canvas-soft border-hairline">
          <CardHeader className="p-5 pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-semibold text-ink">AI Pipeline Turn Latency</CardTitle>
              <Badge variant="cyan" className="font-mono text-[10px]">
                AVG: {(summary?.avg_turn_latency_ms ?? 0).toFixed(0)} ms
              </Badge>
            </div>
            <CardDescription className="text-xs text-body mt-0.5">
              Full STT → LLM → TTS cascade, budgeted against 4,000 ms SLA threshold
            </CardDescription>
          </CardHeader>
          <CardContent className="p-5 pt-3 space-y-4">
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs">
                <span className="text-body font-mono">Average turn latency</span>
                <span className="text-ink font-mono font-medium tabular-nums">
                  {(summary?.avg_turn_latency_ms ?? 0).toFixed(0)} ms / <span className="text-mute">4,000 ms</span>
                </span>
              </div>
              <div className="w-full bg-canvas-elevated h-1.5 rounded-full overflow-hidden border border-hairline">
                <div
                  className="h-full rounded-full transition-all duration-300 bg-primary"
                  style={{ width: `${Math.min(100, Math.round(((summary?.avg_turn_latency_ms ?? 0) / 4000) * 100))}%` }}
                />
              </div>
            </div>
            <div className="pt-2 border-t border-hairline text-[11px] text-mute font-mono">
              Based on {summary?.completed_calls ?? 0} completed calls logged to date
            </div>
          </CardContent>
        </Card>

        {/* Active Campaigns Table */}
        <Card className="lg:col-span-2 bg-canvas-soft border-hairline">
          <CardHeader className="p-5 pb-2">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-sm font-semibold text-ink">Recent Outbound Campaigns</CardTitle>
                <CardDescription className="text-xs text-body mt-0.5">
                  Batch automated voice calls scheduled by university administration
                </CardDescription>
              </div>
              <Button variant="ghost" size="sm" onClick={onLaunchNewCampaign} className="text-primary text-xs">
                + New Campaign
              </Button>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <caption className="sr-only">Recent Outbound Automated Campaigns</caption>
              <TableHeader>
                <TableRow>
                  <TableHead scope="col">CAMPAIGN NAME</TableHead>
                  <TableHead scope="col">TARGET FILTER</TableHead>
                  <TableHead scope="col">STATUS</TableHead>
                  <TableHead scope="col" className="text-right">PROGRESS</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {campaigns.map((camp) => {
                  const pct = Math.round(((camp.completed_tasks + camp.failed_tasks) / (camp.total_tasks || 1)) * 100);
                  return (
                    <TableRow key={camp.id}>
                      <TableCell className="font-medium text-xs text-ink">
                        {camp.name}
                        <div className="text-[10px] text-mute font-mono">ID: #{camp.id}</div>
                      </TableCell>
                      <TableCell className="text-xs text-body font-mono">
                        {camp.target_filter.department || 'All Departments'}
                      </TableCell>
                      <TableCell>
                        <Badge 
                          variant={camp.status === 'running' ? 'live' : camp.status === 'completed' ? 'secondary' : 'amber'}
                          className="text-[10px] uppercase font-mono"
                        >
                          {camp.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end space-x-2">
                          <span className="text-xs font-mono tabular-nums text-ink">
                            {camp.completed_tasks}/{camp.total_tasks}
                          </span>
                          <span className="text-[10px] text-mute font-mono">({pct}%)</span>
                        </div>
                        <Progress value={pct} className="h-1 mt-1 bg-canvas-elevated" />
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </div>
  );
});

DashboardView.displayName = 'DashboardView';
