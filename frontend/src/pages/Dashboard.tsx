import React from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
} from 'recharts';
import {
  HardDrive,
  Clock,
  Layers,
  Activity,
  ArrowUpRight,
  Sparkles,
} from 'lucide-react';
import { Header } from '../components/Header';
import { LoadingSpinner } from '../components/LoadingSpinner';
import { StatusBadge } from '../components/StatusBadge';
import { usePolling } from '../hooks/usePolling';
import { api } from '../api/client';
import { formatBytes, formatRelativeTime } from '../utils/formatters';

const PIE_COLORS = ['#10b981', '#3b82f6', '#8b5cf6', '#f59e0b', '#ec4899'];

export const Dashboard: React.FC = () => {
  const {
    data: stats,
    loading: statsLoading,
    refresh: refreshStats,
  } = usePolling(api.getDashboardStats, 10000);

  const {
    data: history,
    loading: historyLoading,
    refresh: refreshHistory,
  } = usePolling(() => api.getDashboardHistory(30), 30000);

  const {
    data: breakdown,
    loading: breakdownLoading,
    refresh: refreshBreakdown,
  } = usePolling(api.getDashboardBreakdown, 30000);

  const {
    data: activity,
    loading: activityLoading,
    refresh: refreshActivity,
  } = usePolling(() => api.getRecentActivity(10), 10000);

  const handleRefreshAll = () => {
    refreshStats();
    refreshHistory();
    refreshBreakdown();
    refreshActivity();
  };

  const isScanning = Boolean(stats?.active_scan);

  return (
    <div className="flex-1 flex flex-col">
      <Header
        title="Executive Telemetry"
        subtitle="Automated Media Quality Deduplication & Lifecycle Monitoring"
        onRefresh={handleRefreshAll}
        isScanning={isScanning}
      />

      <div className="p-8 space-y-8 max-w-7xl w-full mx-auto">
        {/* 1. Stat Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
          {/* Lifetime Reclaimed */}
          <div className="glass-card p-6 relative overflow-hidden group">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Space Reclaimed
              </span>
              <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                <HardDrive className="w-5 h-5" />
              </div>
            </div>
            <div className="mt-4">
              <div className="text-3xl font-bold tracking-tight text-white font-mono">
                {statsLoading ? '...' : formatBytes(stats?.total_space_reclaimed_bytes ?? 0)}
              </div>
              <div className="flex items-center text-xs text-emerald-400 mt-2 font-medium">
                <ArrowUpRight className="w-3.5 h-3.5 mr-0.5" />
                <span>{stats?.duplicates_resolved_count ?? 0} duplicates purged</span>
              </div>
            </div>
          </div>

          {/* Pending Reclaim (Seed-Locked) */}
          <div className="glass-card p-6 relative overflow-hidden group">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Pending Reclaim
              </span>
              <div className="p-2 rounded-xl bg-blue-500/10 text-blue-400 border border-blue-500/20">
                <Clock className="w-5 h-5" />
              </div>
            </div>
            <div className="mt-4">
              <div className="text-3xl font-bold tracking-tight text-white font-mono">
                {statsLoading ? '...' : formatBytes(stats?.pending_space_to_reclaim_bytes ?? 0)}
              </div>
              <div className="text-xs text-slate-400 mt-2">
                Locked in qBittorrent seeding ({stats?.seed_locked_count ?? 0} torrents)
              </div>
            </div>
          </div>

          {/* Duplicates Found */}
          <div className="glass-card p-6 relative overflow-hidden group">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Duplicates Detected
              </span>
              <div className="p-2 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/20">
                <Layers className="w-5 h-5" />
              </div>
            </div>
            <div className="mt-4">
              <div className="text-3xl font-bold tracking-tight text-white font-mono">
                {statsLoading ? '...' : stats?.duplicates_found_count ?? 0}
              </div>
              <div className="text-xs text-amber-400 mt-2 font-medium">
                {stats?.pending_review_count ?? 0} awaiting manual review
              </div>
            </div>
          </div>

          {/* Scan State */}
          <div className="glass-card p-6 relative overflow-hidden group">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Engine Status
              </span>
              <div
                className={`p-2 rounded-xl border ${
                  isScanning
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20 animate-pulse'
                    : 'bg-slate-800 text-slate-400 border-slate-700'
                }`}
              >
                <Activity className="w-5 h-5" />
              </div>
            </div>
            <div className="mt-4">
              <div className="text-xl font-bold tracking-tight text-white flex items-center space-x-2">
                <span
                  className={`w-2.5 h-2.5 rounded-full ${
                    isScanning ? 'bg-emerald-400 animate-ping' : 'bg-slate-500'
                  }`}
                />
                <span>{isScanning ? 'Scan Running' : 'Engine Idle'}</span>
              </div>
              <div className="text-xs text-slate-400 mt-2 font-mono">
                Last: {formatRelativeTime(stats?.last_scan_completed_at)}
              </div>
            </div>
          </div>
        </div>

        {/* 2. 30-Day Storage Reclaimed Area Chart */}
        <div className="glass-card p-6">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-base font-bold text-white tracking-tight">
                Cumulative Space Reclaimed (30 Days)
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Storage savings over time from automated deduplication & ratio expirations
              </p>
            </div>
            <span className="text-xs font-mono text-emerald-400 bg-emerald-500/10 px-2.5 py-1 rounded-lg border border-emerald-500/20">
              Gigabytes (GB)
            </span>
          </div>

          <div className="h-72 w-full">
            {historyLoading ? (
              <LoadingSpinner message="Loading historical telemetry..." />
            ) : !history || history.length === 0 ? (
              <div className="h-full flex items-center justify-center text-slate-500 text-sm">
                No historical savings recorded yet. Trigger a scan to get started.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart
                  data={history}
                  margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
                >
                  <defs>
                    <linearGradient id="colorReclaimed" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10b981" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis
                    dataKey="date"
                    stroke="#64748b"
                    fontSize={11}
                    tickFormatter={(str) => {
                      const parts = str.split('-');
                      return parts.length === 3 ? `${parts[1]}/${parts[2]}` : str;
                    }}
                  />
                  <YAxis stroke="#64748b" fontSize={11} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#0f172a',
                      borderColor: '#334155',
                      borderRadius: '0.75rem',
                      color: '#f8fafc',
                      fontSize: '12px',
                    }}
                    formatter={(val: any) => [`${val} GB`, 'Cumulative Reclaimed']}
                  />
                  <Area
                    type="monotone"
                    dataKey="cumulative_gb"
                    stroke="#10b981"
                    strokeWidth={2}
                    fillOpacity={1}
                    fill="url(#colorReclaimed)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* 3. Breakdown Charts Section */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Resolution Breakdown */}
          <div className="glass-card p-6 flex flex-col">
            <h3 className="text-sm font-bold text-white tracking-tight mb-1">
              By Resolution
            </h3>
            <p className="text-xs text-slate-400 mb-4">Duplicate distribution by video resolution</p>
            <div className="h-48 flex-1">
              {breakdownLoading ? (
                <LoadingSpinner />
              ) : !breakdown?.by_resolution?.length ? (
                <div className="h-full flex items-center justify-center text-xs text-slate-500">
                  No data available
                </div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={breakdown.by_resolution}
                      cx="50%"
                      cy="50%"
                      innerRadius={50}
                      outerRadius={75}
                      paddingAngle={4}
                      dataKey="value"
                    >
                      {breakdown.by_resolution.map((_, index) => (
                        <Cell
                          key={`cell-${index}`}
                          fill={PIE_COLORS[index % PIE_COLORS.length]}
                        />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#0f172a',
                        borderColor: '#334155',
                        borderRadius: '0.75rem',
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>
            <div className="flex flex-wrap gap-2 justify-center mt-2">
              {breakdown?.by_resolution?.map((item, idx) => (
                <span key={item.name} className="flex items-center text-xs text-slate-300">
                  <span
                    className="w-2.5 h-2.5 rounded-full mr-1.5"
                    style={{ backgroundColor: PIE_COLORS[idx % PIE_COLORS.length] }}
                  />
                  {item.name}: {item.value}
                </span>
              ))}
            </div>
          </div>

          {/* Dynamic Range Breakdown */}
          <div className="glass-card p-6 flex flex-col">
            <h3 className="text-sm font-bold text-white tracking-tight mb-1">
              By Dynamic Range
            </h3>
            <p className="text-xs text-slate-400 mb-4">HDR10 / Dolby Vision vs SDR</p>
            <div className="h-48 flex-1">
              {breakdownLoading ? (
                <LoadingSpinner />
              ) : !breakdown?.by_hdr?.length ? (
                <div className="h-full flex items-center justify-center text-xs text-slate-500">
                  No data available
                </div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={breakdown.by_hdr}
                      cx="50%"
                      cy="50%"
                      innerRadius={50}
                      outerRadius={75}
                      paddingAngle={4}
                      dataKey="value"
                    >
                      {breakdown.by_hdr.map((_, index) => (
                        <Cell
                          key={`cell-hdr-${index}`}
                          fill={PIE_COLORS[(index + 2) % PIE_COLORS.length]}
                        />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#0f172a',
                        borderColor: '#334155',
                        borderRadius: '0.75rem',
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>
            <div className="flex flex-wrap gap-2 justify-center mt-2">
              {breakdown?.by_hdr?.map((item, idx) => (
                <span key={item.name} className="flex items-center text-xs text-slate-300">
                  <span
                    className="w-2.5 h-2.5 rounded-full mr-1.5"
                    style={{ backgroundColor: PIE_COLORS[(idx + 2) % PIE_COLORS.length] }}
                  />
                  {item.name}: {item.value}
                </span>
              ))}
            </div>
          </div>

          {/* Source Breakdown (Usenet vs Torrent) */}
          <div className="glass-card p-6 flex flex-col">
            <h3 className="text-sm font-bold text-white tracking-tight mb-1">
              By Acquisition Source
            </h3>
            <p className="text-xs text-slate-400 mb-4">Usenet downloads vs Seeding torrents</p>
            <div className="h-48 flex-1">
              {breakdownLoading ? (
                <LoadingSpinner />
              ) : !breakdown?.by_source?.length ? (
                <div className="h-full flex items-center justify-center text-xs text-slate-500">
                  No data available
                </div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={breakdown.by_source} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis dataKey="name" stroke="#64748b" fontSize={11} />
                    <YAxis stroke="#64748b" fontSize={11} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#0f172a',
                        borderColor: '#334155',
                        borderRadius: '0.75rem',
                      }}
                    />
                    <Bar dataKey="value" fill="#3b82f6" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>
        </div>

        {/* 4. Recent Activity Stream */}
        <div className="glass-card p-6">
          <h2 className="text-base font-bold text-white tracking-tight mb-4">
            Recent Telemetry & Actions
          </h2>
          {activityLoading ? (
            <LoadingSpinner />
          ) : !activity || activity.length === 0 ? (
            <div className="text-center py-8 text-sm text-slate-500">
              No recent activity recorded.
            </div>
          ) : (
            <div className="divide-y divide-slate-800/60">
              {activity.map((act) => (
                <div
                  key={act.id}
                  className="py-3 flex items-center justify-between hover:bg-slate-800/30 px-3 rounded-lg transition-colors"
                >
                  <div className="flex items-center space-x-3">
                    <span className="text-xs font-mono uppercase px-2 py-0.5 rounded bg-slate-800 text-slate-400">
                      {act.media_type}
                    </span>
                    <span className="font-medium text-sm text-slate-200">{act.title}</span>
                  </div>
                  <div className="flex items-center space-x-4">
                    <span className="text-xs text-emerald-400 font-mono">
                      {act.space_saved_bytes > 0 ? `+${formatBytes(act.space_saved_bytes)} saved` : 'Seed-Locked'}
                    </span>
                    <StatusBadge status={act.status} />
                    <span className="text-xs text-slate-500 font-mono">
                      {formatRelativeTime(act.resolved_at || act.created_at)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
