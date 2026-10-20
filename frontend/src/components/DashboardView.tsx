import React from 'react';
import { PhoneCall, PhoneForwarded, CheckCircle2, Clock, BarChart3, ArrowUpRight, Radio, Sparkles } from 'lucide-react';
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
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
  completed: 'Answered & Engaged',
  no_answer: 'Unanswered / Ringing Timeout',
  busy: 'Busy / Declined',
  failed: 'Carrier Failure',
  cancelled: 'Operator Cancelled',
  pending: 'Queued in Dispatcher',
};

const OUTCOME_COLORS: Record<string, string> = {
  completed: '#10B981',
  no_answer: '#F59E0B',
  busy: '#8B5CF6',
  failed: '#EF4444',
  cancelled: '#94A3B8',
  pending: '#06B6D4',
};

interface MetricCardProps {
  label: string;
  value: string;
  hint: string;
  badge?: string;
  icon: React.ReactNode;
  iconBg: string;
}

const MetricCard: React.FC<MetricCardProps> = ({ label, value, hint, badge, icon, iconBg }) => (
  <Card className="hover:shadow-md hover:border-hairline-strong transition-all duration-200 group">
    <CardContent className="p-5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-body">{label}</span>
        <div className={`w-9 h-9 rounded-xl ${iconBg} flex items-center justify-center transition-transform group-hover:scale-105 duration-200`}>
          {icon}
        </div>
      </div>
      <div className="mt-3 flex items-baseline gap-2">
        <span className="text-2xl sm:text-3xl font-bold tracking-tight text-ink tabular-nums">{value}</span>
        {badge && (
          <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-live-pulse/10 text-live-pulse border border-live-pulse/20">
            {badge}
          </span>
        )}
      </div>
      <div className="text-xs text-mute mt-1.5 flex items-center gap-1 font-mono">
        <span>{hint}</span>
      </div>
    </CardContent>
  </Card>
);

const CustomChartTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div className="rounded-xl border border-hairline bg-white/95 backdrop-blur-md p-3 shadow-lg text-xs font-mono space-y-1.5 min-w-[140px]">
        <p className="font-semibold text-ink border-b border-hairline pb-1">{label}</p>
        {payload.map((entry: any, index: number) => (
          <div key={index} className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-1.5" style={{ color: entry.stroke }}>
              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: entry.stroke }} />
              {entry.name}:
            </span>
            <span className="font-bold text-ink tabular-nums">{entry.value}</span>
          </div>
        ))}
      </div>
    );
  }
  return null;
};

