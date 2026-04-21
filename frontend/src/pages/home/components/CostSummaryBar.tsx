import React, { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

interface CostBreakdown {
  activities: number;
  flights: number;
  hotels: number;
}

interface CostSummaryBarProps {
  grandTotal: number;
  architecture?: string;
  breakdown?: CostBreakdown;
}

export default function CostSummaryBar({ grandTotal, architecture, breakdown }: CostSummaryBarProps) {
  const [expanded, setExpanded] = useState(false);
  const safeTotal = typeof grandTotal === 'number' && isFinite(grandTotal) ? grandTotal : 0;
  const hasBreakdown = !!breakdown;

  return (
    <div className="px-6 py-3 bg-white border-b border-stone-200">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="flex flex-col gap-0.5">
            <span className="text-sm font-semibold text-stone-900">
              Total: SGD {safeTotal.toLocaleString('en-SG', { minimumFractionDigits: 2 })}
            </span>
            <span className="text-[10px] text-stone-400 italic">
              Estimated, actual prices may vary
            </span>
          </div>
          {hasBreakdown && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="ml-2 text-[10px] font-bold text-stone-500 hover:text-stone-700 bg-stone-100 hover:bg-stone-200 px-2 py-0.5 rounded-full transition-all cursor-pointer flex items-center gap-1"
            >
              Breakdown
              {expanded ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
            </button>
          )}
        </div>
        {architecture && (
          <span className="text-[9px] uppercase tracking-widest text-stone-400 bg-stone-100 px-2 py-0.5 rounded-full">
            {architecture}
          </span>
        )}
      </div>

      {expanded && hasBreakdown && (
        <div className="mt-2 flex items-center gap-4 text-[11px] text-stone-600">
          <span>Flights: <strong>{breakdown.flights > 0 ? `SGD ${breakdown.flights.toLocaleString('en-SG')}` : 'Price N/A'}</strong></span>
          <span className="text-stone-300">|</span>
          <span>Hotels: <strong>{breakdown.hotels > 0 ? `SGD ${breakdown.hotels.toLocaleString('en-SG')}` : 'Price N/A'}</strong></span>
          <span className="text-stone-300">|</span>
          <span>Activities & Meals: <strong>SGD {breakdown.activities.toLocaleString('en-SG')}</strong></span>
          {(breakdown.flights === 0 || breakdown.hotels === 0) && (
            <span className="text-[10px] text-stone-400 italic ml-1">(Total excludes N/A items)</span>
          )}
        </div>
      )}
    </div>
  );
}
