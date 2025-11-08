import React, { useState, useEffect } from 'react';
import { format, startOfDay, endOfDay } from 'date-fns';
import { Clock, Calendar as CalendarIcon, TrendingUp, AlertCircle } from 'lucide-react';
import { Event, EventStats } from '../types';
import { apiClient } from '../services/api';

interface DashboardProps {
  onEventClick?: (event: Event) => void;
}

const Dashboard: React.FC<DashboardProps> = ({ onEventClick }) => {
  const [nextEvent, setNextEvent] = useState<Event | null>(null);
  const [todayEvents, setTodayEvents] = useState<Event[]>([]);
  const [stats, setStats] = useState<EventStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    setLoading(true);
    
    try {
      // Load next event
      const nextEventResponse = await apiClient.getNextEvent();
      if (nextEventResponse.status === 'ok' && nextEventResponse.data) {
        setNextEvent(nextEventResponse.data);
      }

      // Load today's events
      const today = new Date();
      const startOfToday = startOfDay(today);
      const endOfToday = endOfDay(today);
      
      const todayResponse = await apiClient.getEvents(
        true,
        startOfToday.toISOString(),
        endOfToday.toISOString()
      );
      
      if (todayResponse.status === 'ok' && todayResponse.data) {
        setTodayEvents(todayResponse.data);
      }

      // Load stats for the current week
      const weekStart = new Date(today);
      weekStart.setDate(today.getDate() - today.getDay());
      const weekEnd = new Date(weekStart);
      weekEnd.setDate(weekStart.getDate() + 6);
      
      const statsResponse = await apiClient.getStats(
        weekStart.toISOString(),
        weekEnd.toISOString()
      );
      
      if (statsResponse.status === 'ok' && statsResponse.data) {
        setStats(statsResponse.data);
      }

    } catch (error) {
      console.error('Dashboard load error:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="bg-white rounded-lg shadow p-6 animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-1/2 mb-4"></div>
            <div className="h-6 bg-gray-200 rounded w-3/4"></div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
      {/* Next Event Card */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center mb-4">
          <Clock className="text-primary-600 mr-2" size={20} />
          <h3 className="text-lg font-semibold text-gray-900">Next Event</h3>
        </div>
        {nextEvent ? (
          <div 
            className="cursor-pointer hover:bg-gray-50 p-2 rounded transition-colors"
            onClick={() => onEventClick?.(nextEvent)}
          >
            <div className="font-medium text-gray-900">{nextEvent.title}</div>
            <div className="text-sm text-gray-600 mt-1">
              {format(new Date(nextEvent.time), 'PPP p')}
            </div>
            <div className="text-sm text-primary-600 mt-1">
              {nextEvent.duration} minutes
            </div>
          </div>
        ) : (
          <div className="text-gray-500">No upcoming events</div>
        )}
      </div>

      {/* Today's Schedule */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center mb-4">
          <CalendarIcon className="text-primary-600 mr-2" size={20} />
          <h3 className="text-lg font-semibold text-gray-900">Today's Schedule</h3>
        </div>
        <div className="space-y-2">
          {todayEvents.length > 0 ? (
            todayEvents.slice(0, 3).map(event => (
              <div 
                key={event.id}
                className="flex justify-between items-center py-1 cursor-pointer hover:bg-gray-50 px-2 rounded transition-colors"
                onClick={() => onEventClick?.(event)}
              >
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-gray-900 truncate">
                    {event.title}
                  </div>
                </div>
                <div className="text-xs text-gray-500 ml-2">
                  {format(new Date(event.time), 'h:mm a')}
                </div>
              </div>
            ))
          ) : (
            <div className="text-gray-500">No events today</div>
          )}
          
          {todayEvents.length > 3 && (
            <div className="text-xs text-gray-500 pt-2">
              +{todayEvents.length - 3} more events
            </div>
          )}
        </div>
      </div>

      {/* Weekly Stats */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center mb-4">
          <TrendingUp className="text-primary-600 mr-2" size={20} />
          <h3 className="text-lg font-semibold text-gray-900">This Week</h3>
        </div>
        {stats ? (
          <div className="space-y-3">
            <div className="flex justify-between">
              <span className="text-sm text-gray-600">Total Events</span>
              <span className="font-medium">{stats.total_events}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-gray-600">Total Hours</span>
              <span className="font-medium">{Math.round(stats.total_minutes / 60)}h</span>
            </div>
            {Object.entries(stats.events_by_category).length > 0 && (
              <div>
                <div className="text-sm text-gray-600 mb-2">By Category</div>
                <div className="space-y-1">
                  {Object.entries(stats.events_by_category)
                    .sort(([,a], [,b]) => b - a)
                    .slice(0, 3)
                    .map(([category, count]) => (
                      <div key={category} className="flex justify-between text-xs">
                        <span className="capitalize">{category}</span>
                        <span>{count}</span>
                      </div>
                    ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="text-gray-500">No data available</div>
        )}
      </div>
    </div>
  );
};

export default Dashboard;