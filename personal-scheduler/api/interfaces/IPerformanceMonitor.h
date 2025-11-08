#pragma once

#include <cstdint>

// Single Responsibility: Only performance monitoring
class IPerformanceMonitor {
public:
    virtual ~IPerformanceMonitor() = default;
    
    struct Metrics {
        uint64_t total_requests;
        uint64_t cached_responses;
        uint64_t async_requests;
        double cache_hit_rate;
        double requests_per_second;
        double uptime_seconds;
    };
    
    virtual void recordRequest() = 0;
    virtual void recordCacheHit() = 0;
    virtual void recordAsyncRequest() = 0;
    virtual Metrics getMetrics() const = 0;
};