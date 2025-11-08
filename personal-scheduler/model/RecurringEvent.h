// RecurringEvent.h
#pragma once

#include "Event.h"
#include "recurrence/RecurrencePattern.h"
#include <memory>
#include <vector>
#include <chrono>
#include <string>

class RecurringEvent : public Event
{
private:
    std::shared_ptr<RecurrencePattern> recurrencePattern;

public:
    // Constructor with optional category
    RecurringEvent(const std::string &id,
                   const std::string &desc,
                   const std::string &title,
                   std::chrono::system_clock::time_point time,
                   std::chrono::system_clock::duration duration,
                   std::shared_ptr<RecurrencePattern> recurrencePattern,
                   const std::string &category = "");

    // Clone method that preserves recurrence pattern and category
    std::unique_ptr<Event> clone() const override;

    // Check if event is due on a specific date
    bool isDueOn(std::chrono::system_clock::time_point date) const;

    // Get next N occurrences after a given time
    std::vector<std::chrono::system_clock::time_point> getNextNOccurrences(
        std::chrono::system_clock::time_point after, int n) const;

    // Get the recurrence pattern
    std::shared_ptr<RecurrencePattern> getRecurrencePattern() const
    {
        return recurrencePattern;
    }

    // Set a new recurrence pattern
    void setRecurrencePattern(std::shared_ptr<RecurrencePattern> pattern)
    {
        recurrencePattern = std::move(pattern);
    }
};
