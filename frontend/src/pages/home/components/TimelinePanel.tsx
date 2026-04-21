import React, { useMemo, useState, useEffect } from 'react';
import { Loader2, Hotel, AlertTriangle } from 'lucide-react';
import {
  DndContext,
  closestCenter,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  arrayMove,
  verticalListSortingStrategy,
  sortableKeyboardCoordinates,
} from '@dnd-kit/sortable';
import type { DayPlan, TimeSlot } from '../types/itinerary';
import TimelineCard from './TimelineCard';
import TransitConnector from './TransitConnector';

interface TimelinePanelProps {
  day: DayPlan | undefined;
  dayNumber: number;
  totalDays?: number;
  isLoading: boolean;
  activeSlotId: string | null;
  onSlotClick: (slotId: string) => void;
  onSlotsReorder?: (newSlots: TimeSlot[]) => void;
  onSlotDelete?: (slotIndex: number) => void;
  onSlotEdit?: (slotIndex: number, field: string, value: string) => void;
  onMoveToDay?: (slotIndex: number, targetDayIdx: number) => void;
  editable?: boolean;
  className?: string;
}

function _parseTime(t: string): number {
  const [h, m] = t.split(':').map(Number);
  return h * 60 + (m || 0);
}

function checkTimeConflicts(slots: TimeSlot[]): string[] {
  const warnings: string[] = [];
  const activityMealSlots = slots.filter(s => s.slot_type === 'activity' || s.slot_type === 'meal');
  for (let i = 0; i < activityMealSlots.length - 1; i++) {
    const curr = activityMealSlots[i];
    const next = activityMealSlots[i + 1];
    if (curr.end_time && next.start_time &&
        _parseTime(curr.end_time) > _parseTime(next.start_time)) {
      warnings.push(
        `Time conflict: "${curr.label}" ends at ${curr.end_time} but "${next.label}" starts at ${next.start_time}`
      );
    }
  }
  return warnings;
}

function checkOverflow(slots: TimeSlot[]): string[] {
  const warnings: string[] = [];
  for (const slot of slots) {
    if (slot.slot_type === 'transit' || slot.slot_type === 'buffer') continue;
    if (slot.end_time && _parseTime(slot.end_time) > 22 * 60) {
      warnings.push(`"${slot.label || slot.activity_name}" ends at ${slot.end_time}, past 22:00`);
    }
    if (slot.start_time && _parseTime(slot.start_time) < 7 * 60) {
      warnings.push(`"${slot.label || slot.activity_name}" starts at ${slot.start_time}, before 07:00`);
    }
  }
  return warnings;
}

