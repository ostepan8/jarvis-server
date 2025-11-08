import { useState } from 'react';
import Calendar from './components/Calendar';
import Dashboard from './components/Dashboard';
import EventModal from './components/EventModal';
import { Event } from './types';

function App() {
  const [selectedEvent, setSelectedEvent] = useState<Event | null>(null);
  const [selectedDate, setSelectedDate] = useState<Date | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [calendarKey, setCalendarKey] = useState(0); // Force calendar refresh

  const handleEventClick = (event: Event) => {
    setSelectedEvent(event);
    setSelectedDate(null);
    setIsModalOpen(true);
  };

  const handleDateClick = (date: Date) => {
    setSelectedDate(date);
    setSelectedEvent(null);
    setIsModalOpen(true);
  };

  const handleCreateEvent = () => {
    setSelectedEvent(null);
    setSelectedDate(new Date());
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setSelectedEvent(null);
    setSelectedDate(null);
  };

  const handleEventSaved = () => {
    // Refresh the calendar
    setCalendarKey(prev => prev + 1);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="container mx-auto px-4 py-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Personal Scheduler</h1>
          <p className="text-gray-600">Manage your events and stay organized</p>
        </div>

        <Dashboard
          onEventClick={handleEventClick}
        />

        <Calendar
          key={calendarKey}
          onEventClick={handleEventClick}
          onDateClick={handleDateClick}
          onCreateEvent={handleCreateEvent}
        />

        <EventModal
          isOpen={isModalOpen}
          onClose={handleCloseModal}
          event={selectedEvent}
          selectedDate={selectedDate || undefined}
          onEventSaved={handleEventSaved}
        />
      </div>
    </div>
  );
}

export default App;
