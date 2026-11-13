import React, { useState, useEffect, useCallback } from 'react';
import { PhoneCall, LogOut, Server, Cpu, Clock, Menu, X, type LucideIcon } from 'lucide-react';
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
  userScope?: string;
  onLogout: () => void;
  systemStatus?: SystemStatus | null;
}

const initialsOf = (name: string) =>
  name.split(' ').map((p) => p[0]).filter(Boolean).slice(0, 2).join('').toUpperCase() || 'ST';

export const Sidebar: React.FC<SidebarProps> = React.memo(({
  tabs,
  activeTab,
  setActiveTab,
  userName,
  userRole,
  userScope,
  onLogout,
  systemStatus,
}) => {
  const [internalStatus, setInternalStatus] = useState<SystemStatus | null>(null);
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);

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

  // Close mobile drawer on Escape key press
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && mobileDrawerOpen) {
        setMobileDrawerOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [mobileDrawerOpen]);

  // Lock body scroll when mobile drawer is open
  useEffect(() => {
    if (mobileDrawerOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [mobileDrawerOpen]);

  const handleTabSelect = useCallback((tabId: string) => {
    setActiveTab(tabId);
    setMobileDrawerOpen(false);
  }, [setActiveTab]);

  const activeStatus = systemStatus ?? internalStatus;
  const isPstnActive = activeStatus ? activeStatus.pstn_status === 'active' : false;
  const pstnLabel = activeStatus?.pstn_label ?? 'Telephony Gateway';
  const llmLabel = activeStatus?.llm_label ?? 'LLM Engine';
  const traiOpen = activeStatus ? activeStatus.trai_is_open : true;
  const traiStatus = activeStatus ? activeStatus.trai_status : 'Active';

  const totalActiveCalls = tabs.find((t) => t.badge && t.badge > 0)?.badge ?? 0;

  return (
    <>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[100] focus:px-3 focus:py-1.5 focus:bg-primary focus:text-white focus:rounded-full focus:text-xs"
      >
        Skip to main content
      </a>

      {/* ─── MOBILE / TABLET TOP APP BAR (< 1024px) ─── */}
      <header className="lg:hidden sticky top-0 z-40 bg-white/95 backdrop-blur-md border-b border-hairline px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center shrink-0 shadow-xs" aria-hidden="true">
            <PhoneCall className="w-4 h-4 text-white" />
          </div>
          <div className="min-w-0">
            <span className="font-bold text-sm tracking-tight text-primary block truncate">NIRMA CALLING</span>
            <span className="text-[10px] font-mono text-mute block leading-none">HPC Voice Agent</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {totalActiveCalls > 0 && (
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-live-pulse/10 text-live-pulse border border-live-pulse/20 text-xs font-semibold tabular-nums">
              <span className="w-1.5 h-1.5 rounded-full bg-live-pulse animate-pulse" />
              {totalActiveCalls} Live
            </span>
          )}

          {/* Hamburger Menu Toggle (44x44px minimum touch target) */}
          <button
            type="button"
            onClick={() => setMobileDrawerOpen(true)}
            aria-label="Open navigation menu"
            aria-expanded={mobileDrawerOpen}
            className="w-11 h-11 rounded-xl bg-canvas-elevated text-ink hover:bg-canvas-elevated/80 flex items-center justify-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            <Menu className="w-5 h-5" aria-hidden="true" />
          </button>
        </div>
      </header>

      {/* ─── MOBILE SLIDE-OUT DRAWER OVERLAY & MENU (< 1024px) ─── */}
      {mobileDrawerOpen && (
        <div className="lg:hidden fixed inset-0 z-50 flex" role="dialog" aria-modal="true" aria-label="Mobile Navigation Drawer">
          {/* Backdrop blur overlay */}
          <div
            className="fixed inset-0 bg-black/50 backdrop-blur-xs transition-opacity duration-300"
            onClick={() => setMobileDrawerOpen(false)}
            aria-hidden="true"
          />

          {/* Drawer Sheet */}
          <div className="relative w-80 max-w-[85vw] bg-white h-full shadow-2xl flex flex-col z-50 p-5 overflow-y-auto animate-in slide-in-from-left duration-300">
            {/* Top row with brand & close button (44x44px touch target) */}
            <div className="flex items-center justify-between pb-4 border-b border-hairline">
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-full bg-primary flex items-center justify-center shadow-xs" aria-hidden="true">
                  <PhoneCall className="w-4 h-4 text-white" />
                </div>
                <div>
                  <div className="font-bold text-sm tracking-tight text-primary">NIRMA CALLING</div>
                  <div className="text-[10px] font-mono text-mute">HPC Mission Control</div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setMobileDrawerOpen(false)}
                aria-label="Close navigation menu"
                className="w-11 h-11 rounded-xl text-mute hover:text-ink hover:bg-canvas-elevated flex items-center justify-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              >
                <X className="w-5 h-5" aria-hidden="true" />
              </button>
            </div>

            {/* User Profile in Drawer */}
            <div className="flex items-center gap-3 py-4 border-b border-hairline">
              <div className="w-12 h-12 rounded-full bg-gradient-to-br from-primary to-primary-deep text-white text-base font-semibold flex items-center justify-center shrink-0 shadow-xs">
                {initialsOf(userName)}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-ink truncate">{userName}</div>
                <div className="text-xs text-mute truncate">
                  {userRole === 'admin' ? 'System Administrator' : 'Faculty Operator'}
                </div>
                {userScope && (
                  <div className="mt-1 inline-block px-2 py-0.5 rounded-full bg-primary/10 text-primary text-[10px] font-mono font-semibold truncate max-w-full">
                    {userScope}
                  </div>
                )}
              </div>
            </div>

            {/* Navigation Tab Links (with min 44px touch height) */}
            <nav className="flex-1 py-4 space-y-1.5" role="tablist" aria-label="Mobile main navigation">
              {tabs.map((tab) => {
                const Icon = tab.icon;
                const isActive = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    role="tab"
                    type="button"
                    aria-selected={isActive}
                    onClick={() => handleTabSelect(tab.id)}
                    className={`w-full min-h-[44px] flex items-center gap-3.5 rounded-xl px-4 py-2.5 text-sm font-medium transition-colors ${
                      isActive
                        ? 'bg-primary text-white shadow-sm'
                        : 'text-ink hover:bg-canvas-elevated active:bg-canvas-elevated/80'
                    }`}
                  >
                    <Icon className="w-5 h-5 shrink-0" aria-hidden="true" />
                    <span className="flex-1 text-left">{tab.label}</span>
                    {tab.badge ? (
                      <span className="h-5 min-w-5 px-1.5 rounded-full bg-live-pulse text-white text-[11px] font-semibold flex items-center justify-center tabular-nums">
                        {tab.badge}
                      </span>
                    ) : null}
                  </button>
                );
              })}
            </nav>

            {/* Telemetry Status Widget */}
            <div className="p-3.5 rounded-xl bg-canvas border border-hairline text-xs font-mono mb-4">
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
                  <span className="font-semibold text-telemetry-cyan truncate max-w-[120px]" title={llmLabel}>
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

            {/* Logout Action in Mobile Drawer (min 44px height) */}
            <button
              type="button"
              onClick={() => {
                setMobileDrawerOpen(false);
                onLogout();
              }}
              className="w-full min-h-[44px] flex items-center justify-center gap-2.5 rounded-xl bg-canvas-elevated px-4 py-2.5 text-sm font-medium text-primary hover:bg-primary/10 transition-colors"
            >
              <LogOut className="w-4 h-4" aria-hidden="true" />
              <span>Sign Out</span>
            </button>
          </div>
        </div>
      )}

      {/* ─── DESKTOP PERSISTENT SIDEBAR (lg: 1024px+) ─── */}
      <aside className="hidden lg:flex lg:w-72 lg:shrink-0 lg:h-screen lg:sticky lg:top-0 flex-col bg-white border-r border-hairline z-30">
        {/* Brand Header */}
        <div className="flex items-center gap-2.5 px-6 pt-7">
          <div className="w-9 h-9 rounded-full bg-primary flex items-center justify-center shadow-xs" aria-hidden="true">
            <PhoneCall className="w-4 h-4 text-white" />
          </div>
          <div>
            <span className="font-bold text-base tracking-tight text-primary block">NIRMA CALLING</span>
            <span className="text-[10px] font-mono text-mute tracking-wide block">HPC Mission Control</span>
          </div>
        </div>

        {/* User Profile Card */}
        <div className="flex flex-col items-center text-center px-6 pt-8 pb-6">
          <div className="w-20 h-20 rounded-full bg-gradient-to-br from-primary to-primary-deep text-white text-2xl font-semibold flex items-center justify-center shadow-md">
            {initialsOf(userName)}
          </div>
          <div className="mt-3 text-xs text-mute">Welcome back,</div>
          <div className="text-base font-semibold text-ink leading-tight">{userName}</div>
          <div className="text-xs text-mute mt-0.5">
            {userRole === 'admin' ? 'System Administrator' : 'Faculty Operator'}
          </div>
          {userScope && (
            <div className="mt-1.5 px-2.5 py-0.5 rounded-full bg-primary/10 text-primary text-[10px] font-mono font-semibold max-w-[200px] truncate">
              {userScope}
            </div>
          )}
        </div>

        {/* Main Desktop Navigation */}
        <nav
          className="flex flex-col gap-1.5 px-4 flex-1 overflow-y-auto"
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
                className={`flex items-center gap-3 rounded-full px-4 py-2.5 text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-primary text-white shadow-sm'
                    : 'text-ink hover:bg-canvas-elevated'
                }`}
              >
                <Icon className="w-5 h-5 shrink-0" aria-hidden="true" />
                <span className="flex-1 text-left">{tab.label}</span>
                {tab.badge ? (
                  <span className="h-5 min-w-5 px-1.5 rounded-full bg-live-pulse text-white text-[11px] font-semibold flex items-center justify-center tabular-nums">
                    {tab.badge}
                  </span>
                ) : null}
              </button>
            );
          })}
        </nav>

        {/* System Telemetry — Desktop */}
        <div className="px-4 py-3 mx-4 mb-2 rounded-2xl bg-canvas border border-hairline text-xs font-mono">
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

        {/* Sign out button — Desktop */}
        <div className="p-4 pt-2">
          <button
            type="button"
            onClick={onLogout}
            className="w-full flex items-center justify-center gap-2.5 rounded-full bg-canvas-elevated px-4 py-2.5 text-sm font-medium text-primary hover:bg-primary/10 transition-colors"
          >
            <LogOut className="w-4 h-4" aria-hidden="true" />
            <span>Sign Out</span>
          </button>
        </div>
      </aside>
    </>
  );
});

Sidebar.displayName = 'Sidebar';

