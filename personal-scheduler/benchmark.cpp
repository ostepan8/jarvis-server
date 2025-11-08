#include "model/Model.h"
#include "database/SQLiteScheduleDatabase.h"
#include "api/UnifiedApiServer.h"
#include "utils/EnvLoader.h"
#include <iostream>
#include <chrono>
#include <thread>
#include <vector>
#include <future>
#include <curl/curl.h>
#include <sstream>
#include <random>
#include <iomanip>

using namespace std::chrono;

// Simple HTTP client response handler
struct HTTPResponse {
    std::string body;
    long status_code;
    double response_time_ms;
};

size_t WriteCallback(void* contents, size_t size, size_t nmemb, HTTPResponse* response) {
    size_t totalSize = size * nmemb;
    response->body.append((char*)contents, totalSize);
    return totalSize;
}

HTTPResponse httpGet(const std::string& url) {
    HTTPResponse response;
    CURL* curl = curl_easy_init();
    
    if (curl) {
        auto start = high_resolution_clock::now();
        
        curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallback);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
        curl_easy_setopt(curl, CURLOPT_TIMEOUT, 10L);
        
        CURLcode res = curl_easy_perform(curl);
        
        auto end = high_resolution_clock::now();
        response.response_time_ms = duration_cast<microseconds>(end - start).count() / 1000.0;
        
        if (res == CURLE_OK) {
            curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &response.status_code);
        } else {
            response.status_code = -1;
        }
        
        curl_easy_cleanup(curl);
    }
    
    return response;
}

class UnifiedBenchmark {
private:
    std::unique_ptr<SQLiteScheduleDatabase> db_;
    std::unique_ptr<Model> model_;
    std::unique_ptr<UnifiedApiServer> server_;
    std::thread server_thread_;
    std::atomic<bool> server_running_{false};
    
    const std::string BASE_URL = "http://127.0.0.1:8090";
    
public:
    UnifiedBenchmark() {
        // Initialize components
        db_ = std::make_unique<SQLiteScheduleDatabase>(":memory:");
        model_ = std::make_unique<Model>(db_.get());
        
        // Start server on a different port to avoid conflicts
        server_ = std::make_unique<UnifiedApiServer>(*model_, 8090, "127.0.0.1");
    }
    
    ~UnifiedBenchmark() {
        stopServer();
    }
    
    void startServer() {
        if (server_running_) return;
        
        server_running_ = true;
        server_thread_ = std::thread([this]() {
            server_->start();
        });
        
        // Wait for server to start
        std::this_thread::sleep_for(std::chrono::milliseconds(500));
        
        // Test if server is responsive
        auto response = httpGet(BASE_URL + "/stats");
        if (response.status_code != 200) {
            std::cout << "⚠️  Server may not be fully ready (got status " << response.status_code << ")\n";
        } else {
            std::cout << "✅ Server started successfully on port 8090\n";
        }
    }
    
    void stopServer() {
        if (!server_running_) return;
        
        server_running_ = false;
        server_->stop();
        
        if (server_thread_.joinable()) {
            server_thread_.join();
        }
        
        std::cout << "🔴 Server stopped\n";
    }
    
    // Model Performance Tests
    void runModelBenchmarks() {
        std::cout << "\n📊 MODEL BENCHMARKS\n";
        std::cout << "==================\n";
        
        // Test 1: Event Creation Speed
        {
            const int NUM_EVENTS = 1000;
            auto start = high_resolution_clock::now();
            
            for (int i = 0; i < NUM_EVENTS; i++) {
                auto now = system_clock::now();
                Event event("bench_" + std::to_string(i), 
                           "Benchmark event", 
                           "Test Event " + std::to_string(i),
                           now + hours(i), 
                           minutes(60));
                model_->addEvent(event);
            }
            
            auto end = high_resolution_clock::now();
            auto duration_ms = duration_cast<milliseconds>(end - start).count();
            
            std::cout << "Event Creation: " << NUM_EVENTS << " events in " 
                      << duration_ms << "ms (" 
                      << std::fixed << std::setprecision(2) 
                      << (NUM_EVENTS * 1000.0 / duration_ms) << " events/sec)\n";
        }
        
        // Test 2: Event Retrieval Speed
        {
            const int NUM_QUERIES = 100;
            auto start = high_resolution_clock::now();
            
            for (int i = 0; i < NUM_QUERIES; i++) {
                auto events = model_->getNextNEvents(50);
            }
            
            auto end = high_resolution_clock::now();
            auto duration_ms = duration_cast<milliseconds>(end - start).count();
            
            std::cout << "Event Retrieval: " << NUM_QUERIES << " queries in " 
                      << duration_ms << "ms (" 
                      << std::fixed << std::setprecision(2)
                      << (NUM_QUERIES * 1000.0 / duration_ms) << " queries/sec)\n";
        }
        
        // Clean up
        model_->removeAllEvents();
    }
    
