#include <cassert>
#include <iostream>
#include "../../model/Model.h"
#include "../../model/OneTimeEvent.h"
#include "../../model/RecurringEvent.h"
#include "../../model/recurrence/DailyRecurrence.h"
#include "../../model/recurrence/WeeklyRecurrence.h"
#include "../test_utils.h"
#include "../../utils/TimeUtils.h"
#include <memory>

using namespace std;
using namespace chrono;

static void testModelAddAndRetrieve()
{
    Model m;
    auto now = chrono::system_clock::now();
    OneTimeEvent e1("1","d1","t1", now + hours(2), hours(1));
    OneTimeEvent e2("2","d2","t2", now + hours(1), hours(1));
    m.addEvent(e1);
    m.addEvent(e2);
    auto next = m.getNextEvent();
    assert(next.getId() == "2");
    auto all = m.getEvents(-1, now + hours(4));
    assert(all.size() == 2);
    assert(all[0].getId() == "2");
    assert(all[1].getId() == "1");
}

static void testModelRemove()
{
    Model m;
    auto now = chrono::system_clock::now();
    OneTimeEvent e1("1","d1","t1", now + hours(1), hours(1));
    OneTimeEvent e2("2","d2","t2", now + hours(2), hours(1));
    m.addEvent(e1);
    m.addEvent(e2);
    assert(m.removeEvent("1"));
    assert(!m.removeEvent("3"));
    auto all = m.getEvents(-1, now + hours(5));
    assert(all.size() == 1 && all[0].getId() == "2");
}

static void testModelRemoveAll()
{
    Model m;
    OneTimeEvent e1("1","d","t", makeTime(2025,6,1,9), hours(1));
    OneTimeEvent e2("2","d","t", makeTime(2025,6,2,9), hours(1));
    m.addEvent(e1);
    m.addEvent(e2);
    m.removeAllEvents();
    auto list = m.getNextNEvents(1);
    assert(list.empty());
}

static void testModelRemoveDay()
{
    Model m;
    OneTimeEvent e1("1","d","t", makeTime(2025,6,1,9), hours(1));
    OneTimeEvent e2("2","d","t", makeTime(2025,6,1,15), hours(1));
    OneTimeEvent e3("3","d","t", makeTime(2025,6,2,9), hours(1));
    m.addEvent(e1); m.addEvent(e2); m.addEvent(e3);
    int n = m.removeEventsOnDay(makeTime(2025,6,1,0));
    assert(n == 2);
    auto list = m.getEventsOnDay(makeTime(2025,6,1,0));
    assert(list.empty());
}

static void testModelRemoveWeek()
{
    Model m;
    OneTimeEvent e1("1","d","t", makeTime(2025,6,2,9), hours(1));
    OneTimeEvent e2("2","d","t", makeTime(2025,6,5,9), hours(1));
    OneTimeEvent e3("3","d","t", makeTime(2025,6,9,9), hours(1));
    m.addEvent(e1); m.addEvent(e2); m.addEvent(e3);
    int n = m.removeEventsInWeek(makeTime(2025,6,3,0));
    assert(n == 2);
    auto left = m.getEventsInWeek(makeTime(2025,6,3,0));
    assert(left.empty());
}

static void testModelRemoveBefore()
{
    Model m;
    OneTimeEvent e1("1","d","t", makeTime(2025,6,1,9), hours(1));
    OneTimeEvent e2("2","d","t", makeTime(2025,6,2,9), hours(1));
    OneTimeEvent e3("3","d","t", makeTime(2025,6,3,9), hours(1));
    m.addEvent(e1); m.addEvent(e2); m.addEvent(e3);
    int n = m.removeEventsBefore(makeTime(2025,6,2,12));
    assert(n == 2);
    auto list = m.getEvents(-1, makeTime(2025,6,4,0));
    assert(list.size() == 1 && list[0].getId() == "3");
}

static void testModelGetEventsLimit()
{
    Model m;
    OneTimeEvent e1("1","d1","t1", makeTime(2025,1,1,8), hours(1));
    OneTimeEvent e2("2","d2","t2", makeTime(2025,1,2,8), hours(1));
    OneTimeEvent e3("3","d3","t3", makeTime(2025,1,3,8), hours(1));
    m.addEvent(e1); m.addEvent(e2); m.addEvent(e3);
    auto limited = m.getEvents(2, makeTime(2025,1,4,0));
    assert(limited.size() == 2);
    auto cutoff = m.getEvents(-1, makeTime(2025,1,2,12));
    assert(cutoff.size() == 2);
}

