#pragma once

#include "../interfaces/IRequestHandler.h"
#include "../interfaces/IEventService.h"
#include "../interfaces/IPerformanceMonitor.h"
#include "../../utils/ResponseCache.h"
#include "../../utils/FastSerializer.h"
#include <memory>
#include <chrono>

// Single Responsibility: Only handles event-related HTTP requests
class EventsHandler : public IRequestHandler {
private:
    IEventService& event_service_;
    IPerformanceMonitor& performance_monitor_;
    ResponseCache& cache_;
    std::string cors_origin_;
    
    bool shouldUseCache(const httplib::Request& req) const;
    std::string generateCacheKey(const httplib::Request& req) const;
    void addPerformanceHeaders(httplib::Response& res, 
                              std::chrono::microseconds processing_time) const;
    
public:
    EventsHandler(IEventService& event_service, 
                 IPerformanceMonitor& performance_monitor,
                 ResponseCache& cache,
                 const std::string& cors_origin = "http://localhost:3000");
                 
    void handle(const httplib::Request& req, httplib::Response& res) override;
};