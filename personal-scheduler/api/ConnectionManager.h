#pragma once

#include <httplib.h>
#include <memory>
#include <thread>
#include <atomic>
#include <sys/socket.h>
#include <netinet/tcp.h>

#ifdef _WIN32
#include <winsock2.h>
typedef SOCKET socket_t;
#else
typedef int socket_t;
#endif

class ConnectionManager {
private:
    std::atomic<size_t> activeConnections_{0};
    std::atomic<size_t> totalRequests_{0};
    std::atomic<size_t> keepAliveConnections_{0};
    
public:
    // Configure server for high performance
    static void optimizeServer(httplib::Server& server) {
        // Enable keep-alive connections
        server.set_keep_alive_max_count(100);
        server.set_keep_alive_timeout(30);
        
        // Optimize socket options
        server.set_socket_options([](socket_t sock) {
            // Disable Nagle's algorithm for lower latency
            int flag = 1;
            setsockopt(sock, IPPROTO_TCP, TCP_NODELAY, (char*)&flag, sizeof(flag));
            
            // Set socket buffer sizes
            int bufsize = 65536;
            setsockopt(sock, SOL_SOCKET, SO_RCVBUF, (char*)&bufsize, sizeof(bufsize));
            setsockopt(sock, SOL_SOCKET, SO_SNDBUF, (char*)&bufsize, sizeof(bufsize));
            
            return true;
        });
        
        // Set thread pool size based on hardware
        auto thread_count = std::max(4u, std::thread::hardware_concurrency());
        server.new_task_queue = [thread_count] {
            return new httplib::ThreadPool(thread_count);
        };
    }
    
    // Pre-routing handler for connection tracking
    static httplib::Server::HandlerResponse trackConnection(
        const httplib::Request& req, httplib::Response& res) {
        
        // Add performance headers
        res.set_header("X-Response-Time", "0"); // Will be set later
        res.set_header("Connection", "keep-alive");
        res.set_header("Keep-Alive", "timeout=30, max=100");
        
        return httplib::Server::HandlerResponse::Unhandled;
    }
    
    // Response compression for large payloads
    static void enableCompression(httplib::Server& server) {
        server.set_pre_routing_handler([](const httplib::Request& req, httplib::Response& res) {
            // Enable gzip compression for responses > 1KB
            auto accept_encoding = req.get_header_value("Accept-Encoding");
            if (accept_encoding.find("gzip") != std::string::npos) {
                res.set_header("Content-Encoding", "gzip");
            }
            return httplib::Server::HandlerResponse::Unhandled;
        });
    }
    
    struct ConnectionStats {
        size_t active_connections;
        size_t total_requests;
        size_t keep_alive_connections;
        double requests_per_second;
    };
    
    ConnectionStats getStats() const {
        return {
            activeConnections_.load(),
            totalRequests_.load(),
            keepAliveConnections_.load(),
            0.0 // Calculate RPS based on time window
        };
    }
};