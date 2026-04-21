import React from 'react';
import { Calendar, Cpu, Clock } from 'lucide-react';

interface ItineraryCardProps {
  id: string;
  destination: string;
  travel_dates: {
    start: string;
    end: string;
  };
  architecture: string;
  status?: string;
  created_at: string;
  onSelect: (id: string) => void;
}

const STATUS_BADGE: Record<string, { label: string; color: string }> = {
  confirmed: { label: 'Confirmed', color: 'bg-emerald-100 text-emerald-700' },
  sandbox_confirmed: { label: 'Sandbox', color: 'bg-amber-100 text-amber-700' },
  pending_approval: { label: 'Draft', color: 'bg-stone-100 text-stone-500' },
};

export default function ItineraryCard({ id, destination, travel_dates, architecture, status, created_at, onSelect }: ItineraryCardProps) {
  const badge = STATUS_BADGE[status || 'pending_approval'] || STATUS_BADGE.pending_approval;
  const formattedDate = new Date(created_at).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric'
  });

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onSelect(id)}
      onKeyDown={(e: React.KeyboardEvent) => { if (e.key === 'Enter') onSelect(id); }}
      className="group relative w-full bg-white border border-stone-100 rounded-[1.5rem] p-5 cursor-pointer transition-all duration-300 hover:shadow-xl hover:shadow-stone-200/50 hover:border-stone-200 hover:-translate-y-0.5 active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-stone-900 focus-visible:ring-offset-2"
    >
      {/* destination */}
      <h3 className="font-headline text-lg font-bold text-stone-800 mb-3 group-hover:text-black transition-colors truncate">
        {destination}
      </h3>

      <div className="flex flex-col gap-2.5">
        {/* Travel Dates */}
        <div className="flex items-center gap-2 text-stone-500">
          <Calendar size={14} className="text-stone-400 shrink-0" />
          <span className="text-xs font-semibold tracking-tight">
            {travel_dates?.start ?? '?'} to {travel_dates?.end ?? '?'}
          </span>
        </div>

        {/* Architecture + Status */}
        <div className="flex items-center gap-2 text-stone-500">
          <Cpu size={14} className="text-stone-400 shrink-0" />
          <span className="text-[10px] font-bold uppercase tracking-widest text-stone-400">
            {architecture}
          </span>
          <span className={`text-[9px] font-bold uppercase tracking-widest px-2 py-0.5 rounded-full ${badge.color}`}>
            {badge.label}
          </span>
        </div>
      </div>

      {/* Footer / Created At */}
      <div className="mt-5 pt-4 border-t border-stone-50 flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-stone-400">
          <Clock size={12} />
          <span className="text-[10px] font-medium uppercase tracking-tighter">
            Created {formattedDate}, {new Date(created_at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>
        
        <div className="text-[10px] font-bold text-stone-300 uppercase tracking-widest opacity-0 group-hover:opacity-100 transition-opacity">
          View Detail →
        </div>
      </div>
    </div>
  );
}
