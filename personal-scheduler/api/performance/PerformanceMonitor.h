#pragma once

#include "../interfaces/IPerformanceMonitor.h"
#include <atomic>
#include <chrono>

// Single Responsibility: Only tracks performance metrics
class PerformanceMonitor : public IPerformanceMonitor {
private:
    std::atomic<uint64_t> total_requests_{0};
    std::atomic<uint64_t> cached_responses_{0};
    std::atomic<uint64_t> async_requests_{0};
    std::chrono::high_resolution_clock::time_point start_time_;
    
public:
    PerformanceMonitor() : start_time_(std::chrono::high_resolution_clock::now()) {}
    
    void recordRequest() override {
        total_requests_.fetch_add(1);
    }
    
    void recordCacheHit() override {
        cached_responses_.fetch_add(1);
    }
    
    void recordAsyncRequest() override {
        async_requests_.fetch_add(1);
    }
    
    Metrics getMetrics() const override {
        auto now = std::chrono::high_resolution_clock::now();
        auto uptime = std::chrono::duration_cast<std::chrono::seconds>(now - start_time_).count();
        
        uint64_t total = total_requests_.load();
        uint64_t cached = cached_responses_.load();
        
        return {
            .total_requests = total,
            .cached_responses = cached,
            .async_requests = async_requests_.load(),
            .cache_hit_rate = total > 0 ? (static_cast<double>(cached) / total * 100.0) : 0.0,
            .requests_per_second = uptime > 0 ? (static_cast<double>(total) / uptime) : 0.0,
            .uptime_seconds = static_cast<double>(uptime)
        };
    }
};