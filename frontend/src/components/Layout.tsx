import React from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { usePolling } from '../hooks/usePolling';
import { api } from '../api/client';

export const Layout: React.FC = () => {
  const { data: settings } = usePolling(api.getSettings, 30000);

  return (
    <div className="flex min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-emerald-500/30 selection:text-emerald-200">
      <Sidebar dryRunActive={settings?.DRY_RUN ?? true} />
      <main className="flex-1 flex flex-col min-w-0 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
};
