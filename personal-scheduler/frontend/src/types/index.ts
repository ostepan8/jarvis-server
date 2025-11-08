export interface Event {
  id: string;
  title: string;
  description: string;
  time: string; // ISO string
  duration: number; // minutes (converted from backend's seconds in API client)
  category: string;
  recurring?: boolean;
  providerEventId?: string;
  providerTaskId?: string;
  notifierName?: string;
  actionName?: string;
}

export interface RecurringEvent extends Event {
  recurring: true;
  recurrencePattern: {
    type: 'daily' | 'weekly' | 'monthly' | 'yearly';
    interval: number;
    days?: number[]; // For weekly recurrence: 0=Sunday, 1=Monday, etc.
    max?: number; // Maximum occurrences (-1 for unlimited)
    end?: string; // End date ISO string
  };
}

export interface CreateRecurringEventRequest {
  title: string;
  description: string;
  start: string; // Local time string YYYY-MM-DD HH:MM
  duration: number; // seconds
  category?: string;
  pattern: {
    type: 'daily' | 'weekly' | 'monthly' | 'yearly';
    interval: number;
    days?: number[]; // For weekly: array of weekday numbers
    max?: number; // -1 for unlimited
    end?: string; // ISO string
  };
}

export interface TimeSlot {
  start: string;
  end: string;
  duration: number;
}

export interface EventStats {
  total_events: number;
  total_minutes: number;
  events_by_category: Record<string, number>;
  busiest_days: Array<{ date: string; event_count: number }>;
  busiest_hours: Array<{ hour: number; event_count: number }>;
}

export interface ApiResponse<T = any> {
  status: 'ok' | 'error';
  data?: T;
  message?: string;
}