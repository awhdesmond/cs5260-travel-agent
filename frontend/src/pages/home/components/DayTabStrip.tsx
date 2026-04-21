import React from 'react';
import type { DayPlan } from '../types/itinerary';

interface DayTabStripProps {
  days: DayPlan[];
  totalDays: number;        // from itinerary_meta — drives skeleton count
  activeDay: number;        // 0-indexed
  onSelectDay: (index: number) => void;
}

/** Format a YYYY-MM-DD date string to "Apr 12" */
function formatTabDate(dateStr: string): string {
  try {
    const d = new Date(dateStr + 'T00:00:00');
    return d.toLocaleDateString('en-SG', { month: 'short', day: 'numeric' });
  } catch {
    return dateStr;
  }
}

/** Determine if all loaded days share the same city (for label simplification) */
function isSingleCity(days: DayPlan[]): boolean {
  if (days.length <= 1) return true;
  const firstCity = days[0]?.city;
  return days.every((d) => d.city === firstCity);
}

export default function DayTabStrip({ days, totalDays, activeDay, onSelectDay }: DayTabStripProps) {
  const singleCity = isSingleCity(days);

  return (
    <div className="px-6 overflow-x-auto flex gap-2 py-3 border-b border-stone-100 custom-scrollbar [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
      {Array.from({ length: totalDays }, (_, i) => {
        const day = days[i];
        const isActive = activeDay === i;

        if (!day) {
          // Skeleton tab — day not yet received
          return (
            <div
              key={i}
              onClick={() => onSelectDay(i)}
              className="bg-stone-200 rounded-lg px-4 py-2 min-w-[80px] animate-pulse cursor-pointer shrink-0"
            >
              <div className="h-3 w-12 bg-stone-300 rounded" />
            </div>
          );
        }

        // Ready tab
        return (
          <div
            key={i}
            onClick={() => onSelectDay(i)}
            className={[
              'px-4 py-2 min-w-[100px] shrink-0 cursor-pointer transition-colors rounded-t-lg flex flex-col gap-0.5',
              isActive
                ? 'bg-white border-b-2 border-black font-semibold text-stone-900'
                : 'bg-transparent text-stone-500 hover:bg-stone-100',
            ].join(' ')}
          >
            <span className="text-xs font-semibold whitespace-nowrap">
              Day {day.day_number}
              {day.date ? ` · ${formatTabDate(day.date)}` : ''}
              {!singleCity && day.city ? ` · ${day.city}` : ''}
            </span>
            <span className="text-[10px] text-stone-400">
              ~SGD {(day.daily_subtotal_sgd ?? 0).toFixed(0)}
            </span>
          </div>
        );
      })}
    </div>
  );
}
