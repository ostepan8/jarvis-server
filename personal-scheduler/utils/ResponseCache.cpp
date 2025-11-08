#include "ResponseCache.h"
#include <algorithm>

ResponseCache::ResponseCache(std::chrono::seconds ttl) : defaultTTL_(ttl) {
    // Start cleanup thread
    cleanupThread_ = std::thread([this]() {
        while (!shutdown_.load()) {
            std::this_thread::sleep_for(std::chrono::seconds(30));
            cleanup();
        }
    });
}

ResponseCache::~ResponseCache() {
    shutdown_.store(true);
    if (cleanupThread_.joinable()) {
        cleanupThread_.join();
    }
}

std::optional<std::string> ResponseCache::get(const std::string& key) const {
    std::shared_lock<std::shared_mutex> lock(mutex_);
    auto it = cache_.find(key);
    if (it != cache_.end() && it->second.expiry > std::chrono::system_clock::now()) {
        hits_.fetch_add(1);
        return it->second.response;
    }
    misses_.fetch_add(1);
    return std::nullopt;
}

void ResponseCache::put(const std::string& key, const std::string& response) {
    std::unique_lock<std::shared_mutex> lock(mutex_);
    cache_[key] = {
        response,
        std::chrono::system_clock::now() + defaultTTL_,
        generateETag(response)
    };
}

void ResponseCache::clear() {
    std::unique_lock<std::shared_mutex> lock(mutex_);
    cache_.clear();
}

std::string ResponseCache::generateKey(const std::string& method, const std::string& path, 
                                     const std::string& query) {
    std::string key = method + ":" + path;
    if (!query.empty()) {
        key += "?" + query;
    }
    return key;
}

void ResponseCache::cleanup() {
    std::unique_lock<std::shared_mutex> lock(mutex_);
    auto now = std::chrono::system_clock::now();
    size_t removed = 0;
    
    for (auto it = cache_.begin(); it != cache_.end();) {
        if (it->second.expiry <= now) {
            it = cache_.erase(it);
            ++removed;
        } else {
            ++it;
        }
    }
    
    // Optional: Log cleanup stats
    if (removed > 0) {
        // std::cout << "Cache cleanup: removed " << removed << " expired entries\n";
    }
}

ResponseCache::CacheStats ResponseCache::getStats() const {
    std::shared_lock<std::shared_mutex> lock(mutex_);
    auto hits = hits_.load();
    auto misses = misses_.load();
    auto total = hits + misses;
    
    return {
        cache_.size(),
        hits,
        misses,
        total > 0 ? static_cast<double>(hits) / total : 0.0
    };
}

std::string ResponseCache::generateETag(const std::string& content) const {
    // Simple hash-based ETag
    auto hash = std::hash<std::string>{}(content);
    return "\"" + std::to_string(hash) + "\"";
}

bool ResponseCache::isModified(const std::string& key, const std::string& ifNoneMatch) const {
    std::shared_lock<std::shared_mutex> lock(mutex_);
    auto it = cache_.find(key);
    if (it != cache_.end() && it->second.expiry > std::chrono::system_clock::now()) {
        return it->second.etag != ifNoneMatch;
    }
    return true; // Assume modified if not in cache
}