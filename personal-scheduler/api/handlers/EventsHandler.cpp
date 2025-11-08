#include "EventsHandler.h"
#include <sstream>

EventsHandler::EventsHandler(IEventService& event_service, 
                           IPerformanceMonitor& performance_monitor,
                           ResponseCache& cache,
                           const std::string& cors_origin)
    : event_service_(event_service), 
      performance_monitor_(performance_monitor),
      cache_(cache),
      cors_origin_(cors_origin) {}

void EventsHandler::handle(const httplib::Request& req, httplib::Response& res) {
    auto start_time = std::chrono::high_resolution_clock::now();
    performance_monitor_.recordRequest();
    
    // Check cache first for GET requests
    if (shouldUseCache(req)) {
        std::string cache_key = generateCacheKey(req);
        auto cached_response = cache_.get(cache_key);
        if (cached_response) {
            performance_monitor_.recordCacheHit();
            res.set_content(*cached_response, "application/json");
            res.set_header("Access-Control-Allow-Origin", cors_origin_);
            res.set_header("X-Cache", "HIT");
            return;
        }
    }
    
    try {
        std::string response;
        
        if (req.method == "GET") {
            if (req.path.find("/events/next/") != std::string::npos) {
                // Extract count from URL
                size_t pos = req.path.find_last_of('/');
                if (pos != std::string::npos) {
                    size_t count = std::stoull(req.path.substr(pos + 1));
                    count = std::min(count, size_t{1000}); // Cap at 1000
                    
                    auto events = event_service_.getNextNEvents(count);
                    response = FastSerializer::serializeEvents(events);
                }
            } else {
                // Get all events with reasonable defaults
                auto now = std::chrono::system_clock::now();
                auto endDate = now + std::chrono::hours(24 * 365);
                auto events = event_service_.getEvents(1000, endDate);
                response = FastSerializer::serializeEvents(events);
            }
        } else if (req.method == "POST") {
            // Simplified event creation
            performance_monitor_.recordAsyncRequest();
            auto now = std::chrono::system_clock::now();
            Event event("new_event_" + std::to_string(std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()).count()),
                       "Created via API",
                       "New Event",
                       now + std::chrono::hours(1),
                       std::chrono::hours(1));
            
            event_service_.addEvent(event);
            cache_.clear(); // Invalidate cache
            
            response = R"({"status":"ok","message":"Event created"})";
        }
        
        // Cache the response if it's a GET request
        if (shouldUseCache(req)) {
            std::string cache_key = generateCacheKey(req);
            cache_.put(cache_key, response);
        }
        
        res.set_content(response, "application/json");
        res.set_header("Access-Control-Allow-Origin", cors_origin_);
        res.set_header("X-Cache", "MISS");
        
        auto processing_time = std::chrono::duration_cast<std::chrono::microseconds>(
            std::chrono::high_resolution_clock::now() - start_time);
        addPerformanceHeaders(res, processing_time);
        
    } catch (const std::exception& e) {
        res.status = 500;
        res.set_content(R"({"status":"error","message":"Internal server error"})", "application/json");
        res.set_header("Access-Control-Allow-Origin", cors_origin_);
    }
}

bool EventsHandler::shouldUseCache(const httplib::Request& req) const {
    return req.method == "GET";
}

std::string EventsHandler::generateCacheKey(const httplib::Request& req) const {
    return req.method + ":" + req.path;
}

void EventsHandler::addPerformanceHeaders(httplib::Response& res, 
                                        std::chrono::microseconds processing_time) const {
    res.set_header("X-Processing-Time", std::to_string(processing_time.count()) + "μs");
    res.set_header("X-Server-Type", "solid-principles");
}