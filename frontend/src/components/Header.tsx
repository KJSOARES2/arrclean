import React, { useState } from 'react';
import { Play, RefreshCw, CheckCircle2 } from 'lucide-react';
import { api } from '../api/client';
import { usePolling } from '../hooks/usePolling';

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
    <header className="h-16 border-b border-slate-800/80 bg-slate-950/40 backdrop-blur-md px-8 flex items-center justify-between shrink-0">
      <div>
        <h1 className="text-lg font-bold text-white tracking-tight">{title}</h1>
        {subtitle && (
          <p className="text-xs text-slate-400 mt-0.5">{subtitle}</p>
        )}
      </div>

      <div className="flex items-center space-x-3">
        {onRefresh && (
          <button
            onClick={onRefresh}
            className="p-2 text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 rounded-xl transition-colors border border-transparent hover:border-slate-700"
            title="Refresh Data"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        )}

        <button
          onClick={handleScanNow}
          disabled={activeScan}
          className={`flex items-center space-x-2 px-3.5 py-2 rounded-xl text-xs font-semibold transition-all shadow-md ${
            triggerSuccess
              ? 'bg-emerald-600 text-white'
              : activeScan
              ? 'bg-slate-800 text-slate-400 cursor-not-allowed border border-slate-700'
              : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-950/40'
          }`}
        >
          {activeScan ? (
            <>
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              <span>Scanning Library...</span>
            </>
          ) : triggerSuccess ? (
            <>
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Scan Initiated!</span>
            </>
          ) : (
            <>
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>Scan Library Now</span>
            </>
          )}
        </button>
      </div>
    </header>
  );
};
