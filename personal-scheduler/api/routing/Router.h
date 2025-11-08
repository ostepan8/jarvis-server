#pragma once

#include "../interfaces/IRequestHandler.h"
#include "httplib.h"
#include <memory>
#include <unordered_map>
#include <string>
#include <regex>

// Open/Closed Principle: Open for extension (new routes), closed for modification
class Router {
public:
    struct Route {
        std::string method;
        std::regex pattern;
        std::shared_ptr<IRequestHandler> handler;
    };
    
private:
    std::vector<Route> routes_;
    
public:
    // Add new routes without modifying existing code
    void addRoute(const std::string& method, 
                 const std::string& pattern, 
                 std::shared_ptr<IRequestHandler> handler) {
        routes_.push_back({method, std::regex(pattern), handler});
    }
    
    // Template method pattern for route matching
    bool handleRequest(const httplib::Request& req, httplib::Response& res) {
        for (const auto& route : routes_) {
            if (route.method == req.method && 
                std::regex_match(req.path, route.pattern)) {
                route.handler->handle(req, res);
                return true;
            }
        }
        return false; // No matching route found
    }
    
    size_t getRouteCount() const { return routes_.size(); }
};