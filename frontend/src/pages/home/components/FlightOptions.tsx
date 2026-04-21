import React from 'react';
import OptionCard from './OptionCard';

interface FlightOptionsProps {
  flights: any;
  selectedOutbound: string | null;
  selectedInbound: string | null;
  onSelectOutbound: (id: string) => void;
  onSelectInbound: (id: string) => void;
  routeContext?: { origin: string; destinations: string[] };
}

/** Format ISO 8601 datetime to "7 Apr, 12:40" */
function formatDateTime(iso: string): string {
  try {
    const d = new Date(iso);
    const day = d.getDate();
    const month = d.toLocaleString('en-US', { month: 'short' });
    const hours = d.getHours().toString().padStart(2, '0');
    const minutes = d.getMinutes().toString().padStart(2, '0');
    return `${day} ${month}, ${hours}:${minutes}`;
  } catch {
    return iso;
  }
}

/** Format ISO 8601 duration "PT4H10M" to "4h 10m" */
function formatDuration(iso: string | null | undefined): string {
  if (!iso) return '';
  const match = iso.match(/PT(?:(\d+)H)?(?:(\d+)M)?/);
  if (!match) return iso;
  const h = match[1] ? `${match[1]}h` : '';
  const m = match[2] ? ` ${match[2]}m` : '';
  return (h + m).trim();
}

/** "0 stops" → "Direct", "1 stop", "2 stops" */
function formatStops(stops: number): string {
  if (stops === 0) return 'Direct';
  return `${stops} stop${stops > 1 ? 's' : ''}`;
}

export default function FlightOptions({
  flights,
  selectedOutbound,
  selectedInbound,
  onSelectOutbound,
  onSelectInbound,
  routeContext,
}: FlightOptionsProps) {
  if (!flights) return null;

  const origin = routeContext?.origin || '';
  const destinations = routeContext?.destinations || [];
  const firstCity = destinations[0] || '';
  const lastCity = destinations[destinations.length - 1] || firstCity;

  const renderFlightCard = (f: any, i: number, isSelected: boolean, onSelect: (id: string) => void) => {
    const id = f.flight_number || f.airline || `flight-${i}`;
    const dep = formatDateTime(f.departure_time);
    const arr = formatDateTime(f.arrival_time);
    const dur = formatDuration(f.duration);
    const stops = formatStops(f.stops ?? 0);
    const flightNum = f.flight_number ? ` (${f.flight_number})` : '';

    return (
      <OptionCard
        key={id}
        isSelected={isSelected}
        onClick={() => onSelect(id)}
      >
        <div className={`text-sm font-bold ${isSelected ? 'text-white' : 'text-stone-800'}`}>
          {f.airline || 'Flight'}{flightNum}
        </div>
        <div className={`text-xs mt-1 ${isSelected ? 'text-stone-300' : 'text-stone-500'}`}>
          {dep} → {arr}
          {dur && <span className="ml-1.5">({dur})</span>}
        </div>
        <div className={`text-xs mt-1 font-medium ${isSelected ? 'text-stone-300' : 'text-stone-600'}`}>
          SGD {f.price_sgd?.toFixed(0)} · {stops}
          {f.cabin_class && f.cabin_class !== 'economy' && (
            <span className="ml-1.5 capitalize">· {f.cabin_class}</span>
          )}
        </div>
        {f.booking_link ? (
          <a href={f.booking_link} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()} className={`text-[10px] mt-1.5 inline-block underline ${isSelected ? 'text-stone-300' : 'text-stone-400 hover:text-stone-600'}`}>Book / View details ↗</a>
        ) : (
          <a href={`https://www.google.com/search?q=${encodeURIComponent((f.airline || '') + ' ' + (f.flight_number || '') + ' flight')}`} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()} className={`text-[10px] mt-1.5 inline-block underline ${isSelected ? 'text-stone-300' : 'text-stone-400 hover:text-stone-600'}`}>Search on Google ↗</a>
        )}
      </OptionCard>
    );
  };

  return (
    <div className="mb-8">
      <h4 className="text-xs font-bold uppercase tracking-widest text-stone-400 mb-4">Flights</h4>
      <div className="flex flex-col gap-4">

        {/* Outbound */}
        {flights.outbound_flights?.length > 0 && (
          <div>
            <h5 className="text-xs font-semibold text-stone-500 mb-2">
              Outbound{origin && firstCity ? `: ${origin} to ${firstCity}` : ''}
            </h5>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {flights.outbound_flights.slice(0, 4).map((f: any, i: number) => {
                const id = f.flight_number || f.airline || `outbound-${i}`;
                return renderFlightCard(f, i, selectedOutbound === id, onSelectOutbound);
              })}
            </div>
          </div>
        )}

        {/* Inbound */}
        {flights.inbound_flights?.length > 0 && (
          <div className="mt-4">
            <h5 className="text-xs font-semibold text-stone-500 mb-2">
              Inbound{lastCity && origin ? `: ${lastCity} to ${origin}` : ''}
            </h5>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {flights.inbound_flights.slice(0, 4).map((f: any, i: number) => {
                const id = f.flight_number || f.airline || `inbound-${i}`;
                return renderFlightCard(f, i, selectedInbound === id, onSelectInbound);
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
