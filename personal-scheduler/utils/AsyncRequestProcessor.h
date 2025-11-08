#pragma once

#include "ThreadPool.h"
#include "../model/Model.h"
#include "FastSerializer.h"
#include <httplib.h>
#include <functional>
#include <chrono>
#include <atomic>

struct RequestTask {
    std::string method;
    std::string path;
    std::string body;
    std::map<std::string, std::string> params;
    std::function<void(int status, const std::string& response, const std::map<std::string, std::string>& headers)> callback;
    std::chrono::high_resolution_clock::time_point start_time;
};

class AsyncRequestProcessor {
private:
    ThreadPool worker_pool_;
    Model& model_;
    
    // Performance metrics
    std::atomic<uint64_t> processed_requests_{0};
    std::atomic<uint64_t> total_processing_time_us_{0};
    std::atomic<uint64_t> queue_wait_time_us_{0};

public:
    AsyncRequestProcessor(Model& model, size_t thread_count = std::thread::hardware_concurrency()) 
        : worker_pool_(thread_count), model_(model) {}
    
    // Asynchronously process a request
    void processAsync(RequestTask task) {
        auto enqueue_time = std::chrono::high_resolution_clock::now();
        
        worker_pool_.enqueue([this, task = std::move(task), enqueue_time]() mutable {
            auto processing_start = std::chrono::high_resolution_clock::now();
            
            // Track queue wait time
            auto wait_time = std::chrono::duration_cast<std::chrono::microseconds>(
                processing_start - enqueue_time).count();
            queue_wait_time_us_ += wait_time;
            
            // Process the request
            processRequest(std::move(task));
            
            // Track total processing time
            auto processing_end = std::chrono::high_resolution_clock::now();
            auto total_time = std::chrono::duration_cast<std::chrono::microseconds>(
                processing_end - task.start_time).count();
            total_processing_time_us_ += total_time;
            processed_requests_++;
        });
    }
    
    // Synchronous processing for comparison
    void processSync(RequestTask task) {
        processRequest(std::move(task));
    }
    
    // Get performance statistics
    struct Stats {
        uint64_t processed_requests;
        double avg_processing_time_ms;
        double avg_queue_wait_time_ms;
        size_t queue_size;
        size_t thread_count;
    };
    
    Stats getStats() const {
        uint64_t requests = processed_requests_.load();
        uint64_t total_time = total_processing_time_us_.load();
        uint64_t wait_time = queue_wait_time_us_.load();
        
        return Stats{
            requests,
            requests > 0 ? static_cast<double>(total_time) / requests / 1000.0 : 0.0,
            requests > 0 ? static_cast<double>(wait_time) / requests / 1000.0 : 0.0,
            worker_pool_.queueSize(),
            worker_pool_.size()
        };
    }
    
