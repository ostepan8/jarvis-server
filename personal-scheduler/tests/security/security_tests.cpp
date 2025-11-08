#include <cassert>
#include <iostream>
#include <thread>
#include <chrono>
#include "../../security/Auth.h"
#include "../../security/RateLimiter.h"
#include "httplib.h"

using namespace std;
using namespace chrono;

static void testAuthBasicAuthentication() {
    Auth auth("secret_key", "admin_key");
    
    // Create mock request
    httplib::Request req;
    
    // Test valid API key
    req.set_header("Authorization", "secret_key");
    assert(auth.authorize(req) == true);
    
    // Test valid admin key
    req.set_header("Authorization", "admin_key");
    assert(auth.authorize(req) == true);
    
    // Test invalid key
    req.set_header("Authorization", "wrong_key");
    assert(auth.authorize(req) == false);
    
    // Test missing header
    req.headers.clear();
    assert(auth.authorize(req) == false);
    
    cout << "Auth basic authentication test passed\n";
}

static void testAuthAdminOnly() {
    Auth auth("user_key", "admin_key");
    
    httplib::Request req;
    
    // Test admin access
    req.set_header("Authorization", "admin_key");
    assert(auth.isAdmin(req) == true);
    assert(auth.authorize(req) == true);
    
    // Test user access (not admin)
    req.set_header("Authorization", "user_key");
    assert(auth.isAdmin(req) == false);
    assert(auth.authorize(req) == true);  // Still authorized, just not admin
    
    // Test invalid key
    req.set_header("Authorization", "invalid_key");
    assert(auth.isAdmin(req) == false);
    assert(auth.authorize(req) == false);
    
    cout << "Auth admin-only test passed\n";
}

static void testAuthNoAdminKey() {
    // Constructor with empty admin key
    Auth auth("user_key", "");
    
    httplib::Request req;
    req.set_header("Authorization", "user_key");
    
    assert(auth.authorize(req) == true);
    assert(auth.isAdmin(req) == false);  // No admin key configured
    
    cout << "Auth no admin key test passed\n";
}

static void testAuthCaseInsensitiveHeader() {
    Auth auth("secret", "");
    
    httplib::Request req;
    
    // Test different header case variations
    req.set_header("authorization", "secret");  // lowercase
    assert(auth.authorize(req) == true);
    
    req.headers.clear();
    req.set_header("AUTHORIZATION", "secret");  // uppercase
    assert(auth.authorize(req) == true);
    
    req.headers.clear();
    req.set_header("Authorization", "secret");  // mixed case
    assert(auth.authorize(req) == true);
    
    cout << "Auth case insensitive header test passed\n";
}

static void testRateLimiterBasic() {
    // Allow 2 requests per second
    RateLimiter limiter(2, seconds(1));
    
    string client_ip = "192.168.1.1";
    
    // First request should be allowed
    assert(limiter.allow(client_ip) == true);
    
    // Second request should be allowed
    assert(limiter.allow(client_ip) == true);
    
    // Third request should be blocked
    assert(limiter.allow(client_ip) == false);
    
    cout << "RateLimiter basic test passed\n";
}

static void testRateLimiterMultipleClients() {
    RateLimiter limiter(1, seconds(1));
    
    string client1 = "192.168.1.1";
    string client2 = "192.168.1.2";
    
    // Each client gets their own limit
    assert(limiter.allow(client1) == true);
    assert(limiter.allow(client2) == true);
    
    // Both should be blocked on next request
    assert(limiter.allow(client1) == false);
    assert(limiter.allow(client2) == false);
    
    cout << "RateLimiter multiple clients test passed\n";
}

static void testRateLimiterWindowReset() {
    // Very short window for testing
    RateLimiter limiter(1, milliseconds(100));
    
    string client_ip = "192.168.1.1";
    
    // First request allowed
    assert(limiter.allow(client_ip) == true);
    
    // Second request blocked
    assert(limiter.allow(client_ip) == false);
    
    // Wait for window to reset
    this_thread::sleep_for(milliseconds(150));
    
    // Should be allowed again
    assert(limiter.allow(client_ip) == true);
    
    cout << "RateLimiter window reset test passed\n";
}

static void testRateLimiterHighVolume() {
    RateLimiter limiter(10, seconds(1));
    
    string client_ip = "192.168.1.1";
    
    // Allow 10 requests
    for (int i = 0; i < 10; i++) {
        assert(limiter.allow(client_ip) == true);
    }
    
    // 11th request should be blocked
    assert(limiter.allow(client_ip) == false);
    
    cout << "RateLimiter high volume test passed\n";
}

static void testRateLimiterZeroLimit() {
    // Zero requests allowed
    RateLimiter limiter(0, seconds(1));
    
    string client_ip = "192.168.1.1";
    
    // All requests should be blocked
    assert(limiter.allow(client_ip) == false);
    assert(limiter.allow(client_ip) == false);
    
    cout << "RateLimiter zero limit test passed\n";
}

static void testRateLimiterLargeLimit() {
    // Very large limit
    RateLimiter limiter(1000, seconds(1));
    
    string client_ip = "192.168.1.1";
    
    // Should allow many requests
    for (int i = 0; i < 500; i++) {
        assert(limiter.allow(client_ip) == true);
    }
    
    cout << "RateLimiter large limit test passed\n";
}

static void testAuthAndRateLimiterIntegration() {
    Auth auth("valid_key", "admin_key");
    RateLimiter limiter(2, seconds(1));
    
    httplib::Request req;
    req.set_header("Authorization", "valid_key");
    req.remote_addr = "192.168.1.1";
    
    // Both auth and rate limiting should pass
    assert(auth.authorize(req) == true);
    assert(limiter.allow(req.remote_addr) == true);
    assert(limiter.allow(req.remote_addr) == true);
    
    // Auth should still pass, but rate limit should block
    assert(auth.authorize(req) == true);
    assert(limiter.allow(req.remote_addr) == false);
    
    // Invalid auth should fail regardless of rate limit
    req.set_header("Authorization", "invalid_key");
    assert(auth.authorize(req) == false);
    
    cout << "Auth and RateLimiter integration test passed\n";
}

static void testSecurityEdgeCases() {
    Auth auth("key", "admin");
    RateLimiter limiter(1, milliseconds(1));
    
    httplib::Request req;
    
    // Test empty authorization header
    req.set_header("Authorization", "");
    assert(auth.authorize(req) == false);
    
    // Test very long authorization header
    string long_key(10000, 'a');
    req.set_header("Authorization", long_key);
    assert(auth.authorize(req) == false);
    
    // Test empty IP address for rate limiter
    assert(limiter.allow("") == true);  // Should handle gracefully
    
    // Test very long IP address
    string long_ip(1000, '1');
    assert(limiter.allow(long_ip) == true);  // Should handle gracefully
    
    cout << "Security edge cases test passed\n";
}

int main() {
    testAuthBasicAuthentication();
    testAuthAdminOnly();
    testAuthNoAdminKey();
    testAuthCaseInsensitiveHeader();
    testRateLimiterBasic();
    testRateLimiterMultipleClients();
    testRateLimiterWindowReset();
    testRateLimiterHighVolume();
    testRateLimiterZeroLimit();
    testRateLimiterLargeLimit();
    testAuthAndRateLimiterIntegration();
    testSecurityEdgeCases();
    
    cout << "All security tests passed!\n";
    return 0;
}