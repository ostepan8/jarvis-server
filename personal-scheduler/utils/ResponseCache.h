#pragma once

#include <unordered_map>
#include <string>
#include <chrono>
#include <mutex>
#include <shared_mutex>
#include <optional>
#include <atomic>
#include <thread>

struct CacheEntry {
    std::string response;
    std::chrono::system_clock::time_point expiry;
    std::string etag;
};

class ResponseCache {
private:
    std::unordered_map<std::string, CacheEntry> cache_;
    mutable std::shared_mutex mutex_;
    std::chrono::seconds defaultTTL_{30}; // 30 second cache
    
    // Statistics
    mutable std::atomic<size_t> hits_{0};
    mutable std::atomic<size_t> misses_{0};
    
    // Background cleanup
    std::thread cleanupThread_;
    std::atomic<bool> shutdown_{false};

public:
    ResponseCache(std::chrono::seconds ttl = std::chrono::seconds{30});
    ~ResponseCache();
    
    // Get cached response if valid
    std::optional<std::string> get(const std::string& key) const;
    
    // Store response with TTL
    void put(const std::string& key, const std::string& response);
    
    // Clear all cache entries
    void clear();
    
    // Generate cache key from request
    static std::string generateKey(const std::string& method, const std::string& path, 
                                 const std::string& query = "");
    
    // Clear expired entries
    void cleanup();
    
    // Check if content is modified (ETag support)
    bool isModified(const std::string& key, const std::string& ifNoneMatch) const;
    
    // Get cache statistics
    struct CacheStats {
        size_t entries;
        size_t hits;
        size_t misses;
        double hitRate;
    };
    
    CacheStats getStats() const;

private:
    std::string generateETag(const std::string& content) const;
};