export const DashboardView: React.FC<DashboardViewProps> = React.memo(({
  campaigns,
  summary,
  volume,
  outcomes,
  onLaunchNewCampaign,
  onViewTranscripts,
}) => {
  const outcomeRows = Object.entries(outcomes?.outcome_counts ?? {}).filter(([, n]) => n > 0);
  const totalOutcomes = outcomeRows.reduce((sum, [, n]) => sum + n, 0);
  const hasVolume = volume.some((v) => v.total_calls > 0);
  const chartData = volume.map((v) => ({
    date: v.date.slice(5),
    Placed: v.total_calls,
    Answered: v.completed_calls,
  }));

  return (
    <div className="space-y-6">
      {/* Action Toolbar Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-white rounded-2xl border border-hairline p-4 sm:p-5 shadow-[0_1px_3px_rgba(15,23,42,0.04)]">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-live-pulse animate-pulse" />
            <h2 className="text-base sm:text-lg font-bold text-ink">Telephony Operations Overview</h2>
          </div>
          <p className="text-xs text-body mt-0.5">
            Aggregated PSTN telemetry across campaigns, answering ratios, and conversational duration
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <Button variant="outline" size="sm" onClick={onViewTranscripts} className="h-9 rounded-full px-4 text-xs">
            <Clock className="w-3.5 h-3.5 mr-1.5 text-mute" />
            Call History
          </Button>
          <Button size="sm" onClick={onLaunchNewCampaign} className="h-9 rounded-full px-4 text-xs bg-primary hover:bg-primary-hover shadow-sm">
            <PhoneCall className="w-3.5 h-3.5 mr-1.5" />
            Start Call Campaign
          </Button>
        </div>
      </div>

      {/* KPI Stat Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Total Calls Dispatched"
          value={(summary?.total_calls ?? 0).toLocaleString()}
          hint={`${summary?.total_campaigns ?? 0} total campaigns launched`}
          icon={<PhoneForwarded className="w-5 h-5 text-primary" />}
          iconBg="bg-primary/10 text-primary"
        />
        <MetricCard
          label="Pickup Connection Rate"
          value={`${(summary?.connection_rate_pct ?? 0).toFixed(0)}%`}
          hint={`${summary?.completed_calls ?? 0} calls answered`}
          badge="TRAI Monitored"
          icon={<CheckCircle2 className="w-5 h-5 text-live-pulse" />}
          iconBg="bg-live-pulse/10 text-live-pulse"
        />
        <MetricCard
          label="Avg Spoken Duration"
          value={`${Math.round(summary?.avg_duration_sec ?? 0)}s`}
          hint="Calculated on connected calls"
          icon={<Clock className="w-5 h-5 text-telemetry-cyan" />}
          iconBg="bg-telemetry-cyan/10 text-telemetry-cyan"
        />
        <MetricCard
          label="Active In-Flight Campaigns"
          value={String(summary?.active_campaigns ?? 0)}
          hint="Multiprocessing workers active"
          icon={<Radio className="w-5 h-5 text-telemetry-amber" />}
          iconBg="bg-telemetry-amber/10 text-telemetry-amber"
        />
      </div>

      {/* Analytics Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Calls Volume Area Chart */}
        <Card className="lg:col-span-2">
          <CardHeader className="p-5 pb-2 border-b border-hairline flex flex-row items-center justify-between">
            <div>
              <CardTitle className="text-sm font-bold text-ink">Calling Volume & Connect Trends</CardTitle>
              <CardDescription className="text-xs text-body mt-0.5">
                Comparison of daily calls placed vs recipient pickups
              </CardDescription>
            </div>
            <div className="flex items-center gap-3 text-xs font-mono">
              <span className="flex items-center gap-1.5 text-body">
                <span className="w-2.5 h-2.5 rounded-full bg-primary" /> Placed
              </span>
              <span className="flex items-center gap-1.5 text-body">
                <span className="w-2.5 h-2.5 rounded-full bg-live-pulse" /> Answered
              </span>
            </div>
          </CardHeader>
          <CardContent className="p-5">
            <div className="h-[240px] w-full">
              {hasVolume ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData} margin={{ top: 10, right: 10, left: -25, bottom: 0 }}>
                    <defs>
                      <linearGradient id="placedGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#2F5BEA" stopOpacity={0.25} />
                        <stop offset="95%" stopColor="#2F5BEA" stopOpacity={0.0} />
                      </linearGradient>
                      <linearGradient id="answeredGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#10B981" stopOpacity={0.25} />
                        <stop offset="95%" stopColor="#10B981" stopOpacity={0.0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="rgba(15, 23, 42, 0.06)" vertical={false} strokeDasharray="3 3" />
                    <XAxis dataKey="date" stroke="#94A3B8" fontSize={11} tickLine={false} axisLine={false} />
                    <YAxis stroke="#94A3B8" fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
                    <Tooltip content={<CustomChartTooltip />} />
                    <Area
                      type="monotone"
                      dataKey="Placed"
                      stroke="#2F5BEA"
                      strokeWidth={2}
                      fillOpacity={1}
                      fill="url(#placedGradient)"
                    />
                    <Area
                      type="monotone"
                      dataKey="Answered"
                      stroke="#10B981"
                      strokeWidth={2}
                      fillOpacity={1}
                      fill="url(#answeredGradient)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex flex-col items-center justify-center text-center p-6 space-y-2">
                  <BarChart3 className="w-8 h-8 text-mute/50" />
                  <p className="text-xs text-mute font-mono">No calls recorded in this 7-day window.</p>
                  <Button variant="outline" size="sm" onClick={onLaunchNewCampaign} className="h-7 text-xs rounded-full">
                    Launch first call
                  </Button>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Call Outcomes Distribution */}
        <Card className="flex flex-col">
          <CardHeader className="p-5 pb-3 border-b border-hairline flex flex-row items-center justify-between">
            <div>
              <CardTitle className="text-sm font-bold text-ink">Call Dispositions</CardTitle>
              <CardDescription className="text-xs text-body mt-0.5">
                PSTN termination results
              </CardDescription>
            </div>
            {totalOutcomes > 0 && (
              <Badge variant="secondary" className="text-[10px] font-mono tabular-nums">
                {totalOutcomes} Total
              </Badge>
            )}
          </CardHeader>
          <CardContent className="p-5 flex-1 flex flex-col justify-between">
            {totalOutcomes === 0 ? (
              <div className="h-full min-h-[180px] flex flex-col items-center justify-center text-xs text-mute font-mono">
                No disposition data yet.
              </div>
            ) : (
              <ul className="space-y-3.5">
                {outcomeRows.map(([key, count]) => {
                  const pct = Math.round((count / totalOutcomes) * 100);
                  const color = OUTCOME_COLORS[key] ?? '#94A3B8';
                  return (
                    <li key={key} className="space-y-1.5">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-medium text-body flex items-center gap-1.5">
                          <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
                          {OUTCOME_LABELS[key] ?? key}
                        </span>
                        <div className="flex items-center gap-2">
                          <span className="text-ink font-semibold tabular-nums">{count}</span>
                          <span className="text-[10px] text-mute font-mono tabular-nums w-8 text-right">({pct}%)</span>
                        </div>
                      </div>
                      <div className="h-2 rounded-full bg-canvas-elevated overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all duration-500"
                          style={{ width: `${pct}%`, backgroundColor: color }}
                        />
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}

            <div className="pt-4 border-t border-hairline mt-4 flex items-center justify-between text-[11px] text-mute font-mono">
              <span>TRAI 09:00 - 21:00 Window</span>
              <span className="text-live-pulse font-semibold">Regulated</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Recent Campaigns Table Card */}
      <Card>
        <CardHeader className="p-5 pb-3 border-b border-hairline flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-sm font-bold text-ink">Recent Outbound Campaigns</CardTitle>
            <CardDescription className="text-xs text-body mt-0.5">
              Scheduled and completed automated voice calling batches
            </CardDescription>
          </div>
          <Badge variant="mono" className="text-[11px]">
            {campaigns.length} Campaigns
          </Badge>
        </CardHeader>
        <CardContent className="p-0">
          {campaigns.length === 0 ? (
            <div className="p-8 text-center text-xs text-mute font-mono">
              No campaigns initiated. Click "Start Call Campaign" to dispatch automated calls.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[40%]">Campaign Name</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-[25%]">Progress</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {campaigns.slice(0, 5).map((c) => {
                  const progressPct = c.total_tasks > 0 ? Math.round((c.completed_tasks / c.total_tasks) * 100) : 0;
                  return (
                    <TableRow key={c.id} className="hover:bg-canvas-elevated/40">
                      <TableCell className="font-medium text-ink">
                        <div className="flex items-center gap-2.5">
                          <div className="w-7 h-7 rounded-lg bg-primary/10 text-primary flex items-center justify-center shrink-0">
                            <PhoneCall className="w-3.5 h-3.5" />
                          </div>
                          <div>
                            <div className="text-sm font-medium text-ink line-clamp-1">{c.name}</div>
                            <div className="text-[11px] text-mute font-mono">ID: #{c.id}</div>
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={c.status === 'running' ? 'live' : c.status === 'completed' ? 'secondary' : 'amber'}
                          className="text-[10px] font-mono uppercase tracking-wider"
                        >
                          {c.status === 'running' && <span className="w-1.5 h-1.5 rounded-full bg-live-pulse mr-1 animate-pulse" />}
                          {c.status}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="space-y-1">
                          <div className="flex items-center justify-between text-xs text-body tabular-nums">
                            <span>{c.completed_tasks} / {c.total_tasks} calls</span>
                            <span className="font-semibold text-ink">{progressPct}%</span>
                          </div>
                          <div className="h-1.5 rounded-full bg-canvas-elevated overflow-hidden">
                            <div
                              className="h-full bg-primary rounded-full transition-all duration-300"
                              style={{ width: `${progressPct}%` }}
                            />
                          </div>
                        </div>
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={onViewTranscripts}
                          className="h-7 text-xs rounded-full text-primary hover:text-primary hover:bg-primary/10"
                        >
                          Inspect <ArrowUpRight className="w-3 h-3 ml-0.5" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
});

DashboardView.displayName = 'DashboardView';
