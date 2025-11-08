#include <cassert>
#include <thread>
#include "../../api/ApiServer.h"
#include "../../model/Model.h"
#include "../../model/OneTimeEvent.h"
#include "../../model/RecurringEvent.h"
#include "../../model/recurrence/DailyRecurrence.h"
#include "../test_utils.h"
#include "../../scheduler/EventLoop.h"
#include "../../external/json/nlohmann/json.hpp"
#include <algorithm>

using json = nlohmann::json;
using namespace std;
using namespace chrono;

static void runServer(ApiServer &srv) {
    srv.start();
}

static const char *API_KEY_VAL = "secret";

static void testDayEndpoint() {
    setenv("API_KEY", API_KEY_VAL, 1);
    Model m;
    OneTimeEvent e1("1","d","t", makeTime(2025,6,1,9), hours(1));
    m.addEvent(e1);
    ApiServer srv(m, 8085);
    thread th(runServer, std::ref(srv));
    this_thread::sleep_for(milliseconds(100));

    httplib::Client cli("localhost", 8085);
    httplib::Headers h{{"Authorization", API_KEY_VAL}};
    auto res = cli.Get("/events/day/2025-06-01", h);
    assert(res && res->status == 200);
    auto j = json::parse(res->body);
    assert(j["status"] == "ok");
    assert(j["data"].size() == 1);

    srv.stop();
    th.join();
}

static void testWeekEndpoint() {
    setenv("API_KEY", API_KEY_VAL, 1);
    Model m;
    OneTimeEvent e1("1","d","t", makeTime(2025,6,2,9), hours(1)); // Monday
    OneTimeEvent e2("2","d","t", makeTime(2025,6,8,10), hours(1)); // Sunday
    m.addEvent(e1); m.addEvent(e2);
    ApiServer srv(m, 8086);
    thread th(runServer, std::ref(srv));
    this_thread::sleep_for(milliseconds(100));

    httplib::Client cli("localhost", 8086);
    httplib::Headers h{{"Authorization", API_KEY_VAL}};
    auto res = cli.Get("/events/week/2025-06-03", h);
    assert(res && res->status == 200);
    auto j = json::parse(res->body);
    assert(j["status"] == "ok");
    assert(j["data"].size() == 2);

    srv.stop();
    th.join();
}

static void testMonthEndpoint() {
    setenv("API_KEY", API_KEY_VAL, 1);
    Model m;
    OneTimeEvent e1("1","d","t", makeTime(2025,6,2,9), hours(1));
    OneTimeEvent e2("2","d","t", makeTime(2025,7,1,9), hours(1));
    m.addEvent(e1); m.addEvent(e2);
    ApiServer srv(m, 8087);
    thread th(runServer, std::ref(srv));
    this_thread::sleep_for(milliseconds(100));

    httplib::Client cli("localhost", 8087);
    httplib::Headers h{{"Authorization", API_KEY_VAL}};
    auto res = cli.Get("/events/month/2025-06", h);
    assert(res && res->status == 200);
    auto j = json::parse(res->body);
    assert(j["status"] == "ok");
    assert(j["data"].size() == 1);

    srv.stop();
    th.join();
}

static void testCORSEnabled() {
    setenv("API_KEY", API_KEY_VAL, 1);
    setenv("CORS_ORIGIN", "*", 1);
    Model m;
    ApiServer srv(m, 8088);
    thread th(runServer, std::ref(srv));
    this_thread::sleep_for(milliseconds(100));

    httplib::Client cli("localhost", 8088);
    httplib::Headers h{{"Authorization", API_KEY_VAL}};
    auto res = cli.Options("/events", h);
    assert(res && res->status == 200);
    assert(res->get_header_value("Access-Control-Allow-Origin") == "*");
    assert(!res->get_header_value("Access-Control-Allow-Methods").empty());

    srv.stop();
    th.join();
}

static void testDeleteAllEndpoint() {
    setenv("API_KEY", API_KEY_VAL, 1);
    Model m;
    OneTimeEvent e1("1","d","t", makeTime(2025,6,1,9), hours(1));
    m.addEvent(e1);
    ApiServer srv(m, 8089);
    thread th(runServer, std::ref(srv));
    this_thread::sleep_for(milliseconds(100));

    httplib::Client cli("localhost", 8089);
    httplib::Headers h{{"Authorization", API_KEY_VAL}};
    auto res = cli.Delete("/events", h);
    assert(res && res->status == 200);
    auto j = json::parse(res->body);
    assert(j["status"] == "ok");

    auto res2 = cli.Get("/events", h);
    auto j2 = json::parse(res2->body);
    assert(j2["data"].size() == 0);

    srv.stop();
    th.join();
}

