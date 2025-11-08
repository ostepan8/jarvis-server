// RecurringEvent.cpp
#include "RecurringEvent.h"
#include <memory>

RecurringEvent::RecurringEvent(const std::string &id,
                               const std::string &desc,
                               const std::string &title,
                               std::chrono::system_clock::time_point time,
                               std::chrono::system_clock::duration duration,
                               std::shared_ptr<RecurrencePattern> recurrencePattern,
                               const std::string &category)
    : Event(id, desc, title, time, duration, category),
      recurrencePattern(std::move(recurrencePattern))
{
    setRecurring(true);
}

std::unique_ptr<Event> RecurringEvent::clone() const
{
    auto ptr = std::make_unique<RecurringEvent>(
        getId(),
        getDescription(),
        getTitle(),
        getTime(),
        getDuration(),
        recurrencePattern, // Share the recurrence pattern
        getCategory());
    ptr->setNotifierName(getNotifierName());
    ptr->setActionName(getActionName());
    ptr->setProviderEventId(getProviderEventId());
    ptr->setProviderTaskId(getProviderTaskId());
    return ptr;
}

bool RecurringEvent::isDueOn(std::chrono::system_clock::time_point date) const
{
    return recurrencePattern->isDueOn(date);
}

std::vector<std::chrono::system_clock::time_point>
RecurringEvent::getNextNOccurrences(std::chrono::system_clock::time_point after, int n) const
{
    return recurrencePattern->getNextNOccurrences(after, n);
}
