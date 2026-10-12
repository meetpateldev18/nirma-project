import React from 'react';
import { PhoneCall, PhoneForwarded, CheckCircle2, Clock } from 'lucide-react';
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { CallCampaign, DashboardSummary, DailyVolume, OutcomeDistribution } from '@/services/api';

interface DashboardViewProps {
  campaigns: CallCampaign[];
  summary: DashboardSummary | null;
  volume: DailyVolume[];
  outcomes: OutcomeDistribution | null;
  onLaunchNewCampaign: () => void;
  onViewTranscripts: () => void;
}

const OUTCOME_LABELS: Record<string, string> = {
  completed: 'Answered',
  no_answer: 'No answer',
  busy: 'Busy',
  failed: 'Failed',
  cancelled: 'Cancelled',
  pending: 'Waiting',
};

const OUTCOME_COLORS: Record<string, string> = {
  completed: '#10B981',
  no_answer: '#F59E0B',
  busy: '#8B5CF6',
  failed: '#EF4444',
  cancelled: '#94A3B8',
  pending: '#06B6D4',
};

const Stat: React.FC<{ label: string; value: string; hint: string; icon: React.ReactNode }> = ({ label, value, hint, icon }) => (
  <Card className="border-hairline">
    <CardContent className="p-4">
      <div className="flex items-center justify-between text-body">
        <span className="text-xs font-medium">{label}</span>
        {icon}
      </div>
      <div className="mt-2 text-2xl sm:text-3xl font-semibold text-ink tabular-nums">{value}</div>
      <div className="text-xs text-mute mt-0.5">{hint}</div>
    </CardContent>
  </Card>
);

const Empty: React.FC<{ text: string }> = ({ text }) => (
  <div className="h-full flex items-center justify-center text-sm text-mute">{text}</div>
);

export const DashboardView: React.FC<DashboardViewProps> = React.memo(({
  campaigns, summary, volume, outcomes, onLaunchNewCampaign, onViewTranscripts,
}) => {
  const outcomeRows = Object.entries(outcomes?.outcome_counts ?? {}).filter(([, n]) => n > 0);
  const totalOutcomes = outcomeRows.reduce((sum, [, n]) => sum + n, 0);
  const hasVolume = volume.some((v) => v.total_calls > 0);
  const chartData = volume.map((v) => ({ date: v.date.slice(5), Placed: v.total_calls, Answered: v.completed_calls }));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-ink">Overview</h1>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={onViewTranscripts}>
            <Clock className="w-4 h-4 mr-1.5" /> Call history
          </Button>
          <Button onClick={onLaunchNewCampaign}>
            <PhoneCall className="w-4 h-4 mr-1.5" /> New call
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat label="Calls made" value={(summary?.total_calls ?? 0).toLocaleString()} hint={`${summary?.total_campaigns ?? 0} campaigns`} icon={<PhoneForwarded className="w-4 h-4 text-primary" />} />
        <Stat label="Answered" value={`${(summary?.connection_rate_pct ?? 0).toFixed(0)}%`} hint={`${summary?.completed_calls ?? 0} calls picked up`} icon={<CheckCircle2 className="w-4 h-4 text-live-pulse" />} />
        <Stat label="Avg call length" value={`${Math.round(summary?.avg_duration_sec ?? 0)}s`} hint="answered calls only" icon={<Clock className="w-4 h-4 text-telemetry-cyan" />} />
        <Stat label="Running now" value={String(summary?.active_campaigns ?? 0)} hint="active campaigns" icon={<PhoneCall className="w-4 h-4 text-telemetry-amber" />} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2 border-hairline">
          <CardHeader className="p-5 pb-0">
            <CardTitle className="text-sm font-semibold text-ink">Calls this week</CardTitle>
          </CardHeader>
          <CardContent className="p-5">
            <div className="h-[220px]">
              {hasVolume ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData} margin={{ top: 5, right: 8, left: -24, bottom: 0 }}>
                    <CartesianGrid stroke="#E5E9F0" vertical={false} />
                    <XAxis dataKey="date" stroke="#8891A6" fontSize={11} tickLine={false} axisLine={false} />
                    <YAxis stroke="#8891A6" fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
                    <Tooltip contentStyle={{ borderRadius: 6, fontSize: 12 }} />
                    <Area type="monotone" dataKey="Placed" stroke="#2F5BEA" fill="#2F5BEA" fillOpacity={0.15} strokeWidth={2} />
                    <Area type="monotone" dataKey="Answered" stroke="#10B981" fill="#10B981" fillOpacity={0.15} strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <Empty text="No calls yet. They will appear here once a call is made." />
              )}
            </div>
          </CardContent>
        </Card>

        <Card className="border-hairline">
          <CardHeader className="p-5 pb-0">
            <CardTitle className="text-sm font-semibold text-ink">Call results</CardTitle>
          </CardHeader>
          <CardContent className="p-5">
            {totalOutcomes === 0 ? (
              <div className="h-[220px]"><Empty text="Nothing to show yet." /></div>
            ) : (
              <ul className="space-y-3">
                {outcomeRows.map(([key, n]) => (
                  <li key={key}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-body">{OUTCOME_LABELS[key] ?? key}</span>
                      <span className="text-ink font-medium tabular-nums">{n}</span>
                    </div>
                    <div className="h-1.5 rounded-full bg-canvas-elevated overflow-hidden">
                      <div className="h-full rounded-full" style={{ width: `${(n / totalOutcomes) * 100}%`, backgroundColor: OUTCOME_COLORS[key] ?? '#94A3B8' }} />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="border-hairline">
        <CardHeader className="p-5 pb-2">
          <CardTitle className="text-sm font-semibold text-ink">Recent campaigns</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {campaigns.length === 0 ? (
            <div className="px-5 pb-6 text-sm text-mute">No campaigns yet.</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Done</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {campaigns.slice(0, 6).map((c) => (
                  <TableRow key={c.id}>
                    <TableCell className="text-sm text-ink">{c.name}</TableCell>
                    <TableCell>
                      <Badge variant={c.status === 'running' ? 'live' : c.status === 'completed' ? 'secondary' : 'amber'} className="text-[10px] capitalize">
                        {c.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right text-sm tabular-nums text-body">{c.completed_tasks}/{c.total_tasks}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
});

DashboardView.displayName = 'DashboardView';
