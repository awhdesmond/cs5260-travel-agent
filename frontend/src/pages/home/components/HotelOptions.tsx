import React from 'react';
import { MapPin } from 'lucide-react';
import OptionCard from './OptionCard';

interface HotelOptionsProps {
  hotels: any;
  selectedHotels: Record<string, string>;
  onSelectHotel: (city: string, id: string) => void;
}

export default function HotelOptions({
  hotels,
  selectedHotels,
  onSelectHotel,
}: HotelOptionsProps) {
  const [imgErrors, setImgErrors] = React.useState<Record<string, boolean>>({});

  if (!hotels?.cities?.length) return null;

  return (
    <div className="mb-8 border-t border-stone-200 pt-6">
      <h4 className="text-xs font-bold uppercase tracking-widest text-stone-400 mb-4">Hotels</h4>
      <div className="flex flex-col gap-6">
        {hotels.cities.map((cityObj: any, cIdx: number) => {
          const city = cityObj.city;
          const nights = cityObj.nights;
          return (
            <div key={city || cIdx}>
              <h5 className="text-xs font-semibold text-stone-500 mb-2">
                {city}
                {nights ? ` · ${nights} night${nights > 1 ? 's' : ''}` : ''}
              </h5>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {cityObj.options?.slice(0, 4).map((h: any, i: number) => {
                  const id = h.name || `hotel-${i}`;
                  const isSelected = selectedHotels[city] === id;
                  return (
                    <OptionCard
                      key={id}
                      isSelected={isSelected}
                      onClick={() => onSelectHotel(city, id)}
                    >
                      {h.image_url && !imgErrors[id] ? (
                        <img
                          src={h.image_url}
                          alt={h.name}
                          className="w-full h-24 object-cover rounded-lg mb-2"
                          loading="lazy"
                          onError={() => setImgErrors(prev => ({ ...prev, [id]: true }))}
                        />
                      ) : h.image_url ? (
                        <div className="w-full h-24 rounded-lg mb-2 bg-stone-100 flex items-center justify-center">
                          <MapPin size={16} className="text-stone-300" />
                        </div>
                      ) : null}
                      <div className={`text-sm font-bold ${isSelected ? 'text-white' : 'text-stone-800'}`}>
                        {h.name || 'Hotel'}
                        {h.star_rating != null && (
                          <span className={`ml-1.5 text-xs font-medium ${isSelected ? 'text-amber-300' : 'text-amber-500'}`}>
                            {'★'.repeat(Math.floor(h.star_rating))}{h.star_rating % 1 >= 0.5 ? '½' : ''}
                          </span>
                        )}
                      </div>
                      <div className={`text-xs mt-1 font-medium ${isSelected ? 'text-stone-300' : 'text-stone-600'}`}>
                        SGD {h.price_per_night_sgd?.toFixed(0)} / night
                        {nights && h.price_per_night_sgd && (
                          <span className="ml-1 opacity-70">
                            (SGD {(h.price_per_night_sgd * nights).toFixed(0)} total)
                          </span>
                        )}
                      </div>
                      {h.address && (
                        <div className={`text-xs mt-1 line-clamp-2 ${isSelected ? 'text-stone-400' : 'text-stone-500'}`}>{h.address}</div>
                      )}
                      <a
                        href={h.place_id ? `https://www.google.com/maps/place/?q=place_id:${h.place_id}` : `https://www.google.com/maps/search/${encodeURIComponent(h.name + ' ' + (city || ''))}`}
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
}
