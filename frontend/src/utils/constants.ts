/** Status badges, color maps, and display constants. */

import type { DuplicatePairStatus, SeedLockStatus } from '../api/types';

export const STATUS_CONFIG: Record<
  DuplicatePairStatus,
  { label: string; bg: string; text: string; border: string }
> = {
  PENDING_REVIEW: {
    label: 'Pending Review',
    bg: 'bg-amber-500/10',
    text: 'text-amber-400',
    border: 'border-amber-500/30',
  },
  APPROVED: {
    label: 'Approved',
    bg: 'bg-emerald-500/10',
    text: 'text-emerald-400',
    border: 'border-emerald-500/30',
  },
  SEED_LOCKED: {
    label: 'Seed-Locked',
    bg: 'bg-blue-500/10',
    text: 'text-blue-400',
    border: 'border-blue-500/30',
  },
  COMPLETED: {
    label: 'Completed',
    bg: 'bg-slate-500/10',
    text: 'text-slate-400',
    border: 'border-slate-500/30',
  },
  IGNORED: {
    label: 'Ignored',
    bg: 'bg-slate-700/20',
    text: 'text-slate-400',
    border: 'border-slate-700/40',
  },
  ERROR: {
    label: 'Error',
    bg: 'bg-rose-500/10',
    text: 'text-rose-400',
    border: 'border-rose-500/30',
  },
};

export const SEED_LOCK_STATUS_CONFIG: Record<
  SeedLockStatus,
  { label: string; bg: string; text: string; border: string }
> = {
  SEEDING: {
    label: 'Active Seeding',
    bg: 'bg-blue-500/10',
    text: 'text-blue-400',
    border: 'border-blue-500/30',
  },
  RATIO_MET: {
    label: 'Ratio Met',
    bg: 'bg-emerald-500/10',
    text: 'text-emerald-400',
    border: 'border-emerald-500/30',
  },
  TIME_MET: {
    label: 'Time Met',
    bg: 'bg-emerald-500/10',
    text: 'text-emerald-400',
    border: 'border-emerald-500/30',
  },
  PURGED: {
    label: 'Purged',
    bg: 'bg-slate-500/10',
    text: 'text-slate-400',
    border: 'border-slate-500/30',
  },
  ERROR: {
    label: 'Error',
    bg: 'bg-rose-500/10',
    text: 'text-rose-400',
    border: 'border-rose-500/30',
  },
};
