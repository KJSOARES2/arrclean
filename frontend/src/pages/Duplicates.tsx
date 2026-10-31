import React, { useState } from 'react';
import {
  Layers,
  Search,
  ArrowRightLeft,
  Check,
  EyeOff,
  Trash2,
  CheckCheck,
  Film,
  Tv,
  HardDrive,
  Link,
  ChevronLeft,
  ChevronRight,
  ShieldAlert,
  Play,
} from 'lucide-react';
import { Header } from '../components/Header';
import { StatusBadge } from '../components/StatusBadge';
import { QualityBadge } from '../components/QualityBadge';
import { LoadingSpinner } from '../components/LoadingSpinner';
import { EmptyState } from '../components/EmptyState';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { usePolling } from '../hooks/usePolling';
import { api } from '../api/client';
import { formatBytes } from '../utils/formatters';
import type { DuplicatePair } from '../api/types';

export const Duplicates: React.FC = () => {
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string>('PENDING_REVIEW');
  const [mediaTypeFilter, setMediaTypeFilter] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');

  const [confirmDialog, setConfirmDialog] = useState<{
    isOpen: boolean;
    title: string;
    message: string;
    isDestructive?: boolean;
    onConfirm: () => void;
  }>({
    isOpen: false,
    title: '',
    message: '',
    onConfirm: () => {},
  });

  const { data, loading, refresh } = usePolling(
    () =>
      api.listDuplicates({
        page,
        limit: 15,
        status: statusFilter || undefined,
        media_type: mediaTypeFilter || undefined,
        search: searchQuery || undefined,
      }),
    10000
  );

  const handleApprove = async (id: number) => {
    try {
      await api.approveDuplicate(id);
      refresh();
    } catch (e) {
      alert(`Error approving duplicate: ${e}`);
    }
  };

  const handleSwap = async (id: number) => {
    try {
      await api.swapDuplicate(id);
      refresh();
    } catch (e) {
      alert(`Error swapping duplicate: ${e}`);
    }
  };

  const handleIgnore = async (id: number) => {
    try {
      await api.ignoreDuplicate(id);
      refresh();
    } catch (e) {
      alert(`Error ignoring duplicate: ${e}`);
    }
  };

  const handleForceDelete = (pair: DuplicatePair) => {
    setConfirmDialog({
      isOpen: true,
      title: 'Force Delete Duplicate Immediately?',
      message: `Are you sure you want to permanently delete the inferior copy for "${pair.title}"? This bypasses qBittorrent seeding retention requirements and dry-run protection.`,
      isDestructive: true,
      onConfirm: async () => {
        try {
          await api.forceDeleteDuplicate(pair.id);
          setConfirmDialog((prev) => ({ ...prev, isOpen: false }));
          refresh();
        } catch (e) {
          alert(`Error during forced deletion: ${e}`);
        }
      },
    });
  };

  const handleApproveAll = () => {
    setConfirmDialog({
      isOpen: true,
      title: 'Approve All Pending Duplicates?',
      message:
        'All pending duplicate pairs will have their winners retained. Inferior copies will either be deleted or transferred to the Seed-Lock queue if active in qBittorrent.',
      onConfirm: async () => {
        try {
          await api.approveAllDuplicates();
          setConfirmDialog((prev) => ({ ...prev, isOpen: false }));
          refresh();
        } catch (e) {
          alert(`Error during bulk approval: ${e}`);
        }
      },
    });
  };

  const handleExecuteApproved = () => {
    setConfirmDialog({
      isOpen: true,
      title: 'Execute All Approved Cleanups?',
      message:
        'All approved duplicate cleanups will be processed. If live deletion mode is active, inferior files will be unlinked or removed from media storage, and any seeding torrents will be transferred to the Seed-Lock Watchlist.',
      onConfirm: async () => {
        try {
          const res = await api.executeApproved();
          setConfirmDialog((prev) => ({ ...prev, isOpen: false }));
          alert(`Execution complete. Cleaned/locked: ${res.cleanup_summary.processed} files (${formatBytes(res.cleanup_summary.space_saved_bytes)}).`);
          refresh();
        } catch (e) {
          alert(`Error executing approved cleanups: ${e}`);
        }
      },
    });
  };

  return (
    <div className="flex-1 flex flex-col">
      <Header
        title="Duplicates Review Queue"
        subtitle="Evaluate and resolve media duplicates using custom format scores and stream metrics"
        onRefresh={refresh}
      />

      <div className="p-8 space-y-6 max-w-7xl w-full mx-auto">
        {/* Filters and Controls */}
        <div className="glass-card p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3 flex-1">
            {/* Search */}
            <div className="relative min-w-[240px]">
              <Search className="w-4 h-4 absolute left-3 top-3 text-slate-400" />
              <input
                type="text"
                placeholder="Search duplicates by title..."
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setPage(1);
                }}
                className="w-full pl-9 pr-4 py-2 bg-slate-900 border border-slate-800 rounded-xl text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500 transition-colors"
              />
            </div>

            {/* Status Filter */}
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(1);
              }}
              className="bg-slate-900 border border-slate-800 text-xs text-slate-300 rounded-xl px-3 py-2 focus:outline-none focus:border-emerald-500"
            >
              <option value="">All Statuses</option>
              <option value="PENDING_REVIEW">Pending Review</option>
              <option value="APPROVED">Approved</option>
              <option value="SEED_LOCKED">Seed-Locked</option>
              <option value="COMPLETED">Completed</option>
              <option value="IGNORED">Ignored</option>
            </select>

            {/* Media Type Filter */}
            <select
              value={mediaTypeFilter}
              onChange={(e) => {
                setMediaTypeFilter(e.target.value);
                setPage(1);
              }}
              className="bg-slate-900 border border-slate-800 text-xs text-slate-300 rounded-xl px-3 py-2 focus:outline-none focus:border-emerald-500"
            >
              <option value="">All Media Types</option>
              <option value="movie">Movies</option>
              <option value="episode">Episodes</option>
            </select>
          </div>

          {/* Bulk Action */}
          <div className="flex items-center space-x-3">
            <button
              onClick={handleExecuteApproved}
              className="flex items-center space-x-2 px-3.5 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-semibold shadow-md shadow-blue-950/40 transition-colors"
              title="Process and execute cleanup on all approved pairs"
            >
              <Play className="w-4 h-4" />
              <span>Execute Approved</span>
            </button>
            <button
              onClick={handleApproveAll}
              className="flex items-center space-x-2 px-3.5 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-semibold shadow-md shadow-emerald-950/40 transition-colors"
            >
              <CheckCheck className="w-4 h-4" />
              <span>Approve All Pending</span>
            </button>
          </div>
        </div>

        {/* Content Area */}
        {loading && !data ? (
          <LoadingSpinner message="Scanning duplicate database..." />
        ) : !data || data.items.length === 0 ? (
          <EmptyState
            title="No duplicates found"
            description="Your library is clean! Either no duplicate movies/episodes were found matching these filters, or the initial scan has not yet run."
            actionText="Run Full Scan"
            onAction={() => api.triggerScan().then(refresh)}
          />
        ) : (
          <div className="space-y-5">
            {data.items.map((pair) => (
              <div
                key={pair.id}
                className="glass-card overflow-hidden border border-slate-800/80 hover:border-slate-700/80 transition-all"
              >
                {/* Pair Header */}
                <div className="p-4 bg-slate-900/60 border-b border-slate-800/80 flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center space-x-3">
                    <div className="p-2 rounded-xl bg-slate-800 text-slate-400">
                      {pair.media_type === 'movie' ? (
                        <Film className="w-4 h-4" />
                      ) : (
                        <Tv className="w-4 h-4" />
                      )}
                    </div>
                    <div>
                      <h3 className="text-sm font-bold text-white tracking-tight">
                        {pair.title}
                      </h3>
                      <div className="flex items-center space-x-2 text-[11px] text-slate-400 font-mono mt-0.5">
                        <span className="uppercase">{pair.media_type}</span>
                        {pair.tmdb_id && <span>• TMDB: {pair.tmdb_id}</span>}
                        {pair.tvdb_id && <span>• TVDB: {pair.tvdb_id}</span>}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center space-x-3">
                    <span className="text-xs font-mono text-emerald-400">
                      Potential saving: {formatBytes(pair.space_saved_bytes)}
                    </span>
                    <StatusBadge status={pair.status} />
                  </div>
                </div>

                {/* Side-by-Side Comparison */}
                <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-slate-800/80">
                  {/* Winner Card */}
                  <div className="p-5 bg-emerald-950/5 flex flex-col justify-between">
                    <div>
                      <div className="flex items-center justify-between mb-3">
                        <span className="flex items-center text-xs font-bold text-emerald-400 tracking-wide uppercase">
                          <span className="w-2 h-2 rounded-full bg-emerald-400 mr-2 animate-pulse" />
                          🏆 WINNER (Keep)
                        </span>
                        <QualityBadge
                          label={`Score: ${pair.winner?.composite_quality_score ?? 0}`}
                          variant="score"
                        />
                      </div>

                      <div className="space-y-2 text-xs">
                        <div className="text-slate-300 font-mono break-all line-clamp-2 bg-slate-950/60 p-2 rounded-lg border border-slate-800/60">
                          {pair.winner?.file_path}
                        </div>

                        <div className="flex flex-wrap gap-1.5 pt-1">
                          <QualityBadge
                            label={formatBytes(pair.winner?.file_size_bytes ?? 0)}
                          />
                          <QualityBadge
                            label={pair.winner?.resolution ?? 'Unknown'}
                            variant="resolution"
                          />
                          <QualityBadge
                            label={pair.winner?.hdr_format ?? 'SDR'}
                            variant="hdr"
                          />
                          <QualityBadge
                            label={pair.winner?.source_type ?? 'Source'}
                            variant="source"
                          />
                          {pair.winner?.audio_codec && (
                            <QualityBadge label={pair.winner.audio_codec} />
                          )}
                          {pair.winner?.video_codec && (
                            <QualityBadge label={pair.winner.video_codec} />
                          )}
                          {pair.winner?.custom_format_score != null && (
                            <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                              CF: {pair.winner.custom_format_score}
                            </span>
                          )}
                          {pair.winner?.edition && (
                            <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-indigo-950/60 text-indigo-300 border border-indigo-800/40">
                              {pair.winner.edition}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Loser Card */}
                  <div className="p-5 bg-rose-950/5 flex flex-col justify-between">
                    <div>
                      <div className="flex items-center justify-between mb-3">
                        <span className="flex items-center text-xs font-bold text-rose-400 tracking-wide uppercase">
                          <span className="w-2 h-2 rounded-full bg-rose-400 mr-2" />
                          ❌ LOSER (Delete / Seed-Lock)
                        </span>
                        <QualityBadge
                          label={`Score: ${pair.loser?.composite_quality_score ?? 0}`}
                        />
                      </div>

                      <div className="space-y-2 text-xs">
                        <div className="text-slate-400 font-mono break-all line-clamp-2 bg-slate-950/60 p-2 rounded-lg border border-slate-800/60">
                          {pair.loser?.file_path}
                        </div>

                        <div className="flex flex-wrap gap-1.5 pt-1">
                          <QualityBadge
                            label={formatBytes(pair.loser?.file_size_bytes ?? 0)}
                          />
                          <QualityBadge
                            label={pair.loser?.resolution ?? 'Unknown'}
                            variant="resolution"
                          />
                          <QualityBadge
                            label={pair.loser?.hdr_format ?? 'SDR'}
                            variant="hdr"
                          />
                          <QualityBadge
                            label={pair.loser?.source_type ?? 'Source'}
                            variant="source"
                          />
                          {pair.loser?.audio_codec && (
                            <QualityBadge label={pair.loser.audio_codec} />
                          )}
                          {pair.loser?.video_codec && (
                            <QualityBadge label={pair.loser.video_codec} />
                          )}
                          {pair.loser?.custom_format_score != null && (
                            <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                              CF: {pair.loser.custom_format_score}
                            </span>
                          )}
                          {pair.loser?.is_hardlinked && (
                            <span className="inline-flex items-center text-[11px] font-mono px-2 py-0.5 rounded bg-blue-950/60 text-blue-300 border border-blue-800/40">
                              <Link className="w-3 h-3 mr-1" /> Hardlinked
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Card Action Controls */}
                <div className="px-5 py-3 bg-slate-900/40 border-t border-slate-800/80 flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center space-x-2">
                    <button
                      onClick={() => handleSwap(pair.id)}
                      className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium transition-colors"
                      title="Swap Winner and Loser"
                    >
                      <ArrowRightLeft className="w-3.5 h-3.5" />
                      <span>Swap Winner</span>
                    </button>
                    <button
                      onClick={() => handleIgnore(pair.id)}
                      className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200 text-xs font-medium transition-colors"
                      title="Ignore this pair"
                    >
                      <EyeOff className="w-3.5 h-3.5" />
                      <span>Ignore</span>
                    </button>
                  </div>

                  <div className="flex items-center space-x-2">
                    <button
                      onClick={() => handleForceDelete(pair)}
                      className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/20 text-xs font-medium transition-colors"
                      title="Bypass Seeding Retention & Force Delete"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                      <span>Force Delete</span>
                    </button>
                    <button
                      onClick={() => handleApprove(pair.id)}
                      className="flex items-center space-x-1.5 px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-md shadow-emerald-950/40 transition-colors"
                    >
                      <Check className="w-3.5 h-3.5" />
                      <span>Approve Decision</span>
                    </button>
                  </div>
                </div>
              </div>
            ))}

            {/* Pagination Controls */}
            {data.pages > 1 && (
              <div className="flex items-center justify-between p-4 glass-card">
                <span className="text-xs text-slate-400">
                  Showing page <span className="font-bold text-white">{data.page}</span> of{' '}
                  <span className="font-bold text-white">{data.pages}</span> ({data.total} total)
                </span>
                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={data.page <= 1}
                    className="p-2 rounded-lg bg-slate-800 text-slate-300 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-700 transition-colors"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
                    disabled={data.page >= data.pages}
                    className="p-2 rounded-lg bg-slate-800 text-slate-300 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-700 transition-colors"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Confirmation Modal */}
      <ConfirmDialog
        isOpen={confirmDialog.isOpen}
        title={confirmDialog.title}
        message={confirmDialog.message}
        isDestructive={confirmDialog.isDestructive}
        onConfirm={confirmDialog.onConfirm}
        onCancel={() => setConfirmDialog((prev) => ({ ...prev, isOpen: false }))}
      />
    </div>
  );
};
