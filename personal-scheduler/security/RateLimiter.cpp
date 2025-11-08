#include "RateLimiter.h"

RateLimiter::RateLimiter(size_t maxRequests, std::chrono::seconds window)
    : max_(maxRequests), window_(window) {}

bool RateLimiter::allow(const std::string &id) {
    using namespace std::chrono;
    auto now = steady_clock::now();
    auto &e = map_[id];
    if (e.reset < now) { e.count = 0; e.reset = now + window_; }
    if (e.count >= max_) return false;
    ++e.count;
    return true;
}
