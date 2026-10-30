import React, { useState } from 'react';
import {
  Clock,
  Trash2,
  RefreshCw,
  Film,
  Tv,
  CheckCircle,
  AlertCircle,
  ExternalLink,
} from 'lucide-react';
import { Header } from '../components/Header';
import { StatusBadge } from '../components/StatusBadge';
import { LoadingSpinner } from '../components/LoadingSpinner';
import { EmptyState } from '../components/EmptyState';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { usePolling } from '../hooks/usePolling';
import { api } from '../api/client';
import { formatDate } from '../utils/formatters';
import type { SeedLockEntry } from '../api/types';

export const SeedWatch: React.FC = () => {
  const [checking, setChecking] = useState(false);
  const [confirmDialog, setConfirmDialog] = useState<{
    isOpen: boolean;
    title: string;
    message: string;
    onConfirm: () => void;
  }>({
    isOpen: false,
    title: '',
    message: '',
    onConfirm: () => {},
  });

  const { data: entries, loading, refresh } = usePolling(
    api.getSeedWatchList,
    10000
  );

  const handleCheckNow = async () => {
    try {
      setChecking(true);
      await api.triggerSeedCheck();
      refresh();
    } catch (e) {
      alert(`Error triggering retention check: ${e}`);
    } finally {
      setChecking(false);
    }
  };

  const handleForcePurge = (entry: SeedLockEntry) => {
    setConfirmDialog({
      isOpen: true,
      title: 'Force Purge Seeding Torrent?',
      message: `Are you sure you want to permanently purge "${entry.torrent_name}" from qBittorrent and delete its disk data? Seeding retention requirements will be aborted.`,
      onConfirm: async () => {
        try {
          await api.forcePurgeSeedEntry(entry.id);
          setConfirmDialog((prev) => ({ ...prev, isOpen: false }));
          refresh();
        } catch (e) {
          alert(`Error purging seed entry: ${e}`);
        }
      },
    });
  };

  const getProgressBarColor = (percent: number) => {
    if (percent >= 100) return 'bg-emerald-500';
    if (percent >= 66) return 'bg-emerald-400';
    if (percent >= 33) return 'bg-amber-400';
    return 'bg-rose-400';
  };

  return (
    <div className="flex-1 flex flex-col">
      <Header
        title="qBittorrent Seeding Watchlist"
        subtitle="Inferior duplicates locked until ratio or seeding time retention thresholds are fulfilled"
        onRefresh={refresh}
      />

      <div className="p-8 space-y-6 max-w-7xl w-full mx-auto">
        {/* Banner with explanation of safeguards */}
        <div className="glass-card p-5 border-blue-500/20 bg-blue-950/10 flex items-start space-x-4">
          <div className="p-2.5 rounded-xl bg-blue-500/10 text-blue-400 border border-blue-500/20 shrink-0 mt-0.5">
            <Clock className="w-5 h-5" />
          </div>
          <div className="flex-1">
            <h3 className="text-sm font-bold text-white tracking-tight">
              Hardlink & Seeding Safeguards Active
            </h3>
            <p className="text-xs text-slate-300 mt-1 leading-relaxed">
              When duplicates are detected, library-side hardlinks are unlinked so Plex and *arr stop displaying redundant files. The underlying files remain active in qBittorrent to maintain your tracker ratio. As soon as a torrent hits either the target ratio (e.g. 1.0) or seeding duration (e.g. 90 days), it is automatically purged from disk and client.
            </p>
          </div>
          <button
            onClick={handleCheckNow}
            disabled={checking}
            className="flex items-center space-x-2 px-3.5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-xl text-xs font-semibold shrink-0 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${checking ? 'animate-spin' : ''}`} />
            <span>Check Status Now</span>
          </button>
        </div>

        {/* Watchlist Table */}
        {loading && !entries ? (
          <LoadingSpinner message="Querying qBittorrent seed locks..." />
        ) : !entries || entries.length === 0 ? (
          <EmptyState
            title="Seeding Watchlist is Empty"
            description="No torrent-backed duplicates are currently held in the seed-lock queue. Once inferior duplicates backed by active torrents are detected, they will appear here."
            icon={Clock}
          />
        ) : (
          <div className="glass-card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-900/80 border-b border-slate-800 text-slate-400 font-semibold uppercase tracking-wider text-[11px]">
                  <tr>
                    <th className="py-3.5 px-4">Title / Torrent</th>
                    <th className="py-3.5 px-4 min-w-[180px]">Share Ratio</th>
                    <th className="py-3.5 px-4 min-w-[180px]">Seeding Time</th>
                    <th className="py-3.5 px-4">Estimated Unlock</th>
                    <th className="py-3.5 px-4">Status</th>
                    <th className="py-3.5 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono">
                  {entries.map((entry) => (
                    <tr
                      key={entry.id}
                      className="hover:bg-slate-800/30 transition-colors"
                    >
                      {/* Title & Torrent info */}
                      <td className="py-4 px-4 font-sans">
                        <div className="flex items-center space-x-3">
                          <div className="p-2 rounded-lg bg-slate-800 text-slate-400 shrink-0">
                            {entry.media_type === 'movie' ? (
                              <Film className="w-4 h-4" />
                            ) : (
                              <Tv className="w-4 h-4" />
                            )}
                          </div>
                          <div className="min-w-0">
                            <span className="font-semibold text-white block truncate max-w-sm">
                              {entry.title}
                            </span>
                            <span className="text-[11px] text-slate-400 font-mono block truncate max-w-sm">
                              {entry.torrent_name}
                            </span>
                          </div>
                        </div>
                      </td>

                      {/* Ratio Progress */}
                      <td className="py-4 px-4">
                        <div className="space-y-1.5">
                          <div className="flex items-center justify-between text-xs">
                            <span className="text-slate-200">
                              {entry.current_ratio.toFixed(2)} /{' '}
                              <span className="text-slate-400">
                                {entry.target_ratio.toFixed(2)}
                              </span>
                            </span>
                            <span className="text-slate-400 text-[11px]">
                              {entry.ratio_progress_percent}%
                            </span>
                          </div>
                          <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                            <div
                              className={`h-full transition-all duration-300 ${getProgressBarColor(
                                entry.ratio_progress_percent
                              )}`}
                              style={{
                                width: `${Math.min(100, entry.ratio_progress_percent)}%`,
                              }}
                            />
                          </div>
                        </div>
                      </td>

                      {/* Days Progress */}
                      <td className="py-4 px-4">
                        <div className="space-y-1.5">
                          <div className="flex items-center justify-between text-xs">
                            <span className="text-slate-200">
                              {entry.current_seed_days} /{' '}
                              <span className="text-slate-400">
                                {entry.target_seed_days} days
                              </span>
                            </span>
                            <span className="text-slate-400 text-[11px]">
                              {entry.days_progress_percent}%
                            </span>
                          </div>
                          <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                            <div
                              className={`h-full transition-all duration-300 ${getProgressBarColor(
                                entry.days_progress_percent
                              )}`}
                              style={{
                                width: `${Math.min(100, entry.days_progress_percent)}%`,
                              }}
                            />
                          </div>
                        </div>
                      </td>

                      {/* Unlock Date */}
                      <td className="py-4 px-4 text-slate-300 font-sans text-xs">
                        {entry.status === 'PURGED' ? (
                          <span className="text-slate-500">Purged</span>
                        ) : entry.ratio_progress_percent >= 100 ||
                          entry.days_progress_percent >= 100 ? (
                          <span className="text-emerald-400 font-semibold flex items-center">
                            <CheckCircle className="w-3.5 h-3.5 mr-1" />
                            Ready for purge
                          </span>
                        ) : (
                          formatDate(entry.estimated_unlock_date)
                        )}
                      </td>

                      {/* Status */}
                      <td className="py-4 px-4 font-sans">
                        <StatusBadge status={entry.status} type="seed" />
                      </td>

                      {/* Actions */}
                      <td className="py-4 px-4 text-right">
                        {entry.status !== 'PURGED' && (
                          <button
                            onClick={() => handleForcePurge(entry)}
                            className="p-1.5 text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition-colors"
                            title="Force purge from qBittorrent"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      <ConfirmDialog
        isOpen={confirmDialog.isOpen}
        title={confirmDialog.title}
        message={confirmDialog.message}
        isDestructive={true}
        onConfirm={confirmDialog.onConfirm}
        onCancel={() => setConfirmDialog((prev) => ({ ...prev, isOpen: false }))}
      />
    </div>
  );
};
