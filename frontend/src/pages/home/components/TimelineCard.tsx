import React, { useState, useRef, useEffect } from 'react';
import { MapPin, Utensils, ExternalLink, GripVertical, X, ArrowRightLeft } from 'lucide-react';
import { clsx } from 'clsx';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import type { TimeSlot } from '../types/itinerary';

interface TimelineCardProps {
  slot: TimeSlot;
  slotId: string;
  pinNumber?: number;
  isActive: boolean;
  onSlotClick: (slotId: string) => void;
  editable?: boolean;
  onDelete?: () => void;
  onEdit?: (field: string, value: string) => void;
  totalDays?: number;
  currentDay?: number;
  onMoveToDay?: (targetDay: number) => void;
}

function _parseTime(t: string): number {
  const [h, m] = t.split(':').map(Number);
  return h * 60 + (m || 0);
}

function _formatDuration(startTime: string, endTime?: string): string {
  if (!endTime) return '';
  const mins = _parseTime(endTime) - _parseTime(startTime);
  if (mins <= 0) return '';
  if (mins < 60) return `${mins}m`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return m > 0 ? `${h}h${m}m` : `${h}h`;
}

function _timeOfDayTint(startTime: string): string {
  const mins = _parseTime(startTime);
  if (mins < 12 * 60) return 'bg-blue-50/40';    // morning
  if (mins < 17 * 60) return 'bg-amber-50/40';   // afternoon
  return 'bg-indigo-50/40';                        // evening
}

