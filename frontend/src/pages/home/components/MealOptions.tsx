import React, { useMemo, useState } from 'react';
import { MapPin } from 'lucide-react';
import OptionCard from './OptionCard';

interface MealOptionsProps {
  mealOptions: any[];
  selectedMeals: Record<string, string>;  // "day-meal_type" -> selected restaurant name
  onSelectMeal: (key: string, name: string) => void;
  onAutoSelect: () => void;
  onSubmit: () => void;
  disabled?: boolean;
}

export default function MealOptions({
  mealOptions,
  selectedMeals,
  onSelectMeal,
  onAutoSelect,
  onSubmit,
  disabled,
}: MealOptionsProps) {
  const [imgErrors, setImgErrors] = React.useState<Record<string, boolean>>({});
  const [activeDay, setActiveDay] = useState(1);

  // Group meal slots by day number
  const dayGroups = useMemo(() => {
    if (!mealOptions?.length) return new Map<number, any[]>();
    const groups = new Map<number, any[]>();
    for (const slot of mealOptions) {
      const day = slot.day_number ?? 1;
      if (!groups.has(day)) groups.set(day, []);
      groups.get(day)!.push(slot);
    }
    return groups;
  }, [mealOptions]);

  const dayNumbers = useMemo(() => Array.from(dayGroups.keys()).sort((a, b) => a - b), [dayGroups]);

  if (!mealOptions || mealOptions.length === 0) return null;

  const hasSelections = Object.keys(selectedMeals).length > 0;
  const currentDaySlots = dayGroups.get(activeDay) || [];

  return (
    <div className={`flex flex-col gap-8 w-full ${disabled ? 'opacity-60 pointer-events-none' : ''}`}>
      <div className="bg-stone-50 border border-stone-200 rounded-2xl p-6 shadow-sm">
        <h3 className="font-headline font-bold text-lg mb-2 text-stone-800">Choose Your Meals</h3>
        <p className="text-sm text-stone-500 font-medium mb-6">
          We found restaurants near your activities. Pick one per meal, or let us choose for you.
        </p>

        {/* Day sub-tabs (sticky) */}
        {dayNumbers.length > 1 && (
          <div className="flex gap-1 mb-4 overflow-x-auto pb-1 sticky top-0 bg-stone-50 z-10 -mx-6 px-6 py-1">
            {dayNumbers.map(day => (
              <button
                key={day}
                onClick={() => setActiveDay(day)}
                className={`px-3 py-1.5 text-[10px] font-bold uppercase tracking-wide rounded-full whitespace-nowrap transition-colors ${
                  activeDay === day
                    ? 'bg-stone-900 text-white'
                    : 'bg-stone-100 text-stone-500 hover:bg-stone-200'
                }`}
              >
                Day {day}
              </button>
            ))}
          </div>
        )}

        {/* Meal slots for active day (lunch + dinner shown together) */}
        <div className="flex flex-col gap-6">
          {currentDaySlots.map((slot: any, sIdx: number) => {
            const key = `${slot.day_number}-${slot.meal_type}`;
            return (
              <div key={key}>
                <h5 className="text-xs font-semibold text-stone-500 mb-2">
                  {slot.meal_type.charAt(0).toUpperCase() + slot.meal_type.slice(1)}
                </h5>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {(slot.options || []).slice(0, 4).map((opt: any, i: number) => {
                    const id = opt.name || `meal-${sIdx}-${i}`;
                    const isSelected = selectedMeals[key] === id;
                    return (
                      <OptionCard
                        key={id}
                        isSelected={isSelected}
                        onClick={() => onSelectMeal(key, id)}
                      >
                        {opt.image_url && !imgErrors[id] ? (
                          <img
                            src={opt.image_url}
                            alt={opt.name}
                            className="w-full h-24 object-cover rounded-lg mb-2"
                            loading="lazy"
                            onError={() => setImgErrors(prev => ({ ...prev, [id]: true }))}
                          />
                        ) : opt.image_url ? (
                          <div className="w-full h-24 rounded-lg mb-2 bg-stone-100 flex items-center justify-center">
                            <MapPin size={16} className="text-stone-300" />
                          </div>
                        ) : null}
                        <div className={`text-sm font-bold ${isSelected ? 'text-white' : 'text-stone-800'}`}>
                          {opt.name || 'Restaurant'}
                        </div>
                        <div className={`text-xs mt-1 ${isSelected ? 'text-stone-300' : 'text-stone-500'}`}>
                          {[opt.cuisine_type, opt.price_range].filter(Boolean).join(' · ')}
                        </div>
                        {opt.proximity_note && (
                          <div className={`text-xs mt-1 ${isSelected ? 'text-stone-400' : 'text-stone-400'}`}>
                            {opt.proximity_note}
                          </div>
                        )}
                        <a
                          href={opt.place_id ? `https://www.google.com/maps/place/?q=place_id:${opt.place_id}` : `https://www.google.com/maps/search/${encodeURIComponent(opt.name || '')}`}
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

        <div className="mt-8 flex justify-end gap-3">
          <button
            onClick={onAutoSelect}
            disabled={disabled}
            className="border border-stone-300 text-stone-600 hover:bg-stone-100 disabled:opacity-50 disabled:cursor-not-allowed transition-all rounded-full px-5 py-2.5 text-sm font-bold"
          >
            Pick for me
          </button>
          <button
            onClick={onSubmit}
            disabled={!hasSelections || disabled}
            className="bg-stone-900 text-white hover:bg-stone-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all rounded-full px-6 py-2.5 text-sm font-bold shadow-sm"
          >
            Confirm Meals
          </button>
        </div>
      </div>
    </div>
  );
}
