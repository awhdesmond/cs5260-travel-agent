import React, { useState, useCallback, useRef } from 'react';
import { APIProvider } from '@vis.gl/react-google-maps';
import toast from 'react-hot-toast';
import type { DayPlan, DailySchedule, TimeSlot } from './types/itinerary';
import BreadcrumbNav from './components/BreadcrumbNav';
import CostSummaryBar from './components/CostSummaryBar';
import DayTabStrip from './components/DayTabStrip';
import TimelinePanel from './components/TimelinePanel';
import MapPanel from './components/MapPanel';
import ChatDrawer from './components/ChatDrawer';

interface DayViewProps {
  itinerary?: DailySchedule;
  days?: DayPlan[];
  totalDays?: number;
  destination?: string;
  onBack: () => void;
  editablePlanId?: string;
  editableThreadId?: string;
  setProgressiveDays?: React.Dispatch<React.SetStateAction<any[]>>;
  // Confirm/booking flow
  canConfirm?: boolean;
  onConfirm?: (bookingMode: 'search_recommend' | 'sandbox') => void;
  isConfirming?: boolean;
  // Historical booking info
  bookingStatus?: string;
  bookingConfirmationId?: string | null;
  bookingLinks?: any[] | null;
}

// ── Time helpers ──

function _timeToMinutes(t: string): number {
  const [h, m] = t.split(':').map(Number);
  return h * 60 + m;
}

