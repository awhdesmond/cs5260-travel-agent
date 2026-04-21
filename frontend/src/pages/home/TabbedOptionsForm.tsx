import React, { useState, useMemo } from 'react';
import FlightOptions from './components/FlightOptions';
import HotelOptions from './components/HotelOptions';
import ActivityOptions from './components/ActivityOptions';
import IntercityTransportOptions from './components/IntercityTransportOptions';

type TabId = 'activities' | 'hotels' | 'flights';

interface TabbedOptionsFormProps {
  options: any;
  routeContext?: { origin: string; destinations: string[] };
  onSubmit: (selections: any) => void;
  disabled?: boolean;
}

const TABS: { id: TabId; label: string }[] = [
  { id: 'flights', label: 'Flights & Transport' },
  { id: 'hotels', label: 'Hotels' },
  { id: 'activities', label: 'Activities' },
];

export default function TabbedOptionsForm({
  options,
  routeContext,
  onSubmit,
  disabled,
}: TabbedOptionsFormProps) {
  const [activeTab, setActiveTab] = useState<TabId>('flights');
  const [activeDay, setActiveDay] = useState(0);

  const [selectedOutboundFlight, setSelectedOutboundFlight] = useState<string | null>(null);
  const [selectedInboundFlight, setSelectedInboundFlight] = useState<string | null>(null);
  const [selectedHotels, setSelectedHotels] = useState<Record<string, string>>({});
  const [selectedActivities, setSelectedActivities] = useState<string[]>([]);
  const [selectedIntercity, setSelectedIntercity] = useState<Record<string, string>>({});

  // Confirmed state per tab
  const [confirmedTabs, setConfirmedTabs] = useState<Record<TabId, boolean>>({
    activities: false,
    hotels: false,
    flights: false,
  });

  // Compute total day count from activities data
  const totalDays = useMemo(() => {
    if (!options?.activities?.cities?.length) return 0;
    return options.activities.cities.reduce((max: number, cityObj: any) => {
      const days = cityObj.options_per_day?.length || 0;
      return Math.max(max, days);
    }, 0);
  }, [options?.activities]);

  const handleHotelSelect = (city: string, id: string) => {
    setSelectedHotels(prev => ({ ...prev, [city]: id }));
  };

  const handleIntercitySelect = (hopKey: string, id: string) => {
    setSelectedIntercity(prev => ({ ...prev, [hopKey]: id }));
  };

  const handleActivityToggle = (id: string) => {
    setSelectedActivities(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    );
  };

  const handleConfirmTab = (tab: TabId) => {
    setConfirmedTabs(prev => ({ ...prev, [tab]: true }));
  };

  // Check if all tabs confirmed — auto-submit
  const allConfirmed = TABS.every(t => confirmedTabs[t.id]);

  const handleSubmitAll = () => {
    const payload: any = {};
    if (selectedOutboundFlight) payload.selected_outbound_flight_id = selectedOutboundFlight;
    if (selectedInboundFlight) payload.selected_inbound_flight_id = selectedInboundFlight;
    if (Object.keys(selectedHotels).length > 0) payload.selected_hotel_ids = selectedHotels;
    if (selectedActivities.length > 0) payload.selected_activity_ids = selectedActivities;
    if (Object.keys(selectedIntercity).length > 0) payload.selected_intercity_ids = selectedIntercity;
    onSubmit(payload);
  };

  // Filter activities for the active day sub-tab
  const filteredActivitiesForDay = useMemo(() => {
    if (!options?.activities?.cities?.length) return options?.activities;
    // Return a copy with only the active day's options
    return {
      ...options.activities,
      cities: options.activities.cities.map((cityObj: any) => ({
        ...cityObj,
        options_per_day: cityObj.options_per_day
          ? [cityObj.options_per_day[activeDay] || []]
          : [],
        // Override so ActivityOptions renders "Day 1" header correctly
        _singleDayIndex: activeDay,
      })),
    };
  }, [options?.activities, activeDay]);

  return (
    <div className={`flex flex-col gap-8 w-full ${disabled ? 'opacity-60 pointer-events-none' : ''}`}>
      <div className="bg-stone-50 border border-stone-200 rounded-2xl p-6 shadow-sm">
        <h3 className="font-headline font-bold text-lg mb-2 text-stone-800">
          Customize Your Trip
        </h3>
        <p className="text-sm text-stone-500 font-medium mb-6">
          Select your preferences for each category, then confirm. Skip to let us pick the best options.
        </p>

        {/* Main tab bar (sticky) */}
        <div className="flex border-b border-stone-200 mb-4 gap-1 sticky top-0 bg-stone-50 z-10 -mx-6 px-6 pt-1">
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`relative px-4 py-2 text-xs font-semibold uppercase tracking-wide transition-colors ${
                activeTab === tab.id
                  ? 'border-b-2 border-black text-stone-900'
                  : 'text-stone-500 hover:text-stone-700'
              }`}
            >
              {tab.label}
              {confirmedTabs[tab.id] && (
                <span className="ml-1.5 text-emerald-600">✓</span>
              )}
            </button>
          ))}
        </div>

        {/* Day sub-tabs for Activities (sticky below main tabs) */}
        {activeTab === 'activities' && totalDays > 0 && (
          <div className="flex gap-1 mb-4 overflow-x-auto pb-1 sticky top-10 bg-stone-50 z-10 -mx-6 px-6 py-1">
            {Array.from({ length: totalDays }, (_, i) => (
              <button
                key={i}
                onClick={() => setActiveDay(i)}
                className={`px-3 py-1.5 text-[10px] font-bold uppercase tracking-wide rounded-full whitespace-nowrap transition-colors ${
                  activeDay === i
                    ? 'bg-stone-900 text-white'
                    : 'bg-stone-100 text-stone-500 hover:bg-stone-200'
                }`}
              >
                Day {i + 1}
              </button>
            ))}
          </div>
        )}

        {/* Tab content — greyed out when confirmed */}
        <div className={`relative ${confirmedTabs[activeTab] ? 'opacity-50 pointer-events-none' : ''}`}>
          {activeTab === 'activities' && (
            <ActivityOptions
              activities={filteredActivitiesForDay}
              selectedActivities={selectedActivities}
              onToggleActivity={handleActivityToggle}
            />
          )}

          {activeTab === 'hotels' && (
            <HotelOptions
              hotels={options?.hotels}
              selectedHotels={selectedHotels}
              onSelectHotel={handleHotelSelect}
            />
          )}

          {activeTab === 'flights' && (
            <div className="flex flex-col gap-0">
              <FlightOptions
                flights={options?.flights}
                selectedOutbound={selectedOutboundFlight}
                onSelectOutbound={setSelectedOutboundFlight}
                selectedInbound={selectedInboundFlight}
                onSelectInbound={setSelectedInboundFlight}
                routeContext={routeContext}
              />
              <IntercityTransportOptions
                intercity={options?.intercity}
                selectedIntercity={selectedIntercity}
                onSelectIntercity={handleIntercitySelect}
              />
            </div>
          )}
        </div>

        {/* Per-tab confirm / edit button */}
        <div className="mt-6 flex items-center justify-between">
          <div className="text-xs text-stone-400 font-medium">
            {Object.values(confirmedTabs).filter(Boolean).length}/{TABS.length} categories confirmed
          </div>
          {!confirmedTabs[activeTab] ? (
            <button
              onClick={() => handleConfirmTab(activeTab)}
              disabled={disabled}
              className="bg-stone-800 text-white hover:bg-stone-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all rounded-full px-5 py-2 text-xs font-bold shadow-sm"
            >
              Confirm {TABS.find(t => t.id === activeTab)?.label}
            </button>
          ) : (
            <button
              onClick={() => setConfirmedTabs(prev => ({ ...prev, [activeTab]: false }))}
              className="border border-stone-300 text-stone-600 hover:bg-stone-100 transition-all rounded-full px-5 py-2 text-xs font-bold"
            >
              Edit {TABS.find(t => t.id === activeTab)?.label}
            </button>
          )}
        </div>

        {/* Final submit — shown when all tabs confirmed */}
        {allConfirmed && (
          <div className="mt-4 pt-4 border-t border-stone-200 flex justify-end">
            <button
              onClick={handleSubmitAll}
              disabled={disabled}
              className="bg-stone-900 text-white hover:bg-stone-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all rounded-full px-6 py-2.5 text-sm font-bold shadow-sm"
            >
              Submit All Selections
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
