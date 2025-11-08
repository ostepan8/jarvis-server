#pragma once

#include "../api/interfaces/IEventService.h"
#include "../model/Model.h"

// Adapter pattern: Adapts Model to IEventService interface
// Single Responsibility: Only handles event business logic
class EventService : public IEventService {
private:
    Model& model_;
    
public:
    explicit EventService(Model& model) : model_(model) {}
    
    std::vector<Event> getEvents(int maxOccurrences, 
                               std::chrono::system_clock::time_point endDate) const override {
        return model_.getEvents(maxOccurrences, endDate);
    }
    
    std::vector<Event> getNextNEvents(int n) const override {
        return model_.getNextNEvents(n);
    }
    
    void addEvent(const Event& event) override {
        model_.addEvent(event);
    }
    
    void removeEvent(const std::string& id) override {
        model_.removeEvent(id);
    }
    
    void updateEvent(const std::string& id, const Event& updatedEvent) override {
        model_.updateEvent(id, updatedEvent);
    }
};