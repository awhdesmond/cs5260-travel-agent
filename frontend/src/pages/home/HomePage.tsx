import React, { useState, useEffect } from 'react';
import { PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import toast from 'react-hot-toast';
import ItineraryCard from './ItineraryCard';
import ChatInterface from './ChatInterface';
import DayView from './DayView';

import {
  ActionNameSetUser,
  useUser,
} from '../../context/user-context';

import UsersAPI from '../../apis/users';
import ItinerariesAPI from '../../apis/itineraries';

export default function HomePage() {
  const [itineraries, setItineraries] = useState<any[]>([]);
  const [selectedItineraryId, setSelectedItineraryId] = useState<string | null>(null);
  const [loadedItinerary, setLoadedItinerary] = useState<any>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const { user, dispatch: userDispatch } = useUser();

  const fetchItineraries = async (token: string) => {
    const resp = await ItinerariesAPI.listItineraries(token);
    if (resp.error) {
      toast.error(resp.error);
      return;
    }
    // Handle both cases: resp itself is an array or resp has an itineraries property
    const data = Array.isArray(resp) ? resp : (resp.itineraries || []);
    setItineraries(data);
  }

  const login = async () => {
    const resp = await UsersAPI.login(
      import.meta.env.VITE_DEMO_EMAIL || 'admin@cs5260.nus.edu.sg',
      import.meta.env.VITE_DEMO_PASSWORD || 'NeuralNets5260!',
    );
    if (resp.error) {
      toast.error(resp.error);
      return;
    }
    userDispatch({
      type: ActionNameSetUser,
      value: { user: resp.user }
    });
  }

  // Always re-login on mount to get a fresh JWT (cached token may be expired)
  useEffect(() => { login(); }, []);

  // Fetch itineraries once we have a valid token
  useEffect(() => {
    if (user?.token) {
      fetchItineraries(user.token);
    }
  }, [user]);

  // Load full itinerary data when a sidebar card is selected
  // getItinerary returns: { destination, travel_dates, architecture, status, itinerary: { days, total_days, grand_total_sgd } }
  useEffect(() => {
    if (selectedItineraryId && user?.token) {
      setLoadedItinerary(null); // reset while loading
      ItinerariesAPI.getItinerary(selectedItineraryId, user.token)
        .then((data) => {
          if (data && !data.error) {
            setLoadedItinerary(data);
          }
        });
    } else {
      setLoadedItinerary(null);
    }
  }, [selectedItineraryId, user?.token]);

  return (
    <div className="flex w-full h-[calc(100vh-140px)] overflow-hidden bg-white">
      {/* Sidebar: Floating History */}
      <aside 
        className={`h-full shrink-0 transition-all duration-300 ease-in-out overflow-hidden ${
          isSidebarOpen ? 'w-[23rem] p-6 opacity-100' : 'w-0 p-0 opacity-0'
        }`}
      >
        <div className="w-80 bg-stone-50/50 border border-stone-100 rounded-[2.5rem] flex flex-col h-full relative overflow-hidden transition-all duration-300 hover:shadow-sm">
          <div className="p-6 border-b border-stone-100/30 text-center sticky top-0 bg-stone-50/80 backdrop-blur-md z-10 relative">
            <h2 className="font-headline font-bold text-[10px] uppercase tracking-widest text-stone-400">History</h2>
            <div className="text-[10px] font-bold text-stone-300 mt-0.5 whitespace-nowrap uppercase tracking-tighter">{itineraries.length} journeys created</div>
            <button
              onClick={() => setIsSidebarOpen(false)}
              className="absolute right-4 top-1/2 -translate-y-1/2 p-2 text-stone-400 hover:text-stone-600 hover:bg-stone-200/50 rounded-full transition-colors"
              title="Collapse history"
            >
              <PanelLeftClose size={18} />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-6 custom-scrollbar flex flex-col">
            <ul className={`flex flex-col gap-8 items-center ${itineraries.length === 0 ? 'flex-1 justify-center' : ''}`}>
              {itineraries.map(itinerary => (
                <li key={itinerary.id} className="w-full flex justify-center">
                  <ItineraryCard 
                    {...itinerary} 
                    onSelect={(id) => setSelectedItineraryId(id)} 
                  />
                </li>
              ))}
              {itineraries.length === 0 && (
                <div className="text-center text-stone-300">
                  <p className="text-sm font-medium">Empty History</p>
                  <p className="text-xs">Your past journeys will appear here.</p>
                </div>
              )}
            </ul>
          </div>
        </div>
      </aside>

      {/* Main Workspace */}
      <main className="flex-1 flex flex-col h-full bg-white relative overflow-hidden transition-all duration-300">
        {!isSidebarOpen && (
          <button
            onClick={() => setIsSidebarOpen(true)}
            className="absolute top-6 left-6 z-20 p-2 text-stone-400 hover:text-stone-600 hover:bg-stone-50 rounded-full transition-all duration-300"
            title="Expand history"
          >
            <PanelLeftOpen size={20} />
          </button>
        )}

        <div className={`w-full h-full pt-6 transition-all duration-300 ${isSidebarOpen ? 'px-10' : 'pl-16 pr-10'}`}>
          {selectedItineraryId ? (
            <DayView
              itinerary={loadedItinerary?.itinerary || loadedItinerary}
              destination={loadedItinerary?.destination || loadedItinerary?.itinerary?.days?.[0]?.city || 'Trip'}
              onBack={() => {
                setSelectedItineraryId(null);
                setLoadedItinerary(null);
              }}
              bookingStatus={loadedItinerary?.status}
              bookingConfirmationId={loadedItinerary?.booking_confirmation_id}
              bookingLinks={loadedItinerary?.booking_links}
            />
          ) : (
            <ChatInterface />
          )}
        </div>
      </main>
    </div>
  );
}