export default function TimelineCard({
  slot,
  slotId,
  pinNumber,
  isActive,
  onSlotClick,
  editable = false,
  onDelete,
  onEdit,
  totalDays,
  currentDay,
  onMoveToDay,
}: TimelineCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [editingStartTime, setEditingStartTime] = useState(false);
  const [editingEndTime, setEditingEndTime] = useState(false);
  const [editingNotes, setEditingNotes] = useState(false);
  const [showMoveMenu, setShowMoveMenu] = useState(false);
  const [startTimeVal, setStartTimeVal] = useState(slot.start_time || '');
  const [endTimeVal, setEndTimeVal] = useState(slot.end_time || '');
  const [notesVal, setNotesVal] = useState(slot.notes || '');
  const cardRef = useRef<HTMLDivElement>(null);

  const sortable = useSortable({ id: slotId, disabled: !editable });
  const style = editable
    ? { transform: CSS.Transform.toString(sortable.transform), transition: sortable.transition }
    : {};

  useEffect(() => {
    if (isActive) {
      cardRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [isActive]);

  useEffect(() => {
    setStartTimeVal(slot.start_time || '');
    setEndTimeVal(slot.end_time || '');
    setNotesVal(slot.notes || '');
  }, [slot.start_time, slot.end_time, slot.notes]);

  const venueName = slot.activity_name || slot.label;
  const isActivity = slot.slot_type === 'activity';
  const isMeal = slot.slot_type === 'meal';
  const duration = _formatDuration(slot.start_time, slot.end_time);
  const tint = _timeOfDayTint(slot.start_time);

  const handleClick = () => {
    setExpanded((prev) => !prev);
    onSlotClick(slotId);
  };

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    onDelete?.();
  };

  const handleStartTimeBlur = () => {
    setEditingStartTime(false);
    if (startTimeVal !== slot.start_time) {
      onEdit?.('start_time', startTimeVal);
    }
  };

  const handleEndTimeBlur = () => {
    setEditingEndTime(false);
    if (endTimeVal !== slot.end_time) {
      onEdit?.('end_time', endTimeVal);
    }
  };

  const handleNotesBlur = () => {
    setEditingNotes(false);
    if (notesVal !== slot.notes) {
      onEdit?.('notes', notesVal);
    }
  };

  const mapsUrl = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(venueName)}`;

  return (
    <div
      ref={(node) => {
        sortable.setNodeRef(node);
        (cardRef as React.MutableRefObject<HTMLDivElement | null>).current = node;
      }}
      id={slotId}
      style={style}
      onClick={handleClick}
      className={clsx(
        'border border-stone-200 rounded-xl p-4 shadow-sm cursor-pointer transition-all duration-200',
        'hover:shadow-md hover:-translate-y-0.5',
        tint,
        isActivity && 'border-l-[3px] border-l-blue-500',
        isMeal && 'border-l-[3px] border-l-amber-500',
        isActive && 'ring-2 ring-stone-900 ring-offset-2 shadow-md',
        sortable.isDragging && 'shadow-xl scale-105 opacity-80 ring-2 ring-stone-300 z-50'
      )}
    >
      {/* Top row */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-start gap-2 min-w-0">
          {editable && (
            <button
              {...sortable.listeners}
              {...sortable.attributes}
              onClick={(e) => e.stopPropagation()}
              className="cursor-grab active:cursor-grabbing p-1 text-stone-300 hover:text-stone-500 shrink-0 mt-0.5"
              aria-label="Drag to reorder"
            >
              <GripVertical size={14} />
            </button>
          )}
          {pinNumber != null ? (
            <span className={clsx(
              'flex items-center justify-center w-5 h-5 rounded-full text-white text-[10px] font-bold shrink-0 mt-0.5',
              isActivity ? 'bg-blue-500' : 'bg-amber-500',
            )}>
              {pinNumber}
            </span>
          ) : (
            <>
              {isActivity && <MapPin size={14} className="text-blue-500 shrink-0 mt-0.5" />}
              {isMeal && <Utensils size={14} className="text-amber-500 shrink-0 mt-0.5" />}
            </>
          )}
          <div className="min-w-0">
            <p className="text-sm font-semibold text-stone-900 truncate">{venueName}</p>
            {editable ? (
              <div className="flex items-center gap-1 text-xs text-stone-500" onClick={(e) => e.stopPropagation()}>
                {editingStartTime ? (
                  <input
                    autoFocus
                    type="text"
                    pattern="\d{2}:\d{2}"
                    value={startTimeVal}
                    onChange={(e) => setStartTimeVal(e.target.value)}
                    onBlur={handleStartTimeBlur}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleStartTimeBlur(); }}
                    className="w-14 border border-stone-300 rounded px-1 py-0.5 text-xs focus:outline-none focus:ring-1 focus:ring-stone-400"
                  />
                ) : (
                  <span
                    className="hover:text-stone-700 hover:underline cursor-text"
                    title="Click to edit"
                    onClick={() => setEditingStartTime(true)}
                  >
                    {startTimeVal || '??'}
                  </span>
                )}
                <span>–</span>
                {editingEndTime ? (
                  <input
                    autoFocus
                    type="text"
                    pattern="\d{2}:\d{2}"
                    value={endTimeVal}
                    onChange={(e) => setEndTimeVal(e.target.value)}
                    onBlur={handleEndTimeBlur}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleEndTimeBlur(); }}
                    className="w-14 border border-stone-300 rounded px-1 py-0.5 text-xs focus:outline-none focus:ring-1 focus:ring-stone-400"
                  />
                ) : (
                  <span
                    className="hover:text-stone-700 hover:underline cursor-text"
                    title="Click to edit"
                    onClick={() => setEditingEndTime(true)}
                  >
                    {endTimeVal || '?'}
                  </span>
                )}
                {duration && (
                  <span className="text-stone-400 ml-1">({duration})</span>
                )}
              </div>
            ) : (
              <div className="flex items-center gap-1">
                <p className="text-xs text-stone-500">
                  {slot.start_time}–{slot.end_time || '?'}
                </p>
                {duration && (
                  <span className="text-[10px] text-stone-400">({duration})</span>
                )}
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {slot.cost_sgd > 0 && (
            <span className="text-[10px] font-semibold bg-stone-100 text-stone-600 px-2 py-0.5 rounded-full whitespace-nowrap">
              SGD {slot.cost_sgd.toFixed(0)}
            </span>
          )}
          {/* Move to day (editable, multi-day) */}
          {editable && onMoveToDay && totalDays && totalDays > 1 && (
            <div className="relative" onClick={(e) => e.stopPropagation()}>
              <button
                onClick={() => setShowMoveMenu((v) => !v)}
                className="p-1 text-stone-300 hover:text-stone-600 transition-colors"
                aria-label="Move to another day"
                title="Move to another day"
              >
                <ArrowRightLeft size={12} />
              </button>
              {showMoveMenu && (
                <div className="absolute right-0 top-6 z-50 bg-white border border-stone-200 rounded-lg shadow-lg py-1 min-w-[80px]">
                  {Array.from({ length: totalDays }, (_, i) => i + 1)
                    .filter((d) => d !== currentDay)
                    .map((d) => (
                      <button
                        key={d}
                        onClick={() => {
                          onMoveToDay(d);
                          setShowMoveMenu(false);
                        }}
                        className="block w-full text-left px-3 py-1 text-xs text-stone-600 hover:bg-stone-50"
                      >
                        Day {d}
                      </button>
                    ))}
                </div>
              )}
            </div>
          )}
          {editable && (
            <button
              onClick={handleDelete}
              className="p-1 text-stone-300 hover:text-red-500 transition-colors"
              aria-label="Remove activity"
            >
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      {slot.image_url && (
        <img
          src={slot.image_url}
          alt={venueName}
          className="w-full h-24 object-cover rounded-lg mt-2"
          onError={(e) => { e.currentTarget.style.display = 'none'; }}
        />
      )}

      {slot.address && !expanded && (
        <p className="text-xs text-stone-500 truncate mt-1">{slot.address}</p>
      )}

      <div className={clsx('overflow-hidden transition-all duration-300', expanded ? 'max-h-96' : 'max-h-0')}>
        {editable ? (
          <div className="mt-3" onClick={(e) => e.stopPropagation()}>
            {editingNotes ? (
              <textarea
                autoFocus
                value={notesVal}
                onChange={(e) => setNotesVal(e.target.value)}
                onBlur={handleNotesBlur}
                placeholder="Add notes..."
                className="w-full text-sm text-stone-600 border border-stone-300 rounded p-2 focus:outline-none focus:ring-1 focus:ring-stone-400 resize-none"
                rows={3}
              />
            ) : (
              <p
                className="text-sm text-stone-600 cursor-text hover:bg-stone-50 rounded p-1 min-h-[1.5rem]"
                title="Click to edit notes"
                onClick={() => setEditingNotes(true)}
              >
                {notesVal || <span className="text-stone-300 italic">Add notes...</span>}
              </p>
            )}
          </div>
        ) : (
          slot.notes && <p className="text-sm text-stone-600 mt-3">{slot.notes}</p>
        )}
        {slot.address && (
          <p className="text-xs text-stone-500 mt-1">{slot.address}</p>
        )}
        <a
          href={mapsUrl}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="text-xs text-blue-600 hover:underline mt-1 inline-flex items-center gap-1"
        >
          <ExternalLink size={12} /> View on Google Maps
        </a>
      </div>
    </div>
  );
}
