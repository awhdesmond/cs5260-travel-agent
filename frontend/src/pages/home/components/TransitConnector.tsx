import React from 'react';
import type { TimeSlot } from '../types/itinerary';

interface TransitConnectorProps {
  slot: TimeSlot;
}

function _durationLabel(start: string, end?: string): string {
  if (!end) return '';
  const [sh, sm] = start.split(':').map(Number);
  const [eh, em] = end.split(':').map(Number);
  const mins = (eh * 60 + em) - (sh * 60 + sm);
  if (mins <= 0) return '';
  return mins < 60 ? `${mins}m` : `${Math.floor(mins / 60)}h${mins % 60 ? mins % 60 + 'm' : ''}`;
}

export default function TransitConnector({ slot }: TransitConnectorProps) {
  const isTransit = slot.slot_type === 'transit';
  const dur = _durationLabel(slot.start_time, slot.end_time);

  return (
    <div className="flex items-center gap-2 py-1 px-4">
      <div
        className={[
          'w-[3px] h-6',
          isTransit
            ? 'border-l border-dashed border-stone-300'
            : 'border-l border-dotted border-stone-200',
        ].join(' ')}
      />
      <div className="flex items-center gap-1.5">
        <span className="text-[10px] text-stone-500">
          {slot.label}
        </span>
        {dur && (
          <span className="text-[9px] text-stone-400 bg-stone-100 px-1.5 py-0.5 rounded-full">{dur}</span>
        )}
      </div>
    </div>
  );
}
