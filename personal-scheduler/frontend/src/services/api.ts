import { Event, ApiResponse, TimeSlot, EventStats, CreateRecurringEventRequest, RecurringEvent } from '../types';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8080';
const API_KEY = process.env.REACT_APP_API_KEY || 'changeme';

class ApiClient {
  private baseURL: string;
  private apiKey: string;

  constructor(baseURL: string = API_BASE_URL, apiKey: string = API_KEY) {
    this.baseURL = baseURL;
    this.apiKey = apiKey;
  }

  // Helper method to convert duration from seconds (backend) to minutes (frontend)
  private convertEventDuration(event: Event): Event {
    return {
      ...event,
      duration: Math.round(event.duration / 60)
    };
  }

  private convertEventsDuration(events: Event[]): Event[] {
    return events.map(event => this.convertEventDuration(event));
  }

  private async request<T = any>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<ApiResponse<T>> {
    const url = `${this.baseURL}${endpoint}`;
    const headers = {
      'Content-Type': 'application/json',
      'Authorization': this.apiKey,
      ...options.headers,
    };

    try {
      const response = await fetch(url, {
        ...options,
        headers,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error(`API request failed: ${endpoint}`, error);
      return {
        status: 'error',
        message: error instanceof Error ? error.message : 'Unknown error',
      };
    }
  }

  // Event operations
  async getEvents(expanded: boolean = false, start?: string, end?: string): Promise<ApiResponse<Event[]>> {
    const params = new URLSearchParams();
    if (expanded) params.append('expanded', 'true');
    if (start) params.append('start', start);
    if (end) params.append('end', end);

    const response = await this.request<Event[]>(`/events?${params.toString()}`);
    
    // Convert duration from seconds (backend) to minutes (frontend)
    if (response.status === 'ok' && response.data) {
      response.data = this.convertEventsDuration(response.data);
    }
    
    return response;
  }

  async createEvent(event: Omit<Event, 'id'>): Promise<ApiResponse<Event>> {
    const response = await this.request<Event>('/events', {
      method: 'POST',
      body: JSON.stringify(event),
    });
    
    // Convert duration from seconds (backend) to minutes (frontend)
    if (response.status === 'ok' && response.data) {
      response.data = this.convertEventDuration(response.data);
    }
    
    return response;
  }

  async updateEvent(id: string, event: Partial<Event>): Promise<ApiResponse<Event>> {
    const response = await this.request<Event>(`/events/${id}`, {
      method: 'PUT',
      body: JSON.stringify(event),
    });
    
    // Convert duration from seconds (backend) to minutes (frontend)
    if (response.status === 'ok' && response.data) {
      response.data = this.convertEventDuration(response.data);
    }
    
    return response;
  }

  async deleteEvent(id: string, soft: boolean = true): Promise<ApiResponse<void>> {
    const params = soft ? '?soft=true' : '';
    return this.request<void>(`/events/${id}${params}`, {
      method: 'DELETE',
    });
  }

  async getNextEvent(): Promise<ApiResponse<Event>> {
    const response = await this.request<Event>('/events/next');
    
    // Convert duration from seconds (backend) to minutes (frontend)
    if (response.status === 'ok' && response.data) {
      response.data = this.convertEventDuration(response.data);
    }
    
    return response;
  }

  // Availability operations
  async findFreeSlots(
    date: string,
    startHour: number = 9,
    endHour: number = 17,
    minDuration: number = 30
  ): Promise<ApiResponse<TimeSlot[]>> {
    const params = new URLSearchParams({
      date,
      startHour: startHour.toString(),
      endHour: endHour.toString(),
      minDuration: minDuration.toString(),
    });

    return this.request<TimeSlot[]>(`/availability/free-slots?${params.toString()}`);
  }

  async getConflicts(time: string, duration: number): Promise<ApiResponse<Event[]>> {
    const params = new URLSearchParams({
      time,
      duration: duration.toString(),
    });

    const response = await this.request<Event[]>(`/availability/conflicts?${params.toString()}`);
    
    // Convert duration from seconds (backend) to minutes (frontend)
    if (response.status === 'ok' && response.data) {
      response.data = this.convertEventsDuration(response.data);
    }
    
    return response;
  }

  // Stats operations
  async getStats(start: string, end: string): Promise<ApiResponse<EventStats>> {
    // Convert ISO datetime strings to YYYY-MM-DD format for the backend
    const startDate = new Date(start).toISOString().split('T')[0];
    const endDate = new Date(end).toISOString().split('T')[0];
    return this.request<EventStats>(`/stats/events/${startDate}/${endDate}`);
  }

  // Task operations
  async createTask(task: {
    title: string;
    description: string;
    time: string;
    duration: number;
    notifier?: string;
    action?: string;
  }): Promise<ApiResponse<Event>> {
    const response = await this.request<Event>('/tasks', {
      method: 'POST',
      body: JSON.stringify(task),
    });
    
    // Convert duration from seconds (backend) to minutes (frontend)
    if (response.status === 'ok' && response.data) {
      response.data = this.convertEventDuration(response.data);
    }
    
    return response;
  }

  // Recurring event operations
  async getRecurringEvents(): Promise<ApiResponse<RecurringEvent[]>> {
    return this.request<RecurringEvent[]>('/recurring');
  }

  async createRecurringEvent(event: CreateRecurringEventRequest): Promise<ApiResponse<RecurringEvent>> {
    console.log('About to send POST /recurring request to:', `${this.baseURL}/recurring`);
    console.log('Request payload:', JSON.stringify(event, null, 2));
    const result = await this.request<RecurringEvent>('/recurring', {
      method: 'POST',
      body: JSON.stringify(event),
    });
    console.log('createRecurringEvent result:', result);
    return result;
  }

  async updateRecurringEvent(id: string, event: CreateRecurringEventRequest): Promise<ApiResponse<RecurringEvent>> {
    return this.request<RecurringEvent>(`/recurring/${id}`, {
      method: 'PUT',
      body: JSON.stringify(event),
    });
  }

  async deleteRecurringEvent(id: string): Promise<ApiResponse<void>> {
    return this.request<void>(`/recurring/${id}`, {
      method: 'DELETE',
    });
  }

  // Wake scheduling
  async getWakePreview(date: string): Promise<ApiResponse<{
    wakeTime: string;
    reason: string;
    firstEvents: Event[];
  }>> {
    return this.request(`/wake/preview/${date}`);
  }
}

export const apiClient = new ApiClient();
export default apiClient;