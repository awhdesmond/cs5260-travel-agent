import React, { useState, useEffect, useMemo } from 'react';
import { X, ArrowUp, Loader2 } from 'lucide-react';
import { clsx } from 'clsx';
import { useUser } from '../../../context/user-context';
import ItinerariesAPI from '../../../apis/itineraries';

interface ChatDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  planId?: string;
  threadId?: string;
  currentDays?: any[];
  onEditComplete?: (result: any) => void;
}

/** Compare old and new itinerary days, return human-readable change summary. */
function _buildChangeSummary(oldDays: any[], newDays: any[]): string {
  const lines: string[] = [];

  const maxDays = Math.max(oldDays.length, newDays.length);
  for (let d = 0; d < maxDays; d++) {
    const oldDay = oldDays[d];
    const newDay = newDays[d];

    if (!oldDay && newDay) {
      lines.push(`Day ${d + 1}: added (${newDay.city || ''})`);
      continue;
    }
    if (oldDay && !newDay) {
      lines.push(`Day ${d + 1}: removed`);
      continue;
    }
    if (!oldDay || !newDay) continue;

    const oldSlots = (oldDay.time_slots || []).filter(
      (s: any) => s.slot_type === 'activity' || s.slot_type === 'meal',
    );
    const newSlots = (newDay.time_slots || []).filter(
      (s: any) => s.slot_type === 'activity' || s.slot_type === 'meal',
    );

    const oldNames = new Set(oldSlots.map((s: any) => (s.activity_name || s.label || '').toLowerCase()));
    const newNames = new Set(newSlots.map((s: any) => (s.activity_name || s.label || '').toLowerCase()));

    const added = newSlots.filter((s: any) => !oldNames.has((s.activity_name || s.label || '').toLowerCase()));
    const removed = oldSlots.filter((s: any) => !newNames.has((s.activity_name || s.label || '').toLowerCase()));

    if (added.length > 0 || removed.length > 0) {
      const dayLabel = `Day ${d + 1}`;
      if (removed.length > 0) {
        lines.push(`${dayLabel}: removed ${removed.map((s: any) => s.activity_name || s.label).join(', ')}`);
      }
      if (added.length > 0) {
        lines.push(`${dayLabel}: added ${added.map((s: any) => s.activity_name || s.label).join(', ')}`);
      }
    }
  }

  return lines.length > 0 ? lines.join('\n') : 'Itinerary updated (minor timing/order changes).';
}

export default function ChatDrawer({
  isOpen,
  onClose,
  planId,
  threadId,
  currentDays,
  onEditComplete,
}: ChatDrawerProps) {
  const [editText, setEditText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [messages, setMessages] = useState<Array<{ role: string; content: string }>>([]);
  const { user } = useUser();

  const editHints = useMemo(() => [
    'Analyzing your request...',
    'Modifying itinerary...',
    'Checking transport impact...',
    'Finalizing changes...',
  ], []);
  const [hintIdx, setHintIdx] = useState(0);
  useEffect(() => {
    if (!isLoading) { setHintIdx(0); return; }
    const timer = setInterval(() => setHintIdx((i) => (i + 1) % editHints.length), 2000);
    return () => clearInterval(timer);
  }, [isLoading, editHints]);

  const handleSubmit = async () => {
    if (!editText.trim() || !planId || !threadId || isLoading) return;
    const text = editText.trim();
    setEditText('');
    setMessages(prev => [...prev, { role: 'user', content: text }]);
    setIsLoading(true);

    try {
      const oldDays = currentDays || [];
      const result = await ItinerariesAPI.editItinerary(planId, text, threadId, user?.token);
      if (result.itinerary) {
        const newDays = result.itinerary.days || [];
        const summary = _buildChangeSummary(oldDays, newDays);
        const transportNote = result.transport_notes?.length
          ? '\n' + result.transport_notes.join('. ')
          : '';
        setMessages(prev => [...prev, { role: 'system', content: summary + transportNote }]);
        onEditComplete?.(result);
      } else {
        setMessages(prev => [...prev, { role: 'system', content: 'Edit processed.' }]);
      }
    } catch (err: any) {
      setMessages(prev => [...prev, { role: 'error', content: err.message || 'Edit failed.' }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <>
      {/* Backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/20 z-40"
          onClick={onClose}
        />
      )}

      {/* Drawer panel */}
      <div
        className={clsx(
          'fixed top-0 right-0 h-full w-96 bg-white shadow-xl z-50 flex flex-col transition-transform duration-300',
          isOpen ? 'translate-x-0' : 'translate-x-full'
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-stone-200 shrink-0">
          <h3 className="font-semibold text-sm text-stone-800">Edit via Chat</h3>
          <button
            onClick={onClose}
            className="p-1 text-stone-400 hover:text-stone-600 cursor-pointer"
            aria-label="Close chat drawer"
          >
            <X size={18} />
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3 custom-scrollbar">
          {messages.length === 0 && (
            <p className="text-xs text-stone-400 italic">
              Tell the agent what to change. E.g. "Find a different restaurant for Day 2 lunch" or "Add a museum visit on Day 3"
            </p>
          )}
          {messages.map((msg, i) => (
            <div
              key={i}
              className={clsx(
                'rounded-xl p-3 text-xs',
                msg.role === 'user' && 'bg-stone-900 text-white self-end max-w-[80%]',
                msg.role === 'system' && 'bg-stone-50 text-stone-700 border border-stone-100 self-start max-w-[80%]',
                msg.role === 'error' && 'bg-red-50 text-red-600 border border-red-100 self-start max-w-[80%]'
              )}
            >
              {msg.content}
            </div>
          ))}
          {isLoading && (
            <div className="flex items-center gap-2 text-stone-400 self-start">
              <Loader2 className="animate-spin" size={14} />
              <span className="text-xs transition-opacity duration-300">{editHints[hintIdx]}</span>
            </div>
          )}
        </div>

        {/* Input */}
        <div className="p-4 border-t border-stone-200 shrink-0">
          <div className="flex gap-2">
            <input
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleSubmit(); }}
              placeholder="Describe your change..."
              className="flex-1 bg-stone-50 border border-stone-200 rounded-full px-4 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-black"
              disabled={isLoading}
            />
            <button
              onClick={handleSubmit}
              disabled={!editText.trim() || isLoading}
              className="p-2 rounded-full bg-stone-900 text-white disabled:opacity-50 cursor-pointer"
              aria-label="Send edit"
            >
              <ArrowUp size={14} strokeWidth={3} />
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
