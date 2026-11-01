import React, { useState, useEffect, useRef } from 'react';
import {
  Terminal,
  Trash2,
  Search,
  Filter,
  ArrowDown,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { Header } from '../components/Header';
import { useWebSocket } from '../hooks/useWebSocket';
import type { LogMessage } from '../api/types';

export const Logs: React.FC = () => {
  const { messages, connected, clearMessages } = useWebSocket('/api/v1/ws/logs');

  const [levelFilter, setLevelFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [autoScroll, setAutoScroll] = useState<boolean>(true);

  const logsEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (autoScroll && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, autoScroll]);

  const filteredLogs = messages.filter((msg) => {
    if (levelFilter !== 'ALL' && msg.level !== levelFilter) {
      return false;
    }
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return (
        msg.message.toLowerCase().includes(q) ||
        msg.logger.toLowerCase().includes(q) ||
        msg.level.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const getLevelColor = (level: string) => {
    switch (level) {
      case 'ERROR':
        return 'text-rose-400 bg-rose-500/10 border-rose-500/20';
      case 'WARNING':
        return 'text-amber-400 bg-amber-500/10 border-amber-500/20';
      case 'INFO':
        return 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20';
      case 'DEBUG':
        return 'text-blue-400 bg-blue-500/10 border-blue-500/20';
      default:
        return 'text-slate-400 bg-slate-800 border-slate-700';
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-[100dvh] h-[100dvh]">
      <Header
        title="Live System Telemetry & Logs"
        subtitle="Real-time WebSocket stream of duplicate scanning, quality scoring, and cleanup actions"
      />

      <div className="flex-1 flex flex-col p-3 sm:p-6 lg:p-8 max-w-7xl w-full mx-auto min-h-0 space-y-3 sm:space-y-4">
        {/* Controls Bar */}
        <div className="glass-card p-3 sm:p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shrink-0">
          <div className="flex flex-wrap items-center gap-2 sm:gap-3 flex-1 min-w-0">
            {/* Search */}
            <div className="relative w-full sm:w-auto flex-1 min-w-0 sm:min-w-[180px]">
              <Search className="w-3.5 h-3.5 absolute left-3 top-3 text-slate-400" />
              <input
                type="text"
                placeholder="Filter logs..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-4 py-2 bg-slate-900 border border-slate-800 rounded-xl text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500"
              />
            </div>

            {/* Level Filter */}
            <select
              value={levelFilter}
              onChange={(e) => setLevelFilter(e.target.value)}
              className="bg-slate-900 border border-slate-800 text-xs text-slate-300 rounded-xl px-3 py-2 focus:outline-none focus:border-emerald-500"
            >
              <option value="ALL">All Levels</option>
              <option value="INFO">INFO Only</option>
              <option value="WARNING">WARNING Only</option>
              <option value="ERROR">ERROR Only</option>
              <option value="DEBUG">DEBUG Only</option>
            </select>

            {/* Auto scroll toggle */}
            <label className="flex items-center space-x-2 text-xs text-slate-300 cursor-pointer select-none py-1">
              <input
                type="checkbox"
                checked={autoScroll}
                onChange={(e) => setAutoScroll(e.target.checked)}
                className="rounded bg-slate-900 border-slate-700 text-emerald-500 focus:ring-0"
              />
              <ArrowDown className="w-3.5 h-3.5 text-slate-400" />
              <span>Auto-Scroll</span>
            </label>
          </div>

          <div className="flex items-center justify-between sm:justify-end space-x-3 shrink-0 pt-1 sm:pt-0 border-t sm:border-t-0 border-slate-800/60">
            {/* Connection Pill */}
            <span
              className={`flex items-center space-x-1.5 px-2.5 sm:px-3 py-1 rounded-full text-[11px] sm:text-xs font-mono border ${
                connected
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                  : 'bg-rose-500/10 text-rose-400 border-rose-500/20'
              }`}
            >
              {connected ? (
                <>
                  <Wifi className="w-3.5 h-3.5 shrink-0" />
                  <span className="hidden sm:inline">WebSocket Connected</span>
                  <span className="sm:hidden">Live</span>
                </>
              ) : (
                <>
                  <WifiOff className="w-3.5 h-3.5 shrink-0" />
                  <span>Connecting...</span>
                </>
              )}
            </span>

            {/* Clear Button */}
            <button
              onClick={clearMessages}
              className="p-2 text-slate-400 hover:text-rose-400 hover:bg-slate-800 rounded-xl transition-colors"
              title="Clear Console"
              aria-label="Clear Console"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Terminal Window */}
        <div className="flex-1 bg-slate-950 border border-slate-800/80 rounded-2xl p-2.5 sm:p-4 overflow-y-auto font-mono text-[11px] sm:text-xs shadow-inner min-h-0 space-y-1.5 select-text">
          {filteredLogs.length === 0 ? (
            <div className="text-slate-600 italic py-8 text-center text-xs">
              Waiting for log events... All operations will appear here in real time.
            </div>
          ) : (
            filteredLogs.map((log, idx) => (
              <div
                key={idx}
                className="flex items-start space-x-2 sm:space-x-3 py-0.5 hover:bg-slate-900/60 px-1.5 sm:px-2 rounded transition-colors group"
              >
                <span className="text-slate-500 shrink-0 select-none text-[10px] sm:text-[11px]">
                  {log.timestamp ? log.timestamp.substring(11, 19) : ''}
                </span>

                <span
                  className={`px-1.5 py-0.5 rounded text-[9px] sm:text-[10px] font-bold border shrink-0 ${getLevelColor(
                    log.level
                  )}`}
                >
                  {log.level}
                </span>

                <span className="text-slate-400 shrink-0 text-[10px] sm:text-[11px] max-w-[120px] sm:max-w-[160px] truncate hidden xs:inline sm:inline">
                  [{log.logger}]
                </span>

                <span className="text-slate-200 flex-1 break-all leading-relaxed">
                  {log.message}
                </span>
              </div>
            ))
          )}
          <div ref={logsEndRef} />
        </div>
      </div>
    </div>
  );
};
