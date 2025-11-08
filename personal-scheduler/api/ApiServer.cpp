#include "ApiServer.h"
#include "performance/PerformanceMonitor.h"
#include "handlers/EventsHandler.h"
#include "handlers/StatsHandler.h"
#include <iostream>

ApiServer::ApiServer(IEventService& event_service,
                              int port,
                              const std::string& host,
                              Auth* auth,
                              RateLimiter* limiter,
                              const std::string& cors_origin)
    : port_(port), host_(host), cors_origin_(cors_origin), auth_(auth), limiter_(limiter) {
    
    // Initialize dependencies following SOLID principles
    performance_monitor_ = std::make_unique<PerformanceMonitor>();
    cache_ = std::make_unique<ResponseCache>();
    router_ = std::make_unique<Router>();
    
    setupCors();
    setupRoutes(event_service);
}

void ApiServer::setupCors() {
    // Single responsibility: Only handle CORS and security
    server_.set_pre_routing_handler([this](const httplib::Request& req, httplib::Response& res) -> httplib::Server::HandlerResponse {
        // Handle preflight OPTIONS requests
        if (req.method == "OPTIONS") {
            res.status = 200;
            res.set_header("Access-Control-Allow-Origin", cors_origin_);
            res.set_header("Access-Control-Allow-Headers", "Content-Type, Authorization");
            res.set_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS");
            res.set_header("Access-Control-Max-Age", "86400");
            return httplib::Server::HandlerResponse::Handled;
        }

        // Rate limiting
        if (limiter_ && !limiter_->allow(req.remote_addr)) {
            res.status = 429;
            res.set_header("Access-Control-Allow-Origin", cors_origin_);
            res.set_content(R"({"status":"error","message":"Too Many Requests"})", "application/json");
            return httplib::Server::HandlerResponse::Handled;
        }

        // Authentication
        if (auth_ && !auth_->authorize(req)) {
            res.status = 401;
            res.set_header("Access-Control-Allow-Origin", cors_origin_);
            res.set_content(R"({"status":"error","message":"Unauthorized"})", "application/json");
            return httplib::Server::HandlerResponse::Handled;
        }

        return httplib::Server::HandlerResponse::Unhandled;
    });
}

void ApiServer::setupRoutes(IEventService& event_service) {
    // Open/Closed Principle: Add new handlers without modifying this method
    
    // Create specialized handlers (Single Responsibility)
    auto events_handler = std::make_shared<EventsHandler>(
        event_service, *performance_monitor_, *cache_, cors_origin_);
    auto stats_handler = std::make_shared<StatsHandler>(
        *performance_monitor_, cors_origin_);
    
    // Register routes using the router (Open/Closed)
    router_->addRoute("GET", "/events", events_handler);
    router_->addRoute("GET", "/events/next/\\d+", events_handler);
    router_->addRoute("POST", "/events", events_handler);
    router_->addRoute("GET", "/stats", stats_handler);
    
    // Set up route handlers using httplib's route system
    server_.Get("/events", [this, events_handler](const httplib::Request& req, httplib::Response& res) {
        events_handler->handle(req, res);
    });
    
    server_.Get(R"(/events/next/(\d+))", [this, events_handler](const httplib::Request& req, httplib::Response& res) {
        events_handler->handle(req, res);
    });
    
    server_.Post("/events", [this, events_handler](const httplib::Request& req, httplib::Response& res) {
        events_handler->handle(req, res);
    });
    
    server_.Get("/stats", [this, stats_handler](const httplib::Request& req, httplib::Response& res) {
        stats_handler->handle(req, res);
    });
}

void ApiServer::start() {
    std::cout << "📊 Routes registered: " << router_->getRouteCount() << "\n";
    server_.listen(host_.c_str(), port_);
}

void ApiServer::stop() {
    server_.stop();
}