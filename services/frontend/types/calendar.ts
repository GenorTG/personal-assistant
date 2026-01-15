// Calendar types

export interface CalendarEvent {
  id: string;
  title: string;
  description?: string;
  start_time: string;
  end_time: string;
  location?: string;
  all_day?: boolean;
  conflicts?: CalendarEvent[];
  has_conflicts?: boolean;
}




