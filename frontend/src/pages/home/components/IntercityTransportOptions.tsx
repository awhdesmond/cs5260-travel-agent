import React from 'react';
import OptionCard from './OptionCard';

interface IntercityTransportOptionsProps {
  intercity: any;
  selectedIntercity: Record<string, string>;
  onSelectIntercity: (hopKey: string, id: string) => void;
}

export default function IntercityTransportOptions({
  intercity,
  selectedIntercity,
  onSelectIntercity,
}: IntercityTransportOptionsProps) {
  if (!intercity?.hops?.length) return null;

  // Build route summary: "Kunming → Dali → Lijiang"
  const cities: string[] = [];
  for (const hop of intercity.hops) {
    if (cities.length === 0 && hop.from_city) cities.push(hop.from_city);
    if (hop.to_city) cities.push(hop.to_city);
  }
  const routeSummary = cities.join(' → ');

  return (
    <div className="mb-8 border-t border-stone-200 pt-6">
      <h4 className="text-xs font-bold uppercase tracking-widest text-stone-400 mb-2">Inter-City Transport</h4>
      <p className="text-sm text-stone-600 font-medium mb-4">
        Planned route: <span className="font-bold text-stone-800">{routeSummary}</span>
      </p>
      <div className="flex flex-col gap-6">
        {intercity.hops.map((hop: any, hIdx: number) => {
          const hopKey = `${hop.from_city}->${hop.to_city}`;
          return (
            <div key={hopKey || hIdx}>
              <h5 className="text-xs font-semibold text-stone-500 mb-2">
                {hop.from_city} → {hop.to_city}
              </h5>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {hop.options?.map((opt: any, i: number) => {
                  const id = opt.operator || opt.mode || `intercity-${i}`;
                  const isSelected = selectedIntercity[hopKey] === id;
                  return (
                    <OptionCard
                      key={id}
                      isSelected={isSelected}
                      onClick={() => onSelectIntercity(hopKey, id)}
                    >
                      <div className={`text-sm font-bold capitalize ${isSelected ? 'text-white' : 'text-stone-800'}`}>
                        {opt.mode || 'Transport'}
                      </div>
                      {opt.operator && (
                        <div className={`text-xs mt-1 ${isSelected ? 'text-stone-300' : 'text-stone-500'}`}>
                          {opt.operator}
                        </div>
                      )}
                      <div className={`text-xs mt-1 font-medium ${isSelected ? 'text-stone-300' : 'text-stone-600'}`}>
                        SGD {opt.price_sgd?.toFixed(0)}
                        {opt.duration && ` • ${opt.duration}`}
                      </div>
                      {opt.booking_link ? (
                        <a
                          href={opt.booking_link}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className={`text-[10px] mt-1.5 inline-block underline ${isSelected ? 'text-stone-300' : 'text-stone-400 hover:text-stone-600'}`}
                        >
                          Book / View details ↗
                        </a>
                      ) : (
                        <a
                          href={`https://www.google.com/search?q=${encodeURIComponent(`${hop.from_city} to ${hop.to_city} ${opt.mode || 'transport'}`)}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className={`text-[10px] mt-1.5 inline-block underline ${isSelected ? 'text-stone-300' : 'text-stone-400 hover:text-stone-600'}`}
                        >
                          Search on Google ↗
                        </a>
                      )}
                    </OptionCard>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