static void testDeleteDayEndpoint() {
    setenv("API_KEY", API_KEY_VAL, 1);
    Model m;
    OneTimeEvent e1("1","d","t", makeTime(2025,6,1,9), hours(1));
    m.addEvent(e1);
    ApiServer srv(m, 8090);
    thread th(runServer, std::ref(srv));
    this_thread::sleep_for(milliseconds(100));

    httplib::Client cli("localhost", 8090);
    httplib::Headers h{{"Authorization", API_KEY_VAL}};
    auto res = cli.Delete("/events/day/2025-06-01", h);
    assert(res && res->status == 200);
    auto j = json::parse(res->body);
    assert(j["status"] == "ok");

    auto res2 = cli.Get("/events", h);
    auto j2 = json::parse(res2->body);
    assert(j2["data"].size() == 0);

    srv.stop();
    th.join();
}

static void testDeleteBeforeEndpoint() {
    setenv("API_KEY", API_KEY_VAL, 1);
    Model m;
    OneTimeEvent e1("1","d","t", makeTime(2025,6,1,9), hours(1));
    OneTimeEvent e2("2","d","t", makeTime(2025,6,3,9), hours(1));
    m.addEvent(e1); m.addEvent(e2);
    ApiServer srv(m, 8091);
    thread th(runServer, std::ref(srv));
    this_thread::sleep_for(milliseconds(100));

    httplib::Client cli("localhost", 8091);
    httplib::Headers h{{"Authorization", API_KEY_VAL}};
    auto res = cli.Delete("/events/before/2025-06-02T00:00", h);
    assert(res && res->status == 200);
    auto j = json::parse(res->body);
    assert(j["status"] == "ok");

    auto res2 = cli.Get("/events", h);
    auto j2 = json::parse(res2->body);
    assert(j2["data"].size() == 1);

    srv.stop();
    th.join();
}

static void testNotifierAndActionEndpoints() {
    setenv("API_KEY", API_KEY_VAL, 1);
    Model m;
    EventLoop loop(m);
    loop.start();
    ApiServer srv(m, 8092, "127.0.0.1", &loop);
    std::thread th(runServer, std::ref(srv));
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    httplib::Client cli("localhost", 8092);
    httplib::Headers h{{"Authorization", API_KEY_VAL}};
    auto res1 = cli.Get("/notifiers", h);
    assert(res1 && res1->status == 200);
    auto j1 = json::parse(res1->body);
    assert(j1["status"] == "ok");
    assert(std::find(j1["data"].begin(), j1["data"].end(), "console") != j1["data"].end());

    auto res2 = cli.Get("/actions", h);
    assert(res2 && res2->status == 200);
    auto j2 = json::parse(res2->body);
    assert(j2["status"] == "ok");
    assert(std::find(j2["data"].begin(), j2["data"].end(), "hello") != j2["data"].end());

    json body = {
        {"title","Task"},
        {"description","demo"},
        {"time","2025-06-01 12:00"},
        {"notifier","console"},
        {"action","hello"}
    };
    auto res3 = cli.Post("/tasks", h, body.dump(), "application/json");
    assert(res3 && res3->status == 200);
    auto j3 = json::parse(res3->body);
    assert(j3["status"] == "ok");

    auto res4 = cli.Get("/tasks", h);
    auto j4 = json::parse(res4->body);
    assert(j4["status"] == "ok");
    assert(j4["data"].size() == 1);

    srv.stop();
    th.join();
    loop.stop();
}

static void testEventsExpandedEndpoint() {
    setenv("API_KEY", API_KEY_VAL, 1);
    Model m;
    auto start = makeTime(2025,6,1,9);
    auto pat = std::make_shared<DailyRecurrence>(start, 1);
    RecurringEvent r("R","d","daily", start, std::chrono::hours(1), pat);
    m.addEvent(r);

    ApiServer srv(m, 8093);
    std::thread th(runServer, std::ref(srv));
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    httplib::Client cli("localhost", 8093);
    httplib::Headers h{{"Authorization", API_KEY_VAL}};

    // Non-expanded should return the stored entries (1 recurring seed)
    auto res0 = cli.Get("/events", h);
    assert(res0 && res0->status == 200);
    auto j0 = json::parse(res0->body);
    assert(j0["status"] == "ok");
    assert(j0["data"].size() == 1);

    // Expanded with a 3-day window should return 3 occurrences
    auto res = cli.Get("/events?expanded=true&start=2025-06-01%2000:00&end=2025-06-04%2000:00", h);
    assert(res && res->status == 200);
    auto j = json::parse(res->body);
    assert(j["status"] == "ok");
    assert(j["data"].size() == 3);

    srv.stop();
    th.join();
}

int main() {
    testDayEndpoint();
    testWeekEndpoint();
    testMonthEndpoint();
    testCORSEnabled();
    testDeleteAllEndpoint();
    testDeleteDayEndpoint();
    testDeleteBeforeEndpoint();
    testNotifierAndActionEndpoints();
    testEventsExpandedEndpoint();
    cout << "API tests passed\n";
    return 0;
}