    // API Performance Tests
    void runApiBenchmarks() {
        std::cout << "\n🌐 API BENCHMARKS\n";
        std::cout << "================\n";
        
        startServer();
        
        // Add some test events first
        for (int i = 0; i < 100; i++) {
            auto now = system_clock::now();
            Event event("api_test_" + std::to_string(i), 
                       "API test event", 
                       "API Test Event " + std::to_string(i),
                       now + hours(i), 
                       minutes(60));
            model_->addEvent(event);
        }
        
        // Test 1: Single Request Performance
        {
            auto response = httpGet(BASE_URL + "/events/next/10");
            std::cout << "Single Request: " << response.response_time_ms << "ms "
                      << "(Status: " << response.status_code << ")\n";
        }
        
        // Test 2: Concurrent Request Performance
        {
            const int NUM_CONCURRENT = 20;
            const int REQUESTS_PER_THREAD = 10;
            
            auto start = high_resolution_clock::now();
            
            std::vector<std::future<void>> futures;
            std::atomic<int> total_requests{0};
            std::atomic<long> total_response_time_us{0}; // Use microseconds as integer
            
            for (int i = 0; i < NUM_CONCURRENT; i++) {
                futures.push_back(std::async(std::launch::async, [&]() {
                    for (int j = 0; j < REQUESTS_PER_THREAD; j++) {
                        auto response = httpGet(BASE_URL + "/events/next/5");
                        if (response.status_code == 200) {
                            total_requests++;
                            total_response_time_us += static_cast<long>(response.response_time_ms * 1000);
                        }
                    }
                }));
            }
            
            // Wait for all threads
            for (auto& future : futures) {
                future.wait();
            }
            
            auto end = high_resolution_clock::now();
            auto total_duration_ms = duration_cast<milliseconds>(end - start).count();
            
            int successful_requests = total_requests.load();
            double avg_response_time = (total_response_time_us.load() / 1000.0) / successful_requests;
            double rps = (successful_requests * 1000.0) / total_duration_ms;
            
            std::cout << "Concurrent Load: " << successful_requests << " requests in " 
                      << total_duration_ms << "ms\n";
            std::cout << "  - RPS: " << std::fixed << std::setprecision(1) << rps << "\n";
            std::cout << "  - Avg Response Time: " << std::fixed << std::setprecision(2) 
                      << avg_response_time << "ms\n";
        }
        
        // Test 3: Cache Performance
        {
            std::cout << "\n🚀 Cache Performance Test:\n";
            
            // First request (cache miss)
            auto miss_response = httpGet(BASE_URL + "/events/next/20");
            
            // Second request (should be cache hit)
            auto hit_response = httpGet(BASE_URL + "/events/next/20");
            
            std::cout << "  - Cache Miss: " << std::fixed << std::setprecision(2) 
                      << miss_response.response_time_ms << "ms\n";
            std::cout << "  - Cache Hit: " << std::fixed << std::setprecision(2) 
                      << hit_response.response_time_ms << "ms\n";
            
            if (hit_response.response_time_ms < miss_response.response_time_ms) {
                double speedup = miss_response.response_time_ms / hit_response.response_time_ms;
                std::cout << "  - Cache Speedup: " << std::fixed << std::setprecision(1) 
                          << speedup << "x faster\n";
            }
        }
        
        // Test 4: Server Stats
        {
            auto stats_response = httpGet(BASE_URL + "/stats");
            if (stats_response.status_code == 200) {
                std::cout << "\n📈 Server Stats Response Time: " 
                          << std::fixed << std::setprecision(2) 
                          << stats_response.response_time_ms << "ms\n";
            }
        }
        
        stopServer();
    }
    
