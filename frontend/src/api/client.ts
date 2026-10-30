/** API client wrapper for communication with the ArrClean backend REST API. */

import type {
  AppSettings,
  BreakdownData,
  ConnectionTestResult,
  DashboardStats,
  DuplicatePair,
  HistoryPoint,
  PaginatedResponse,
  RecentActivity,
  SeedLockEntry,
} from './types';

const API_BASE = '/api/v1';

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const headers = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
    ...options.headers,
  };

  const response = await fetch(url, { ...options, headers });

  if (!response.ok) {
    let errorDetail = response.statusText;
    try {
      const errorJson = await response.json();
      errorDetail = errorJson.detail || errorJson.error || response.statusText;
    } catch {
      // ignore json parse error
    }
    throw new Error(errorDetail || `HTTP error ${response.status}`);
  }

  return response.json();
}

export const api = {
  // Dashboard
  getDashboardStats: () => request<DashboardStats>('/dashboard/stats'),
  getDashboardHistory: (days: number = 30) =>
    request<HistoryPoint[]>(`/dashboard/history?days=${days}`),
  getDashboardBreakdown: () => request<BreakdownData>('/dashboard/breakdown'),
  getRecentActivity: (limit: number = 10) =>
    request<RecentActivity[]>(`/dashboard/recent-activity?limit=${limit}`),

  // Duplicates
  listDuplicates: (params: {
    page?: number;
    limit?: number;
    status?: string;
    media_type?: string;
    search?: string;
  }) => {
    const searchParams = new URLSearchParams();
    if (params.page) searchParams.set('page', params.page.toString());
    if (params.limit) searchParams.set('limit', params.limit.toString());
    if (params.status) searchParams.set('status', params.status);
    if (params.media_type) searchParams.set('media_type', params.media_type);
    if (params.search) searchParams.set('search', params.search);
    return request<PaginatedResponse<DuplicatePair>>(
      `/duplicates?${searchParams.toString()}`
    );
  },
  getDuplicate: (id: number) => request<DuplicatePair>(`/duplicates/${id}`),
  approveDuplicate: (id: number) =>
    request<{ status: string; result: any }>(`/duplicates/${id}/approve`, {
      method: 'POST',
    }),
  swapDuplicate: (id: number) =>
    request<{ status: string; pair: DuplicatePair }>(`/duplicates/${id}/swap`, {
      method: 'POST',
    }),
  ignoreDuplicate: (id: number) =>
    request<{ status: string; id: number }>(`/duplicates/${id}/ignore`, {
      method: 'POST',
    }),
  forceDeleteDuplicate: (id: number) =>
    request<{ status: string; result: any }>(
      `/duplicates/${id}/force-delete`,
      { method: 'POST' }
    ),
  approveAllDuplicates: () =>
    request<{ status: string; count: number; cleanup_summary: any }>(
      '/duplicates/approve-all',
      { method: 'POST' }
    ),

  // Seed Watch
  getSeedWatchList: () => request<SeedLockEntry[]>('/seed-watch'),
  forcePurgeSeedEntry: (id: number) =>
    request<{ status: string; id: number }>(`/seed-watch/${id}`, {
      method: 'DELETE',
    }),
  triggerSeedCheck: () =>
    request<{ status: string; summary: any }>('/seed-watch/check', {
      method: 'POST',
    }),

  // Settings & Scan Controls
  getSettings: () => request<AppSettings>('/settings'),
  updateSettings: (settings: Partial<AppSettings>) =>
    request<{ status: string; updated_keys: string[] }>('/settings', {
      method: 'PUT',
      body: JSON.stringify(settings),
    }),
  triggerScan: () =>
    request<{ status: string; message: string }>('/settings/scan/trigger', {
      method: 'POST',
    }),
  getScanStatus: () =>
    request<{ status: 'idle' | 'running'; job: any | null }>(
      '/settings/scan/status'
    ),
  resetStats: () =>
    request<{ status: string; message: string }>('/settings/reset-stats', {
      method: 'POST',
    }),

  // Connections
  getConnectionsStatus: () => request<Record<string, any>>('/connections/status'),
  testConnection: (data: {
    service: string;
    url?: string;
    token?: string;
    apikey?: string;
    username?: string;
    password?: string;
  }) =>
    request<ConnectionTestResult>('/connections/test', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  testNotification: (channel: string) =>
    request<{ status: string; results: any }>(
      '/connections/test-notification',
      {
        method: 'POST',
        body: JSON.stringify({ channel }),
      }
    ),
};
