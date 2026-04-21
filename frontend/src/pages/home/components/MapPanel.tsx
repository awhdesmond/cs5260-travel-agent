import React, { useMemo, useEffect } from 'react';
import { Map, AdvancedMarker, useMap } from '@vis.gl/react-google-maps';
import { Hotel } from 'lucide-react';
import { clsx } from 'clsx';
import type { DayPlan } from '../types/itinerary';

interface MapPanelProps {
  day: DayPlan | undefined;
  activeSlotId: string | null;
  onPinClick: (slotId: string) => void;
  className?: string;
}

interface MapPin {
  slotId: string;
  lat: number;
  lng: number;
  label: string;
  slotType: 'activity' | 'meal';
  pinNumber: number;
}

interface MapContentProps {
  pins: MapPin[];
  hotelPin: { lat: number; lng: number } | null;
  activeSlotId: string | null;
  onPinClick: (id: string) => void;
}

function _haversineKm(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLng = ((lng2 - lng1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function _routeLabel(km: number): string {
  if (km < 1) return `${Math.round(km * 1000)}m`;
  return `${km.toFixed(1)}km`;
}

interface SegmentLabel {
  lat: number;
  lng: number;
  text: string;
}

function MapContent({ pins, hotelPin, activeSlotId, onPinClick }: MapContentProps) {
  const map = useMap();

  // Auto-fit bounds when pins change
  useEffect(() => {
    if (!map || pins.length === 0 || typeof google === 'undefined') return;
    const bounds = new google.maps.LatLngBounds();
    pins.forEach(p => bounds.extend({ lat: p.lat, lng: p.lng }));
    if (hotelPin) bounds.extend({ lat: hotelPin.lat, lng: hotelPin.lng });
    map.fitBounds(bounds, 60);
  }, [map, pins, hotelPin]);

  // Fly to active pin when activeSlotId changes
  useEffect(() => {
    if (!map || !activeSlotId) return;
    const pin = pins.find(p => p.slotId === activeSlotId);
    if (pin) {
      map.panTo({ lat: pin.lat, lng: pin.lng });
      map.setZoom(16);
    }
  }, [map, activeSlotId, pins]);

  // Draw polyline connecting pins chronologically
  useEffect(() => {
    if (!map || pins.length < 2 || typeof google === 'undefined') return;
    const path = pins.map(p => ({ lat: p.lat, lng: p.lng }));
    const polyline = new google.maps.Polyline({
      path,
      strokeColor: '#3b82f6',
      strokeWeight: 2,
      strokeOpacity: 0.6,
      geodesic: true,
      map,
    });
    return () => polyline.setMap(null);
  }, [map, pins]);

  // Compute segment distance labels at midpoints between consecutive pins
  const segments: SegmentLabel[] = useMemo(() => {
    if (pins.length < 2) return [];
    return pins.slice(0, -1).map((p, i) => {
      const next = pins[i + 1];
      const km = _haversineKm(p.lat, p.lng, next.lat, next.lng);
      return {
        lat: (p.lat + next.lat) / 2,
        lng: (p.lng + next.lng) / 2,
        text: _routeLabel(km),
      };
    });
  }, [pins]);

  return (
    <>
      {/* Distance labels between pins */}
      {segments.map((seg, i) => (
        <AdvancedMarker key={`seg-${i}`} position={{ lat: seg.lat, lng: seg.lng }} zIndex={0}>
          <div className="bg-white/90 backdrop-blur-sm text-[9px] text-stone-500 font-medium px-1.5 py-0.5 rounded shadow-sm border border-stone-200 pointer-events-none">
            {seg.text}
          </div>
        </AdvancedMarker>
      ))}

      {/* Numbered pins */}
      {pins.map((pin) => (
        <AdvancedMarker
          key={pin.slotId}
          position={{ lat: pin.lat, lng: pin.lng }}
          onClick={() => onPinClick(pin.slotId)}
          zIndex={pin.slotId === activeSlotId ? 100 : 1}
        >
          <div
            className={clsx(
              'flex items-center justify-center rounded-full text-white text-xs font-bold shadow-md cursor-pointer transition-transform',
              'w-7 h-7',
              pin.slotType === 'activity' ? 'bg-blue-500' : 'bg-amber-500',
              pin.slotId === activeSlotId && 'ring-4 ring-white ring-offset-2 scale-125'
            )}
          >
            {pin.pinNumber}
          </div>
        </AdvancedMarker>
      ))}

      {hotelPin && (
        <AdvancedMarker position={{ lat: hotelPin.lat, lng: hotelPin.lng }}>
          <div className="flex items-center justify-center w-8 h-8 rounded-full bg-stone-700 text-white shadow-md">
            <Hotel size={14} />
          </div>
        </AdvancedMarker>
      )}
    </>
  );
}

export default function MapPanel({ day, activeSlotId, onPinClick, className }: MapPanelProps) {
  const pins: MapPin[] = useMemo(() => {
    if (!day) return [];
    let pinNum = 0;
    return day.time_slots
      .map((slot, index) => {
        // Only activity/meal with coordinates get pins
        if ((slot.slot_type !== 'activity' && slot.slot_type !== 'meal') || slot.lat == null || slot.lng == null) return null;
        pinNum++;
        return {
          slotId: `day-${day.day_number}-slot-${index}`,
          lat: slot.lat,
          lng: slot.lng,
          label: slot.activity_name || slot.label,
          slotType: slot.slot_type as 'activity' | 'meal',
          pinNumber: pinNum,
        };
      })
      .filter(Boolean) as MapPin[];
  }, [day]);

  // Hotel coordinates not on DayPlan currently — render when available
  // Future: backend enrichment could add hotel_lat/hotel_lng to DayPlan
  const hotelPin = useMemo(() => {
    if (!day?.hotel_name) return null;
    // Return null for now — hotel pin will appear when backend provides coordinates
    return null;
  }, [day]);

  // Count total activity/meal slots to detect missing pins
  const totalVenueSlots = useMemo(() => {
    if (!day) return 0;
    return day.time_slots.filter(s => s.slot_type === 'activity' || s.slot_type === 'meal').length;
  }, [day]);

  // If no pins (no coordinates on slots), show message
  if (pins.length === 0) {
    return (
      <div className={clsx('flex items-center justify-center bg-stone-50 text-stone-300 text-sm', className)}>
        No location data available for this day
      </div>
    );
  }

  return (
    <div className={clsx('relative', className)}>
      {pins.length < totalVenueSlots && (
        <div className="absolute bottom-1 left-1 z-10 bg-white/80 backdrop-blur-sm rounded px-2 py-1">
          <span className="text-[9px] text-stone-400">{pins.length}/{totalVenueSlots} locations shown</span>
        </div>
      )}
      <Map
        defaultCenter={{ lat: pins[0]?.lat || 0, lng: pins[0]?.lng || 0 }}
        defaultZoom={13}
        mapId="DEMO_MAP_ID"
        style={{ width: '100%', height: '100%' }}
        gestureHandling="greedy"
        disableDefaultUI={false}
      >
        <MapContent
          pins={pins}
          hotelPin={hotelPin}
          activeSlotId={activeSlotId}
          onPinClick={onPinClick}
        />
      </Map>
    </div>
  );
}
