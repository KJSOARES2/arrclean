import React, { useState, useEffect } from 'react';
import {
  ShieldAlert,
  Save,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Send,
  Trash2,
  Server,
  Bell,
  Sliders,
  Clock,
  Sparkles,
} from 'lucide-react';
import { Header } from '../components/Header';
import { LoadingSpinner } from '../components/LoadingSpinner';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { usePolling } from '../hooks/usePolling';
import { api } from '../api/client';
import type { AppSettings } from '../api/types';

export const Settings: React.FC = () => {
  const { data: initialSettings, loading, refresh } = usePolling(api.getSettings, 0);

  const [form, setForm] = useState<Partial<AppSettings>>({});
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Connection test states: { [service]: { loading, success, error, details } }
  const [testStates, setTestStates] = useState<Record<string, any>>({});
  const [notificationTestStates, setNotificationTestStates] = useState<Record<string, any>>({});

  const [confirmReset, setConfirmReset] = useState(false);

  useEffect(() => {
    if (initialSettings) {
      setForm(initialSettings);
    }
  }, [initialSettings]);

  const handleChange = (key: keyof AppSettings, value: any) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      await api.updateSettings(form);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
      refresh();
    } catch (e) {
      alert(`Error saving settings: ${e}`);
    } finally {
      setSaving(false);
    }
  };

  const handleTestService = async (service: string) => {
    setTestStates((prev) => ({ ...prev, [service]: { loading: true } }));
    try {
      let reqData: any = { service };
      if (service === 'plex') {
        reqData.url = form.PLEX_URL;
        reqData.token = form.PLEX_TOKEN;
      } else if (service === 'radarr') {
        reqData.url = form.RADARR_URL;
        reqData.apikey = form.RADARR_APIKEY;
      } else if (service === 'sonarr') {
        reqData.url = form.SONARR_URL;
        reqData.apikey = form.SONARR_APIKEY;
      } else if (service === 'qbittorrent') {
        reqData.url = form.QBITTORRENT_URL;
        reqData.username = form.QBITTORRENT_USERNAME;
        reqData.password = form.QBITTORRENT_PASSWORD;
      } else if (service === 'sabnzbd') {
        reqData.url = form.SABNZBD_URL;
        reqData.apikey = form.SABNZBD_APIKEY;
      } else if (service === 'overseerr') {
        reqData.url = form.OVERSEERR_URL;
        reqData.apikey = form.OVERSEERR_APIKEY;
      } else if (service === 'prowlarr') {
        reqData.url = form.PROWLARR_URL;
        reqData.apikey = form.PROWLARR_APIKEY;
      }

      const res = await api.testConnection(reqData);
      setTestStates((prev) => ({
        ...prev,
        [service]: {
          loading: false,
          success: res.success,
          error: res.error,
          details: res.details,
        },
      }));
    } catch (e: any) {
      setTestStates((prev) => ({
        ...prev,
        [service]: { loading: false, success: false, error: e.message },
      }));
    }
  };

  const handleTestNotification = async (channel: string) => {
    setNotificationTestStates((prev) => ({ ...prev, [channel]: { loading: true } }));
    try {
      const res = await api.testNotification(channel);
      setNotificationTestStates((prev) => ({
        ...prev,
        [channel]: { loading: false, success: true, results: res.results },
      }));
    } catch (e: any) {
      setNotificationTestStates((prev) => ({
        ...prev,
        [channel]: { loading: false, success: false, error: e.message },
      }));
    }
  };

  const handleResetData = async () => {
    try {
      await api.resetStats();
      setConfirmReset(false);
      alert('All duplicate records and job history have been reset.');
      refresh();
    } catch (e) {
      alert(`Error resetting data: ${e}`);
    }
  };

  if (loading && !initialSettings) {
    return <LoadingSpinner message="Loading application settings..." />;
  }

  const dryRun = form.DRY_RUN ?? true;

  return (
    <div className="flex-1 flex flex-col">
      <Header
        title="Settings & Safety Controls"
        subtitle="Manage service connections, seeding retention rules, scoring weights, and automation schedules"
      />

      <div className="p-8 space-y-8 max-w-5xl w-full mx-auto pb-24">
        {/* Safety Warning Banner if Live */}
        {!dryRun ? (
          <div className="glass-card p-5 border-rose-500/40 bg-rose-950/20 flex items-start space-x-4 animate-pulse">
            <div className="p-2.5 rounded-xl bg-rose-500/10 text-rose-400 border border-rose-500/30 shrink-0">
              <ShieldAlert className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-rose-300 tracking-tight">
                CRITICAL WARNING: Dry-Run Mode is Disabled!
              </h3>
              <p className="text-xs text-rose-200/80 mt-1 leading-relaxed">
                Live deletion mode is ACTIVE. Approved duplicate cleanups will permanently purge inferior files and torrents from your media storage and qBittorrent client according to seeding policy rules.
              </p>
            </div>
          </div>
        ) : (
          <div className="glass-card p-4 border-amber-500/20 bg-amber-950/10 flex items-center space-x-3 text-amber-300 text-xs">
            <CheckCircle2 className="w-5 h-5 text-amber-400 shrink-0" />
            <span>
              <strong>Dry-Run Mode Enabled (Default Safe State):</strong> Scans will simulate deletions and calculate potential storage savings without modifying files on disk or deleting torrents.
            </span>
          </div>
        )}

        {/* 1. General & Safety */}
        <div className="glass-card p-6 space-y-6">
          <div className="flex items-center space-x-3 border-b border-slate-800 pb-4">
            <div className="p-2 rounded-xl bg-slate-800 text-slate-300">
              <Clock className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white tracking-tight">
                General Automation & Safety
              </h2>
              <p className="text-xs text-slate-400">
                Configure safety barriers, scan crons, and edition matching
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Dry-Run Toggle */}
            <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 flex items-center justify-between">
              <div>
                <span className="text-sm font-semibold text-white block">
                  Dry-Run Mode
                </span>
                <span className="text-xs text-slate-400 block mt-0.5">
                  Simulate actions without deleting files
                </span>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={form.DRY_RUN ?? true}
                  onChange={(e) => handleChange('DRY_RUN', e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-600"></div>
              </label>
            </div>

            {/* Edition Consolidation Toggle */}
            <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 flex items-center justify-between">
              <div>
                <span className="text-sm font-semibold text-white block">
                  Consolidate Movie Editions
                </span>
                <span className="text-xs text-slate-400 block mt-0.5">
                  Compare Director's / Theatrical cuts as duplicates
                </span>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={form.EDITION_CONSOLIDATE ?? true}
                  onChange={(e) => handleChange('EDITION_CONSOLIDATE', e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-600"></div>
              </label>
            </div>

            {/* Scan Cron */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-300">
                Full Scan Cron Schedule
              </label>
              <input
                type="text"
                value={form.SCAN_CRON || ''}
                onChange={(e) => handleChange('SCAN_CRON', e.target.value)}
                placeholder="0 3 * * *"
                className="w-full px-3.5 py-2 bg-slate-900 border border-slate-800 rounded-xl text-xs text-slate-200 font-mono focus:outline-none focus:border-emerald-500"
              />
              <span className="text-[11px] text-slate-500">
                Default: 0 3 * * * (Daily at 3:00 AM)
              </span>
            </div>

            {/* Seed Monitor Interval */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-300">
                Seed Watchdog Interval (Minutes)
              </label>
              <input
                type="number"
                min={1}
                value={form.SEED_MONITOR_INTERVAL_MINUTES || 30}
                onChange={(e) =>
                  handleChange('SEED_MONITOR_INTERVAL_MINUTES', parseInt(e.target.value) || 30)
                }
                className="w-full px-3.5 py-2 bg-slate-900 border border-slate-800 rounded-xl text-xs text-slate-200 font-mono focus:outline-none focus:border-emerald-500"
              />
            </div>
          </div>
        </div>

        {/* 2. qBittorrent Seeding Policy Thresholds */}
        <div className="glass-card p-6 space-y-6">
          <div className="flex items-center space-x-3 border-b border-slate-800 pb-4">
            <div className="p-2 rounded-xl bg-blue-500/10 text-blue-400 border border-blue-500/20">
              <Sliders className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white tracking-tight">
                qBittorrent Seeding Policy Rules
              </h2>
              <p className="text-xs text-slate-400">
                A torrent-backed duplicate is purged ONLY when ratio OR seeding duration threshold is satisfied
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-300">
                Minimum Share Ratio Threshold
              </label>
              <input
                type="number"
                step="0.1"
                min="0"
                value={form.MIN_SEED_RATIO ?? 1.0}
                onChange={(e) =>
                  handleChange('MIN_SEED_RATIO', parseFloat(e.target.value) || 1.0)
                }
                className="w-full px-3.5 py-2 bg-slate-900 border border-slate-800 rounded-xl text-xs text-slate-200 font-mono focus:outline-none focus:border-emerald-500"
              />
              <span className="text-[11px] text-slate-500">
                Default: 1.0 (seed at least 1:1 before purge)
              </span>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-300">
                Minimum Seeding Duration (Days)
              </label>
              <input
                type="number"
                min="1"
                value={form.MIN_SEED_DAYS ?? 90}
                onChange={(e) =>
                  handleChange('MIN_SEED_DAYS', parseInt(e.target.value) || 90)
                }
                className="w-full px-3.5 py-2 bg-slate-900 border border-slate-800 rounded-xl text-xs text-slate-200 font-mono focus:outline-none focus:border-emerald-500"
              />
              <span className="text-[11px] text-slate-500">
                Default: 90 days (3 months retention safeguard)
              </span>
            </div>
          </div>
        </div>

        {/* 3. Service Integrations */}
        <div className="glass-card p-6 space-y-6">
          <div className="flex items-center space-x-3 border-b border-slate-800 pb-4">
            <div className="p-2 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/20">
              <Server className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white tracking-tight">
                Connected Media Services
              </h2>
              <p className="text-xs text-slate-400">
                API credentials for Plex, Radarr, Sonarr, qBittorrent, SABnzbd, Overseerr, and Prowlarr
              </p>
            </div>
          </div>

          <div className="space-y-6">
            {/* Plex */}
            <div className="p-4 rounded-xl bg-slate-900/50 border border-slate-800 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-bold text-white">Plex Media Server</span>
                <button
                  type="button"
                  onClick={() => handleTestService('plex')}
                  disabled={testStates.plex?.loading}
                  className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-200 rounded-lg flex items-center space-x-1.5 transition-colors"
                >
                  <RefreshCw
                    className={`w-3 h-3 ${testStates.plex?.loading ? 'animate-spin' : ''}`}
                  />
                  <span>Test Connection</span>
                </button>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <input
                  type="text"
                  placeholder="http://192.168.1.50:32400"
                  value={form.PLEX_URL || ''}
                  onChange={(e) => handleChange('PLEX_URL', e.target.value)}
                  className="px-3 py-2 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-200 font-mono"
                />
                <input
                  type="password"
                  placeholder="X-Plex-Token"
                  value={form.PLEX_TOKEN || ''}
                  onChange={(e) => handleChange('PLEX_TOKEN', e.target.value)}
                  className="px-3 py-2 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-200 font-mono"
                />
              </div>
              {testStates.plex && (
                <div
                  className={`text-xs flex items-center space-x-1.5 ${
                    testStates.plex.success ? 'text-emerald-400' : 'text-rose-400'
                  }`}
                >
                  {testStates.plex.success ? (
                    <CheckCircle2 className="w-3.5 h-3.5" />
                  ) : (
                    <XCircle className="w-3.5 h-3.5" />
                  )}
                  <span>
                    {testStates.plex.success
                      ? 'Connected successfully to Plex!'
                      : `Error: ${testStates.plex.error}`}
                  </span>
                </div>
              )}
            </div>

            {/* Radarr */}
            <div className="p-4 rounded-xl bg-slate-900/50 border border-slate-800 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-bold text-white">Radarr (v3 / v4 / v5)</span>
                <button
                  type="button"
                  onClick={() => handleTestService('radarr')}
                  disabled={testStates.radarr?.loading}
                  className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-200 rounded-lg flex items-center space-x-1.5 transition-colors"
                >
                  <RefreshCw
                    className={`w-3 h-3 ${testStates.radarr?.loading ? 'animate-spin' : ''}`}
                  />
                  <span>Test Connection</span>
                </button>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <input
                  type="text"
                  placeholder="http://192.168.1.50:7878"
                  value={form.RADARR_URL || ''}
                  onChange={(e) => handleChange('RADARR_URL', e.target.value)}
                  className="px-3 py-2 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-200 font-mono"
                />
                <input
                  type="password"
                  placeholder="Radarr API Key"
                  value={form.RADARR_APIKEY || ''}
                  onChange={(e) => handleChange('RADARR_APIKEY', e.target.value)}
                  className="px-3 py-2 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-200 font-mono"
                />
              </div>
              {testStates.radarr && (
                <div
                  className={`text-xs flex items-center space-x-1.5 ${
                    testStates.radarr.success ? 'text-emerald-400' : 'text-rose-400'
                  }`}
                >
                  {testStates.radarr.success ? (
                    <CheckCircle2 className="w-3.5 h-3.5" />
                  ) : (
                    <XCircle className="w-3.5 h-3.5" />
                  )}
                  <span>
                    {testStates.radarr.success
                      ? 'Connected successfully to Radarr!'
                      : `Error: ${testStates.radarr.error}`}
                  </span>
                </div>
              )}
            </div>

            {/* Sonarr */}
            <div className="p-4 rounded-xl bg-slate-900/50 border border-slate-800 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-bold text-white">Sonarr (v3 / v4)</span>
                <button
                  type="button"
                  onClick={() => handleTestService('sonarr')}
                  disabled={testStates.sonarr?.loading}
                  className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-200 rounded-lg flex items-center space-x-1.5 transition-colors"
                >
                  <RefreshCw
                    className={`w-3 h-3 ${testStates.sonarr?.loading ? 'animate-spin' : ''}`}
                  />
                  <span>Test Connection</span>
                </button>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <input
                  type="text"
                  placeholder="http://192.168.1.50:8989"
                  value={form.SONARR_URL || ''}
                  onChange={(e) => handleChange('SONARR_URL', e.target.value)}
                  className="px-3 py-2 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-200 font-mono"
                />
                <input
                  type="password"
                  placeholder="Sonarr API Key"
                  value={form.SONARR_APIKEY || ''}
                  onChange={(e) => handleChange('SONARR_APIKEY', e.target.value)}
                  className="px-3 py-2 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-200 font-mono"
                />
              </div>
              {testStates.sonarr && (
                <div
                  className={`text-xs flex items-center space-x-1.5 ${
                    testStates.sonarr.success ? 'text-emerald-400' : 'text-rose-400'
                  }`}
                >
                  {testStates.sonarr.success ? (
                    <CheckCircle2 className="w-3.5 h-3.5" />
                  ) : (
                    <XCircle className="w-3.5 h-3.5" />
                  )}
                  <span>
                    {testStates.sonarr.success
                      ? 'Connected successfully to Sonarr!'
                      : `Error: ${testStates.sonarr.error}`}
                  </span>
                </div>
              )}
            </div>

            {/* qBittorrent */}
            <div className="p-4 rounded-xl bg-slate-900/50 border border-slate-800 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-bold text-white">qBittorrent (Web UI)</span>
                <button
                  type="button"
                  onClick={() => handleTestService('qbittorrent')}
                  disabled={testStates.qbittorrent?.loading}
                  className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-200 rounded-lg flex items-center space-x-1.5 transition-colors"
                >
                  <RefreshCw
                    className={`w-3 h-3 ${testStates.qbittorrent?.loading ? 'animate-spin' : ''}`}
                  />
                  <span>Test Connection</span>
                </button>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <input
                  type="text"
                  placeholder="http://192.168.1.50:8080"
                  value={form.QBITTORRENT_URL || ''}
                  onChange={(e) => handleChange('QBITTORRENT_URL', e.target.value)}
                  className="px-3 py-2 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-200 font-mono"
                />
                <input
                  type="text"
                  placeholder="Username (e.g. admin)"
                  value={form.QBITTORRENT_USERNAME || ''}
                  onChange={(e) => handleChange('QBITTORRENT_USERNAME', e.target.value)}
                  className="px-3 py-2 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-200"
                />
                <input
                  type="password"
                  placeholder="Password"
                  value={form.QBITTORRENT_PASSWORD || ''}
                  onChange={(e) => handleChange('QBITTORRENT_PASSWORD', e.target.value)}
                  className="px-3 py-2 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-200 font-mono"
                />
              </div>
              {testStates.qbittorrent && (
                <div
                  className={`text-xs flex items-center space-x-1.5 ${
                    testStates.qbittorrent.success ? 'text-emerald-400' : 'text-rose-400'
                  }`}
                >
                  {testStates.qbittorrent.success ? (
                    <CheckCircle2 className="w-3.5 h-3.5" />
                  ) : (
                    <XCircle className="w-3.5 h-3.5" />
                  )}
                  <span>
                    {testStates.qbittorrent.success
                      ? 'Connected successfully to qBittorrent!'
                      : `Error: ${testStates.qbittorrent.error}`}
                  </span>
                </div>
              )}
            </div>

            {/* SABnzbd */}
            <div className="p-4 rounded-xl bg-slate-900/50 border border-slate-800 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-bold text-white">SABnzbd (Usenet)</span>
                <button
                  type="button"
                  onClick={() => handleTestService('sabnzbd')}
                  disabled={testStates.sabnzbd?.loading}
                  className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-200 rounded-lg flex items-center space-x-1.5 transition-colors"
                >
                  <RefreshCw
                    className={`w-3 h-3 ${testStates.sabnzbd?.loading ? 'animate-spin' : ''}`}
                  />
                  <span>Test Connection</span>
                </button>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <input
                  type="text"
                  placeholder="http://192.168.1.50:8085"
                  value={form.SABNZBD_URL || ''}
                  onChange={(e) => handleChange('SABNZBD_URL', e.target.value)}
                  className="px-3 py-2 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-200 font-mono"
                />
                <input
                  type="password"
                  placeholder="SABnzbd API Key"
                  value={form.SABNZBD_APIKEY || ''}
                  onChange={(e) => handleChange('SABNZBD_APIKEY', e.target.value)}
                  className="px-3 py-2 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-200 font-mono"
                />
              </div>
              {testStates.sabnzbd && (
                <div
                  className={`text-xs flex items-center space-x-1.5 ${
                    testStates.sabnzbd.success ? 'text-emerald-400' : 'text-rose-400'
                  }`}
                >
                  {testStates.sabnzbd.success ? (
                    <CheckCircle2 className="w-3.5 h-3.5" />
                  ) : (
                    <XCircle className="w-3.5 h-3.5" />
                  )}
                  <span>
                    {testStates.sabnzbd.success
                      ? 'Connected successfully to SABnzbd!'
                      : `Error: ${testStates.sabnzbd.error}`}
                  </span>
                </div>
              )}
            </div>

            {/* Overseerr / Jellyseerr */}
            <div className="p-4 rounded-xl bg-slate-900/50 border border-slate-800 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-bold text-white">Overseerr / Jellyseerr</span>
                <button
                  type="button"
                  onClick={() => handleTestService('overseerr')}
                  disabled={testStates.overseerr?.loading}
                  className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-200 rounded-lg flex items-center space-x-1.5 transition-colors"
                >
                  <RefreshCw
                    className={`w-3 h-3 ${testStates.overseerr?.loading ? 'animate-spin' : ''}`}
                  />
                  <span>Test Connection</span>
                </button>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <input
                  type="text"
                  placeholder="http://192.168.1.50:5055"
                  value={form.OVERSEERR_URL || ''}
                  onChange={(e) => handleChange('OVERSEERR_URL', e.target.value)}
                  className="px-3 py-2 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-200 font-mono"
                />
                <input
                  type="password"
                  placeholder="Overseerr API Key"
                  value={form.OVERSEERR_APIKEY || ''}
                  onChange={(e) => handleChange('OVERSEERR_APIKEY', e.target.value)}
                  className="px-3 py-2 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-200 font-mono"
                />
              </div>
            </div>

            {/* Prowlarr */}
            <div className="p-4 rounded-xl bg-slate-900/50 border border-slate-800 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-bold text-white">Prowlarr (Indexer Manager)</span>
                <button
                  type="button"
                  onClick={() => handleTestService('prowlarr')}
                  disabled={testStates.prowlarr?.loading}
                  className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-200 rounded-lg flex items-center space-x-1.5 transition-colors"
                >
                  <RefreshCw
                    className={`w-3 h-3 ${testStates.prowlarr?.loading ? 'animate-spin' : ''}`}
                  />
                  <span>Test Connection</span>
                </button>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <input
                  type="text"
                  placeholder="http://192.168.1.50:9696"
                  value={form.PROWLARR_URL || ''}
                  onChange={(e) => handleChange('PROWLARR_URL', e.target.value)}
                  className="px-3 py-2 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-200 font-mono"
                />
                <input
                  type="password"
                  placeholder="Prowlarr API Key"
                  value={form.PROWLARR_APIKEY || ''}
                  onChange={(e) => handleChange('PROWLARR_APIKEY', e.target.value)}
                  className="px-3 py-2 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-200 font-mono"
                />
              </div>
            </div>
          </div>
        </div>

        {/* 4. Alert Notifications */}
        <div className="glass-card p-6 space-y-6">
          <div className="flex items-center space-x-3 border-b border-slate-800 pb-4">
            <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <Bell className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white tracking-tight">
                Notification Webhooks
              </h2>
              <p className="text-xs text-slate-400">
                Receive summaries after each cleanup run via Discord, Notifiarr, or Gotify
              </p>
            </div>
          </div>

          <div className="space-y-4">
            {/* Discord */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-slate-300">
                  Discord Webhook URL
                </label>
                <button
                  type="button"
                  onClick={() => handleTestNotification('discord')}
                  disabled={notificationTestStates.discord?.loading}
                  className="text-xs text-emerald-400 hover:text-emerald-300 flex items-center space-x-1"
                >
                  <Send className="w-3 h-3" />
                  <span>Send Test Ping</span>
                </button>
              </div>
              <input
                type="text"
                placeholder="https://discord.com/api/webhooks/..."
                value={form.DISCORD_WEBHOOK_URL || ''}
                onChange={(e) => handleChange('DISCORD_WEBHOOK_URL', e.target.value)}
                className="w-full px-3.5 py-2 bg-slate-900 border border-slate-800 rounded-xl text-xs text-slate-200 font-mono focus:outline-none focus:border-emerald-500"
              />
            </div>

            {/* Notifiarr */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-slate-300">
                  Notifiarr API Key
                </label>
                <button
                  type="button"
                  onClick={() => handleTestNotification('notifiarr')}
                  disabled={notificationTestStates.notifiarr?.loading}
                  className="text-xs text-emerald-400 hover:text-emerald-300 flex items-center space-x-1"
                >
                  <Send className="w-3 h-3" />
                  <span>Send Test Ping</span>
                </button>
              </div>
              <input
                type="password"
                placeholder="Notifiarr API Key"
                value={form.NOTIFIARR_APIKEY || ''}
                onChange={(e) => handleChange('NOTIFIARR_APIKEY', e.target.value)}
                className="w-full px-3.5 py-2 bg-slate-900 border border-slate-800 rounded-xl text-xs text-slate-200 font-mono focus:outline-none focus:border-emerald-500"
              />
            </div>

            {/* Gotify */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-slate-300">
                  Gotify Server URL
                </label>
                <input
                  type="text"
                  placeholder="https://gotify.example.com"
                  value={form.GOTIFY_URL || ''}
                  onChange={(e) => handleChange('GOTIFY_URL', e.target.value)}
                  className="w-full px-3.5 py-2 bg-slate-900 border border-slate-800 rounded-xl text-xs text-slate-200 font-mono"
                />
              </div>
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-slate-300">
                    Gotify Token
                  </label>
                  <button
                    type="button"
                    onClick={() => handleTestNotification('gotify')}
                    disabled={notificationTestStates.gotify?.loading}
                    className="text-xs text-emerald-400 hover:text-emerald-300 flex items-center space-x-1"
                  >
                    <Send className="w-3 h-3" />
                    <span>Ping</span>
                  </button>
                </div>
                <input
                  type="password"
                  placeholder="App Token"
                  value={form.GOTIFY_TOKEN || ''}
                  onChange={(e) => handleChange('GOTIFY_TOKEN', e.target.value)}
                  className="w-full px-3.5 py-2 bg-slate-900 border border-slate-800 rounded-xl text-xs text-slate-200 font-mono"
                />
              </div>
            </div>
          </div>
        </div>

        {/* 5. Save & Danger Zone */}
        <div className="flex flex-col md:flex-row items-center justify-between gap-4 pt-4">
          <button
            onClick={() => setConfirmReset(true)}
            className="flex items-center space-x-2 px-4 py-2.5 rounded-xl text-xs font-semibold text-rose-400 hover:text-rose-300 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/20 transition-colors"
          >
            <Trash2 className="w-4 h-4" />
            <span>Reset Database Telemetry</span>
          </button>

          <button
            onClick={handleSave}
            disabled={saving}
            className={`flex items-center space-x-2 px-6 py-2.5 rounded-xl text-xs font-bold transition-all shadow-lg ${
              saveSuccess
                ? 'bg-emerald-600 text-white'
                : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-950/40'
            }`}
          >
            {saving ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : saveSuccess ? (
              <CheckCircle2 className="w-4 h-4" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            <span>{saveSuccess ? 'Settings Saved!' : 'Save Configuration'}</span>
          </button>
        </div>
      </div>

      <ConfirmDialog
        isOpen={confirmReset}
        title="Reset All Database Statistics?"
        message="This will clear all discovered duplicate records, duplicate pairs, and scan job history from SQLite. Your actual media files and *arr configurations will NOT be touched."
        isDestructive={true}
        onConfirm={handleResetData}
        onCancel={() => setConfirmReset(false)}
      />
    </div>
  );
};
