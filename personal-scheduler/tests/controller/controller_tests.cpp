#include <cassert>
#include <iostream>
#include <sstream>
#include "../../model/Model.h"
#include "../../model/OneTimeEvent.h"
#include "../../model/RecurringEvent.h"
#include "../../model/recurrence/DailyRecurrence.h"
#include "../test_utils.h"
#include <memory>

#define private public
#include "../../controller/Controller.h"
#undef private
#include "../../utils/TimeUtils.h"

using namespace std;
using namespace chrono;

static void testControllerParseFormat()
{
    auto tp = TimeUtils::parseTimePoint("2025-06-01 09:30");
    string s = TimeUtils::formatTimePoint(tp);
    assert(s == "2025-06-01 09:30");

    bool threw = false;
    try { TimeUtils::parseTimePoint("bad format"); }
    catch(const exception&) { threw = true; }
    assert(threw);

    const char* prevPtr = getenv("TZ");
    std::string prev = prevPtr ? std::string(prevPtr) : std::string();
    bool hadPrev = prevPtr != nullptr;
    setenv("TZ", "Europe/Berlin", 1);
    tzset();
    auto tp2 = TimeUtils::parseTimePoint("2025-06-05 12:00");
    string s2 = TimeUtils::formatTimePoint(tp2);
    assert(s2 == "2025-06-05 12:00");
    if (hadPrev)
        setenv("TZ", prev.c_str(), 1);
    else
        unsetenv("TZ");
    tzset();
}

static void testControllerParseFormatTimeZones()
{
    struct Case { const char* zone; const char* utc; } cases[] = {
        {"UTC", "2025-06-05 12:00"},
        {"Europe/London", "2025-06-05 11:00"},
        {"America/Chicago", "2025-06-05 17:00"},
        {"Asia/Tokyo", "2025-06-05 03:00"}
    };

    for (const auto &c : cases)
    {
        const char* prevPtr = getenv("TZ");
        std::string prev = prevPtr ? std::string(prevPtr) : std::string();
        bool hadPrev = prevPtr != nullptr;
        setenv("TZ", c.zone, 1);
        tzset();

        auto tp = TimeUtils::parseTimePoint("2025-06-05 12:00");
        string round = TimeUtils::formatTimePoint(tp);
        assert(round == "2025-06-05 12:00");

        time_t t = system_clock::to_time_t(tp);
        tm gm;
        gmtime_r(&t, &gm);
        char buf[32];
        strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M", &gm);
        string utc = buf;
        assert(utc == c.utc);

        if (hadPrev)
            setenv("TZ", prev.c_str(), 1);
        else
            unsetenv("TZ");
        tzset();
    }
}

static void testControllerCrossTimeZones()
{
    const char* prevPtr = getenv("TZ");
    std::string prev = prevPtr ? std::string(prevPtr) : std::string();
    bool hadPrev = prevPtr != nullptr;

    // Event created in Chicago during DST
    setenv("TZ", "America/Chicago", 1);
    tzset();
    auto tpSummer = TimeUtils::parseTimePoint("2025-06-01 14:00");

    // View the event from different locations
    string chicago = TimeUtils::formatTimePoint(tpSummer);
    assert(chicago == "2025-06-01 14:00");

    setenv("TZ", "Europe/London", 1);
    tzset();
    string london = TimeUtils::formatTimePoint(tpSummer);
    assert(london == "2025-06-01 20:00");

    setenv("TZ", "Asia/Tokyo", 1);
    tzset();
    string tokyo = TimeUtils::formatTimePoint(tpSummer);
    assert(tokyo == "2025-06-02 04:00");

    // Event created in Chicago outside of DST
    setenv("TZ", "America/Chicago", 1);
    tzset();
    auto tpWinter = TimeUtils::parseTimePoint("2025-01-15 14:00");
    string chicagoW = TimeUtils::formatTimePoint(tpWinter);
    assert(chicagoW == "2025-01-15 14:00");

    setenv("TZ", "Europe/London", 1);
    tzset();
    string londonW = TimeUtils::formatTimePoint(tpWinter);
    assert(londonW == "2025-01-15 20:00");

    setenv("TZ", "Asia/Tokyo", 1);
    tzset();
    string tokyoW = TimeUtils::formatTimePoint(tpWinter);
    assert(tokyoW == "2025-01-16 05:00");

    if (hadPrev)
        setenv("TZ", prev.c_str(), 1);
    else
        unsetenv("TZ");
    tzset();
}

