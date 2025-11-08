#pragma once

#include "../../model/Event.h"
#include <vector>
#include <string>

// Dependency Inversion: Abstract interface for event operations
class IEventService {
public:
    virtual ~IEventService() = default;
    
    virtual std::vector<Event> getEvents(int maxOccurrences, 
                                       std::chrono::system_clock::time_point endDate) const = 0;
    virtual std::vector<Event> getNextNEvents(int n) const = 0;
    virtual void addEvent(const Event& event) = 0;
    virtual void removeEvent(const std::string& id) = 0;
    virtual void updateEvent(const std::string& id, const Event& updatedEvent) = 0;
};