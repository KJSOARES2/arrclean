import React from 'react';
import { LucideIcon, Sparkles } from 'lucide-react';

interface EmptyStateProps {
  title: string;
  description: string;
  icon?: LucideIcon;
  actionText?: string;
  onAction?: () => void;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title,
  description,
  icon: Icon = Sparkles,
  actionText,
  onAction,
}) => (
  <div className="flex flex-col items-center justify-center p-12 text-center border border-dashed border-slate-800 rounded-2xl bg-slate-900/30">
    <div className="w-12 h-12 rounded-xl bg-slate-800/80 flex items-center justify-center mb-4 text-slate-400">
      <Icon className="w-6 h-6" />
    </div>
    <h3 className="text-base font-semibold text-slate-200">{title}</h3>
    <p className="text-sm text-slate-400 max-w-sm mt-1">{description}</p>
    {actionText && onAction && (
      <button
        onClick={onAction}
        className="mt-4 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm font-medium transition-colors shadow-lg shadow-emerald-900/20"
      >
        {actionText}
      </button>
    )}
  </div>
);
