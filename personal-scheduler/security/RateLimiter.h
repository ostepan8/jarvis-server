#pragma once
#include <unordered_map>
#include <chrono>
#include <string>

// Very simple fixed-window rate limiter.
class RateLimiter {
public:
    RateLimiter(size_t maxRequests = 100, std::chrono::seconds window = std::chrono::seconds(60));
    bool allow(const std::string &id);
private:
    struct Entry {
        size_t count = 0;
        std::chrono::steady_clock::time_point reset;
    };
    size_t max_;
    std::chrono::seconds window_;
    std::unordered_map<std::string, Entry> map_;
};
