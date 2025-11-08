import React, { useState, useEffect } from 'react';
import { X, Calendar, Clock, Tag, FileText, Repeat } from 'lucide-react';
import { format } from 'date-fns';
import { Event, RecurringEvent, CreateRecurringEventRequest } from '../types';
import { apiClient } from '../services/api';
import InteractiveRecurrenceSelector, { RecurrencePattern } from './InteractiveRecurrenceSelector';

interface EventModalProps {
  isOpen: boolean;
  onClose: () => void;
  event?: Event | null;
  selectedDate?: Date;
  onEventSaved: () => void;
}

const EventModal: React.FC<EventModalProps> = ({
  isOpen,
  onClose,
  event,
  selectedDate,
  onEventSaved,
}) => {
  const [formData, setFormData] = useState({
    title: '',
    description: '',
    time: '',
    duration: 60,
    category: 'personal',
  });
  const [isRecurring, setIsRecurring] = useState(false);
  const [recurrencePattern, setRecurrencePattern] = useState<RecurrencePattern>({
    type: 'weekly',
    interval: 1,
    days: [],
    max: -1,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isEditing = !!event;
  const isRecurringEvent = event && 'recurring' in event && event.recurring;

  useEffect(() => {
    if (isOpen) {
      if (event) {
        // Editing existing event
        const eventDate = new Date(event.time);
        setFormData({
          title: event.title,
          description: event.description,
          time: format(eventDate, "yyyy-MM-dd'T'HH:mm"),
          duration: event.duration,
          category: event.category || 'personal',
        });

        // Handle recurring event data
        if (isRecurringEvent) {
          const recurringEvent = event as RecurringEvent;
          setIsRecurring(true);
          setRecurrencePattern({
            type: recurringEvent.recurrencePattern.type,
            interval: recurringEvent.recurrencePattern.interval,
            days: recurringEvent.recurrencePattern.days || [],
            max: recurringEvent.recurrencePattern.max || -1,
            end: recurringEvent.recurrencePattern.end,
          });
        } else {
          setIsRecurring(false);
        }
      } else if (selectedDate) {
        // Creating new event for selected date
        const defaultTime = new Date(selectedDate);
        defaultTime.setHours(9, 0, 0, 0); // Default to 9 AM
        setFormData({
          title: '',
          description: '',
          time: format(defaultTime, "yyyy-MM-dd'T'HH:mm"),
          duration: 60,
          category: 'personal',
        });
        setIsRecurring(false);
        // Set default weekly pattern for the selected day
        setRecurrencePattern({
          type: 'weekly',
          interval: 1,
          days: [defaultTime.getDay()],
          max: -1,
        });
      }
      setError(null);
    }
  }, [isOpen, event, selectedDate, isRecurringEvent]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      if (isRecurring) {
        // Validate recurring pattern
        if (!recurrencePattern.type || !recurrencePattern.interval) {
          setError('Please complete the recurrence pattern setup');
          setLoading(false);
          return;
        }
        if (recurrencePattern.type === 'weekly' && (!recurrencePattern.days || recurrencePattern.days.length === 0)) {
          setError('Please select at least one day for weekly recurrence');
          setLoading(false);
          return;
        }

        // Handle recurring event
        const startDate = new Date(formData.time);
        const startFormatted = `${startDate.getFullYear()}-${String(startDate.getMonth() + 1).padStart(2, '0')}-${String(startDate.getDate()).padStart(2, '0')} ${String(startDate.getHours()).padStart(2, '0')}:${String(startDate.getMinutes()).padStart(2, '0')}`;
        
        const recurringEventData: CreateRecurringEventRequest = {
          title: formData.title,
          description: formData.description,
          start: startFormatted,
          duration: formData.duration * 60, // Convert minutes to seconds for backend
          category: formData.category,
          pattern: {
            type: recurrencePattern.type,
            interval: recurrencePattern.interval,
            days: recurrencePattern.days,
            max: recurrencePattern.max,
            end: recurrencePattern.end,
          },
        };

        console.log('Sending recurring event data:', JSON.stringify(recurringEventData, null, 2));

        const response = isEditing && event && isRecurringEvent
          ? await apiClient.updateRecurringEvent(event.id, recurringEventData)
          : await apiClient.createRecurringEvent(recurringEventData);

        console.log('API response:', response);
        if (response.status === 'ok') {
          onEventSaved();
          onClose();
        } else {
          setError(response.message || 'Failed to save recurring event');
        }
      } else {
        // Handle one-time event
        const eventData = {
          title: formData.title,
          description: formData.description,
          time: new Date(formData.time).toISOString(),
          duration: formData.duration,
          category: formData.category,
        };

        const response = isEditing && event && !isRecurringEvent
          ? await apiClient.updateEvent(event.id, eventData)
          : await apiClient.createEvent(eventData);

        if (response.status === 'ok') {
          onEventSaved();
          onClose();
        } else {
          setError(response.message || 'Failed to save event');
        }
      }
    } catch (err) {
      setError('Failed to save event');
      console.error('Save event error:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!event || !window.confirm('Are you sure you want to delete this event?')) {
      return;
    }

    setLoading(true);
    try {
      const response = isRecurringEvent
        ? await apiClient.deleteRecurringEvent(event.id)
        : await apiClient.deleteEvent(event.id);
      
      if (response.status === 'ok') {
        onEventSaved();
        onClose();
      } else {
        setError(response.message || 'Failed to delete event');
      }
    } catch (err) {
      setError('Failed to delete event');
      console.error('Delete event error:', err);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[95vh] overflow-hidden flex flex-col">
        <div className="flex-shrink-0 px-6 pt-4 pb-0">
          {/* Header */}
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-bold text-gray-900">
              {isEditing ? 'Edit Event' : 'New Event'}
            </h2>
            <button
              onClick={onClose}
              className="p-1 hover:bg-gray-100 rounded-md transition-colors"
            >
              <X size={20} />
            </button>
          </div>

          {/* Error Message */}
          {error && (
            <div className="mb-4 p-3 bg-red-100 border border-red-400 text-red-700 rounded">
              {error}
            </div>
          )}
        </div>

        {/* Scrollable Form Content */}
        <form onSubmit={handleSubmit} className="flex flex-col flex-1 min-h-0">
          <div className="flex-1 overflow-y-auto px-6 py-2 space-y-3">
          {/* Title */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              <FileText size={16} className="inline mr-1" />
              Title
            </label>
            <input
              type="text"
              required
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
              placeholder="Event title"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Description
            </label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
              placeholder="Event description (optional)"
              rows={3}
            />
          </div>

          {/* Date and Time */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              <Calendar size={16} className="inline mr-1" />
              Date & Time
            </label>
            <input
              type="datetime-local"
              required
              value={formData.time}
              onChange={(e) => setFormData({ ...formData, time: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            />
          </div>

          {/* Duration */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              <Clock size={16} className="inline mr-1" />
              Duration (minutes)
            </label>
            <input
              type="number"
              required
              min="1"
              value={formData.duration}
              onChange={(e) => setFormData({ ...formData, duration: parseInt(e.target.value) })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            />
          </div>

          {/* Category */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              <Tag size={16} className="inline mr-1" />
              Category
            </label>
            <select
              value={formData.category}
              onChange={(e) => setFormData({ ...formData, category: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            >
              <option value="personal">Personal</option>
              <option value="work">Work</option>
              <option value="meeting">Meeting</option>
              <option value="task">Task</option>
            </select>
          </div>

          {/* Recurring Toggle */}
          <div>
            <label className="flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={isRecurring}
                onChange={(e) => setIsRecurring(e.target.checked)}
                disabled={isEditing && isRecurringEvent !== isRecurring} // Prevent changing type when editing
                className="mr-2 h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
              />
              <Repeat size={16} className="inline mr-1" />
              <span className="text-sm font-medium text-gray-700">Make this a recurring event</span>
            </label>
            {isEditing && isRecurringEvent !== isRecurring && (
              <p className="text-xs text-gray-500 mt-1">
                Cannot change event type when editing. Create a new event to change from recurring to one-time or vice versa.
              </p>
            )}
          </div>

          {/* Recurrence Pattern */}
          {isRecurring && (
            <div className="border-t pt-4">
              <InteractiveRecurrenceSelector
                value={recurrencePattern}
                onChange={setRecurrencePattern}
                startDate={new Date(formData.time)}
              />
            </div>
          )}

          </div>

          {/* Fixed Footer with Buttons */}
          <div className="flex-shrink-0 px-6 py-4 border-t bg-gray-50">
            <div className="flex justify-between">
            <div>
              {isEditing && (
                <button
                  type="button"
                  onClick={handleDelete}
                  disabled={loading}
                  className="px-4 py-2 text-red-600 border border-red-600 rounded-md hover:bg-red-50 disabled:opacity-50 transition-colors"
                >
                  Delete
                </button>
              )}
            </div>
            
            <div className="flex space-x-2">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading}
                className="px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700 disabled:opacity-50 transition-colors"
              >
                {loading 
                  ? 'Saving...' 
                  : isEditing 
                    ? `Update ${isRecurring ? 'Recurring Event' : 'Event'}` 
                    : `Create ${isRecurring ? 'Recurring Event' : 'Event'}`
                }
              </button>
            </div>
          </div>
          </div>
        </form>
      </div>
    </div>
  );
};

export default EventModal;