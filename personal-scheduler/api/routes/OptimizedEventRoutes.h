#pragma once

#include <httplib.h>
#include <nlohmann/json.hpp>
#include <atomic>
#include <chrono>
#include <sstream>
#include <iomanip>
#include "../../model/Model.h"
#include "../../utils/ResponseCache.h"
#include "../../utils/FastSerializer.h"
#include "../../utils/TimeUtils.h"

namespace OptimizedEventRoutes {

class HighPerformanceEventHandler {
private:
    Model& model_;
    ResponseCache cache_;
    
    // Performance counters
    std::atomic<size_t> cache_hits_{0};
    std::atomic<size_t> cache_misses_{0};
    
public:
    HighPerformanceEventHandler(Model& model) 
        : model_(model), cache_(std::chrono::seconds{30}) {}
    
    // Ultra-fast GET /events with caching
    void handleGetEvents(const httplib::Request& req, httplib::Response& res) {
        auto start = std::chrono::high_resolution_clock::now();
        
        // Generate cache key
        std::string cache_key = ResponseCache::generateKey("GET", "/events", req.target);
        
        // Try cache first
        if (auto cached = cache_.get(cache_key)) {
            res.set_content(*cached, "application/json");
            cache_hits_++;
            return;
        }
        
        cache_misses_++;
        
        // Fast path for common queries
        if (!req.has_param("expanded") && !req.has_param("start") && !req.has_param("end")) {
            // Default query - get next 100 events
            auto events = model_.getNextNEvents(100);
            std::string response = FastSerializer::serializeEvents(events);
            
            cache_.put(cache_key, response);
            res.set_content(response, "application/json");
            return;
        }
        
        // Complex query path
        handleComplexEventQuery(req, res, cache_key);
        
        // Add performance timing
        auto end = std::chrono::high_resolution_clock::now();
        auto duration = std::chrono::duration_cast<std::chrono::microseconds>(end - start);
        res.set_header("X-Response-Time", std::to_string(duration.count()) + "μs");
    }
    
    // Batch event creation
    void handleBatchCreateEvents(const httplib::Request& req, httplib::Response& res) {
        try {
            auto body = nlohmann::json::parse(req.body);
            
            if (body.is_array()) {
                // Batch processing
                std::vector<bool> results;
                results.reserve(body.size());
                
                for (const auto& event_json : body) {
                    Event event = parseEventFromJson(event_json);
                    results.push_back(model_.addEvent(event));
                }
                
                // Fast response generation
                std::ostringstream response;
                response << R"({"status":"ok","results":[)";
                for (size_t i = 0; i < results.size(); ++i) {
                    if (i > 0) response << ",";
                    response << (results[i] ? "true" : "false");
                }
                response << "]}";
                
                res.set_content(response.str(), "application/json");
                
                // Invalidate related caches
                invalidateEventCaches();
            } else {
                // Single event
                Event event = parseEventFromJson(body);
                bool success = model_.addEvent(event);
                
                if (success) {
                    res.set_content(FastSerializer::successResponse(
                        FastSerializer::serializeEvent(event)), "application/json");
                    invalidateEventCaches();
                } else {
                    res.set_content(FastSerializer::errorResponse("Failed to create event"), 
                                  "application/json");
                }
            }
        } catch (const std::exception& e) {
            res.status = 400;
            res.set_content(FastSerializer::errorResponse("Invalid JSON"), "application/json");
        }
    }
    
    // Streaming response for large datasets
    void handleStreamingEvents(const httplib::Request& req, httplib::Response& res) {
        res.set_chunked_content_provider("application/json",
            [this](size_t offset, httplib::DataSink& sink) {
                static constexpr size_t BATCH_SIZE = 1000;
                
                if (offset == 0) {
                    // Send header
                    sink.write(R"({"status":"ok","data":[)", 22);
                }
                
                // Get batch of events
                auto events = model_.getEvents(BATCH_SIZE, 
                    std::chrono::system_clock::now() + std::chrono::hours(24 * 365));
                
                if (events.empty()) {
                    sink.write("]}", 2);
                    sink.done();
                    return true;
                }
                
                // Stream events
                for (size_t i = 0; i < events.size(); ++i) {
                    if (offset > 0 || i > 0) {
                        sink.write(",", 1);
                    }
                    std::string event_json = FastSerializer::serializeEvent(events[i]);
                    sink.write(event_json.data(), event_json.size());
                }
                
                return true;
            }
        );
    }
    
