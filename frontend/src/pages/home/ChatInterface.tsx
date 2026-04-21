import React, { useState, useRef, useEffect } from 'react';
import { ArrowUp, Loader2, StopCircle } from 'lucide-react';
import toast from 'react-hot-toast';

import { useUser } from '../../context/user-context';
import ItinerariesAPI from '../../apis/itineraries';
import TabbedOptionsForm from './TabbedOptionsForm';
import MealOptions from './components/MealOptions';
import BookingCards from './components/BookingCards';
import HowToUseModal from './components/HowToUseModal';
import DayView from './DayView';

const ARCH_SUPERVISOR = "supervisor";
const ARCH_SWARM = "swarm";

function formatItinerary(data: any): string {
  if (!data?.itinerary?.days || !Array.isArray(data.itinerary.days)) {
    return `✅ Tour itinerary finalized!\n\n${JSON.stringify(data?.itinerary || data, null, 2)}`;
  }

  const itin = data.itinerary;
  let text = `✅ Tour itinerary finalized!\n`;
  if (itin.grand_total_sgd != null) {
    text += `\n💰 Grand Total: SGD ${itin.grand_total_sgd.toFixed(2)}\n`;
  }

  itin.days.forEach((day: any) => {
    text += `\n📅 Day ${day.day_number}: ${day.date || ''} (${day.city || ''})\n`;
    if (day.hotel_name) text += `🏨 Hotel: ${day.hotel_name}\n`;

    if (Array.isArray(day.time_slots) && day.time_slots.length > 0) {
      day.time_slots.forEach((s: any) => {
        // For meal slots, append restaurant name if available
        let slotLabel = s.label || '';
        if (s.slot_type === 'meal' && s.activity_name) {
          slotLabel = `${slotLabel} at ${s.activity_name}`;
        }
        text += `  • ${s.start_time || '??'}–${s.end_time || '??'} [${s.slot_type || '?'}] ${slotLabel}`;
        if (s.cost_sgd != null) text += ` (SGD ${s.cost_sgd.toFixed(2)})`;
        if (s.booking_link) text += `\n    Booking: ${s.booking_link}`;
        // Show notes for buffer/transit slots (travel time info) and meal slots
        if (s.notes && (s.slot_type === 'buffer' || s.slot_type === 'transit' || s.slot_type === 'meal')) {
          text += `\n    ${s.notes}`;
        }
        text += '\n';
      });
    }

    if (day.daily_subtotal_sgd != null) {
      text += `  👉 Day subtotal: SGD ${day.daily_subtotal_sgd.toFixed(2)}\n`;
    }
  });

  if (Array.isArray(data.booking_links) && data.booking_links.length > 0) {
    text += `\n🔗 Booking Links:\n`;
    data.booking_links.forEach((link: any) => {
      text += `  • ${link.label || 'Book Now'}: ${link.url}\n`;
    });
  }

  return text;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'agent' | 'system' | 'error' | 'options' | 'meals' | 'booking';
  content: string;
  data?: any;
  planId?: string;
  threadId?: string;
  submitted?: boolean;
  editable?: boolean;  // true for the final itinerary message
}

/** Wrapper that manages meal selection state for a single MealOptions message */
function MealOptionsCard({ msg, onSubmit }: { msg: ChatMessage; onSubmit: (meals: any[], auto: boolean) => void }) {
  const [selectedMeals, setSelectedMeals] = React.useState<Record<string, string>>({});

  const handleSelect = (key: string, name: string) => {
    setSelectedMeals(prev => ({ ...prev, [key]: name }));
  };

  const handleAutoSelect = () => onSubmit([], true);

  const handleConfirm = () => {
    const meals = Object.entries(selectedMeals).map(([key, name]) => {
      const [dayStr, mealType] = key.split('-');
      return { day_number: parseInt(dayStr), meal_type: mealType, selected_name: name };
    });
    onSubmit(meals, false);
  };

  return (
    <MealOptions
      mealOptions={msg.data}
      selectedMeals={selectedMeals}
      onSelectMeal={handleSelect}
      onAutoSelect={handleAutoSelect}
      onSubmit={handleConfirm}
      disabled={msg.submitted}
    />
  );
}


