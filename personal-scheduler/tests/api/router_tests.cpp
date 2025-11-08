#include <cassert>
#include <iostream>
#include <memory>
#include "../../api/routing/Router.h"
#include "../../api/interfaces/IRequestHandler.h"

using namespace std;

// Mock handler for testing
class MockHandler : public IRequestHandler {
private:
    string name_;
    
public:
    bool handleCalled = false;
    string lastMethod;
    string lastPath;
    
    explicit MockHandler(const string& name) : name_(name) {}
    
    void handle(const httplib::Request& req, httplib::Response& res) override {
        handleCalled = true;
        lastMethod = req.method;
        lastPath = req.path;
        res.status = 200;
        res.set_content("Handled by " + name_, "text/plain");
    }
};

static void testRouterAddRoute() {
    Router router;
    auto handler = make_shared<MockHandler>("test");
    
    router.addRoute("GET", "/test", handler);
    
    assert(router.getRouteCount() == 1);
    
    cout << "Router addRoute test passed\n";
}

static void testRouterFindHandler() {
    Router router;
    auto getHandler = make_shared<MockHandler>("get");
    auto postHandler = make_shared<MockHandler>("post");
    
    router.addRoute("GET", "/events", getHandler);
    router.addRoute("POST", "/events", postHandler);
    
    // Test exact match
    auto foundGet = router.findHandler("GET", "/events");
    auto foundPost = router.findHandler("POST", "/events");
    
    assert(foundGet == getHandler);
    assert(foundPost == postHandler);
    
    cout << "Router findHandler test passed\n";
}

static void testRouterRegexPattern() {
    Router router;
    auto handler = make_shared<MockHandler>("regex");
    
    // Add route with regex pattern
    router.addRoute("GET", "/events/next/\\\\d+", handler);
    
    // Test that it finds handler for matching paths
    auto found1 = router.findHandler("GET", "/events/next/5");
    auto found2 = router.findHandler("GET", "/events/next/100");
    
    assert(found1 == handler);
    assert(found2 == handler);
    
    // Test that it doesn't match non-matching paths
    auto notFound = router.findHandler("GET", "/events/next/abc");
    assert(notFound == nullptr);
    
    cout << "Router regex pattern test passed\n";
}

static void testRouterMethodDistinction() {
    Router router;
    auto getHandler = make_shared<MockHandler>("get");
    auto postHandler = make_shared<MockHandler>("post");
    auto putHandler = make_shared<MockHandler>("put");
    
    router.addRoute("GET", "/resource", getHandler);
    router.addRoute("POST", "/resource", postHandler);
    router.addRoute("PUT", "/resource", putHandler);
    
    assert(router.findHandler("GET", "/resource") == getHandler);
    assert(router.findHandler("POST", "/resource") == postHandler);
    assert(router.findHandler("PUT", "/resource") == putHandler);
    assert(router.findHandler("DELETE", "/resource") == nullptr);
    
    cout << "Router method distinction test passed\n";
}

static void testRouterNotFound() {
    Router router;
    auto handler = make_shared<MockHandler>("test");
    
    router.addRoute("GET", "/exists", handler);
    
    // Test non-existent paths
    assert(router.findHandler("GET", "/doesntexist") == nullptr);
    assert(router.findHandler("POST", "/exists") == nullptr);
    assert(router.findHandler("GET", "/") == nullptr);
    
    cout << "Router not found test passed\n";
}

static void testRouterMultiplePatterns() {
    Router router;
    auto handler1 = make_shared<MockHandler>("handler1");
    auto handler2 = make_shared<MockHandler>("handler2");
    auto handler3 = make_shared<MockHandler>("handler3");
    
    router.addRoute("GET", "/api/v1/users", handler1);
    router.addRoute("GET", "/api/v1/users/\\\\d+", handler2);
    router.addRoute("POST", "/api/v1/users", handler3);
    
    assert(router.getRouteCount() == 3);
    
    // Test specific matches
    assert(router.findHandler("GET", "/api/v1/users") == handler1);
    assert(router.findHandler("GET", "/api/v1/users/123") == handler2);
    assert(router.findHandler("POST", "/api/v1/users") == handler3);
    
    cout << "Router multiple patterns test passed\n";
}

static void testRouterCaseSensitivity() {
    Router router;
    auto handler = make_shared<MockHandler>("case");
    
    router.addRoute("GET", "/CaseSensitive", handler);
    
    // Paths should be case sensitive
    assert(router.findHandler("GET", "/CaseSensitive") == handler);
    assert(router.findHandler("GET", "/casesensitive") == nullptr);
    assert(router.findHandler("GET", "/CASESENSITIVE") == nullptr);
    
    // Methods should be case sensitive
    assert(router.findHandler("get", "/CaseSensitive") == nullptr);
    assert(router.findHandler("Get", "/CaseSensitive") == nullptr);
    
    cout << "Router case sensitivity test passed\n";
}

static void testRouterComplexRegex() {
    Router router;
    auto dateHandler = make_shared<MockHandler>("date");
    auto timeHandler = make_shared<MockHandler>("time");
    
    // Date pattern: YYYY-MM-DD
    router.addRoute("GET", "/events/date/\\\\d{4}-\\\\d{2}-\\\\d{2}", dateHandler);
    
    // Time pattern: HH:MM
    router.addRoute("GET", "/events/time/\\\\d{2}:\\\\d{2}", timeHandler);
    
    // Test date pattern
    assert(router.findHandler("GET", "/events/date/2025-06-01") == dateHandler);
    assert(router.findHandler("GET", "/events/date/25-06-01") == nullptr);  // Wrong year format
    
    // Test time pattern  
    assert(router.findHandler("GET", "/events/time/14:30") == timeHandler);
    assert(router.findHandler("GET", "/events/time/1:30") == nullptr);  // Wrong hour format
    
    cout << "Router complex regex test passed\n";
}

static void testRouterOverwrite() {
    Router router;
    auto handler1 = make_shared<MockHandler>("first");
    auto handler2 = make_shared<MockHandler>("second");
    
    // Add route
    router.addRoute("GET", "/test", handler1);
    assert(router.getRouteCount() == 1);
    assert(router.findHandler("GET", "/test") == handler1);
    
    // Add same route again - should overwrite
    router.addRoute("GET", "/test", handler2);
    assert(router.getRouteCount() == 1);  // Count shouldn't increase
    assert(router.findHandler("GET", "/test") == handler2);  // Should return new handler
    
    cout << "Router overwrite test passed\n";
}

int main() {
    testRouterAddRoute();
    testRouterFindHandler();
    testRouterRegexPattern();
    testRouterMethodDistinction();
    testRouterNotFound();
    testRouterMultiplePatterns();
    testRouterCaseSensitivity();
    testRouterComplexRegex();
    testRouterOverwrite();
    
    cout << "All Router tests passed!\n";
    return 0;
}