    // Full System Performance Test
    void runFullSystemBenchmark() {
        std::cout << "\n🏆 FULL SYSTEM BENCHMARK\n";
        std::cout << "========================\n";
        
        startServer();
        
        const int WARMUP_EVENTS = 50;
        const int TEST_EVENTS = 500;
        const int CONCURRENT_CLIENTS = 10;
        const int REQUESTS_PER_CLIENT = 25;
        
        // Add events for testing
        std::cout << "Adding " << TEST_EVENTS << " test events...\n";
        auto event_start = high_resolution_clock::now();
        
        for (int i = 0; i < TEST_EVENTS; i++) {
            auto now = system_clock::now();
            Event event("full_test_" + std::to_string(i), 
                       "Full system test event", 
                       "Full Test Event " + std::to_string(i),
                       now + hours(i % 168), // Spread over a week
                       minutes(30 + (i % 120))); // 30-150 minute events
            model_->addEvent(event);
        }
        
        auto event_end = high_resolution_clock::now();
        auto event_creation_ms = duration_cast<milliseconds>(event_end - event_start).count();
        
        std::cout << "Event creation: " << event_creation_ms << "ms ("
                  << std::fixed << std::setprecision(1)
                  << (TEST_EVENTS * 1000.0 / event_creation_ms) << " events/sec)\n";
        
        // Warmup requests
        std::cout << "Warming up server cache...\n";
        for (int i = 0; i < WARMUP_EVENTS; i++) {
            httpGet(BASE_URL + "/events/next/10");
        }
        
        // Full load test
        std::cout << "Running full load test (" << CONCURRENT_CLIENTS 
                  << " concurrent clients, " << REQUESTS_PER_CLIENT << " requests each)...\n";
        
        auto load_start = high_resolution_clock::now();
        
        std::vector<std::future<std::pair<int, double>>> futures;
        
        for (int i = 0; i < CONCURRENT_CLIENTS; i++) {
            futures.push_back(std::async(std::launch::async, [&]() -> std::pair<int, double> {
                int successful = 0;
                double total_time = 0.0;
                
                std::vector<std::string> endpoints = {
                    "/events/next/10",
                    "/events/next/25", 
                    "/events/next/5",
                    "/stats"
                };
                
                std::mt19937 rng(std::random_device{}());
                std::uniform_int_distribution<> dist(0, endpoints.size() - 1);
                
                for (int j = 0; j < REQUESTS_PER_CLIENT; j++) {
                    std::string endpoint = endpoints[dist(rng)];
                    auto response = httpGet(BASE_URL + endpoint);
                    
                    if (response.status_code == 200) {
                        successful++;
                        total_time += response.response_time_ms;
                    }
                    
                    // Small delay to simulate real usage
                    std::this_thread::sleep_for(std::chrono::milliseconds(1));
                }
                
                return {successful, total_time};
            }));
        }
        
        // Collect results
        int total_successful = 0;
        double total_response_time = 0.0;
        
        for (auto& future : futures) {
            auto [successful, response_time] = future.get();
            total_successful += successful;
            total_response_time += response_time;
        }
        
        auto load_end = high_resolution_clock::now();
        auto total_test_ms = duration_cast<milliseconds>(load_end - load_start).count();
        
        // Results
        double avg_response_time = total_response_time / total_successful;
        double rps = (total_successful * 1000.0) / total_test_ms;
        
        std::cout << "\n🎯 FINAL RESULTS:\n";
        std::cout << "  - Total Requests: " << total_successful << " successful\n";
        std::cout << "  - Total Time: " << total_test_ms << "ms\n";
        std::cout << "  - Requests/Second: " << std::fixed << std::setprecision(1) << rps << "\n";
        std::cout << "  - Avg Response Time: " << std::fixed << std::setprecision(2) 
                  << avg_response_time << "ms\n";
        std::cout << "  - Events in Database: " << TEST_EVENTS << "\n";
        
        // Performance rating
        if (rps > 1000) {
            std::cout << "  - Rating: 🚀 EXCELLENT (>1000 RPS)\n";
        } else if (rps > 500) {
            std::cout << "  - Rating: ✅ GOOD (>500 RPS)\n";
        } else if (rps > 100) {
            std::cout << "  - Rating: ⚡ DECENT (>100 RPS)\n";
        } else {
            std::cout << "  - Rating: ⚠️  NEEDS IMPROVEMENT (<100 RPS)\n";
        }
        
        stopServer();
    }
    
    void runAllBenchmarks() {
        std::cout << "🔥 UNIFIED SCHEDULER PERFORMANCE BENCHMARK\n";
        std::cout << "==========================================\n";
        std::cout << "Testing the new unified architecture with optimizations\n";
        
        curl_global_init(CURL_GLOBAL_DEFAULT);
        
        runModelBenchmarks();
        runApiBenchmarks();
        runFullSystemBenchmark();
        
        curl_global_cleanup();
        
        std::cout << "\n✨ Benchmark Complete! ✨\n";
    }
};

int main(int argc, char* argv[]) {
    EnvLoader::load();
    
    std::cout << "🚀 Unified Scheduler Benchmark Tool\n";
    std::cout << "===================================\n";
    
    if (argc > 1) {
        std::string arg = argv[1];
        
        if (arg == "--help" || arg == "-h") {
            std::cout << "Usage: " << argv[0] << " [option]\n";
            std::cout << "Options:\n";
            std::cout << "  --model     Run model benchmarks only\n";
            std::cout << "  --api       Run API benchmarks only\n";
            std::cout << "  --full      Run full system benchmark only\n";
            std::cout << "  --help      Show this help\n";
            std::cout << "  (no args)   Run all benchmarks\n";
            return 0;
        }
    }
    
    UnifiedBenchmark benchmark;
    
    if (argc > 1) {
        std::string arg = argv[1];
        if (arg == "--model") {
            benchmark.runModelBenchmarks();
        } else if (arg == "--api") {
            benchmark.runApiBenchmarks();
        } else if (arg == "--full") {
            benchmark.runFullSystemBenchmark();
        } else {
            std::cout << "Unknown option: " << arg << "\n";
            return 1;
        }
    } else {
        benchmark.runAllBenchmarks();
    }
    
    return 0;
}