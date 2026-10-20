import React, { useState, useEffect } from 'react';
import { PhoneCall, LogOut, Server, Cpu, Clock, type LucideIcon } from 'lucide-react';
import { getSystemStatus, type SystemStatus } from '@/lib/api-client';

export interface NavTab {
  id: string;
  label: string;
  icon: LucideIcon;
  badge?: number;
}

interface SidebarProps {
  tabs: NavTab[];
  activeTab: string;
  setActiveTab: (tab: string) => void;
  userName: string;
  userRole: string;
  onLogout: () => void;
  systemStatus?: SystemStatus | null;
}

const initialsOf = (name: string) =>
  name.split(' ').map((p) => p[0]).filter(Boolean).slice(0, 2).join('').toUpperCase() || 'ST';

export const Sidebar: React.FC<SidebarProps> = React.memo(({ tabs, activeTab, setActiveTab, userName, userRole, onLogout, systemStatus }) => {
  const [internalStatus, setInternalStatus] = useState<SystemStatus | null>(null);

  useEffect(() => {
    if (systemStatus) return;
    let cancelled = false;
    const fetchStatus = () => {
      getSystemStatus()
        .then((data) => { if (!cancelled) setInternalStatus(data); })
        .catch(() => {});
    };
    fetchStatus();
    const timer = setInterval(fetchStatus, 15000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [systemStatus]);

  const activeStatus = systemStatus ?? internalStatus;
  const isPstnActive = activeStatus ? activeStatus.pstn_status === 'active' : false;
  const pstnLabel = activeStatus?.pstn_label ?? 'Telephony Gateway';
  const llmLabel = activeStatus?.llm_label ?? 'LLM Engine';
  const traiOpen = activeStatus ? activeStatus.trai_is_open : true;
  const traiStatus = activeStatus ? activeStatus.trai_status : 'Active';

  return (
  <aside className="bg-white lg:w-72 lg:shrink-0 lg:h-screen lg:sticky lg:top-0 flex flex-col border-b lg:border-b-0 lg:border-r border-hairline">
    <a
      href="#main-content"
      className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[100] focus:px-3 focus:py-1.5 focus:bg-primary focus:text-white focus:rounded-full focus:text-xs"
    >
      Skip to main content
    </a>

    {/* Top row: brand (+ sign out on small screens) */}
    <div className="flex items-center justify-between px-4 pt-4 lg:px-6 lg:pt-7">
      <div className="flex items-center gap-2.5">
        <div className="w-9 h-9 rounded-full bg-primary flex items-center justify-center" aria-hidden="true">
          <PhoneCall className="w-4 h-4 text-white" />
        </div>
        <span className="font-bold text-lg tracking-tight text-primary">NIRMA CALLS</span>
      </div>
      <button
        type="button"
        onClick={onLogout}
        aria-label="Sign out"
        className="lg:hidden h-9 w-9 rounded-full bg-canvas-elevated text-primary flex items-center justify-center"
      >
        <LogOut className="w-4 h-4" />
      </button>
    </div>

    {/* Profile — desktop only */}
    <div className="hidden lg:flex flex-col items-center text-center px-6 pt-8 pb-6">
      <div className="w-24 h-24 rounded-full bg-gradient-to-br from-primary to-primary-deep text-white text-3xl font-semibold flex items-center justify-center">
        {initialsOf(userName)}
      </div>
      <div className="mt-4 text-xs text-mute">Welcome back,</div>
      <div className="text-base font-semibold text-ink">{userName}</div>
      <div className="text-xs text-mute mt-0.5">{userRole === 'admin' ? 'Administrator' : 'Faculty'}</div>
    </div>

    {/* Nav */}
    <nav
      className="flex lg:flex-col gap-1.5 overflow-x-auto lg:overflow-visible px-3 py-3 lg:px-4 lg:py-0 lg:flex-1"
      role="tablist"
      aria-label="Main navigation"
    >
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            role="tab"
            type="button"
            aria-selected={isActive}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-3 rounded-full px-4 py-2.5 text-sm font-medium whitespace-nowrap transition-colors ${
              isActive ? 'bg-primary text-white shadow-sm' : 'text-ink hover:bg-canvas-elevated'
            }`}
          >
            <Icon className="w-5 h-5 shrink-0" aria-hidden="true" />
            <span className="lg:flex-1 text-left">{tab.label}</span>
            {tab.badge ? (
              <span className="h-5 min-w-5 px-1.5 rounded-full bg-live-pulse text-white text-[11px] font-semibold flex items-center justify-center">
                {tab.badge}
              </span>
            ) : null}
          </button>
        );
      })}
    </nav>

    {/* System Telemetry — desktop only */}
    <div className="hidden lg:block px-4 py-3 mx-4 mb-2 rounded-2xl bg-canvas border border-hairline text-xs font-mono">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-mute mb-2">
        System Status
      </div>
      <div className="space-y-1.5 text-[11px]">
        <div className="flex items-center justify-between">
          <span className="text-mute flex items-center gap-1">
            <Server className="w-3 h-3 text-mute" /> PSTN:
          </span>
          <span className={`font-semibold flex items-center gap-1.5 ${isPstnActive ? 'text-live-pulse' : 'text-telemetry-amber'}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${isPstnActive ? 'bg-live-pulse' : 'bg-telemetry-amber'} animate-pulse`} />
            {pstnLabel}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-mute flex items-center gap-1">
            <Cpu className="w-3 h-3 text-mute" /> LLM:
          </span>
          <span className="font-semibold text-telemetry-cyan truncate max-w-[130px]" title={llmLabel}>
            {llmLabel}
          </span>
        </div>
        <div className="flex items-center justify-between border-t border-hairline/60 pt-1.5">
          <span className="text-mute flex items-center gap-1">
            <Clock className="w-3 h-3 text-mute" /> TRAI:
          </span>
          <span className={`font-semibold ${traiOpen ? 'text-ink' : 'text-mute'}`}>
            {traiStatus}
          </span>
        </div>
      </div>
    </div>

    {/* Logout — desktop only */}
    <div className="hidden lg:block p-4">
      <button
        type="button"
        onClick={onLogout}
        className="w-full flex items-center gap-3 rounded-full bg-canvas-elevated px-5 py-3 text-sm font-medium text-primary hover:bg-primary/10 transition-colors"
      >
        <LogOut className="w-5 h-5" aria-hidden="true" /> Logout
      </button>
    </div>
  </aside>
  );
});

Sidebar.displayName = 'Sidebar';
