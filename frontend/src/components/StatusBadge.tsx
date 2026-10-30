import React from 'react';
import { STATUS_CONFIG, SEED_LOCK_STATUS_CONFIG } from '../utils/constants';
import type { DuplicatePairStatus, SeedLockStatus } from '../api/types';

interface StatusBadgeProps {
  status: DuplicatePairStatus | SeedLockStatus;
  type?: 'pair' | 'seed';
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  type = 'pair',
}) => {
  const config =
    type === 'pair'
      ? STATUS_CONFIG[status as DuplicatePairStatus] || {
          label: status,
          bg: 'bg-slate-500/10',
          text: 'text-slate-400',
          border: 'border-slate-500/30',
        }
      : SEED_LOCK_STATUS_CONFIG[status as SeedLockStatus] || {
          label: status,
          bg: 'bg-slate-500/10',
          text: 'text-slate-400',
          border: 'border-slate-500/30',
        };

  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${config.bg} ${config.text} ${config.border}`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current mr-1.5 opacity-80" />
      {config.label}
    </span>
  );
};
