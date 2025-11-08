#pragma once

#include "../model/Event.h"
#include "../model/Model.h"  // For TimeSlot and EventStats
#include <string>
#include <vector>
#include <sstream>
#include <iomanip>
#include <chrono>
#include <map>

class FastSerializer {
public:
    // Ultra-fast event serialization (avoid nlohmann::json for hot paths)
    static std::string serializeEvent(const Event& event);
    
    // Batch serialize events for better performance
    static std::string serializeEvents(const std::vector<Event>& events);
    
    // Pre-computed response templates
    static std::string successResponse(const std::string& data);
    static std::string errorResponse(const std::string& message);
    
    // TimeSlot serialization
    static std::string serializeTimeSlot(const TimeSlot& slot);
    static std::string serializeTimeSlots(const std::vector<TimeSlot>& slots);
    
    // Batch operations
    static std::string batchResponse(const std::vector<bool>& results);
    
    // Statistics
    static std::string serializeStats(const EventStats& stats);
    
    // Streaming JSON for large datasets
    class JsonStream {
    private:
        std::ostringstream ss_;
        bool first_ = true;
        
    public:
        JsonStream();
        void addEvent(const Event& event);
        std::string finalize();
    };

private:
    static std::string escapeJson(const std::string& str);
    static std::string formatTime(std::chrono::system_clock::time_point tp);
};