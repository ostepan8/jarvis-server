import React, { useState, useEffect } from 'react';
import { format, startOfMonth, endOfMonth, startOfWeek, endOfWeek, startOfDay, endOfDay, eachDayOfInterval, eachHourOfInterval, isSameMonth, isSameDay, isToday, addDays, subDays, addWeeks, subWeeks, addMonths, subMonths } from 'date-fns';
import { ChevronLeft, ChevronRight, Plus, Calendar as CalendarIcon, Grid3X3, Columns, Square } from 'lucide-react';
import { Event } from '../types';
import { apiClient } from '../services/api';

type ViewMode = 'day' | 'week' | 'month';

interface CalendarProps {
  onEventClick?: (event: Event) => void;
  onDateClick?: (date: Date) => void;
  onCreateEvent?: () => void;
}

const Calendar: React.FC<CalendarProps> = ({ onEventClick, onDateClick, onCreateEvent }) => {
  const [currentDate, setCurrentDate] = useState(new Date());
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('month');

  // Calculate date ranges based on view mode
  const getDateRange = () => {
    switch (viewMode) {
      case 'day':
        const dayStart = startOfDay(currentDate);
        const dayEnd = endOfDay(currentDate);
        return { start: dayStart, end: dayEnd, days: [currentDate] };
      
      case 'week':
        const weekStart = startOfWeek(currentDate);
        const weekEnd = endOfWeek(currentDate);
        const weekDays = eachDayOfInterval({ start: weekStart, end: weekEnd });
        return { start: weekStart, end: weekEnd, days: weekDays };
      
      case 'month':
      default:
        const monthStart = startOfMonth(currentDate);
        const monthEnd = endOfMonth(currentDate);
        const calendarStart = startOfWeek(monthStart);
        const calendarEnd = endOfWeek(monthEnd);
        const calendarDays = eachDayOfInterval({ start: calendarStart, end: calendarEnd });
        return { start: calendarStart, end: calendarEnd, days: calendarDays };
    }
  };

  const { start: calendarStart, end: calendarEnd, days: calendarDays } = getDateRange();

  useEffect(() => {
    loadEvents();
  }, [currentDate, viewMode]);

  const loadEvents = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await apiClient.getEvents(
        true, // expanded
        format(calendarStart, 'yyyy-MM-dd HH:mm'),
        format(calendarEnd, 'yyyy-MM-dd HH:mm')
      );

      if (response.status === 'ok' && response.data) {
        setEvents(response.data);
      } else {
        setError(response.message || 'Failed to load events');
      }
    } catch (err) {
      setError('Failed to load events');
      console.error('Calendar load error:', err);
    } finally {
      setLoading(false);
    }
  };

  const getEventsForDate = (date: Date) => {
    return events.filter(event => {
      const eventDate = new Date(event.time);
      return isSameDay(eventDate, date);
    });
  };

  const navigate = (direction: 'prev' | 'next') => {
    let newDate: Date;
    
    switch (viewMode) {
      case 'day':
        newDate = direction === 'next' ? addDays(currentDate, 1) : subDays(currentDate, 1);
        break;
      case 'week':
        newDate = direction === 'next' ? addWeeks(currentDate, 1) : subWeeks(currentDate, 1);
        break;
      case 'month':
      default:
        newDate = direction === 'next' ? addMonths(currentDate, 1) : subMonths(currentDate, 1);
        break;
    }
    
    setCurrentDate(newDate);
  };

  const getHeaderTitle = () => {
    switch (viewMode) {
      case 'day':
        return format(currentDate, 'EEEE, MMMM d, yyyy');
      case 'week':
        const weekStart = startOfWeek(currentDate);
        const weekEnd = endOfWeek(currentDate);
        return `${format(weekStart, 'MMM d')} - ${format(weekEnd, 'MMM d, yyyy')}`;
      case 'month':
      default:
        return format(currentDate, 'MMMM yyyy');
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-lg p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center space-x-4">
          <h2 className="text-2xl font-bold text-gray-900">
            {getHeaderTitle()}
          </h2>
          <div className="flex items-center space-x-1">
            <button
              onClick={() => navigate('prev')}
              className="p-2 hover:bg-gray-100 rounded-md transition-colors"
            >
              <ChevronLeft size={20} />
            </button>
            <button
              onClick={() => navigate('next')}
              className="p-2 hover:bg-gray-100 rounded-md transition-colors"
            >
              <ChevronRight size={20} />
            </button>
          </div>
        </div>

        <div className="flex items-center space-x-4">
          {/* View Mode Toggle */}
          <div className="flex items-center bg-gray-100 rounded-lg p-1">
            <button
              onClick={() => setViewMode('day')}
              className={`flex items-center space-x-1 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                viewMode === 'day' 
                  ? 'bg-white text-gray-900 shadow-sm' 
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              <Square size={16} />
              <span>Day</span>
            </button>
            <button
              onClick={() => setViewMode('week')}
              className={`flex items-center space-x-1 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                viewMode === 'week' 
                  ? 'bg-white text-gray-900 shadow-sm' 
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              <Columns size={16} />
              <span>Week</span>
            </button>
            <button
              onClick={() => setViewMode('month')}
              className={`flex items-center space-x-1 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                viewMode === 'month' 
                  ? 'bg-white text-gray-900 shadow-sm' 
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              <Grid3X3 size={16} />
              <span>Month</span>
            </button>
          </div>
        
          <button
            onClick={onCreateEvent}
            className="flex items-center space-x-2 bg-primary-600 text-white px-4 py-2 rounded-md hover:bg-primary-700 transition-colors"
          >
            <Plus size={16} />
            <span>New Event</span>
          </button>
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="mb-4 p-3 bg-red-100 border border-red-400 text-red-700 rounded">
          {error}
        </div>
      )}

      {/* Calendar Content */}
      {viewMode === 'month' && (
        <>
          {/* Days of week header */}
          <div className="grid grid-cols-7 gap-1 mb-2">
            {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(day => (
              <div key={day} className="p-3 text-center text-sm font-medium text-gray-500">
                {day}
              </div>
            ))}
          </div>

          {/* Month grid */}
          <div className="grid grid-cols-7 gap-1">
            {calendarDays.map(date => {
              const dayEvents = getEventsForDate(date);
              const isCurrentMonth = isSameMonth(date, currentDate);
              const isCurrentDay = isToday(date);

              return (
                <div
                  key={date.toISOString()}
                  className={`
                    min-h-[120px] border border-gray-200 p-1 cursor-pointer hover:bg-gray-50 transition-colors
                    ${!isCurrentMonth ? 'bg-gray-50 text-gray-400' : 'bg-white'}
                    ${isCurrentDay ? 'bg-primary-50 border-primary-200' : ''}
                  `}
                  onClick={() => onDateClick?.(date)}
                >
                  <div className={`
                    text-sm font-medium mb-1 
                    ${isCurrentDay ? 'text-primary-600' : isCurrentMonth ? 'text-gray-900' : 'text-gray-400'}
                  `}>
                    {format(date, 'd')}
                  </div>
                  
                  <div className="space-y-1">
                    {dayEvents.slice(0, 3).map(event => (
                      <div
                        key={event.id}
                        onClick={(e) => {
                          e.stopPropagation();
                          onEventClick?.(event);
                        }}
                        className={`
                          text-xs p-1 rounded truncate cursor-pointer transition-colors
                          ${getCategoryColor(event.category)}
                        `}
                        title={`${event.title} - ${format(new Date(event.time), 'h:mm a')}`}
                      >
                        {format(new Date(event.time), 'h:mm a')} {event.title}
                      </div>
                    ))}
                    
                    {dayEvents.length > 3 && (
                      <div className="text-xs text-gray-500 px-1">
                        +{dayEvents.length - 3} more
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}

      {viewMode === 'week' && (
        <>
          {/* Days of week header */}
          <div className="grid grid-cols-7 gap-1 mb-2">
            {calendarDays.map(date => (
              <div key={date.toISOString()} className="p-3 text-center text-sm font-medium text-gray-500">
                <div>{format(date, 'EEE')}</div>
                <div className={`text-lg ${isToday(date) ? 'text-primary-600 font-bold' : 'text-gray-900'}`}>
                  {format(date, 'd')}
                </div>
              </div>
            ))}
          </div>

          {/* Week grid */}
          <div className="grid grid-cols-7 gap-1">
            {calendarDays.map(date => {
              const dayEvents = getEventsForDate(date);
              const isCurrentDay = isToday(date);

              return (
                <div
                  key={date.toISOString()}
                  className={`
                    min-h-[400px] border border-gray-200 p-2 cursor-pointer hover:bg-gray-50 transition-colors
                    ${isCurrentDay ? 'bg-primary-50 border-primary-200' : 'bg-white'}
                  `}
                  onClick={() => onDateClick?.(date)}
                >
                  <div className="space-y-1">
                    {dayEvents.map(event => (
                      <div
                        key={event.id}
                        onClick={(e) => {
                          e.stopPropagation();
                          onEventClick?.(event);
                        }}
                        className={`
                          text-xs p-2 rounded cursor-pointer transition-colors
                          ${getCategoryColor(event.category)}
                        `}
                        title={`${event.title} - ${format(new Date(event.time), 'h:mm a')}`}
                      >
                        <div className="font-medium truncate">{event.title}</div>
                        <div className="text-xs opacity-75">{format(new Date(event.time), 'h:mm a')}</div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}

      {viewMode === 'day' && (
        <div className="space-y-4">
          {/* Day header */}
          <div className="text-center py-4 bg-gray-50 rounded-lg">
            <div className="text-2xl font-bold text-gray-900">{format(currentDate, 'd')}</div>
            <div className="text-sm text-gray-500">{format(currentDate, 'EEEE, MMMM yyyy')}</div>
          </div>

          {/* Day events */}
          <div className="space-y-2">
            {getEventsForDate(currentDate).length > 0 ? (
              getEventsForDate(currentDate)
                .sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime())
                .map(event => (
                  <div
                    key={event.id}
                    onClick={() => onEventClick?.(event)}
                    className={`
                      p-4 rounded-lg border cursor-pointer transition-colors
                      ${getCategoryColor(event.category)}
                    `}
                  >
                    <div className="flex justify-between items-start">
                      <div className="flex-1">
                        <h3 className="font-medium text-lg">{event.title}</h3>
                        {event.description && (
                          <p className="text-sm opacity-75 mt-1">{event.description}</p>
                        )}
                      </div>
                      <div className="text-right text-sm">
                        <div className="font-medium">{format(new Date(event.time), 'h:mm a')}</div>
                        <div className="text-xs opacity-75">{event.duration} min</div>
                      </div>
                    </div>
                  </div>
                ))
            ) : (
              <div className="text-center py-8 text-gray-500">
                No events for this day
              </div>
            )}
          </div>
        </div>
      )}

      {/* Loading indicator */}
      {loading && (
        <div className="absolute inset-0 bg-white bg-opacity-75 flex items-center justify-center">
          <div className="text-gray-500">Loading events...</div>
        </div>
      )}
    </div>
  );
};

const getCategoryColor = (category: string): string => {
  const colors: Record<string, string> = {
    work: 'bg-blue-100 text-blue-800 hover:bg-blue-200',
    personal: 'bg-green-100 text-green-800 hover:bg-green-200',
    task: 'bg-purple-100 text-purple-800 hover:bg-purple-200',
    meeting: 'bg-orange-100 text-orange-800 hover:bg-orange-200',
    default: 'bg-gray-100 text-gray-800 hover:bg-gray-200',
  };
  return colors[category] || colors.default;
};

export default Calendar;