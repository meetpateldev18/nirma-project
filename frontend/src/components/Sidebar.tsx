import React from 'react';
import { PhoneCall, LogOut, type LucideIcon } from 'lucide-react';

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
}

const initialsOf = (name: string) =>
  name.split(' ').map((p) => p[0]).filter(Boolean).slice(0, 2).join('').toUpperCase() || 'ST';

export const Sidebar: React.FC<SidebarProps> = React.memo(({ tabs, activeTab, setActiveTab, userName, userRole, onLogout }) => (
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
));

Sidebar.displayName = 'Sidebar';
