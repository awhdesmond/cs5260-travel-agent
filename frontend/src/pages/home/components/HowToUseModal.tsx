import React from 'react';
import { X, Info } from 'lucide-react';

interface HowToUseModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function HowToUseModal({ isOpen, onClose }: HowToUseModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 animate-in fade-in duration-200">
      <div className="bg-white rounded-2xl w-full max-w-2xl shadow-xl overflow-hidden animate-in zoom-in-95 duration-200 flex flex-col max-h-[90vh]">
        
        {/* Header */}
        <div className="px-6 py-4 border-b border-stone-100 flex items-center justify-between bg-stone-50">
          <div className="flex items-center gap-2">
            <Info size={20} className="text-black" />
            <h2 className="text-lg font-bold text-stone-800">How to Use the Planner</h2>
          </div>
          <button 
            onClick={onClose}
            className="p-2 rounded-full hover:bg-stone-200 text-stone-500 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-stone-900 focus-visible:ring-offset-2"
          >
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto custom-scrollbar flex-1">
          <div className="space-y-6 text-stone-700 text-sm">
            <p>
              The multi-agent travel planner runs a <strong>4-Pass Pipeline</strong> to produce a complete day-by-day itinerary tailored to you.
            </p>

            <div className="space-y-4">
              <div className="flex gap-4">
                <div className="w-8 h-8 shrink-0 rounded-full bg-stone-100 text-black font-bold flex items-center justify-center">1</div>
                <div>
                  <h3 className="font-bold text-stone-900 text-base mb-1">Tell us what you want</h3>
                  <p>Type a natural language trip request like <em>"5 days in Tokyo and Osaka, cultural, moderate pace"</em>. The agent may ask clarification questions. Once ready, simply verify the summary and reply <strong>"Confirm"</strong>.</p>
                </div>
              </div>

              <div className="flex gap-4">
                <div className="w-8 h-8 shrink-0 rounded-full bg-stone-100 text-black font-bold flex items-center justify-center">2</div>
                <div>
                  <h3 className="font-bold text-stone-900 text-base mb-1">Pick Flights, Hotels & Activities</h3>
                  <p>The agents will search for real-time options. Select your preferred flights and hotel from the interactive cards provided.</p>
                </div>
              </div>

              <div className="flex gap-4">
                <div className="w-8 h-8 shrink-0 rounded-full bg-stone-100 text-black font-bold flex items-center justify-center">3</div>
                <div>
                  <h3 className="font-bold text-stone-900 text-base mb-1">Select Meals</h3>
                  <p>Based on your selected activities, you'll be presented with nearby restaurant recommendations. Pick your favorites or let the agent auto-select.</p>
                </div>
              </div>

              <div className="flex gap-4">
                <div className="w-8 h-8 shrink-0 rounded-full bg-stone-100 text-black font-bold flex items-center justify-center">4</div>
                <div>
                  <h3 className="font-bold text-stone-900 text-base mb-1">Review & Book</h3>
                  <p>The planner will assemble all your choices into a complete day-by-day schedule, including transit details. You can chat to make edits, then generate final <strong>Booking Links</strong> when you're ready.</p>
                </div>
              </div>
            </div>

            <div className="bg-stone-50 p-4 rounded-xl border border-stone-100 mt-6 pt-4">
              <h4 className="font-bold text-stone-800 mb-2">Architecture Options</h4>
              <p>You can toggle between two agent orchestrations at the bottom of the chat:</p>
              <ul className="list-disc pl-5 mt-2 space-y-1">
                <li><strong>Supervisor:</strong> A hierarchical approach with a root coordinator.</li>
                <li><strong>Swarm:</strong> A flat, parallel worker architecture.</li>
              </ul>
            </div>
            
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-stone-100 bg-stone-50 flex justify-end">
          <button 
            onClick={onClose}
            className="px-6 py-2 bg-black text-white font-bold rounded-full hover:bg-stone-800 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-2 focus-visible:ring-offset-black"
          >
            Got it
          </button>
        </div>

      </div>
    </div>
  );
}
