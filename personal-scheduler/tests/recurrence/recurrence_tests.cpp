#include <cassert>
#include <iostream>
#include <vector>
#include <ctime>
#include "../../model/recurrence/DailyRecurrence.h"
#include "../../model/recurrence/WeeklyRecurrence.h"
#include "../../model/recurrence/MonthlyRecurrence.h"
#include "../../model/recurrence/YearlyRecurrence.h"
#include "../../utils/WeekDay.h"
#include "../../utils/TimeUtils.h"

using namespace std;
using namespace chrono;

static system_clock::time_point makeTime(int year, int month, int day, int hour=0, int min=0, int sec=0)
{
    std::tm tm{};
    tm.tm_year = year - 1900;
    tm.tm_mon = month - 1;
    tm.tm_mday = day;
    tm.tm_hour = hour;
    tm.tm_min = min;
    tm.tm_sec = sec;
    tm.tm_isdst = -1;
    time_t tt = timegm(&tm);
    return system_clock::from_time_t(tt);
}

void testDailyRecurrence()
{
    auto start = makeTime(2025, 6, 1, 9); // 2025-06-01 09:00
    DailyRecurrence rec(start, 2, 5);     // every 2 days, max 5 times

    auto all = rec.getNextNOccurrences(start - seconds(1), 10);
    assert(all.size() == 5);
    assert(all[0] == start);
    assert(all[1] == start + hours(48));
    assert(all[2] == start + hours(96));

    assert(rec.isDueOn(start + hours(48*2)));
    assert(!rec.isDueOn(start + hours(24)));
    assert(!rec.isDueOn(start + hours(48*5))); // beyond max occurrences

    auto partial = rec.getNextNOccurrences(start + hours(48*2), 2);
    assert(partial.size() == 2);
    assert(partial[0] == start + hours(48*3));
    assert(partial[1] == start + hours(48*4));
}

void testWeeklyRecurrence()
{
    auto start = makeTime(2025, 6, 2, 9); // Monday
    vector<Weekday> days{Weekday::Monday, Weekday::Wednesday};
    WeeklyRecurrence rec(start, days, 1, 5); // weekly on Mon/Wed, max 5

    auto all = rec.getNextNOccurrences(start - seconds(1), 10);
    assert(all.size() == 5);
    assert(all[0] == start);
    assert(all[1] == makeTime(2025,6,4,9));
    assert(all[2] == makeTime(2025,6,9,9));
    assert(all[4] == makeTime(2025,6,16,9));

    assert(rec.isDueOn(makeTime(2025,6,9,9)));
    assert(!rec.isDueOn(makeTime(2025,6,10,9)));

    auto partial = rec.getNextNOccurrences(makeTime(2025,6,9,10), 2);
    assert(partial.size() == 2);
    assert(partial[0] == makeTime(2025,6,11,9));
    assert(partial[1] == makeTime(2025,6,16,9));

    auto none = rec.getNextNOccurrences(makeTime(2025,6,16,9), 1);
    assert(none.empty());
}

void testMonthlyRecurrence()
{
    auto start = makeTime(2024,1,31,9);
    MonthlyRecurrence rec(start, 1, 4); // every month

    auto all = rec.getNextNOccurrences(start - seconds(1), 5);
    assert(all.size() == 4);
    assert(all[0] == makeTime(2024,1,31,9));
    // Feb 2024 has 29 days (leap year)
    assert(all[1] == makeTime(2024,2,29,9));
    assert(all[2] == makeTime(2024,3,31,9));
    // April has 30 days -> adjust
    assert(all[3] == makeTime(2024,4,30,9));

    assert(rec.isDueOn(makeTime(2024,4,30,9)));
    assert(!rec.isDueOn(makeTime(2024,4,29,9)));
}

void testYearlyRecurrence()
{
    auto start = makeTime(2024,2,29,10);
    YearlyRecurrence rec(start, 1, 5);

    auto all = rec.getNextNOccurrences(start - seconds(1), 5);
    assert(all.size() == 5);
    assert(all[0] == makeTime(2024,2,29,10));
    assert(all[1] == makeTime(2025,2,28,10));
    assert(all[2] == makeTime(2026,2,28,10));
    assert(all[3] == makeTime(2027,2,28,10));
    assert(all[4] == makeTime(2028,2,29,10));

    assert(rec.isDueOn(makeTime(2025,2,28,10)));
    assert(!rec.isDueOn(makeTime(2025,2,27,10)));
}

void testDailyRecurrenceDST()
{
    const char* prevPtr = getenv("TZ");
    std::string prev = prevPtr ? std::string(prevPtr) : std::string();
    bool hadPrev = prevPtr != nullptr;

    setenv("TZ", "America/New_York", 1);
    tzset();

    auto start = TimeUtils::parseTimePoint("2025-03-08 09:00");
    DailyRecurrence rec(start, 1, 3);

    auto occ = rec.getNextNOccurrences(start - seconds(1), 3);
    assert(TimeUtils::formatTimePoint(occ[0]) == "2025-03-08 09:00");
    assert(TimeUtils::formatTimePoint(occ[1]) == "2025-03-09 10:00");
    assert(TimeUtils::formatTimePoint(occ[2]) == "2025-03-10 10:00");

    if (hadPrev)
        setenv("TZ", prev.c_str(), 1);
    else
        unsetenv("TZ");
    tzset();
}

void testRecurringCrossTimeZones()
{
    const char* prevPtr = getenv("TZ");
    std::string prev = prevPtr ? std::string(prevPtr) : std::string();
    bool hadPrev = prevPtr != nullptr;

    setenv("TZ", "America/New_York", 1);
    tzset();
    auto start = TimeUtils::parseTimePoint("2025-03-08 09:00");
    DailyRecurrence rec(start, 1, 3);
    auto occ = rec.getNextNOccurrences(start - seconds(1), 3);

    setenv("TZ", "Asia/Tokyo", 1);
    tzset();
    assert(TimeUtils::formatTimePoint(occ[0]) == "2025-03-08 23:00");
    assert(TimeUtils::formatTimePoint(occ[1]) == "2025-03-09 23:00");
    assert(TimeUtils::formatTimePoint(occ[2]) == "2025-03-10 23:00");

    setenv("TZ", "America/Mexico_City", 1);
    tzset();
    assert(TimeUtils::formatTimePoint(occ[0]) == "2025-03-08 08:00");
    assert(TimeUtils::formatTimePoint(occ[1]) == "2025-03-09 08:00");
    assert(TimeUtils::formatTimePoint(occ[2]) == "2025-03-10 08:00");

    if (hadPrev)
        setenv("TZ", prev.c_str(), 1);
    else
        unsetenv("TZ");
    tzset();
}

int main()
{
    testDailyRecurrence();
    testWeeklyRecurrence();
    testMonthlyRecurrence();
    testYearlyRecurrence();
    testDailyRecurrenceDST();
    testRecurringCrossTimeZones();
    std::cout << "All recurrence tests passed\n";
    return 0;
}

