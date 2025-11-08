#include <cassert>
#include <iostream>
#include <vector>
#include "../../model/OneTimeEvent.h"
#include "../../model/RecurringEvent.h"
#include "../../model/recurrence/DailyRecurrence.h"
#include "../../model/recurrence/WeeklyRecurrence.h"
#include "../../utils/WeekDay.h"
#include "../../scheduler/ScheduledTask.h"
#include "../test_utils.h"
#include <memory>

using namespace std;
using namespace chrono;

static void testOneTimeEvent()
{
    auto tp = makeTime(2025,1,1,12);
    OneTimeEvent e("1","desc","title", tp, hours(2));
    assert(e.getId() == "1");
    assert(e.getDescription() == "desc");
    assert(e.getTitle() == "title");
    assert(e.getTime() == tp);
    assert(e.getDuration() == hours(2));
}

static void testRecurringEventDelegation()
{
    auto pat = std::make_shared<FakePattern>();
    pat->dueResult = true;
    pat->nextResult.push_back(makeTime(2030,1,1,8));
    string id = "R";
    string desc = "d";
    string title = "t";
    RecurringEvent ev(id, desc, title, makeTime(2030,1,1,8), hours(1), pat);
    assert(ev.isDueOn(makeTime(2030,1,1,8)));
    assert(pat->isDueCalled);
    auto nxt = ev.getNextNOccurrences(makeTime(2029,12,31,0), 1);
    assert(pat->getNextCalled);
    assert(nxt.size() == 1 && nxt[0] == makeTime(2030,1,1,8));
}

static void testScheduledTaskCustomTimes()
{
    auto exec = makeTime(2025,6,1,10);
    auto notify = exec - minutes(5);
    ScheduledTask t("X","d","t", exec, hours(1), std::vector<std::chrono::system_clock::time_point>{notify},
                    [](){}, [](){});
    assert(t.getNextNotifyTime() == notify);
    ScheduledTask t2("Y","d","t", exec, hours(1), std::vector<std::chrono::system_clock::duration>{minutes(15)}, [](){}, [](){});
    assert(t2.getNextNotifyTime() == exec - minutes(15));

    ScheduledTask tmulti("Z","d","t", exec, hours(1), std::vector<std::chrono::system_clock::duration>{hours(1), minutes(30)}, [](){}, [](){});
    assert(tmulti.getNextNotifyTime() == exec - hours(1));
    tmulti.markNotificationSent();
    assert(tmulti.getNextNotifyTime() == exec - minutes(30));
}

int main()
{
    testOneTimeEvent();
    testRecurringEventDelegation();
    testScheduledTaskCustomTimes();
    cout << "Event tests passed\n";
    return 0;
}
