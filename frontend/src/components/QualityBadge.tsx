import React from 'react';

interface QualityBadgeProps {
  label: string;
  variant?: 'resolution' | 'hdr' | 'source' | 'audio' | 'codec' | 'score';
}

export const QualityBadge: React.FC<QualityBadgeProps> = ({
  label,
  variant = 'resolution',
}) => {
  if (!label) return null;

  let colorClasses = 'bg-slate-800 text-slate-300 border-slate-700';

  if (variant === 'resolution') {
    if (label.includes('2160') || label.toLowerCase().includes('4k')) {
      colorClasses = 'bg-purple-950/60 text-purple-300 border-purple-800/60';
    } else if (label.includes('1080')) {
      colorClasses = 'bg-blue-950/60 text-blue-300 border-blue-800/60';
    } else {
      colorClasses = 'bg-slate-800 text-slate-400 border-slate-700';
    }
  } else if (variant === 'hdr') {
    if (label.toLowerCase().includes('dolby vision') || label.toLowerCase().includes('dv')) {
      colorClasses = 'bg-amber-950/60 text-amber-300 border-amber-800/60';
    } else if (label.toLowerCase().includes('hdr')) {
      colorClasses = 'bg-orange-950/60 text-orange-300 border-orange-800/60';
    } else {
      colorClasses = 'bg-slate-800/80 text-slate-400 border-slate-700/80';
    }
  } else if (variant === 'score') {
    colorClasses = 'bg-emerald-950/60 text-emerald-300 border-emerald-800/60 font-semibold';
  } else if (variant === 'source') {
    if (label.toLowerCase().includes('remux')) {
      colorClasses = 'bg-emerald-950/60 text-emerald-300 border-emerald-800/60';
    } else if (label.toLowerCase().includes('bluray')) {
      colorClasses = 'bg-indigo-950/60 text-indigo-300 border-indigo-800/60';
    } else {
      colorClasses = 'bg-slate-800 text-slate-300 border-slate-700';
    }
  }

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-medium border ${colorClasses}`}
    >
      {label}
    </span>
  );
};
