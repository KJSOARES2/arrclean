/** TypeScript models corresponding to ArrClean backend models and API contracts. */

export type MediaType = 'movie' | 'episode';

export type DuplicatePairStatus =
  | 'PENDING_REVIEW'
  | 'APPROVED'
  | 'SEED_LOCKED'
  | 'COMPLETED'
  | 'IGNORED'
  | 'ERROR';

export type ActionTaken =
  | 'NONE'
  | 'DELETED'
  | 'HARDLINK_REMOVED'
  | 'SEED_LOCK_QUEUED';

export type SeedLockStatus =
  | 'SEEDING'
  | 'RATIO_MET'
  | 'TIME_MET'
  | 'PURGED'
  | 'ERROR';

export interface DuplicateRecord {
  id: number;
  media_type: MediaType;
  tmdb_id?: number | null;
  tvdb_id?: number | null;
  imdb_id?: string | null;
  title: string;
  season?: number | null;
  episode?: number | null;
  edition?: string | null;
  file_path: string;
  file_size_bytes: number;
  resolution?: string | null;
  hdr_format?: string | null;
  source_type?: string | null;
  audio_codec?: string | null;
  video_codec?: string | null;
  video_bitrate?: number | null;
  custom_format_score?: number | null;
  quality_profile_rank?: number | null;
  composite_quality_score: number;
  is_hardlinked: boolean;
  inode_number?: number | null;
  torrent_hash?: string | null;
}

export interface DuplicatePair {
  id: number;
  media_type: MediaType;
  title: string;
  tmdb_id?: number | null;
  tvdb_id?: number | null;
  status: DuplicatePairStatus;
  action_taken: ActionTaken;
  space_saved_bytes: number;
  winner?: DuplicateRecord | null;
  loser?: DuplicateRecord | null;
  created_at: string;
  resolved_at?: string | null;
}

export interface SeedLockEntry {
  id: number;
  duplicate_pair_id: number;
  title: string;
  media_type: MediaType;
  torrent_name: string;
  torrent_hash: string;
  file_path: string;
  current_ratio: number;
  target_ratio: number;
  ratio_progress_percent: number;
  current_seed_days: number;
  target_seed_days: number;
  days_progress_percent: number;
  status: SeedLockStatus;
  estimated_unlock_date?: string | null;
  created_at?: string | null;
  purged_at?: string | null;
}

export interface DashboardStats {
  total_space_reclaimed_bytes: number;
  pending_space_to_reclaim_bytes: number;
  duplicates_found_count: number;
  duplicates_resolved_count: number;
  pending_review_count: number;
  seed_locked_count: number;
  active_scan?: {
    id: number;
    type: string;
    started_at: string;
  } | null;
  last_scan_completed_at?: string | null;
}

export interface HistoryPoint {
  date: string;
  space_reclaimed_bytes: number;
  space_reclaimed_gb: number;
  cumulative_gb: number;
  duplicates_resolved: number;
}

export interface ChartItem {
  name: string;
  value: number;
}

export interface BreakdownData {
  by_resolution: ChartItem[];
  by_hdr: ChartItem[];
  by_source: ChartItem[];
}

export interface RecentActivity {
  id: number;
  title: string;
  media_type: MediaType;
  status: DuplicatePairStatus;
  action_taken: ActionTaken;
  space_saved_bytes: number;
  created_at?: string | null;
  resolved_at?: string | null;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
  pages: number;
}

export interface AppSettings {
  DATABASE_URL: string;
  LOG_LEVEL: string;
  DRY_RUN: boolean;
  SCAN_CRON: string;
  SEED_MONITOR_INTERVAL_MINUTES: number;
  QUEUE_CHECK_INTERVAL_MINUTES: number;

  PLEX_URL: string;
  PLEX_TOKEN: string;
  PLEX_TOKEN_SET?: boolean;

  RADARR_URL: string;
  RADARR_APIKEY: string;
  RADARR_APIKEY_SET?: boolean;

  SONARR_URL: string;
  SONARR_APIKEY: string;
  SONARR_APIKEY_SET?: boolean;

  QBITTORRENT_URL: string;
  QBITTORRENT_USERNAME: string;
  QBITTORRENT_PASSWORD: string;
  QBITTORRENT_PASSWORD_SET?: boolean;

  SABNZBD_URL: string;
  SABNZBD_APIKEY: string;
  SABNZBD_APIKEY_SET?: boolean;

  OVERSEERR_URL: string;
  OVERSEERR_APIKEY: string;
  OVERSEERR_APIKEY_SET?: boolean;

  PROWLARR_URL: string;
  PROWLARR_APIKEY: string;
  PROWLARR_APIKEY_SET?: boolean;

  DISCORD_WEBHOOK_URL: string;
  NOTIFIARR_APIKEY: string;
  NOTIFIARR_APIKEY_SET?: boolean;
  GOTIFY_URL: string;
  GOTIFY_TOKEN: string;
  GOTIFY_TOKEN_SET?: boolean;

  MIN_SEED_RATIO: number;
  MIN_SEED_DAYS: number;
  EDITION_CONSOLIDATE: boolean;

  WEIGHT_RESOLUTION: number;
  WEIGHT_HDR: number;
  WEIGHT_SOURCE: number;
  WEIGHT_AUDIO: number;
  WEIGHT_CODEC: number;
}

export interface ConnectionTestResult {
  service: string;
  success: boolean;
  details: Record<string, any>;
  error?: string | null;
}

export interface LogMessage {
  timestamp: string;
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR';
  logger: string;
  message: string;
}