    // Performance monitoring endpoint
    void handlePerformanceStats(const httplib::Request& req, httplib::Response& res) {
        auto cache_stats = cache_.getStats();
        double hit_rate = cache_hits_.load() + cache_misses_.load() > 0 
            ? static_cast<double>(cache_hits_.load()) / (cache_hits_.load() + cache_misses_.load())
            : 0.0;
        
        std::ostringstream stats;
        stats << R"({"cache":{"hits":)" << cache_hits_.load()
              << R"(,"misses":)" << cache_misses_.load()
              << R"(,"hit_rate":)" << hit_rate
              << R"(,"entries":)" << cache_stats.entries
              << "}}";
        
        res.set_content(stats.str(), "application/json");
    }

private:
    void handleComplexEventQuery(const httplib::Request& req, httplib::Response& res, 
                                const std::string& cache_key) {
        // Parse parameters efficiently
        bool expanded = req.has_param("expanded");
        auto start_param = req.get_param_value("start");
        auto end_param = req.get_param_value("end");
        
        std::vector<Event> events;
        
        if (!start_param.empty() && !end_param.empty()) {
            auto start_time = parseTimePoint(start_param);
            auto end_time = parseTimePoint(end_param);
            
            if (expanded) {
                events = model_.getEventsInRangeExpanded(start_time, end_time);
            } else {
                events = model_.getEventsInRange(start_time, end_time);
            }
        } else {
            events = model_.getEvents(1000, std::chrono::system_clock::now() + 
                                    std::chrono::hours(24 * 30));
        }
        
        std::string response = FastSerializer::serializeEvents(events);
        cache_.put(cache_key, response);
        res.set_content(response, "application/json");
    }
    
    Event parseEventFromJson(const nlohmann::json& json) {
        // Fast JSON parsing with minimal validation
        std::string id = json.value("id", model_.generateUniqueId());
        std::string title = json.at("title");
        std::string description = json.value("description", "");
        std::string time_str = json.at("time");
        int duration_sec = json.value("duration", 3600);
        std::string category = json.value("category", "");
        
        auto time = parseTimePoint(time_str);
        return Event(id, description, title, time, 
                    std::chrono::seconds(duration_sec), category);
    }
    
    std::chrono::system_clock::time_point parseTimePoint(const std::string& time_str) {
        // Fast time parsing - use existing TimeUtils
        return TimeUtils::parseTimePoint(time_str);
    }
    
    void invalidateEventCaches() {
        // Smart cache invalidation - only clear relevant entries
        cache_.cleanup(); // For now, just cleanup expired entries
    }
};

// Register optimized routes
void registerOptimizedRoutes(httplib::Server& server, Model& model) {
    static HighPerformanceEventHandler handler(model);
    
    // Standard routes with caching
    server.Get("/events", [&](const httplib::Request& req, httplib::Response& res) {
        handler.handleGetEvents(req, res);
    });
    
    // Batch operations
    server.Post("/events/batch", [&](const httplib::Request& req, httplib::Response& res) {
        handler.handleBatchCreateEvents(req, res);
    });
    
    // Streaming for large datasets
    server.Get("/events/stream", [&](const httplib::Request& req, httplib::Response& res) {
        handler.handleStreamingEvents(req, res);
    });
    
    // Performance monitoring
    server.Get("/events/stats", [&](const httplib::Request& req, httplib::Response& res) {
        handler.handlePerformanceStats(req, res);
    });
}

} // namespace OptimizedEventRoutes