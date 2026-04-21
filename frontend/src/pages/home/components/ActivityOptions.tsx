import React from 'react';
import { MapPin } from 'lucide-react';
import OptionCard from './OptionCard';

interface ActivityOptionsProps {
  activities: any;
  selectedActivities: string[];
  onToggleActivity: (id: string) => void;
}

/** "SGD 0" → "Free Entry", otherwise "SGD 25" */
function formatCost(cost: number | null | undefined): string {
  if (cost == null || cost === 0) return 'Free Entry';
  return `SGD ${cost.toFixed(0)}`;
}

/** Format duration: 120 → "2h", 90 → "1.5h", null → "" */
function formatDuration(minutes: number | null | undefined): string {
  if (!minutes) return '';
  const hours = minutes / 60;
  if (hours === Math.floor(hours)) return `${hours}h`;
  return `${hours.toFixed(1)}h`;
}

/** Capitalize first letter: "morning" → "Morning" */
function capitalize(s: string | null | undefined): string {
  if (!s) return '';
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export default function ActivityOptions({
  activities,
  selectedActivities,
  onToggleActivity,
}: ActivityOptionsProps) {
  const [imgErrors, setImgErrors] = React.useState<Record<string, boolean>>({});

  if (!activities?.cities?.length) return null;

  return (
    <div className="mb-6 border-t border-stone-200 pt-6">
      <h4 className="text-xs font-bold uppercase tracking-widest text-stone-400 mb-4">Activities</h4>
      <div className="flex flex-col gap-6">
        {activities.cities.map((cityObj: any, cIdx: number) => {
          const city = cityObj.city;
          return (
            <div key={city || cIdx}>
              <h5 className="text-xs font-semibold text-stone-500 mb-2">{city}</h5>
              <div className="flex flex-col gap-4">
                {cityObj.options_per_day?.map((dayOpts: any[], dayIdx: number) => {
                  if (!dayOpts || dayOpts.length === 0) return null;
                  return (
                    <div key={dayIdx}>
                      <h6 className="text-[10px] uppercase font-bold text-stone-400 mb-2">Day {(cityObj._singleDayIndex ?? dayIdx) + 1}</h6>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {dayOpts.slice(0, 4).map((a: any, i: number) => {
                          const id = a.place_id || (a.name && a.address ? `${a.name}|${a.address}` : a.name) || `activity-${cIdx}-${dayIdx}-${i}`;
                          const isSelected = selectedActivities.includes(id);
                          const cost = formatCost(a.estimated_cost_sgd);
                          const duration = formatDuration(a.estimated_duration_minutes);
                          const timeOfDay = capitalize(a.recommended_time_of_day);
                          const details = [cost, duration, timeOfDay].filter(Boolean).join(' · ');

                          return (
                            <OptionCard
                              key={id}
                              isSelected={isSelected}
                              onClick={() => onToggleActivity(id)}
                            >
                              {a.image_url && !imgErrors[id] ? (
                                <img
                                  src={a.image_url}
                                  alt={a.name}
                                  className="w-full h-24 object-cover rounded-lg mb-2"
                                  loading="lazy"
                                  onError={() => setImgErrors(prev => ({ ...prev, [id]: true }))}
                                />
                              ) : a.image_url ? (
                                <div className="w-full h-24 rounded-lg mb-2 bg-stone-100 flex items-center justify-center">
                                  <MapPin size={16} className="text-stone-300" />
                                </div>
                              ) : null}
                              <div className={`text-sm font-bold ${isSelected ? 'text-white' : 'text-stone-800'}`}>{a.name || 'Activity'}</div>
                              <div className={`text-xs mt-1 font-medium ${isSelected ? 'text-stone-300' : 'text-stone-600'}`}>
                                {details}
                              </div>
                              {a.category && (
                                <div className={`text-xs mt-1 capitalize ${isSelected ? 'text-stone-400' : 'text-stone-500'}`}>{a.category}</div>
                              )}
                              {a.address && (
                                <div className={`text-xs mt-1 line-clamp-1 ${isSelected ? 'text-stone-400' : 'text-stone-500'}`}>{a.address}</div>
                              )}
                              <a
                                href={a.place_id ? `https://www.google.com/maps/place/?q=place_id:${a.place_id}` : `https://www.google.com/maps/search/${encodeURIComponent(a.name + ' ' + (city || ''))}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                onClick={(e) => e.stopPropagation()}
                                className={`text-[10px] mt-1.5 inline-block underline ${isSelected ? 'text-stone-300' : 'text-stone-400 hover:text-stone-600'}`}
                              >View on Google Maps ↗</a>
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
        })}
      </div>
    </div>
  );
}
