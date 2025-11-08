#pragma once
#include <map>
#include <mutex>
#include <chrono>
#include <string>
#include <memory>
#include <set>
#include <unordered_map>
#include "Event.h"
#include "ReadOnlyModel.h"
#include "../database/IScheduleDatabase.h"
#include "../calendar/CalendarApi.h"
#include <vector>

// Structure to hold event statistics
struct EventStats
{
  int totalEvents;
  int totalMinutes;
  std::map<std::string, int> eventsByCategory;
  std::vector<std::pair<std::chrono::system_clock::time_point, int>> busiestDays;
  std::vector<std::pair<int, int>> busiestHours; // hour -> count
};

// Structure for conflict checking
struct TimeSlot
{
  std::chrono::system_clock::time_point start;
  std::chrono::system_clock::time_point end;
  std::chrono::minutes duration;
};

/*
  Model extends ReadOnlyModel by adding mutators (addEvent, removeEvent).
  Internally it keeps events in a time-ordered container. Access is protected
  by a mutex so multiple API threads can modify the schedule concurrently.
*/
class Model : public ReadOnlyModel
{
private:
  std::multimap<std::chrono::system_clock::time_point, std::unique_ptr<Event>> events;
  IScheduleDatabase *db_;
  mutable std::mutex mutex_;
  std::chrono::system_clock::time_point preloadEnd_;
  std::vector<std::shared_ptr<CalendarApi>> apis_;

  // New: Categories tracking
  std::set<std::string> categories_;

  // New: Soft delete support
  std::multimap<std::chrono::system_clock::time_point, std::unique_ptr<Event>> deletedEvents;

  // Check if an event ID already exists in the current list
  bool eventExists(const std::string &id) const;

public:
  // Construct with an initial list of events and optional database.
  explicit Model(IScheduleDatabase *db = nullptr,
                 int preloadDaysAhead = -1);

  // ReadOnlyModel overrides (note the const):
  std::vector<Event>
  getEvents(int maxOccurrences,
            std::chrono::system_clock::time_point endDate) const override;

  Event getNextEvent() const override;

  // Return the next n upcoming event occurrences expanding recurring events.
  std::vector<Event> getNextNEvents(int n) const;

  // Additional query methods
  std::vector<Event> getEventsOnDay(std::chrono::system_clock::time_point day) const;
  std::vector<Event> getEventsInWeek(std::chrono::system_clock::time_point day) const;
  std::vector<Event> getEventsInMonth(std::chrono::system_clock::time_point day) const;

  // ====== New Query Methods ======

  // Search events by title or description
  std::vector<Event> searchEvents(const std::string &query,
                                  int maxResults = -1) const;

  // Get events within a date range
  std::vector<Event> getEventsInRange(
      std::chrono::system_clock::time_point start,
      std::chrono::system_clock::time_point end) const;

  // Get events within a range, expanding recurring series into occurrences
  std::vector<Event> getEventsInRangeExpanded(
      std::chrono::system_clock::time_point start,
      std::chrono::system_clock::time_point end,
      int maxOccurrencesPerSeries = 10000) const;

  // Get events by duration range (in minutes)
  std::vector<Event> getEventsByDuration(int minMinutes, int maxMinutes) const;

  // Get events by category
  std::vector<Event> getEventsByCategory(const std::string &category) const;

  // Get all categories
  std::set<std::string> getCategories() const;

  // Check for conflicts at a given time
  std::vector<Event> getConflicts(
      std::chrono::system_clock::time_point time,
      std::chrono::minutes duration) const;

  // Find free time slots
  std::vector<TimeSlot> findFreeSlots(
      std::chrono::system_clock::time_point date,
      int startHour = 9,
      int endHour = 17,
      int minDurationMinutes = 30) const;

  // Get next available slot
  TimeSlot findNextAvailableSlot(
      std::chrono::minutes duration,
      std::chrono::system_clock::time_point after = std::chrono::system_clock::now(),
      int startHour = 9,
      int endHour = 17) const;

  // Get event statistics
  EventStats getEventStats(
      std::chrono::system_clock::time_point start,
      std::chrono::system_clock::time_point end) const;

  // Get deleted events (soft delete)
  std::vector<Event> getDeletedEvents() const;

  // Get event by ID
  std::unique_ptr<Event> getEventById(const std::string &id) const;

  // ====== Mutation methods ======

  // Add a new event. Returns true on success.
  bool addEvent(const Event &e);

  // Update an existing event
  bool updateEvent(const std::string &id, const Event &updatedEvent);

  // Partial update of an event
  bool updateEventFields(const std::string &id,
                         const std::unordered_map<std::string, std::string> &fields);

  // Remove by full Event object (matches by ID internally). Returns true if removed.
  bool removeEvent(const Event &e);

  // Remove by ID. Returns true if at least one Event with that ID was erased.
  bool removeEvent(const std::string &id, bool softDelete = false);

  // Restore a soft-deleted event
  bool restoreEvent(const std::string &id);

  // Remove all events from the model
  void removeAllEvents();

  // Remove events occurring on the given day. Returns number removed.
  int removeEventsOnDay(std::chrono::system_clock::time_point day);

  // Remove events in the week that contains the given day. Returns number removed.
  int removeEventsInWeek(std::chrono::system_clock::time_point day);

  // Remove all events strictly before the specified time. Returns number removed.
  int removeEventsBefore(std::chrono::system_clock::time_point time);

  // ====== Bulk Operations ======

  // Add multiple events at once
  std::vector<bool> addEvents(const std::vector<Event> &events);

  // Remove multiple events by ID
  int removeEvents(const std::vector<std::string> &ids);

  // Update multiple events
  std::vector<bool> updateEvents(
      const std::vector<std::pair<std::string, Event>> &updates);

  // Generate a unique ID not currently in use
  std::string generateUniqueId() const;

  // Register an external calendar API to mirror changes
  void addCalendarApi(std::shared_ptr<CalendarApi> api);

  // Validate if an event can be scheduled (no conflicts)
  bool validateEventTime(const Event &e) const;
};
