// Matches backend/src/state/models.py DayPlan / DailySchedule structure

export interface TimeSlot {
  slot_type: 'activity' | 'meal' | 'buffer' | 'transit';
  label: string;
  start_time: string;        // "HH:MM"
  end_time?: string;         // "HH:MM"
  cost_sgd: number;
  notes?: string;
  activity_name?: string;
  address?: string;
  booking_required?: boolean;
  booking_link?: string;
  image_url?: string;        // from Places API enrichment
  lat?: number;              // from Places API enrichment (may be undefined)
  lng?: number;              // from Places API enrichment (may be undefined)
}

export interface DayPlan {
  day_number: number;        // 1-based
  date: string;              // "YYYY-MM-DD"
  city: string;
  time_slots: TimeSlot[];
  hotel_name?: string;
  daily_subtotal_sgd: number;
}

export interface DailySchedule {
  total_days: number;
  days: DayPlan[];
  grand_total_sgd: number;
}