export default function ChatInterface() {
  const { user } = useUser();

  const [architecture, setArchitecture] = useState(ARCH_SUPERVISOR);
  const [inputVal, setInputVal] = useState('');

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [agentStatus, setAgentStatus] = useState<string>('');
  const [currentThreadId, setCurrentThreadId] = useState<string | null>(null);
  const [abortController, setAbortController] = useState<AbortController | null>(null);
  const [editablePlan, setEditablePlan] = useState<{ planId: string; threadId: string } | null>(null);
  // Booking confirmation flow state
  const [confirmedPlan, setConfirmedPlan] = useState<{ planId: string; threadId: string } | null>(null);
  const [bookingDone, setBookingDone] = useState(false);
  const [isHowToUseOpen, setIsHowToUseOpen] = useState(false);
  // Progressive DayView state — populated by day_ready SSE events
  const [dayViewMode, setDayViewMode] = useState(false);
  const [progressiveDays, setProgressiveDays] = useState<any[]>([]);
  const [totalDays, setTotalDays] = useState(0);
  const [dayViewDestination, setDayViewDestination] = useState('');
  const [completeItinerary, setCompleteItinerary] = useState<any>(null);

  const endOfMessagesRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endOfMessagesRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, agentStatus, isLoading]);

  const handleSend = async () => {
    if (!inputVal.trim() || isLoading) return;
    if (!user || (!user.token && !user.email)) {
      toast.error('You must be logged in to plan a trip.');
      return;
    }

    const query = inputVal.trim();
    setInputVal('');

    // Reset DayView state when starting a new plan
    setDayViewMode(false);
    setProgressiveDays([]);
    setTotalDays(0);
    setDayViewDestination('');
    setCompleteItinerary(null);

    // If there's a completed editable itinerary, route through edit flow
    if (editablePlan) {
      await handleEdit(editablePlan.planId, editablePlan.threadId, query);
      return;
    }

    const newMessage: ChatMessage = { id: Date.now().toString(), role: 'user', content: query };
    setMessages((prev) => [...prev, newMessage]);
    setIsLoading(true);
    setAgentStatus('Initialize trip planning...');

    const ctl = new AbortController();
    setAbortController(ctl);

    try {
      await ItinerariesAPI.streamPlan(
        { user_input: query, mode: architecture, booking_mode: 'search_recommend', thread_id: currentThreadId },
        user.token,
        (type, data) => {
          if (type === 'agent_active') {
            setAgentStatus(data.summary || `${data.agent} working...`);
            if (data.thread_id) setCurrentThreadId(data.thread_id);
          } else if (type === 'options') {
            if (data.plan_id) {
              setMessages((prev) => [...prev, { id: Date.now().toString(), role: 'options', content: '', data: { ...data.options, _routeContext: data.route_context }, planId: data.plan_id }]);
            }
          } else if (type === 'error') {
            setMessages((prev) => [...prev, { id: Date.now().toString(), role: 'error', content: `Stream error: ${data.error}` }]);
          }
        },
        (data) => {
          setIsLoading(false);
          setAbortController(null);

          if (data.plan_id) {
            const content = data.itinerary
              ? formatItinerary(data)
              : `✅ Plan created (ID: ${data.plan_id})`;
            setMessages((prev) => [...prev, { id: Date.now().toString(), role: 'system', content }]);
          } else {
            if (!data.is_feasible) {
              setMessages((prev) => [...prev, { id: Date.now().toString(), role: 'error', content: data.feasibility_rejection_reason || 'Infeasible request.' }]);
            } else if (data.awaiting_confirmation) {
              const summary = data.confirmation_summary?.map((l: string) => `- ${l}`).join('\n') || '';
              setMessages((prev) => [...prev, { id: Date.now().toString(), role: 'system', content: `Here's what I'll search for:\n${summary}\n\nSay **Confirm** to proceed, or tell me what to change.` }]);
            } else if (data.needs_clarification) {
              const qs = data.clarification_questions?.join('\n- ') || 'Needs clarification.';
              setMessages((prev) => [...prev, { id: Date.now().toString(), role: 'system', content: `Clarification needed:\n- ${qs}` }]);
            } else {
              setMessages((prev) => [...prev, { id: Date.now().toString(), role: 'error', content: 'Plan completed with unknown result.' }]);
            }
          }
        },
        ctl.signal
      );
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        toast.error('Network or streaming error occurred.');
        setMessages((prev) => [...prev, { id: Date.now().toString(), role: 'error', content: err.message || 'Stream failed.' }]);
      } else {
        setMessages((prev) => [...prev, { id: Date.now().toString(), role: 'system', content: 'Query stopped by user.' }]);
      }
    } finally {
      setIsLoading(false);
      setAbortController(null);
    }
  };

  const handleOptionsSubmit = async (messageId: string, planId: string, selections: any) => {
    setMessages(prev => prev.map(m => m.id === messageId ? { ...m, submitted: true } : m));
    setIsLoading(true);
    setAgentStatus('Finding restaurants near your activities...');

    const ctl = new AbortController();
    setAbortController(ctl);

    try {
      await ItinerariesAPI.streamPass2(
        planId,
        selections,
        user?.token,
        (type, data) => {
          if (type === 'agent_active') {
            setAgentStatus(data.summary || `${data.agent} working...`);
          } else if (type === 'meal_options') {
            // Backend now sends meal_options instead of complete
            setMessages((prev) => [...prev, {
              id: Date.now().toString(),
              role: 'meals',
              content: '',
              data: data.meal_options,
              planId: data.plan_id,
              threadId: data.thread_id,
            }]);
            setIsLoading(false);
            setAbortController(null);
          } else if (type === 'error') {
            setMessages((prev) => [...prev, { id: Date.now().toString(), role: 'error', content: `Stream error: ${data.error}` }]);
          }
        },
        (data) => {
          // Fallback: if backend sends complete directly (e.g. cached result)
          setIsLoading(false);
          setAbortController(null);

          if (data.plan_id) {
            const content = data.itinerary
              ? formatItinerary(data)
              : `✅ Plan created (ID: ${data.plan_id})`;
            setMessages((prev) => [...prev, {
              id: Date.now().toString(), role: 'system', content,
              planId: data.plan_id, threadId: data.thread_id, editable: !!data.itinerary,
            }]);
            if (data.itinerary && data.thread_id) {
              setEditablePlan({ planId: data.plan_id, threadId: data.thread_id });
            }
          }
        },
        ctl.signal
      );
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        toast.error('Network or streaming error occurred.');
        setMessages((prev) => [...prev, { id: Date.now().toString(), role: 'error', content: err.message || 'Stream failed.' }]);
      } else {
        setMessages((prev) => [...prev, { id: Date.now().toString(), role: 'system', content: 'Query stopped by user.' }]);
      }
    } finally {
      setIsLoading(false);
      setAbortController(null);
    }
  };

  const handleMealsSubmit = async (messageId: string, planId: string, selectedMeals: any[], autoSelect: boolean) => {
    setMessages(prev => prev.map(m => m.id === messageId ? { ...m, submitted: true } : m));
    setIsLoading(true);
    setAgentStatus('Assembling your itinerary with selected meals...');

    const ctl = new AbortController();
    setAbortController(ctl);

    try {
      await ItinerariesAPI.streamMeals(
        planId,
        { selected_meals: selectedMeals, auto_select: autoSelect },
        user?.token,
        (type, data) => {
          if (type === 'agent_active') {
            setAgentStatus(data.summary || `${data.agent} working...`);
          } else if (type === 'itinerary_meta') {
            setTotalDays(data.total_days);
            setDayViewDestination(data.destination || '');
          } else if (type === 'day_ready') {
            setProgressiveDays(prev => [...prev, data.day]);
            // Auto-open DayView on first day_ready event
            setDayViewMode(true);
          } else if (type === 'error') {
            setMessages((prev) => [...prev, { id: Date.now().toString(), role: 'error', content: `Stream error: ${data.error}` }]);
          }
        },
        (data) => {
          setIsLoading(false);
          setAbortController(null);

          if (data.itinerary) {
            // DayView is already open from day_ready events.
            // Update editable plan state for future edits.
            if (data.plan_id && data.thread_id) {
              setEditablePlan({ planId: data.plan_id, threadId: data.thread_id });
            }
            // Always update with the complete itinerary — it has enriched
            // lat/lng coordinates and grand_total_sgd with flights+hotels.
            const schedule = data.itinerary;
            setProgressiveDays(schedule.days || []);
            setTotalDays(schedule.total_days || schedule.days?.length || 0);
            setCompleteItinerary(schedule);
            if (!dayViewMode) setDayViewMode(true);
          } else {
            if (!dayViewMode) {
              setMessages((prev) => [...prev, { id: Date.now().toString(), role: 'system', content: 'Itinerary assembly completed.' }]);
            }
          }
        },
        ctl.signal
      );
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        toast.error('Network or streaming error occurred.');
        setMessages((prev) => [...prev, { id: Date.now().toString(), role: 'error', content: err.message || 'Stream failed.' }]);
      } else {
        setMessages((prev) => [...prev, { id: Date.now().toString(), role: 'system', content: 'Query stopped by user.' }]);
      }
    } finally {
      setIsLoading(false);
      setAbortController(null);
    }
  };

  const handleEdit = async (planId: string, threadId: string, editText: string) => {
    if (!editText.trim()) return;

    setMessages((prev) => [...prev, { id: Date.now().toString(), role: 'user', content: editText }]);
    setIsLoading(true);
    setAgentStatus('Applying your edit...');

    try {
      const result = await ItinerariesAPI.editItinerary(planId, editText, threadId, user?.token);
      if (result.itinerary) {
        let content = formatItinerary({ itinerary: result.itinerary });
        if (result.transport_notes?.length) {
          content = `Transport updated:\n${result.transport_notes.map((n: string) => `  - ${n}`).join('\n')}\n\n${content}`;
        }
        setMessages((prev) => [...prev, {
          id: Date.now().toString(), role: 'system', content,
          planId, threadId, editable: true,
        }]);
        setEditablePlan({ planId, threadId });
      } else {
        setMessages((prev) => [...prev, { id: Date.now().toString(), role: 'system', content: 'Edit applied.' }]);
      }
    } catch (err: any) {
      toast.error('Edit failed.');
      setMessages((prev) => [...prev, { id: Date.now().toString(), role: 'error', content: err.message || 'Edit failed.' }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleConfirmItinerary = async (planId: string, bookingMode: 'search_recommend' | 'sandbox') => {
    setIsLoading(true);
    setAgentStatus(bookingMode === 'sandbox' ? 'Processing sandbox booking...' : 'Extracting booking links...');
    try {
      const result = await ItinerariesAPI.confirmPlan(planId, bookingMode, user?.token);
      setBookingDone(true);
      setConfirmedPlan(null);

      setMessages((prev) => [...prev, {
        id: Date.now().toString(), role: 'booking', content: '', data: result,
      }]);
    } catch (err: any) {
      toast.error('Confirmation failed.');
      setMessages((prev) => [...prev, { id: Date.now().toString(), role: 'error', content: err.message || 'Confirmation failed.' }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleBackToEditing = (planId: string, threadId: string) => {
    setConfirmedPlan(null);
    setEditablePlan({ planId, threadId });
  };

  const stopQuery = () => {
    if (abortController) {
      abortController.abort();
      setAbortController(null);
      setIsLoading(false);
    }
  };

  const isChatActive = messages.length > 0 || isLoading;

  // When DayView is active, render it instead of the chat UI
  if (dayViewMode) {
    const canConfirmFromMap = !!(editablePlan && !confirmedPlan && !bookingDone);
    return (
      <DayView
        itinerary={completeItinerary}
        days={progressiveDays}
        totalDays={totalDays}
        destination={dayViewDestination}
        onBack={() => setDayViewMode(false)}
        editablePlanId={editablePlan?.planId}
        editableThreadId={editablePlan?.threadId}
        setProgressiveDays={setProgressiveDays}
        canConfirm={canConfirmFromMap}
        onConfirm={(mode) => {
          if (!editablePlan) return;
          setDayViewMode(false);
          // Confirm in chat: set confirmed state, then trigger booking
          const plan = { planId: editablePlan.planId, threadId: editablePlan.threadId };
          setEditablePlan(null);
          setConfirmedPlan(plan);
          setMessages((prev) => [...prev, {
            id: Date.now().toString(), role: 'system',
            content: 'Itinerary confirmed! Processing booking...',
          }]);
          handleConfirmItinerary(plan.planId, mode);
        }}
        isConfirming={isLoading}
      />
    );
  }

  return (
    <div className={`flex flex-col w-full max-w-4xl mx-auto transition-all duration-700 ${isChatActive ? 'h-full justify-end pb-8' : 'justify-center h-full'}`}>

      {/* Dynamic Messages Window */}
      {isChatActive && (
        <div className="flex-1 overflow-y-auto w-full mb-6 custom-scrollbar px-4 pt-4 flex flex-col gap-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
          {messages.map((msg) => (
            <div key={msg.id} className={`flex w-full ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              {msg.role === 'options' ? (
                <TabbedOptionsForm
                  options={msg.data}
                  routeContext={msg.data?._routeContext}
                  disabled={msg.submitted}
                  onSubmit={(selections) => handleOptionsSubmit(msg.id, msg.planId!, selections)}
                />
              ) : msg.role === 'meals' ? (
                <MealOptionsCard
                  msg={msg}
                  onSubmit={(selectedMeals, autoSelect) => handleMealsSubmit(msg.id, msg.planId!, selectedMeals, autoSelect)}
                />
              ) : msg.role === 'booking' ? (
                <div className="max-w-[80%]">
                  <BookingCards {...msg.data} />
                </div>
              ) : (
                <div className="max-w-[80%] flex flex-col gap-3">
                  <div className={`
                    rounded-2xl p-4 text-sm whitespace-pre-wrap leading-relaxed shadow-sm
                    ${msg.role === 'user' ? 'bg-stone-900 text-white rounded-br-sm' : ''}
                    ${msg.role === 'system' ? 'bg-white text-stone-800 rounded-bl-sm border border-stone-200' : ''}
                    ${msg.role === 'error' ? 'bg-red-50 text-red-600 rounded-bl-sm border border-red-100' : ''}
                  `}>
                    {msg.content}
                  </div>

                  {/* Confirm Itinerary button — show on the latest editable message when still editing */}
                  {msg.editable && msg.planId && msg.threadId && !confirmedPlan && !bookingDone && editablePlan?.planId === msg.planId && (
                    <div className="flex flex-col gap-2 pl-1">
                      <button
                        onClick={() => {
                          const plan = { planId: msg.planId!, threadId: msg.threadId! };
                          setEditablePlan(null);
                          setConfirmedPlan(plan);
                          setMessages((prev) => [...prev, {
                            id: Date.now().toString(), role: 'system',
                            content: '✅ Itinerary confirmed! Choose how you\'d like to proceed with booking:',
                          }]);
                        }}
                        disabled={isLoading}
                        className="px-4 py-2 text-xs font-bold rounded-full bg-stone-900 text-white hover:bg-stone-700 transition-all shadow-sm disabled:opacity-50 cursor-pointer self-start"
                      >
                        Confirm Itinerary
                      </button>
                      <p className="text-[10px] text-stone-400 italic">You can still edit the itinerary above by typing in the chat box.</p>
                    </div>
                  )}

                  {/* Booking choice buttons — shown after itinerary is confirmed, before booking done */}
                  {msg.editable && msg.planId && msg.threadId && confirmedPlan?.planId === msg.planId && !bookingDone && !isLoading && (
                    <div className="flex flex-col gap-3 pl-1">
                      <div className="flex items-center gap-3">
                        <button
                          onClick={() => handleConfirmItinerary(msg.planId!, 'search_recommend')}
                          className="px-4 py-2 text-xs font-bold rounded-full bg-stone-900 text-white hover:bg-stone-700 transition-all shadow-sm cursor-pointer"
                        >
                          Get Booking Links
                        </button>
                        <button
                          onClick={() => handleConfirmItinerary(msg.planId!, 'sandbox')}
                          className="px-4 py-2 text-xs font-bold rounded-full border border-stone-300 text-stone-600 hover:bg-stone-100 transition-all shadow-sm cursor-pointer"
                        >
                          Sandbox Booking
                        </button>
                      </div>
                      <p className="text-[10px] text-stone-400 italic max-w-md">
                        "Sandbox Booking" simulates the booking process for demonstration purposes. No real transactions will be made.
                      </p>
                      <button
                        onClick={() => handleBackToEditing(msg.planId!, msg.threadId!)}
                        className="text-[10px] text-stone-500 underline hover:text-stone-700 transition-all cursor-pointer self-start"
                      >
                        ← Back to editing
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}

          {isLoading && (
            <div className="flex w-full justify-start animate-in fade-in slide-in-from-bottom-2">
              <div className="max-w-[80%] rounded-2xl rounded-bl-sm p-4 text-sm bg-stone-50 text-stone-600 border border-stone-100 flex items-center gap-3 shadow-sm">
                <Loader2 className="animate-spin text-stone-400" size={16} />
                <span className="font-medium italic text-stone-500">{agentStatus || 'Working...'}</span>
              </div>
            </div>
          )}
          <div ref={endOfMessagesRef} className="h-4 shrink-0" />
        </div>
      )}

      {/* Hero Welcome (Fades out when chat starts) */}
      {!isChatActive && (
        <div className="w-full text-center pb-12 animate-in fade-in zoom-in duration-500">
          <h1 className="text-4xl sm:text-5xl font-headline font-bold text-stone-800 tracking-tight">Where to next?</h1>
        </div>
      )}

      {/* Input Box Container */}
      <div className="flex flex-col shrink-0 bg-stone-50/50 border border-stone-200 rounded-[2rem] shadow-sm overflow-hidden focus-within:ring-1 focus-within:ring-black focus-within:border-black transition-all">
        {/* Input Area */}
        <div className="relative flex items-center px-4 pt-4 pb-2">
          <textarea
            value={inputVal}
            onChange={(e) => setInputVal(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder={confirmedPlan || bookingDone ? "Itinerary confirmed. Choose a booking option above." : editablePlan ? "Edit your itinerary, e.g. swap a restaurant, change a city..." : "Ask agent to plan a journey..."}
            className="flex-1 bg-transparent border-none py-4 px-4 text-sm font-medium placeholder:text-stone-400 focus:outline-none resize-none custom-scrollbar"
            disabled={isLoading || !!confirmedPlan || bookingDone}
            rows={Math.min(Math.max(inputVal.split('\n').length, 1), 5)}
          />

          <div className="flex items-center gap-2 shrink-0">
            {isLoading ? (
              <button
                onClick={stopQuery}
                className="p-3 rounded-full bg-red-50 text-red-500 hover:bg-red-100 hover:text-red-600 transition-all cursor-pointer"
                title="Stop generating"
              >
                <StopCircle size={18} />
              </button>
            ) : (
              <button
                onClick={handleSend}
                className={`p-3 rounded-full transition-all ${inputVal.trim() ? 'bg-black text-white shadow-md hover:bg-stone-800 hover:-translate-y-0.5' : 'bg-stone-200 text-stone-400'} cursor-pointer`}
                disabled={!inputVal.trim()}
                title="Send message"
              >
                <ArrowUp size={18} strokeWidth={3} />
              </button>
            )}
          </div>
        </div>

        {/* Integrated Control Strip */}
        <div className="flex items-center justify-between w-full px-6 pb-4">
          <div className="flex items-center gap-2">
            <span className="text-[9px] font-bold text-stone-400 uppercase tracking-widest">Architecture</span>
            <select
              value={architecture}
              onChange={(e) => setArchitecture(e.target.value)}
              className="bg-transparent border border-stone-200 rounded-full px-3 py-1 text-[9px] text-stone-600 font-bold focus:outline-none hover:bg-white hover:border-stone-300 transition-all cursor-pointer appearance-none disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-transparent disabled:hover:border-stone-200"
              disabled={isChatActive}
            >
              <option value={ARCH_SUPERVISOR}>Supervisor</option>
              <option value={ARCH_SWARM}>Swarm</option>
            </select>
          </div>
          <div className="flex items-center gap-3">
            {progressiveDays.length > 0 && !dayViewMode && (
              <button
                onClick={() => setDayViewMode(true)}
                className="text-[10px] font-bold text-stone-600 hover:text-stone-900 bg-stone-100 hover:bg-stone-200 px-3 py-1 rounded-full transition-all cursor-pointer"
              >
                View Map
              </button>
            )}
            <button
              onClick={() => setIsHowToUseOpen(true)}
              className="text-[10px] font-bold text-stone-400 hover:text-stone-700 underline transition-colors cursor-pointer"
            >
              How to use this Planner?
            </button>
          </div>
        </div>
      </div>

      <HowToUseModal isOpen={isHowToUseOpen} onClose={() => setIsHowToUseOpen(false)} />
    </div>
  );
}