static void testModelWithDailyRecurring()
{
    Model m;
    auto start = makeTime(2025,6,1,9);
    auto rec = std::make_shared<DailyRecurrence>(start, 1);
    string id("R");
    string desc("d");
    string title("t");
    RecurringEvent r(id, desc, title, start, hours(1), rec);
    OneTimeEvent o("O","d","t", makeTime(2025,6,2,9), hours(1));
    m.addEvent(o);
    m.addEvent(r);

    auto next = m.getNextEvent();
    assert(next.getId() == "R");

    auto evs = m.getEvents(-1, makeTime(2025,6,3,0));
    assert(evs.size() == 2);
    assert(evs[0].getId() == "R");
    assert(evs[1].getId() == "O");
}

static void testNextNWithRecurring()
{
    Model m;
    auto now = chrono::system_clock::now();
    auto start = now + hours(1);
    auto rec = std::make_shared<DailyRecurrence>(start, 1);
    RecurringEvent wake("W","wake","Wake", start, hours(1), rec);
    OneTimeEvent ball("B","play","Ball", start + hours(24*4) + hours(4), hours(2));
    m.addEvent(wake);
    m.addEvent(ball);

    auto next = m.getNextEvent();
    assert(next.getId() == "W");

    auto list = m.getNextNEvents(6);
    assert(list.size() == 6);
    for(int i=0;i<5;i++)
        assert(list[i].getTime() == start + hours(24*i));
    assert(list[5].getId() == "B");
}

static void testNextNSkipsPast()
{
    Model m;
    auto now = chrono::system_clock::now();
    auto pastStart = now - chrono::hours(24 * 2) - chrono::hours(5); // two days and 5 hours ago
    auto rec = std::make_shared<DailyRecurrence>(pastStart, 1);
    RecurringEvent past("R","d","t", pastStart, hours(1), rec);
    auto futureTime = now + chrono::hours(2);
    OneTimeEvent upcoming("F","d","t", futureTime, hours(1));
    m.addEvent(past);
    m.addEvent(upcoming);

    auto list = m.getNextNEvents(5);
    assert(!list.empty());
    // First event should be the upcoming one-time event in two hours
    assert(list.front().getId() == "F");
    for (const auto &e : list)
    {
        assert(e.getTime() > now);
    }
}

static void testEventsOnDay()
{
    Model m;
    OneTimeEvent e1("1","d","t", makeTime(2025,6,1,8), hours(1));
    OneTimeEvent e2("2","d","t", makeTime(2025,6,1,12), hours(1));
    OneTimeEvent e3("3","d","t", makeTime(2025,6,2,9), hours(1));
    m.addEvent(e1); m.addEvent(e2); m.addEvent(e3);
    auto evs = m.getEventsOnDay(makeTime(2025,6,1,0));
    assert(evs.size() == 2);
    assert(evs[0].getId() == "1");
    assert(evs[1].getId() == "2");
}

static void testEventsInWeek()
{
    Model m;
    OneTimeEvent e1("1","d","t", makeTime(2025,6,2,9), hours(1)); // Monday
    OneTimeEvent e2("2","d","t", makeTime(2025,6,5,9), hours(1)); // Thursday
    OneTimeEvent e3("3","d","t", makeTime(2025,6,9,9), hours(1)); // next Monday
    m.addEvent(e1); m.addEvent(e2); m.addEvent(e3);
    auto evs = m.getEventsInWeek(makeTime(2025,6,3,0));
    assert(evs.size() == 2);
    assert(evs[0].getId() == "1");
    assert(evs[1].getId() == "2");
}

