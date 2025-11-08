#include "FastSerializer.h"

std::string FastSerializer::serializeEvent(const Event& event) {
    std::ostringstream ss;
    ss << R"({"id":")" << event.getId() 
       << R"(","title":")" << escapeJson(event.getTitle())
       << R"(","description":")" << escapeJson(event.getDescription())
       << R"(","time":")" << formatTime(event.getTime())
       << R"(","duration":)" << std::chrono::duration_cast<std::chrono::seconds>(event.getDuration()).count()
       << R"(,"category":")" << escapeJson(event.getCategory())
       << R"(","recurring":)" << (event.isRecurring() ? "true" : "false")
       << "}";
    return ss.str();
}

std::string FastSerializer::serializeEvents(const std::vector<Event>& events) {
    if (events.empty()) {
        return R"({"status":"ok","data":[]})";
    }
    
    std::ostringstream ss;
    ss << R"({"status":"ok","data":[)";
    
    for (size_t i = 0; i < events.size(); ++i) {
        if (i > 0) ss << ",";
        ss << serializeEvent(events[i]);
    }
    
    ss << "]}";
    return ss.str();
}

std::string FastSerializer::successResponse(const std::string& data) {
    return R"({"status":"ok","data":)" + data + "}";
}

std::string FastSerializer::errorResponse(const std::string& message) {
    return R"({"status":"error","message":")" + escapeJson(message) + R"("})";
}

// TimeSlot serialization for availability endpoints
std::string FastSerializer::serializeTimeSlot(const TimeSlot& slot) {
    std::ostringstream ss;
    ss << R"({"start":")" << formatTime(slot.start)
       << R"(","end":")" << formatTime(slot.end)  
       << R"(","duration":)" << slot.duration.count()
       << "}";
    return ss.str();
}

std::string FastSerializer::serializeTimeSlots(const std::vector<TimeSlot>& slots) {
    if (slots.empty()) {
        return R"({"status":"ok","data":[]})";
    }
    
    std::ostringstream ss;
    ss << R"({"status":"ok","data":[)";
    
    for (size_t i = 0; i < slots.size(); ++i) {
        if (i > 0) ss << ",";
        ss << serializeTimeSlot(slots[i]);
    }
    
    ss << "]}";
    return ss.str();
}

// Batch response for multiple operations
std::string FastSerializer::batchResponse(const std::vector<bool>& results) {
    std::ostringstream ss;
    ss << R"({"status":"ok","results":[)";
    
    for (size_t i = 0; i < results.size(); ++i) {
        if (i > 0) ss << ",";
        ss << (results[i] ? "true" : "false");
    }
    
    ss << "]}";
    return ss.str();
}

// Statistics serialization
std::string FastSerializer::serializeStats(const EventStats& stats) {
    std::ostringstream ss;
    ss << R"({"total_events":)" << stats.totalEvents
       << R"(,"total_minutes":)" << stats.totalMinutes;
    
    // Categories
    ss << R"(,"events_by_category":{)";
    bool first = true;
    for (const auto& [category, count] : stats.eventsByCategory) {
        if (!first) ss << ",";
        ss << R"(")" << escapeJson(category) << R"(":)" << count;
        first = false;
    }
    ss << "}";
    
    // Busiest days
    ss << R"(,"busiest_days":[)";
    for (size_t i = 0; i < stats.busiestDays.size(); ++i) {
        if (i > 0) ss << ",";
        ss << R"({"date":")" << formatTime(stats.busiestDays[i].first)
           << R"(","event_count":)" << stats.busiestDays[i].second << "}";
    }
    ss << "]";
    
    // Busiest hours  
    ss << R"(,"busiest_hours":[)";
    for (size_t i = 0; i < stats.busiestHours.size(); ++i) {
        if (i > 0) ss << ",";
        ss << R"({"hour":)" << stats.busiestHours[i].first
           << R"(,"event_count":)" << stats.busiestHours[i].second << "}";
    }
    ss << "]}";
    
    return ss.str();
}

std::string FastSerializer::escapeJson(const std::string& str) {
    std::string result;
    result.reserve(str.length() + str.length() / 4); // Reserve extra space for escapes
    
    for (char c : str) {
        switch (c) {
            case '"': result += R"(\")"; break;
            case '\\': result += R"(\\)"; break;
            case '\n': result += R"(\n)"; break;
            case '\r': result += R"(\r)"; break;
            case '\t': result += R"(\t)"; break;
            case '\b': result += R"(\b)"; break;
            case '\f': result += R"(\f)"; break;
            default: 
                if (static_cast<unsigned char>(c) < 0x20) {
                    // Control characters
                    result += "\\u00";
                    result += "0123456789abcdef"[(c >> 4) & 0xF];
                    result += "0123456789abcdef"[c & 0xF];
                } else {
                    result += c;
                }
                break;
        }
    }
    return result;
}

std::string FastSerializer::formatTime(std::chrono::system_clock::time_point tp) {
    auto time_t = std::chrono::system_clock::to_time_t(tp);
    std::ostringstream ss;
    ss << std::put_time(std::localtime(&time_t), "%Y-%m-%d %H:%M");
    return ss.str();
}

// FastSerializer::JsonStream implementation
FastSerializer::JsonStream::JsonStream() {
    ss_ << R"({"status":"ok","data":[)";
}

void FastSerializer::JsonStream::addEvent(const Event& event) {
    if (!first_) ss_ << ",";
    ss_ << FastSerializer::serializeEvent(event);
    first_ = false;
}

std::string FastSerializer::JsonStream::finalize() {
    ss_ << "]}";
    return ss_.str();
}