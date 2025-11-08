#pragma once

#include "../model/Event.h"

struct ProviderIds {
    std::string eventId; // calendar event id
    std::string taskId;  // task id
};

class CalendarApi
{
public:
    virtual ~CalendarApi() = default;

    // Add a new event to the calendar
    virtual ProviderIds addEvent(const Event &event) = 0;

    // Update an existing event and optionally return resulting provider IDs
    virtual ProviderIds updateEvent(const Event &oldEvent, const Event &newEvent) = 0;

    // Delete an event from the calendar
    virtual void deleteEvent(const Event &event) = 0;
};
