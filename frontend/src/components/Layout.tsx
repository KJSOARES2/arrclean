import React, { useState, createContext, useContext } from 'react';
import { Outlet, NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Layers,
  Clock,
  Settings as SettingsIcon,
  Terminal,
} from 'lucide-react';
import { Sidebar } from './Sidebar';
import { usePolling } from '../hooks/usePolling';
import { api } from '../api/client';

export interface LayoutContextType {
  mobileMenuOpen: boolean;
  setMobileMenuOpen: React.Dispatch<React.SetStateAction<boolean>>;
  toggleMobileMenu: () => void;
  closeMobileMenu: () => void;
}

export const LayoutContext = createContext<LayoutContextType>({
  mobileMenuOpen: false,
  setMobileMenuOpen: () => {},
  toggleMobileMenu: () => {},
  closeMobileMenu: () => {},
});

export const useLayoutContext = () => useContext(LayoutContext);

export const Layout: React.FC = () => {
  const { data: settings } = usePolling(api.getSettings, 30000);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const toggleMobileMenu = () => setMobileMenuOpen((prev) => !prev);
  const closeMobileMenu = () => setMobileMenuOpen(false);

  const navItems = [
    { to: '/', label: 'Dashboard', icon: LayoutDashboard },
    { to: '/duplicates', label: 'Duplicates', icon: Layers },
    { to: '/seed-watch', label: 'Seed-Lock', icon: Clock },
    { to: '/settings', label: 'Settings', icon: SettingsIcon },
    { to: '/logs', label: 'Logs', icon: Terminal },
  ];

  return (
    <LayoutContext.Provider
      value={{
        mobileMenuOpen,
        setMobileMenuOpen,
        toggleMobileMenu,
        closeMobileMenu,
      }}
    >
      <div className="flex min-h-[100dvh] bg-slate-950 text-slate-100 font-sans selection:bg-emerald-500/30 selection:text-emerald-200">
        {/* Responsive Sidebar (Desktop & Mobile Drawer) */}
        <Sidebar
          dryRunActive={settings?.DRY_RUN ?? true}
          isOpen={mobileMenuOpen}
          onClose={closeMobileMenu}
        />

        {/* Main Content Area */}
        <main className="flex-1 flex flex-col min-w-0 overflow-y-auto pb-16 lg:pb-0">
          <Outlet />
        </main>

        {/* Mobile Bottom Navigation Bar */}
        <nav
          className="fixed bottom-0 left-0 right-0 z-30 lg:hidden bg-slate-950/95 backdrop-blur-xl border-t border-slate-800/80 px-2 py-1 pb-safe flex items-center justify-around"
          aria-label="Mobile Navigation"
        >
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `flex flex-col items-center justify-center flex-1 py-1.5 px-1 rounded-xl transition-colors min-h-[44px] ${
                    isActive
                      ? 'text-emerald-400 font-semibold'
                      : 'text-slate-400 hover:text-slate-200'
                  }`
                }
              >
                <Icon className="w-5 h-5 shrink-0" />
                <span className="text-[10px] tracking-tight mt-0.5 truncate max-w-full">
                  {item.label}
                </span>
              </NavLink>
            );
          })}
        </nav>
      </div>
    </LayoutContext.Provider>
  );
};
