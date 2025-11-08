#pragma once

#include "../interfaces/IRequestHandler.h"
#include "../interfaces/IPerformanceMonitor.h"
#include <sstream>

// Single Responsibility: Only handles stats requests
// Interface Segregation: Only implements what it needs
class StatsHandler : public IRequestHandler {
private:
    IPerformanceMonitor& performance_monitor_;
    std::string cors_origin_;
    
public:
    StatsHandler(IPerformanceMonitor& performance_monitor,
                const std::string& cors_origin = "http://localhost:3000")
        : performance_monitor_(performance_monitor), cors_origin_(cors_origin) {}
    
    void handle(const httplib::Request& req, httplib::Response& res) override {
        performance_monitor_.recordRequest();
        
        auto metrics = performance_monitor_.getMetrics();
        
        std::ostringstream response;
        response << R"({"status":"ok","data":{)";
        response << R"("total_requests":)" << metrics.total_requests << ",";
        response << R"("cached_responses":)" << metrics.cached_responses << ",";
        response << R"("async_requests":)" << metrics.async_requests << ",";
        response << R"("cache_hit_rate":)" << metrics.cache_hit_rate << ",";
        response << R"("requests_per_second":)" << metrics.requests_per_second << ",";
        response << R"("uptime_seconds":)" << metrics.uptime_seconds;
        response << R"(}})";
        
        res.set_content(response.str(), "application/json");
        res.set_header("Access-Control-Allow-Origin", cors_origin_);
        res.set_header("X-Handler-Type", "stats-only");
    }
};