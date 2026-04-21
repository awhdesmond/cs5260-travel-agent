import React from 'react';
import { Plane, Hotel, MapPin, Train, Ticket } from 'lucide-react';

interface BookingLink {
  type: string;
  description: string;
  subtitle?: string;
  url: string;
  image_url?: string | null;
  price_label?: string | null;
}

interface BookingCardsProps {
  mode: 'search_recommend' | 'sandbox';
  confirmation_id?: string | null;
  message: string;
  booking_links?: BookingLink[] | null;
  price_disclaimer?: string | null;
}

const TYPE_META: Record<string, { label: string; icon: React.ReactNode; color: string }> = {
  flight_outbound: { label: 'Flight', icon: <Plane size={12} />, color: 'bg-sky-100 text-sky-700' },
  flight_return:   { label: 'Flight', icon: <Plane size={12} />, color: 'bg-sky-100 text-sky-700' },
  hotel:           { label: 'Hotel',  icon: <Hotel size={12} />, color: 'bg-amber-100 text-amber-700' },
  activity:        { label: 'Ticket', icon: <Ticket size={12} />, color: 'bg-emerald-100 text-emerald-700' },
  intercity:       { label: 'Transport', icon: <Train size={12} />, color: 'bg-violet-100 text-violet-700' },
};

const FALLBACK = { label: 'Link', icon: <MapPin size={12} />, color: 'bg-stone-100 text-stone-600' };

export default function BookingCards({ mode, confirmation_id, message, booking_links, price_disclaimer }: BookingCardsProps) {
  const [imgErrors, setImgErrors] = React.useState<Record<number, boolean>>({});
  const meta = (type: string) => TYPE_META[type] || FALLBACK;

  return (
    <div className="w-full flex flex-col gap-4">
      {/* Header */}
      <div className="bg-white border border-stone-200 rounded-2xl p-5 shadow-sm">
        {mode === 'sandbox' && confirmation_id && (
          <div className="mb-3 inline-block px-3 py-1 rounded-full bg-amber-50 border border-amber-200 text-amber-700 text-[10px] font-bold uppercase tracking-widest">
            Sandbox · {confirmation_id}
          </div>
        )}
        <p className="text-sm text-stone-600 leading-relaxed">{message}</p>
        {price_disclaimer && (
          <p className="text-[11px] text-stone-400 mt-2 italic">{price_disclaimer}</p>
        )}
      </div>

      {/* Cards grid */}
      {booking_links && booking_links.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {booking_links.map((link, i) => {
            const m = meta(link.type);
            return (
              <a
                key={i}
                href={link.url}
                target="_blank"
                rel="noopener noreferrer"
                className="group flex flex-col bg-white border border-stone-200 rounded-xl overflow-hidden hover:border-stone-300 hover:shadow-md hover:-translate-y-0.5 transition-all"
              >
                {/* Image or colored fallback strip */}
                {link.image_url && !imgErrors[i] ? (
                  <div className="w-full h-28 relative bg-stone-100 overflow-hidden">
                    <img
                      src={link.image_url}
                      alt={link.description}
                      className="w-full h-28 object-cover absolute inset-0"
                      loading="lazy"
                      onError={() => setImgErrors(prev => ({ ...prev, [i]: true }))}
                    />
                  </div>
                ) : link.image_url && imgErrors[i] ? (
                  <div className="w-full h-28 bg-stone-100 flex items-center justify-center">
                    <MapPin size={20} className="text-stone-300" />
                  </div>
                ) : (
                  <div className="w-full h-2 bg-stone-100" />
                )}

                <div className="p-3.5 flex flex-col gap-1.5">
                  {/* Type badge */}
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wider self-start ${m.color}`}>
                    {m.icon} {m.label}
                  </span>

                  {/* Name */}
                  <div className="text-sm font-bold text-stone-800 leading-snug group-hover:text-stone-900">
                    {link.description}
                  </div>

                  {/* Subtitle + price */}
                  <div className="flex items-center justify-between gap-2">
                    {link.subtitle && (
                      <span className="text-xs text-stone-500 truncate">{link.subtitle}</span>
                    )}
                    {link.price_label && (
                      <span className="text-xs font-semibold text-stone-700 whitespace-nowrap">{link.price_label}</span>
                    )}
                  </div>

                  {/* CTA */}
                  <span className="text-[10px] font-bold text-stone-400 group-hover:text-stone-600 mt-1 transition-colors">
                    {link.type === 'activity' ? 'Find Tickets ↗' : 'Book Now ↗'}
                  </span>
                </div>
              </a>
            );
          })}
        </div>
      )}
    </div>
  );
}