static void testEventsInMonth()
{
    Model m;
    OneTimeEvent e1("1","d","t", makeTime(2025,6,2,9), hours(1));
    OneTimeEvent e2("2","d","t", makeTime(2025,7,1,9), hours(1));
    OneTimeEvent e3("3","d","t", makeTime(2025,6,20,9), hours(1));
    m.addEvent(e1); m.addEvent(e2); m.addEvent(e3);
    auto evs = m.getEventsInMonth(makeTime(2025,6,10,0));
    assert(evs.size() == 2);
    assert(evs[0].getId() == "1");
    assert(evs[1].getId() == "3");
}

static void testRecurringInDayWeekMonth()
{
    Model m;
    auto start = makeTime(2025,6,1,9);
    auto pat = std::make_shared<DailyRecurrence>(start, 1);
    RecurringEvent r("R","d","t", start, hours(1), pat);
    OneTimeEvent o("O","d","t", makeTime(2025,6,3,10), hours(1));
    m.addEvent(r);
    m.addEvent(o);

    auto day = makeTime(2025,6,3,0);
    auto d = m.getEventsOnDay(day);
    assert(d.size() == 2);
    assert(d[0].getId() == "R");
    assert(d[1].getId() == "O");

    auto w = m.getEventsInWeek(day);
    assert(w.size() == 8); // 7 occurrences + 1 one-time

    auto mo = m.getEventsInMonth(day);
    assert(mo.size() == 31); // 30 daily occurrences + 1 one-time
}

static void testEventsTimeZones()
{
    const char *prevPtr = getenv("TZ");
    std::string prev = prevPtr ? std::string(prevPtr) : std::string();
    bool hadPrev = prevPtr != nullptr;
    // Use a zone far ahead of UTC so local midnight is well before UTC midnight
    setenv("TZ", "Australia/Sydney", 1);
    tzset();

    Model m({});
    using TimeUtils::parseTimePoint;
    using TimeUtils::parseDate;

    // Event just after local midnight
    auto evTime = parseTimePoint("2025-06-01 00:30");
    OneTimeEvent e("1","d","t", evTime, hours(1));
    m.addEvent(e);

    auto queryDay = parseDate("2025-06-01");
    auto d = m.getEventsOnDay(queryDay);
    assert(d.size() == 1);
    auto w = m.getEventsInWeek(queryDay);
    assert(w.size() == 1);
    auto mo = m.getEventsInMonth(queryDay);
    assert(mo.size() == 1);

    // Previous day should have no events
    auto prevDay = parseDate("2025-05-31");
    auto prevList = m.getEventsOnDay(prevDay);
    assert(prevList.empty());

    if (hadPrev)
        setenv("TZ", prev.c_str(), 1);
    else
        unsetenv("TZ");
    tzset();
}

static void testEventsChicagoTimeZone()
{
    const char *prevPtr = getenv("TZ");
    std::string prev = prevPtr ? std::string(prevPtr) : std::string();
    bool hadPrev = prevPtr != nullptr;

    setenv("TZ", "America/Chicago", 1);
    tzset();

    Model m({});
    using TimeUtils::parseTimePoint;
    using TimeUtils::parseDate;

    auto evTime = parseTimePoint("2025-06-01 00:30");
    OneTimeEvent e("1","d","t", evTime, hours(1));
    m.addEvent(e);

    auto queryDay = parseDate("2025-06-01");
    auto d = m.getEventsOnDay(queryDay);
    assert(d.size() == 1);
    auto w = m.getEventsInWeek(queryDay);
    assert(w.size() == 1);
    auto mo = m.getEventsInMonth(queryDay);
    assert(mo.size() == 1);

    auto prevDay = parseDate("2025-05-31");
    auto prevList = m.getEventsOnDay(prevDay);
    assert(prevList.empty());

    if (hadPrev)
        setenv("TZ", prev.c_str(), 1);
    else
        unsetenv("TZ");
    tzset();
}

int main()
{
    testModelAddAndRetrieve();
    testModelRemove();
    testModelRemoveAll();
    testModelRemoveDay();
    testModelRemoveWeek();
    testModelRemoveBefore();
    testModelGetEventsLimit();
    testModelWithDailyRecurring();
    testNextNWithRecurring();
    testNextNSkipsPast();
    testEventsOnDay();
    testEventsInWeek();
    testEventsInMonth();
    testRecurringInDayWeekMonth();
    testEventsTimeZones();
    testEventsChicagoTimeZone();
    cout << "Model tests passed\n";
    return 0;
}
