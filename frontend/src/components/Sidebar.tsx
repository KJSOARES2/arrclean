import React, { useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Layers,
  Clock,
  Settings as SettingsIcon,
  Terminal,
  ShieldCheck,
  X,
} from 'lucide-react';

interface SidebarProps {
  dryRunActive?: boolean;
  isOpen?: boolean;
  onClose?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  dryRunActive = true,
  isOpen = false,
  onClose,
}) => {
  const navItems = [
    { to: '/', label: 'Dashboard', icon: LayoutDashboard },
    { to: '/duplicates', label: 'Duplicates Queue', icon: Layers },
    { to: '/seed-watch', label: 'Seeding Watchlist', icon: Clock },
    { to: '/settings', label: 'Settings & Safety', icon: SettingsIcon },
    { to: '/logs', label: 'Live Logs', icon: Terminal },
  ];

  // Close on Escape key
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose?.();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  const content = (
    <div className="flex flex-col h-full bg-slate-950 text-slate-100">
      {/* Brand Header */}
      <div className="h-16 flex items-center justify-between px-5 sm:px-6 border-b border-slate-800/80">
        <div className="flex items-center space-x-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-400 flex items-center justify-center shadow-lg shadow-emerald-950/50">
            <ShieldCheck className="w-5 h-5 text-slate-950" />
          </div>
          <div>
            <span className="font-bold text-base tracking-tight text-white block">
              ArrClean
            </span>
            <span className="text-[10px] text-emerald-400 font-mono tracking-wider uppercase block">
              Media Lifecycle
            </span>
          </div>
        </div>

        {/* Mobile close button */}
        {onClose && (
          <button
            onClick={onClose}
            className="p-2 -mr-1 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800/60 lg:hidden transition-colors"
            title="Close Navigation"
            aria-label="Close Navigation"
          >
            <X className="w-5 h-5" />
          </button>
        )}
      </div>

      {/* Safety Badge */}
      <div className="px-4 py-3 border-b border-slate-800/60">
        <div
          className={`flex items-center justify-between px-3 py-2 rounded-xl text-xs font-medium border ${
            dryRunActive
              ? 'bg-amber-500/10 text-amber-300 border-amber-500/20'
              : 'bg-rose-500/10 text-rose-300 border-rose-500/20'
          }`}
        >
          <span className="flex items-center space-x-1.5">
            <span
              className={`w-2 h-2 rounded-full animate-pulse ${
                dryRunActive ? 'bg-amber-400' : 'bg-rose-400'
              }`}
            />
            <span>{dryRunActive ? 'Dry-Run Active' : 'Live Deletion Mode'}</span>
          </span>
          <span className="text-[10px] opacity-70">
            {dryRunActive ? 'Safe' : 'Armed'}
          </span>
        </div>
      </div>

      {/* Navigation Links */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={() => onClose?.()}
              className={({ isActive }) =>
                `flex items-center px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-150 space-x-3 min-h-[44px] ${
                  isActive
                    ? 'bg-emerald-500/10 text-emerald-400 font-semibold border border-emerald-500/20 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
                }`
              }
            >
              <Icon className="w-4 h-4 shrink-0" />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </nav>

      {/* Footer Info */}
      <div className="p-4 border-t border-slate-800/80 text-[11px] text-slate-500 font-mono pb-safe">
        <div>v1.0.5 • Docker Edition</div>
        <div className="text-slate-600 mt-0.5">Port 9494 • APScheduler</div>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop Fixed Sidebar */}
      <aside className="hidden lg:flex w-64 border-r border-slate-800/80 bg-slate-950/80 backdrop-blur-xl flex-col shrink-0 min-h-[100dvh]">
        {content}
      </aside>

      {/* Mobile Slide-Out Drawer Overlay */}
      {isOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-black/75 backdrop-blur-sm transition-opacity animate-fade-in"
            onClick={onClose}
            aria-hidden="true"
          />

          {/* Drawer container */}
          <div
            className="fixed inset-y-0 left-0 w-72 max-w-[85vw] shadow-2xl z-50 transition-transform animate-slide-in"
            role="dialog"
            aria-modal="true"
            aria-label="Navigation Menu"
          >
            {content}
          </div>
        </div>
      )}
    </>
  );
};