function _minutesToTime(mins: number): string {
  const clamped = Math.max(0, Math.min(mins, 23 * 60 + 59));
  const h = Math.floor(clamped / 60);
  const m = clamped % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

function _snapTo15(mins: number): number {
  return Math.round(mins / 15) * 15;
}

function _slotDuration(slot: TimeSlot): number {
  if (!slot.start_time || !slot.end_time) return 60;
  const d = _timeToMinutes(slot.end_time) - _timeToMinutes(slot.start_time);
  return d > 0 ? d : 60;
}

function _haversineKm(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLng = ((lng2 - lng1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function _estimateTransitMinutes(km: number): { minutes: number; mode: string } {
  if (km < 1.5) return { minutes: Math.max(5, Math.ceil((km / 5) * 60)), mode: 'Walk' };
  return { minutes: Math.max(5, Math.ceil((km / 25) * 60)), mode: 'Drive' };
}

/** Recalculate times sequentially and update transit slots with estimated travel time. */
function _recalcTimesSequentially(slots: TimeSlot[]): TimeSlot[] {
  if (slots.length === 0) return slots;
  const result: TimeSlot[] = [];
  let cursor = slots[0].start_time ? _snapTo15(_timeToMinutes(slots[0].start_time)) : 9 * 60;

  let prevVenue: TimeSlot | null = null;

  for (const slot of slots) {
    if (slot.slot_type === 'transit' || slot.slot_type === 'buffer') {
      // Estimate transit time from previous venue to next venue
      let transitMins = _slotDuration(slot);
      let transitLabel = slot.label;

      if (prevVenue?.lat && prevVenue?.lng) {
        // Find the next venue slot
        const slotIdx = slots.indexOf(slot);
        const nextVenue = slots.slice(slotIdx + 1).find(
          (s) => s.slot_type === 'activity' || s.slot_type === 'meal',
        );
        if (nextVenue?.lat && nextVenue?.lng) {
          const km = _haversineKm(prevVenue.lat!, prevVenue.lng!, nextVenue.lat!, nextVenue.lng!);
          const est = _estimateTransitMinutes(km);
          transitMins = _snapTo15(est.minutes) || 15;
          transitLabel = `${est.mode} (~${km < 1 ? `${Math.round(km * 1000)}m` : `${km.toFixed(1)}km`})`;
        }
      }

      const newStart = _minutesToTime(cursor);
      const newEnd = _minutesToTime(cursor + transitMins);
      result.push({ ...slot, start_time: newStart, end_time: newEnd, label: transitLabel });
      cursor += transitMins;
    } else {
      const duration = _slotDuration(slot);
      const snappedStart = _snapTo15(cursor);
      const newStart = _minutesToTime(snappedStart);
      const newEnd = _minutesToTime(snappedStart + duration);
      result.push({ ...slot, start_time: newStart, end_time: newEnd });
      cursor = snappedStart + duration;
      prevVenue = slot;
    }
  }
  return result;
}

// ── Undo history ──

interface HistoryEntry {
  label: string;
  dayIndex: number;
  day: DayPlan;
}

const MAX_UNDO = 20;

// ── Component ──

export default function DayView({
  itinerary,
  days: progressiveDaysProp,
  totalDays: progressiveTotalDays,
  destination,
  onBack,
  editablePlanId,
  editableThreadId,
  setProgressiveDays,
  canConfirm,
  onConfirm,
  isConfirming,
  bookingStatus,
  bookingConfirmationId,
  bookingLinks,
}: DayViewProps) {
  const [activeDay, setActiveDay] = useState(0);
  const [activeSlotId, setActiveSlotId] = useState<string | null>(null);
  const [editedDays, setEditedDays] = useState<Map<number, DayPlan>>(new Map());
  const [chatDrawerOpen, setChatDrawerOpen] = useState(false);
  const [showBookingLinks, setShowBookingLinks] = useState(false);
  const undoStack = useRef<HistoryEntry[]>([]);

  const baseDays = itinerary?.days ?? progressiveDaysProp ?? [];
  const totalDays = itinerary?.total_days ?? progressiveTotalDays ?? baseDays.length;
  const activitiesTotal = baseDays.reduce((sum, d) => sum + (d.daily_subtotal_sgd || 0), 0);

  // Extract flight and hotel costs from embedded plans
  const plans = (itinerary as any)?.plans;
  const travelerCount = (itinerary as any)?.traveler_count || 1;
  const roomSharing = (itinerary as any)?.room_sharing || 'shared';
  const roomsNeeded = roomSharing === 'separate' ? travelerCount : Math.ceil(travelerCount / 2);

  const flightCost = (() => {
    if (!plans?.transport_plan) return 0;
    const tp = plans.transport_plan;
    const ob = tp.outbound_flights?.[0]?.price_sgd || 0;
    const ib = tp.inbound_flights?.[0]?.price_sgd || 0;
    return (ob + ib) * travelerCount;
  })();
  const hotelCost = (() => {
    if (!plans?.accommodation_plan?.cities) return 0;
    const nights = Math.max(1, totalDays - 1);
    return plans.accommodation_plan.cities.reduce((sum: number, c: any) => {
      const price = c.options?.[0]?.price_per_night_sgd || 0;
      return sum + price * nights * roomsNeeded;
    }, 0);
  })();

  const grandTotal =
    itinerary?.grand_total_sgd ??
    (activitiesTotal + flightCost + hotelCost);

  const costBreakdown = {
    activities: Math.round(activitiesTotal),
    flights: Math.round(flightCost),
    hotels: Math.round(hotelCost),
  };

  const currentDay = editedDays.get(activeDay) ?? baseDays[activeDay];
  const isCurrentDayLoading = !currentDay;
  const dest = destination || baseDays[0]?.city || 'Trip';
  const apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;

  const pushUndo = useCallback(
    (label: string) => {
      if (!currentDay) return;
      undoStack.current = [
        ...undoStack.current.slice(-(MAX_UNDO - 1)),
        { label, dayIndex: activeDay, day: currentDay },
      ];
    },
    [currentDay, activeDay],
  );

  const handleUndo = useCallback(() => {
    const entry = undoStack.current.pop();
    if (!entry) return;
    setEditedDays((prev) => new Map(prev).set(entry.dayIndex, entry.day));
    if (entry.dayIndex !== activeDay) setActiveDay(entry.dayIndex);
    toast(`Undone: ${entry.label}`, { duration: 2000 });
  }, [activeDay]);

  // --- Editing callbacks ---

  const applyDay = useCallback(
    (dayIdx: number, updated: DayPlan) => {
      setEditedDays((prev) => new Map(prev).set(dayIdx, updated));
    },
    [],
  );

  const handleSlotsReorder = (newSlots: TimeSlot[]) => {
    if (!currentDay) return;
    pushUndo('reorder');
    setActiveSlotId(null);
    const recalculated = _recalcTimesSequentially(newSlots);
    const subtotal = recalculated.reduce((sum, s) => sum + (s.cost_sgd || 0), 0);
    applyDay(activeDay, { ...currentDay, time_slots: recalculated, daily_subtotal_sgd: subtotal });
    toast('Reordered. Press Ctrl+Z or tap Undo to revert.', {
      duration: 3000,
      id: 'undo-hint',
    });
  };

  const handleSlotDelete = (slotIndex: number) => {
    if (!currentDay) return;
    pushUndo('delete');
    const deletedSlot = currentDay.time_slots[slotIndex];
    const newSlots = currentDay.time_slots.filter((_, i) => i !== slotIndex);

    if (deletedSlot.start_time && deletedSlot.end_time) {
      const freedMinutes =
        _timeToMinutes(deletedSlot.end_time) - _timeToMinutes(deletedSlot.start_time);
      if (freedMinutes > 0) {
        for (let i = slotIndex; i < newSlots.length; i++) {
          const slot = newSlots[i];
          if (slot.start_time) {
            newSlots[i] = {
              ...slot,
              start_time: _minutesToTime(_timeToMinutes(slot.start_time) - freedMinutes),
              end_time: slot.end_time
                ? _minutesToTime(_timeToMinutes(slot.end_time) - freedMinutes)
                : slot.end_time,
            };
          }
        }
      }
    }

    const subtotal = newSlots.reduce((sum, s) => sum + (s.cost_sgd || 0), 0);
    applyDay(activeDay, { ...currentDay, time_slots: newSlots, daily_subtotal_sgd: subtotal });
    toast.dismiss('undo-hint');
    toast(
      (t) => (
        <span className="flex items-center gap-2 text-sm">
          Removed.
          <button
            onClick={() => {
              handleUndo();
              toast.dismiss(t.id);
            }}
            className="font-bold underline"
          >
            Undo
          </button>
        </span>
      ),
      { duration: 5000 },
    );
  };

  const handleSlotEdit = (slotIndex: number, field: string, value: string) => {
    if (!currentDay) return;
    pushUndo('edit');
    const newSlots = [...currentDay.time_slots];
    const slot = newSlots[slotIndex];

    if (field === 'start_time' && slot.start_time && slot.end_time) {
      const duration = _timeToMinutes(slot.end_time) - _timeToMinutes(slot.start_time);
      const newStart = _snapTo15(_timeToMinutes(value));
      const effectiveDuration = duration > 0 ? duration : 60;
      newSlots[slotIndex] = {
        ...slot,
        start_time: _minutesToTime(newStart),
        end_time: _minutesToTime(newStart + effectiveDuration),
      };

      let cursor = newStart + effectiveDuration;
      for (let i = slotIndex + 1; i < newSlots.length; i++) {
        const s = newSlots[i];
        const d = _slotDuration(s);
        newSlots[i] = {
          ...s,
          start_time: _minutesToTime(_snapTo15(cursor)),
          end_time: _minutesToTime(_snapTo15(cursor) + d),
        };
        cursor = _snapTo15(cursor) + d;
      }
    } else if (field === 'end_time') {
      newSlots[slotIndex] = { ...slot, end_time: _minutesToTime(_snapTo15(_timeToMinutes(value))) };
      let cursor = _snapTo15(_timeToMinutes(value));
      for (let i = slotIndex + 1; i < newSlots.length; i++) {
        const s = newSlots[i];
        const d = _slotDuration(s);
        newSlots[i] = {
          ...s,
          start_time: _minutesToTime(_snapTo15(cursor)),
          end_time: _minutesToTime(_snapTo15(cursor) + d),
        };
        cursor = _snapTo15(cursor) + d;
      }
    } else {
      newSlots[slotIndex] = { ...slot, [field]: value };
    }

    applyDay(activeDay, { ...currentDay, time_slots: newSlots });
  };

  const handleMoveToDay = (slotIndex: number, targetDayIdx: number) => {
    if (!currentDay || targetDayIdx === activeDay) return;
    const targetDay = editedDays.get(targetDayIdx) ?? baseDays[targetDayIdx];
    if (!targetDay) return;

    pushUndo('move');
    const slot = currentDay.time_slots[slotIndex];

    // Remove from current day
    const srcSlots = currentDay.time_slots.filter((_, i) => i !== slotIndex);
    const srcSubtotal = srcSlots.reduce((sum, s) => sum + (s.cost_sgd || 0), 0);

    // Add to end of target day (before last transit/buffer if any)
    const dstSlots = [...targetDay.time_slots];
    const lastSlot = dstSlots[dstSlots.length - 1];
    const lastStart = lastSlot?.end_time ? _timeToMinutes(lastSlot.end_time) : 18 * 60;
    const duration = _slotDuration(slot);
    const movedSlot: TimeSlot = {
      ...slot,
      start_time: _minutesToTime(_snapTo15(lastStart)),
      end_time: _minutesToTime(_snapTo15(lastStart) + duration),
    };
    dstSlots.push(movedSlot);
    const dstSubtotal = dstSlots.reduce((sum, s) => sum + (s.cost_sgd || 0), 0);

    setEditedDays((prev) => {
      const next = new Map(prev);
      next.set(activeDay, { ...currentDay, time_slots: srcSlots, daily_subtotal_sgd: srcSubtotal });
      next.set(targetDayIdx, { ...targetDay, time_slots: dstSlots, daily_subtotal_sgd: dstSubtotal });
      return next;
    });

    toast(
      (t) => (
        <span className="flex items-center gap-2 text-sm">
          Moved to Day {targetDayIdx + 1}.
          <button
            onClick={() => {
              handleUndo();
              toast.dismiss(t.id);
            }}
            className="font-bold underline"
          >
            Undo
          </button>
        </span>
      ),
      { duration: 4000 },
    );
  };

  const handleEditComplete = (result: any) => {
    if (result.itinerary?.days) {
      setEditedDays(new Map());
      undoStack.current = [];
      if (setProgressiveDays) {
        setProgressiveDays(result.itinerary.days);
      }
    }
  };

  // Keyboard undo (Ctrl+Z / Cmd+Z)
  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'z' && !e.shiftKey) {
        e.preventDefault();
        handleUndo();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [handleUndo]);

  const sideBySidePanels = (
    <div className="flex flex-1 overflow-hidden">
      <TimelinePanel
        day={currentDay}
        dayNumber={activeDay + 1}
        totalDays={totalDays}
        isLoading={isCurrentDayLoading}
        activeSlotId={activeSlotId}
        onSlotClick={setActiveSlotId}
        editable={!!currentDay && !isCurrentDayLoading}
        onSlotsReorder={handleSlotsReorder}
        onSlotDelete={handleSlotDelete}
        onSlotEdit={handleSlotEdit}
        onMoveToDay={handleMoveToDay}
        className="w-[400px] shrink-0 border-r border-stone-100"
      />
      <MapPanel
        day={currentDay}
        activeSlotId={activeSlotId}
        onPinClick={setActiveSlotId}
        className="flex-1 min-w-0"
      />
    </div>
  );

  return (
    <div className="flex flex-col h-full">
      <BreadcrumbNav
        destination={dest}
        activeDay={activeDay + 1}
        onBack={onBack}
        onHome={onBack}
      />
      <CostSummaryBar grandTotal={grandTotal} breakdown={costBreakdown} />
      <DayTabStrip
        days={baseDays}
        totalDays={totalDays}
        activeDay={activeDay}
        onSelectDay={setActiveDay}
      />
      {apiKey ? (
        <APIProvider apiKey={apiKey}>
          {sideBySidePanels}
        </APIProvider>
      ) : (
        <div className="flex flex-1 overflow-hidden">
          <TimelinePanel
            day={currentDay}
            dayNumber={activeDay + 1}
            totalDays={totalDays}
            isLoading={isCurrentDayLoading}
            activeSlotId={activeSlotId}
            onSlotClick={setActiveSlotId}
            editable={!!currentDay && !isCurrentDayLoading}
            onSlotsReorder={handleSlotsReorder}
            onSlotDelete={handleSlotDelete}
            onSlotEdit={handleSlotEdit}
            onMoveToDay={handleMoveToDay}
            className="w-[400px] shrink-0 border-r border-stone-100"
          />
          <div className="flex-1 min-w-0 bg-stone-50 flex items-center justify-center text-stone-300 text-sm">
            Set VITE_GOOGLE_MAPS_API_KEY to enable map
          </div>
        </div>
      )}

      {/* Historical booking status bar + links */}
      {bookingStatus && (
        <div className="shrink-0 border-t border-stone-200 bg-stone-50">
          <div className="px-6 py-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className={`text-[10px] font-bold uppercase tracking-widest px-2 py-0.5 rounded-full ${
                bookingStatus === 'confirmed' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'
              }`}>
                {bookingStatus === 'sandbox_confirmed' ? 'Sandbox' : 'Confirmed'}
              </span>
              {bookingConfirmationId && (
                <span className="text-xs text-stone-500">{bookingConfirmationId}</span>
              )}
            </div>
            {bookingLinks && bookingLinks.length > 0 && (
              <button
                onClick={() => setShowBookingLinks((v) => !v)}
                className="text-[10px] font-bold text-stone-500 hover:text-stone-700 underline cursor-pointer"
              >
                {showBookingLinks ? 'Hide Booking Links' : `View ${bookingLinks.length} Booking Links`}
              </button>
            )}
          </div>
          {showBookingLinks && bookingLinks && bookingLinks.length > 0 && (
            <div className="px-6 pb-4 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
              {bookingLinks.map((link: any, i: number) => (
                <a
                  key={i}
                  href={link.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex flex-col bg-white border border-stone-200 rounded-lg p-3 hover:shadow-md hover:-translate-y-0.5 transition-all"
                >
                  <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full self-start mb-1 ${
                    link.type?.includes('flight') ? 'bg-sky-100 text-sky-700' :
                    link.type === 'hotel' ? 'bg-amber-100 text-amber-700' :
                    'bg-emerald-100 text-emerald-700'
                  }`}>
                    {link.type?.includes('flight') ? 'Flight' : link.type === 'hotel' ? 'Hotel' : 'Activity'}
                  </span>
                  <span className="text-xs font-semibold text-stone-800 truncate">{link.description}</span>
                  {link.subtitle && <span className="text-[10px] text-stone-500 truncate">{link.subtitle}</span>}
                  {link.price_label && <span className="text-[10px] font-semibold text-stone-600 mt-0.5">{link.price_label}</span>}
                  <span className="text-[9px] text-stone-400 mt-1">Book Now ↗</span>
                </a>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Confirm/booking bar */}
      {canConfirm && onConfirm && (
        <div className="shrink-0 border-t border-stone-200 bg-white px-6 py-3 flex items-center justify-between">
          <p className="text-xs text-stone-500">Happy with the itinerary?</p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => onConfirm('search_recommend')}
              disabled={isConfirming}
              className="px-4 py-2 text-xs font-bold rounded-full bg-stone-900 text-white hover:bg-stone-700 disabled:opacity-50 transition-all cursor-pointer shadow-sm"
            >
              {isConfirming ? 'Processing...' : 'Get Booking Links'}
            </button>
            <button
              onClick={() => onConfirm('sandbox')}
              disabled={isConfirming}
              className="px-4 py-2 text-xs font-bold rounded-full border border-stone-300 text-stone-600 hover:bg-stone-100 disabled:opacity-50 transition-all cursor-pointer"
            >
              Sandbox Booking
            </button>
          </div>
        </div>
      )}

      {editablePlanId && editableThreadId && (
        <>
          <button
            onClick={() => setChatDrawerOpen(true)}
            className="fixed bottom-6 right-6 px-4 py-2 bg-stone-900 text-white text-xs font-bold rounded-full shadow-lg hover:bg-stone-700 transition-all cursor-pointer z-30"
          >
            Edit via Chat
          </button>

          <ChatDrawer
            isOpen={chatDrawerOpen}
            onClose={() => setChatDrawerOpen(false)}
            planId={editablePlanId}
            threadId={editableThreadId}
            currentDays={baseDays}
            onEditComplete={handleEditComplete}
          />
        </>
      )}
    </div>
  );
}