export default function TimelinePanel({
  day,
  dayNumber,
  totalDays,
  isLoading,
  activeSlotId,
  onSlotClick,
  onSlotsReorder,
  onSlotDelete,
  onSlotEdit,
  onMoveToDay,
  editable = false,
  className,
}: TimelinePanelProps) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const sortableSlots = useMemo(() => {
    if (!day) return [];
    return day.time_slots
      .map((slot, index) => ({
        ...slot,
        _originalIndex: index,
        _slotId: `day-${day.day_number}-slot-${index}`,
      }))
      .filter(s => s.slot_type === 'activity' || s.slot_type === 'meal');
  }, [day]);

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id || !onSlotsReorder || !day) return;

    const oldIndex = sortableSlots.findIndex(s => s._slotId === active.id);
    const newIndex = sortableSlots.findIndex(s => s._slotId === over.id);
    const reordered = arrayMove(sortableSlots, oldIndex, newIndex);

    const newSlots = [...day.time_slots];
    let reorderIdx = 0;
    for (let i = 0; i < newSlots.length; i++) {
      if (newSlots[i].slot_type === 'activity' || newSlots[i].slot_type === 'meal') {
        if (reorderIdx < reordered.length) {
          newSlots[i] = reordered[reorderIdx];
          reorderIdx++;
        }
      }
    }
    onSlotsReorder(newSlots);
  };

  // Cycling status messages for day generation spinner
  const generatingHints = useMemo(() => [
    `Generating Day ${dayNumber}...`,
    'Scheduling activities...',
    'Adding meals...',
    'Optimizing routes...',
    'Finalizing schedule...',
  ], [dayNumber]);

  const [hintIdx, setHintIdx] = useState(0);
  useEffect(() => {
    if (!isLoading) { setHintIdx(0); return; }
    const timer = setInterval(() => setHintIdx((i) => (i + 1) % generatingHints.length), 2500);
    return () => clearInterval(timer);
  }, [isLoading, generatingHints]);

  // All hooks must be above early returns to avoid React ordering violations
  const pinNumberMap = useMemo(() => {
    if (!day) return new Map<number, number>();
    const map = new Map<number, number>();
    let pinNum = 0;
    day.time_slots.forEach((slot, index) => {
      if ((slot.slot_type === 'activity' || slot.slot_type === 'meal') && slot.lat && slot.lng) {
        pinNum++;
        map.set(index, pinNum);
      }
    });
    return map;
  }, [day]);

  if (isLoading) {
    return (
      <div className={['flex flex-col', className].filter(Boolean).join(' ')}>
        <div className="flex-1 flex flex-col items-center justify-center gap-3 text-stone-400">
          <Loader2 className="animate-spin" size={24} />
          <span className="text-sm font-medium transition-opacity duration-300">{generatingHints[hintIdx]}</span>
        </div>
      </div>
    );
  }

  if (!day) return null;

  const conflicts = editable ? checkTimeConflicts(day.time_slots) : [];
  const overflows = editable ? checkOverflow(day.time_slots) : [];
  const allWarnings = [...conflicts, ...overflows];

  const renderCards = () =>
    day.time_slots.map((slot, index) => {
      const slotId = `day-${day.day_number}-slot-${index}`;
      if (slot.slot_type === 'buffer' || slot.slot_type === 'transit') {
        return <TransitConnector key={slotId} slot={slot} />;
      }
      return (
        <TimelineCard
          key={slotId}
          slot={slot}
          slotId={slotId}
          pinNumber={pinNumberMap.get(index)}
          isActive={activeSlotId === slotId}
          onSlotClick={onSlotClick}
          editable={editable}
          onDelete={() => onSlotDelete?.(index)}
          onEdit={(field, value) => onSlotEdit?.(index, field, value)}
          totalDays={totalDays}
          currentDay={dayNumber}
          onMoveToDay={onMoveToDay ? (targetDay) => onMoveToDay(index, targetDay - 1) : undefined}
        />
      );
    });

  return (
    <div className={['flex flex-col overflow-hidden', className].filter(Boolean).join(' ')}>
      {day.hotel_name && (
        <div className="bg-stone-50 p-4 border-b border-stone-100 flex items-center gap-2 shrink-0">
          <Hotel size={16} className="text-stone-500" />
          <span className="text-xs font-semibold text-stone-600">{day.hotel_name}</span>
        </div>
      )}

      {allWarnings.length > 0 && (
        <div className="bg-amber-50 border-b border-amber-200 px-4 py-2 shrink-0 flex items-start gap-2">
          <AlertTriangle size={14} className="text-amber-500 shrink-0 mt-0.5" />
          <div>
            {allWarnings.map((w, i) => (
              <p key={i} className="text-xs text-amber-700">{w}</p>
            ))}
          </div>
        </div>
      )}

      <div className="overflow-y-auto custom-scrollbar p-4 flex flex-col gap-3 flex-1">
        {day.time_slots.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-2 text-stone-300 py-12">
            <span className="text-sm font-semibold text-stone-400">Free Day</span>
            <span className="text-xs text-stone-300">No activities scheduled. Add something via chat.</span>
          </div>
        ) : editable ? (
          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
            <SortableContext items={sortableSlots.map(s => s._slotId)} strategy={verticalListSortingStrategy}>
              {renderCards()}
            </SortableContext>
          </DndContext>
        ) : (
          renderCards()
        )}
      </div>
    </div>
  );
}