static void testControllerPrintNextEvent()
{
    Model m;
    auto now = chrono::system_clock::now();
    OneTimeEvent e1("1","d","t", now + chrono::hours(1), hours(1));
    m.addEvent(e1);
    StubView v(m);
    Controller c(m,v);

    std::ostringstream ss;
    auto old = cout.rdbuf(ss.rdbuf());
    c.printNextEvent();
    cout.rdbuf(old);
    assert(ss.str().find("[1]") != string::npos);
}

static void testControllerPrintNextEventNone()
{
    Model m;
    StubView v(m);
    Controller c(m,v);
    std::ostringstream ss;
    auto old = cout.rdbuf(ss.rdbuf());
    c.printNextEvent();
    cout.rdbuf(old);
    assert(ss.str().find("no upcoming events") != string::npos);
}

static void testControllerAddRecurring()
{
    Model m;
    StubView v(m);
    Controller c(m,v);

    auto now = chrono::system_clock::now();
    auto start = now + chrono::hours(1);
    auto pattern = std::make_shared<DailyRecurrence>(start, 1);
    std::string id = c.addRecurringEvent("t", "d", start, hours(1), pattern);

    OneTimeEvent o("O","d","t", start + chrono::hours(24), hours(1));
    m.addEvent(o);

    std::ostringstream ss;
    auto old = cout.rdbuf(ss.rdbuf());
    c.printNextEvent();
    cout.rdbuf(old);
    assert(ss.str().find("[" + id + "]") != string::npos);
}

static void testControllerRemoveAll()
{
    Model m;
    OneTimeEvent e1("1","d","t", makeTime(2025,6,1,9), hours(1));
    OneTimeEvent e2("2","d","t", makeTime(2025,6,2,9), hours(1));
    m.addEvent(e1);
    m.addEvent(e2);
    StubView v(m);
    Controller c(m, v);
    c.removeAllEvents();
    auto list = m.getNextNEvents(1);
    assert(list.empty());
}

static void testControllerRemoveDay()
{
    Model m;
    OneTimeEvent e1("1","d","t", makeTime(2025,6,1,9), hours(1));
    OneTimeEvent e2("2","d","t", makeTime(2025,6,2,9), hours(1));
    m.addEvent(e1); m.addEvent(e2);
    StubView v(m);
    Controller c(m, v);
    c.removeEventsOnDay(makeTime(2025,6,1,0));
    auto d = m.getEventsOnDay(makeTime(2025,6,1,0));
    assert(d.empty());
}

static void testControllerRemoveBefore()
{
    Model m;
    OneTimeEvent e1("1","d","t", makeTime(2025,6,1,9), hours(1));
    OneTimeEvent e2("2","d","t", makeTime(2025,6,3,9), hours(1));
    m.addEvent(e1); m.addEvent(e2);
    StubView v(m);
    Controller c(m, v);
    c.removeEventsBefore(makeTime(2025,6,2,0));
    auto evs = m.getEvents(-1, makeTime(2025,6,4,0));
    assert(evs.size() == 1 && evs[0].getId() == "2");
}

int main()
{
    testControllerParseFormat();
    testControllerParseFormatTimeZones();
    testControllerCrossTimeZones();
    testControllerPrintNextEvent();
    testControllerPrintNextEventNone();
    testControllerAddRecurring();
    testControllerRemoveAll();
    testControllerRemoveDay();
    testControllerRemoveBefore();
    cout << "Controller tests passed\n";
    return 0;
}
