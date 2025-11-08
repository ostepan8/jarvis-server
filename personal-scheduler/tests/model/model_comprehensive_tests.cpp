#include <cassert>
#include <iostream>
#include "../../model/Model.h"
#include "../../model/OneTimeEvent.h"
#include "../../model/RecurringEvent.h"
#include "../../model/recurrence/DailyRecurrence.h"
#include "../../model/recurrence/WeeklyRecurrence.h"
#include "../test_utils.h"
#include <memory>

using namespace std;
using namespace chrono;

static void testAddMixedEvents()
{
    Model m;
    auto pat = std::make_shared<FakePattern>();
    auto now = chrono::system_clock::now();
    OneTimeEvent o1("O1","d1","t1", now + hours(1), hours(1));
    OneTimeEvent o2("O2","d2","t2", now + hours(2), hours(1));
    string r1id = "R1"; string r1d = "dr1"; string r1t = "tr1";
    string r2id = "R2"; string r2d = "dr2"; string r2t = "tr2";
    RecurringEvent r1(r1id, r1d, r1t, now + hours(3), hours(1), pat);
    RecurringEvent r2(r2id, r2d, r2t, now + hours(4), hours(1), pat);

    m.addEvent(r2); // add out of order on purpose
    m.addEvent(o1);
    m.addEvent(r1);
    m.addEvent(o2);

    auto evs = m.getEvents(-1, now + hours(5));
    assert(evs.size() == 4);
    assert(evs[0].getId() == "O1");
    assert(evs[1].getId() == "O2");
    assert(evs[2].getId() == "R1");
    assert(evs[3].getId() == "R2");

    Event next = m.getNextEvent();
    assert(next.getId() == "O1");
}

static void testRemoveMixedEvents()
{
    Model m;
    auto pat = std::make_shared<FakePattern>();
    OneTimeEvent o1("O1","d1","t1", makeTime(2025,6,1,8), hours(1));
    OneTimeEvent o2("O2","d2","t2", makeTime(2025,6,2,8), hours(1));
    string r1id = "R1"; string r1d = "dr1"; string r1t = "tr1";
    string r2id = "R2"; string r2d = "dr2"; string r2t = "tr2";
    RecurringEvent r1(r1id, r1d, r1t, makeTime(2025,6,2,9), hours(1), pat);
    RecurringEvent r2(r2id, r2d, r2t, makeTime(2025,6,3,9), hours(1), pat);
    m.addEvent(o1); m.addEvent(o2); m.addEvent(r1); m.addEvent(r2);

    assert(m.removeEvent("R1"));
    assert(!m.removeEvent("NOPE"));
    assert(m.removeEvent(o2));

    auto evs = m.getEvents(-1, makeTime(2025,6,4,0));
    assert(evs.size() == 2);
    assert(evs[0].getId() == "O1");
    assert(evs[1].getId() == "R2");
}

static void testNextEventThrows()
{
    Model m;
    bool threw = false;
    try { m.getNextEvent(); }
    catch(const runtime_error&) { threw = true; }
    assert(threw);
}

static void testGetEventsLimitAndCutoff()
{
    Model m;
    auto pat = std::make_shared<FakePattern>();
    OneTimeEvent e1("E1","d","t", makeTime(2025,6,1,8), hours(1));
    string r1id = "R1"; string r1d = "d1"; string r1t = "t1";
    string r2id = "R2"; string r2d = "d2"; string r2t = "t2";
    RecurringEvent r1(r1id, r1d, r1t, makeTime(2025,6,1,9), hours(1), pat);
    OneTimeEvent e2("E2","d","t", makeTime(2025,6,2,8), hours(1));
    RecurringEvent r2(r2id, r2d, r2t, makeTime(2025,6,3,8), hours(1), pat);
    OneTimeEvent e3("E3","d","t", makeTime(2025,6,4,8), hours(1));
    m.addEvent(e3); m.addEvent(r2); m.addEvent(e2); m.addEvent(r1); m.addEvent(e1);

    auto limited = m.getEvents(3, makeTime(2025,6,3,0));
    assert(limited.size() == 3);
    assert(limited[0].getId() == "E1");
    assert(limited[1].getId() == "R1");
    assert(limited[2].getId() == "E2");

    auto cutoff = m.getEvents(-1, makeTime(2025,6,2,12));
    assert(cutoff.size() == 3);
    assert(cutoff[2].getId() == "E2");
}

static void testDuplicatesRejected()
{
    Model m;
    OneTimeEvent a("A","d","t", makeTime(2025,6,1,8), hours(1));
    OneTimeEvent a2("A","d2","t2", makeTime(2025,6,1,9), hours(1));

    assert(m.addEvent(a));
    assert(!m.addEvent(a2));

    auto evs = m.getEvents(-1, makeTime(2025,6,2,0));
    assert(evs.size() == 1);
    assert(evs[0].getId() == "A");
}

int main()
{
    testAddMixedEvents();
    testRemoveMixedEvents();
    testNextEventThrows();
    testGetEventsLimitAndCutoff();
    testDuplicatesRejected();
    cout << "Comprehensive model tests passed\n";
    return 0;
}

