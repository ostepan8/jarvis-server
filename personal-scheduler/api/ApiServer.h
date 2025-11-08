#pragma once

#include "httplib.h"
#include "routing/Router.h"
#include "interfaces/IPerformanceMonitor.h"
#include "interfaces/IEventService.h"
#include "../utils/ResponseCache.h"
#include "../security/Auth.h"
#include "../security/RateLimiter.h"
#include <memory>
#include <string>

// Single Responsibility: Only HTTP server orchestration
// Dependency Inversion: Depends on abstractions, not concretions
// Open/Closed: Can add new handlers without modifying this class
class ApiServer {
private:
    // Core HTTP server functionality
    httplib::Server server_;
    std::unique_ptr<Router> router_;
    int port_;
    std::string host_;
    std::string cors_origin_;
    
    // Injected dependencies (following DIP)
    std::unique_ptr<IPerformanceMonitor> performance_monitor_;
    std::unique_ptr<ResponseCache> cache_;
    
    // Optional security components
    Auth* auth_;
    RateLimiter* limiter_;
    
    void setupCors();
    void setupRoutes(IEventService& event_service);
    
public:
    // Constructor with dependency injection
    ApiServer(IEventService& event_service,
                  int port = 8080,
                  const std::string& host = "127.0.0.1",
                  Auth* auth = nullptr,
                  RateLimiter* limiter = nullptr,
                  const std::string& cors_origin = "http://localhost:3000");
    
    ~ApiServer() = default;
    
    // Simple interface
    void start();
    void stop();
    
    // Access to performance data
    IPerformanceMonitor& getPerformanceMonitor() const { 
        return *performance_monitor_; 
    }
    
    size_t getRouteCount() const { 
        return router_->getRouteCount(); 
    }
};