    void stop() {
        worker_pool_.stop();
    }

private:
    void processRequest(RequestTask task) {
        try {
            std::string response;
            std::map<std::string, std::string> headers;
            int status = 200;
            
            // Route the request
            if (task.method == "GET") {
                handleGetRequest(task, response, headers, status);
            } else if (task.method == "POST") {
                handlePostRequest(task, response, headers, status);
            } else if (task.method == "PUT") {
                handlePutRequest(task, response, headers, status);
            } else if (task.method == "DELETE") {
                handleDeleteRequest(task, response, headers, status);
            } else {
                status = 405; // Method Not Allowed
                response = FastSerializer::errorResponse("Method not allowed");
            }
            
            // Add performance headers
            auto processing_time = std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::high_resolution_clock::now() - task.start_time).count();
            headers["X-Processing-Time"] = std::to_string(processing_time) + "μs";
            headers["X-Processed-By"] = "AsyncRequestProcessor";
            
            // Call the callback with result
            task.callback(status, response, headers);
            
        } catch (const std::exception& e) {
            task.callback(500, FastSerializer::errorResponse("Internal server error"), {});
        }
    }
    
    void handleGetRequest(const RequestTask& task, std::string& response, 
                         std::map<std::string, std::string>& headers, int& status) {
        if (task.path == "/events" || (task.path.length() >= 8 && task.path.substr(0, 8) == "/events/")) {
            handleEventGetRequest(task, response, headers, status);
        } else if (task.path == "/availability" || (task.path.length() >= 14 && task.path.substr(0, 14) == "/availability/")) {
            handleAvailabilityRequest(task, response, headers, status);
        } else if (task.path == "/stats") {
            handleStatsRequest(task, response, headers, status);
        } else {
            status = 404;
            response = FastSerializer::errorResponse("Not found");
        }
    }
    
    void handlePostRequest(const RequestTask& task, std::string& response, 
                          std::map<std::string, std::string>& headers, int& status) {
        if (task.path == "/events") {
            handleEventCreateRequest(task, response, headers, status);
        } else {
            status = 404;
            response = FastSerializer::errorResponse("Not found");
        }
    }
    
    void handlePutRequest(const RequestTask& task, std::string& response, 
                         std::map<std::string, std::string>& headers, int& status) {
        if (task.path.length() >= 8 && task.path.substr(0, 8) == "/events/") {
            handleEventUpdateRequest(task, response, headers, status);
        } else {
            status = 404;
            response = FastSerializer::errorResponse("Not found");
        }
    }
    
    void handleDeleteRequest(const RequestTask& task, std::string& response, 
                           std::map<std::string, std::string>& headers, int& status) {
        if (task.path.length() >= 8 && task.path.substr(0, 8) == "/events/") {
            handleEventDeleteRequest(task, response, headers, status);
        } else {
            status = 404;
            response = FastSerializer::errorResponse("Not found");
        }
    }
    
    void handleEventGetRequest(const RequestTask& task, std::string& response, 
                              std::map<std::string, std::string>& headers, int& status) {
        if (task.path == "/events" || task.path == "/events/all") {
            // Get all events (limited for performance)
            auto events = model_.getNextNEvents(1000);
            response = FastSerializer::serializeEvents(events);
        } else if (task.path.length() >= 13 && task.path.substr(0, 13) == "/events/next/") {
            // Extract count from path
            size_t count = 10; // default
            try {
                std::string count_str = task.path.substr(13); // "/events/next/"
                count = std::stoul(count_str);
                count = std::min(count, size_t{1000}); // Cap at 1000
            } catch (...) {
                count = 10;
            }
            auto events = model_.getNextNEvents(count);
            response = FastSerializer::serializeEvents(events);
        } else {
            status = 404;
            response = FastSerializer::errorResponse("Event endpoint not found");
        }
    }
    
    void handleAvailabilityRequest(const RequestTask& task, std::string& response, 
                                  std::map<std::string, std::string>& headers, int& status) {
        // Simplified availability check
        // auto now = std::chrono::system_clock::now();
        // auto end_time = now + std::chrono::hours(24);
        
        // For now, return mock availability data
        response = FastSerializer::successResponse(R"([{"start":"2024-01-01 09:00","end":"2024-01-01 10:00","duration":60}])");
    }
    
    void handleStatsRequest(const RequestTask& task, std::string& response, 
                           std::map<std::string, std::string>& headers, int& status) {
        auto stats = getStats();
        
        std::ostringstream ss;
        ss << R"({"async_processor":{"processed_requests":)" << stats.processed_requests
           << R"(,"avg_processing_time_ms":)" << stats.avg_processing_time_ms
           << R"(,"avg_queue_wait_time_ms":)" << stats.avg_queue_wait_time_ms
           << R"(,"queue_size":)" << stats.queue_size
           << R"(,"thread_count":)" << stats.thread_count
           << "}}";
        
        response = ss.str();
    }
    
    void handleEventCreateRequest(const RequestTask& task, std::string& response, 
                                 std::map<std::string, std::string>& headers, int& status) {
        // Simple event creation - would need JSON parsing in real implementation
        status = 501; // Not Implemented for now
        response = FastSerializer::errorResponse("Event creation not implemented in async processor");
    }
    
    void handleEventUpdateRequest(const RequestTask& task, std::string& response, 
                                 std::map<std::string, std::string>& headers, int& status) {
        status = 501; // Not Implemented for now
        response = FastSerializer::errorResponse("Event update not implemented in async processor");
    }
    
    void handleEventDeleteRequest(const RequestTask& task, std::string& response, 
                                 std::map<std::string, std::string>& headers, int& status) {
        status = 501; // Not Implemented for now
        response = FastSerializer::errorResponse("Event deletion not implemented in async processor");
    }
};