import React, { useState } from 'react';
import { Play, RefreshCw, CheckCircle2, Menu } from 'lucide-react';
import { api } from '../api/client';
import { usePolling } from '../hooks/usePolling';
import { useLayoutContext } from './Layout';

interface HeaderProps {
  title: string;
  subtitle?: string;
  onRefresh?: () => void;
  isScanning?: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  title,
  subtitle,
  onRefresh,
  isScanning: propIsScanning = false,
}) => {
  const { toggleMobileMenu } = useLayoutContext();
  const [triggering, setTriggering] = useState(false);
  const [triggerSuccess, setTriggerSuccess] = useState(false);

  // Poll scan status every 3 seconds so all pages stay globally synchronized
  const { data: scanStatus, refresh: refreshScanStatus } = usePolling(
    api.getScanStatus,
    3000
  );

  const activeScan = Boolean(
    propIsScanning || triggering || scanStatus?.status === 'running'
  );

  const handleScanNow = async () => {
    if (activeScan) return;
    try {
      setTriggering(true);
      const res = await api.triggerScan();
      if (res.status === 'already_running') {
        alert(res.message);
      } else {
        setTriggerSuccess(true);
        setTimeout(() => setTriggerSuccess(false), 3000);
      }
      refreshScanStatus();
      if (onRefresh) onRefresh();
    } catch (e) {
      alert(`Failed to trigger scan: ${e}`);
    } finally {
      setTriggering(false);
    }
  };

  return (
    <header className="h-16 border-b border-slate-800/80 bg-slate-950/40 backdrop-blur-md px-4 sm:px-6 lg:px-8 flex items-center justify-between shrink-0">
      <div className="flex items-center min-w-0 mr-3">
        {/* Mobile menu hamburger toggle button */}
        <button
          onClick={toggleMobileMenu}
          className="p-2 -ml-2 mr-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800/60 lg:hidden transition-colors shrink-0"
          title="Open Navigation Menu"
          aria-label="Open Navigation Menu"
        >
          <Menu className="w-5 h-5" />
        </button>

        <div className="min-w-0">
          <h1 className="text-base sm:text-lg font-bold text-white tracking-tight truncate">
            {title}
          </h1>
          {subtitle && (
            <p className="text-[11px] sm:text-xs text-slate-400 mt-0.5 truncate hidden sm:block">
              {subtitle}
            </p>
          )}
        </div>
      </div>

      <div className="flex items-center space-x-2 sm:space-x-3 shrink-0">
        {onRefresh && (
          <button
            onClick={onRefresh}
            className="p-2 text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 rounded-xl transition-colors border border-transparent hover:border-slate-700"
            title="Refresh Data"
            aria-label="Refresh Data"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        )}

        <button
          onClick={handleScanNow}
          disabled={activeScan}
          className={`flex items-center space-x-1.5 sm:space-x-2 px-3 sm:px-3.5 py-2 rounded-xl text-xs font-semibold transition-all shadow-md shrink-0 min-h-[38px] ${
            triggerSuccess
              ? 'bg-emerald-600 text-white'
              : activeScan
              ? 'bg-slate-800 text-slate-400 cursor-not-allowed border border-slate-700'
              : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-950/40'
          }`}
        >
          {activeScan ? (
            <>
              <RefreshCw className="w-3.5 h-3.5 animate-spin shrink-0" />
              <span className="hidden sm:inline">Scanning Library...</span>
              <span className="sm:hidden">Scanning...</span>
            </>
          ) : triggerSuccess ? (
            <>
              <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
              <span className="hidden sm:inline">Scan Initiated!</span>
              <span className="sm:hidden">Started!</span>
            </>
          ) : (
            <>
              <Play className="w-3.5 h-3.5 fill-current shrink-0" />
              <span className="hidden sm:inline">Scan Library Now</span>
              <span className="sm:hidden">Scan</span>
            </>
          )}
        </button>
      </div>
    </header>
  );
};
