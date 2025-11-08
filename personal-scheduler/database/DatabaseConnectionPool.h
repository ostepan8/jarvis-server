#pragma once

#include "SQLiteScheduleDatabase.h"
#include "IScheduleDatabase.h"
#include <memory>
#include <vector>
#include <mutex>
#include <condition_variable>
#include <queue>
#include <atomic>
#include <chrono>

// Forward declaration
class DatabaseConnectionPool;

class DatabaseConnection {
private:
    std::unique_ptr<SQLiteScheduleDatabase> db_;
    DatabaseConnectionPool* pool_;
    bool in_use_;
    
public:
    DatabaseConnection(std::unique_ptr<SQLiteScheduleDatabase> db, DatabaseConnectionPool* pool)
        : db_(std::move(db)), pool_(pool), in_use_(false) {}
    
    SQLiteScheduleDatabase* get() { return db_.get(); }
    SQLiteScheduleDatabase& operator*() { return *db_; }
    SQLiteScheduleDatabase* operator->() { return db_.get(); }
    
    bool isInUse() const { return in_use_; }
    void setInUse(bool in_use) { in_use_ = in_use; }
    
    // Auto-return connection to pool when destroyed
    ~DatabaseConnection();
};

class DatabaseConnectionPool {
private:
    std::vector<std::unique_ptr<DatabaseConnection>> connections_;
    std::queue<DatabaseConnection*> available_connections_;
    std::mutex pool_mutex_;
    std::condition_variable pool_condition_;
    
    size_t max_connections_;
    size_t min_connections_;
    std::string db_path_;
    
    // Performance metrics
    std::atomic<uint64_t> total_borrows_{0};
    std::atomic<uint64_t> total_wait_time_us_{0};
    std::atomic<uint64_t> active_connections_{0};
    
public:
    DatabaseConnectionPool(const std::string& db_path, 
                          size_t min_connections = 2,
                          size_t max_connections = 10) 
        : max_connections_(max_connections), min_connections_(min_connections), db_path_(db_path) {
        initializePool();
    }
    
    ~DatabaseConnectionPool() {
        shutdown();
    }
    
    // Get a connection from the pool (blocks if none available)
    std::shared_ptr<DatabaseConnection> borrowConnection(
        std::chrono::milliseconds timeout = std::chrono::milliseconds{5000}) {
        
        auto start_time = std::chrono::high_resolution_clock::now();
        std::unique_lock<std::mutex> lock(pool_mutex_);
        
        // Wait for available connection
        if (!pool_condition_.wait_for(lock, timeout, 
            [this]{ return !available_connections_.empty(); })) {
            
            // Timeout - try to create new connection if under limit
            if (connections_.size() < max_connections_) {
                auto new_conn = createConnection();
                if (new_conn) {
                    connections_.push_back(std::move(new_conn));
                    auto* raw_conn = connections_.back().get();
                    raw_conn->setInUse(true);
                    active_connections_++;
                    
                    // Track metrics
                    total_borrows_++;
                    auto wait_time = std::chrono::duration_cast<std::chrono::microseconds>(
                        std::chrono::high_resolution_clock::now() - start_time).count();
                    total_wait_time_us_ += wait_time;
                    
                    return std::shared_ptr<DatabaseConnection>(raw_conn, 
                        [this](DatabaseConnection* conn) { 
                            this->returnConnection(conn); 
                        });
                }
            }
            
            throw std::runtime_error("Database connection pool timeout");
        }
        
        // Get available connection
        auto* conn = available_connections_.front();
        available_connections_.pop();
        conn->setInUse(true);
        active_connections_++;
        
        // Track metrics
        total_borrows_++;
        auto wait_time = std::chrono::duration_cast<std::chrono::microseconds>(
            std::chrono::high_resolution_clock::now() - start_time).count();
        total_wait_time_us_ += wait_time;
        
        return std::shared_ptr<DatabaseConnection>(conn, 
            [this](DatabaseConnection* conn) { 
                this->returnConnection(conn); 
            });
    }
    
    // Return connection to pool
    void returnConnection(DatabaseConnection* conn) {
        std::unique_lock<std::mutex> lock(pool_mutex_);
        
        if (conn && conn->isInUse()) {
            conn->setInUse(false);
            available_connections_.push(conn);
            active_connections_--;
            pool_condition_.notify_one();
        }
    }
    
    // Get pool statistics
    struct PoolStats {
        size_t total_connections;
        size_t available_connections;
        size_t active_connections;
        size_t max_connections;
        uint64_t total_borrows;
        double avg_wait_time_ms;
    };
    
    PoolStats getStats() const {
        std::unique_lock<std::mutex> lock(const_cast<std::mutex&>(pool_mutex_));
        uint64_t borrows = total_borrows_.load();
        uint64_t wait_time = total_wait_time_us_.load();
        
        return PoolStats{
            connections_.size(),
            available_connections_.size(),
            active_connections_.load(),
            max_connections_,
            borrows,
            borrows > 0 ? static_cast<double>(wait_time) / borrows / 1000.0 : 0.0
        };
    }
    
    void shutdown() {
        std::unique_lock<std::mutex> lock(pool_mutex_);
        
        // Wait for all connections to be returned
        pool_condition_.wait(lock, [this]{ 
            return available_connections_.size() == connections_.size(); 
        });
        
        // Clear all connections
        while (!available_connections_.empty()) {
            available_connections_.pop();
        }
        connections_.clear();
    }

private:
    void initializePool() {
        std::unique_lock<std::mutex> lock(pool_mutex_);
        
        // Create minimum number of connections
        for (size_t i = 0; i < min_connections_; ++i) {
            auto conn = createConnection();
            if (conn) {
                available_connections_.push(conn.get());
                connections_.push_back(std::move(conn));
            }
        }
    }
    
    std::unique_ptr<DatabaseConnection> createConnection() {
        try {
            auto db = std::make_unique<SQLiteScheduleDatabase>(db_path_);
            return std::make_unique<DatabaseConnection>(std::move(db), this);
        } catch (const std::exception& e) {
            // Log error in production
            return nullptr;
        }
    }
};

// Implementation of DatabaseConnection destructor
inline DatabaseConnection::~DatabaseConnection() {
    if (pool_ && in_use_) {
        pool_->returnConnection(this);
    }
}