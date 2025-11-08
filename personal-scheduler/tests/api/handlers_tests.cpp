#include <cassert>
#include <iostream>
#include <sstream>
#include "../../api/handlers/EventsHandler.h"
#include "../../api/handlers/StatsHandler.h"
#include "../../api/performance/PerformanceMonitor.h"
#include "../../services/EventService.h"
#include "../../model/Model.h"
#include "../../model/OneTimeEvent.h"
#include "../../database/SQLiteScheduleDatabase.h"
#include "../../utils/ResponseCache.h"
#include "../test_utils.h"

using namespace std;
using namespace chrono;

// Mock HTTP request/response for testing
class MockRequest {
public:
    string method;
    string path;
    string body;
    map<string, string> params;
};

class MockResponse {
public:
    int status = 200;
    string body;
    map<string, string> headers;
    
    void set_content(const string& content, const string& type) {
        body = content;
        headers["Content-Type"] = type;
    }
    
    void set_header(const string& key, const string& value) {
        headers[key] = value;
    }
};

static void testEventsHandlerGetEvents() {
    SQLiteScheduleDatabase db(":memory:");
    Model model(&db);
    EventService service(model);
    PerformanceMonitor monitor;
    ResponseCache cache;
    
    // Add test event
    OneTimeEvent event("1", "desc", "Test Event", makeTime(2025, 6, 1, 9), hours(1));
    service.addEvent(event);
    
    EventsHandler handler(service, monitor, cache, "http://localhost:3000");
    
    // Mock GET /events request
    httplib::Request req;
    req.method = "GET";
    req.path = "/events";
    
    httplib::Response res;
    handler.handle(req, res);
    
    assert(res.status == 200);
    assert(res.body.find("Test Event") != string::npos);
    assert(res.get_header_value("Access-Control-Allow-Origin") == "http://localhost:3000");
    
    cout << "EventsHandler GET events test passed\n";
}

static void testEventsHandlerPostEvent() {
    SQLiteScheduleDatabase db(":memory:");
    Model model(&db);
    EventService service(model);
    PerformanceMonitor monitor;
    ResponseCache cache;
    
    EventsHandler handler(service, monitor, cache, "http://localhost:3000");
    
    // Mock POST /events request
    httplib::Request req;
    req.method = "POST";
    req.path = "/events";
    req.body = R"({
        "title": "New Event",
        "description": "Test description",
        "time": "2025-06-01 10:00",
        "duration": 60
    })";
    req.set_header("Content-Type", "application/json");
    
    httplib::Response res;
    handler.handle(req, res);
    
    assert(res.status == 200);
    assert(res.body.find("ok") != string::npos);
    
    // Verify event was added
    auto events = service.getEvents(10, makeTime(2025, 7, 1));
    assert(events.size() == 1);
    assert(events[0].getTitle() == "New Event");
    
    cout << "EventsHandler POST event test passed\n";
}

static void testEventsHandlerGetNext() {
    SQLiteScheduleDatabase db(":memory:");
    Model model(&db);
    EventService service(model);
    PerformanceMonitor monitor;
    ResponseCache cache;
    
    // Add multiple events
    OneTimeEvent e1("1", "desc1", "Event 1", makeTime(2025, 6, 1, 9), hours(1));
    OneTimeEvent e2("2", "desc2", "Event 2", makeTime(2025, 6, 2, 10), hours(1));
    OneTimeEvent e3("3", "desc3", "Event 3", makeTime(2025, 6, 3, 11), hours(1));
    
    service.addEvent(e1);
    service.addEvent(e2);
    service.addEvent(e3);
    
    EventsHandler handler(service, monitor, cache, "http://localhost:3000");
    
    // Mock GET /events/next/2 request
    httplib::Request req;
    req.method = "GET";
    req.path = "/events/next/2";
    req.matches = {"2"};  // Simulating regex match
    
    httplib::Response res;
    handler.handle(req, res);
    
    assert(res.status == 200);
    // Should return first 2 events
    assert(res.body.find("Event 1") != string::npos);
    assert(res.body.find("Event 2") != string::npos);
    assert(res.body.find("Event 3") == string::npos);
    
    cout << "EventsHandler GET next events test passed\n";
}

static void testStatsHandler() {
    PerformanceMonitor monitor;
    
    // Add some test metrics
    monitor.recordApiCall("/events", 50);
    monitor.recordApiCall("/stats", 25);
    monitor.recordCacheHit();
    monitor.recordCacheMiss();
    
    StatsHandler handler(monitor, "http://localhost:3000");
    
    // Mock GET /stats request
    httplib::Request req;
    req.method = "GET";
    req.path = "/stats";
    
    httplib::Response res;
    handler.handle(req, res);
    
    assert(res.status == 200);
    assert(res.body.find("total_requests") != string::npos);
    assert(res.body.find("average_response_time") != string::npos);
    assert(res.body.find("cache_hit_rate") != string::npos);
    assert(res.get_header_value("Access-Control-Allow-Origin") == "http://localhost:3000");
    
    cout << "StatsHandler test passed\n";
}

static void testHandlerErrorCases() {
    SQLiteScheduleDatabase db(":memory:");
    Model model(&db);
    EventService service(model);
    PerformanceMonitor monitor;
    ResponseCache cache;
    
    EventsHandler handler(service, monitor, cache, "http://localhost:3000");
    
    // Test invalid JSON
    httplib::Request req;
    req.method = "POST";
    req.path = "/events";
    req.body = "invalid json";
    req.set_header("Content-Type", "application/json");
    
    httplib::Response res;
    handler.handle(req, res);
    
    assert(res.status == 400);
    assert(res.body.find("error") != string::npos);
    
    cout << "Handler error cases test passed\n";
}

static void testHandlerCaching() {
    SQLiteScheduleDatabase db(":memory:");
    Model model(&db);
    EventService service(model);
    PerformanceMonitor monitor;
    ResponseCache cache;
    
    // Add test event
    OneTimeEvent event("1", "desc", "Cached Event", makeTime(2025, 6, 1, 9), hours(1));
    service.addEvent(event);
    
    EventsHandler handler(service, monitor, cache, "http://localhost:3000");
    
    // First request - should miss cache
    httplib::Request req1;
    req1.method = "GET";
    req1.path = "/events";
    
    httplib::Response res1;
    handler.handle(req1, res1);
    
    assert(res1.status == 200);
    
    // Second identical request - should hit cache
    httplib::Request req2;
    req2.method = "GET";
    req2.path = "/events";
    
    httplib::Response res2;
    handler.handle(req2, res2);
    
    assert(res2.status == 200);
    assert(res1.body == res2.body);
    
    // Verify cache metrics
    auto stats = monitor.getStats();
    assert(stats.cache_hits > 0);
    
    cout << "Handler caching test passed\n";
}

int main() {
    testEventsHandlerGetEvents();
    testEventsHandlerPostEvent();
    testEventsHandlerGetNext();
    testStatsHandler();
    testHandlerErrorCases();
    testHandlerCaching();
    
    cout << "All handler tests passed!\n";
    return 0;
}