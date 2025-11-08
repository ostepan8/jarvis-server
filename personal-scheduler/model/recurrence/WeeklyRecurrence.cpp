#include "WeeklyRecurrence.h"
#include "../../utils/WeekDay.h"
#include <algorithm>

namespace
{
Weekday weekdayFromTimePoint(chrono::system_clock::time_point tp)
{
    time_t t_c = chrono::system_clock::to_time_t(tp);
    tm tm_buf;
#if defined(_MSC_VER)
    localtime_s(&tm_buf, &t_c);
#else
    localtime_r(&t_c, &tm_buf);
#endif
    return static_cast<Weekday>(tm_buf.tm_wday);
}
}

WeeklyRecurrence::WeeklyRecurrence(
    chrono::system_clock::time_point start,
    vector<Weekday> daysOfTheWeek,
    int repeatingInterval,
    int maxOccurrences,
    chrono::system_clock::time_point endDate)
    : startingPoint(start),
      daysOfTheWeek(std::move(daysOfTheWeek)),
      repeatingInterval(repeatingInterval),
      maxOccurrences(maxOccurrences),
      endDate(endDate)
{
    std::sort(this->daysOfTheWeek.begin(), this->daysOfTheWeek.end());
}

vector<chrono::system_clock::time_point> WeeklyRecurrence::getNextNOccurrences(
    chrono::system_clock::time_point after, int n) const
{
    vector<chrono::system_clock::time_point> result;
    if (n <= 0)
        return result;

    auto day = chrono::hours(24);

    // base date at midnight
    auto daysSinceEpoch = chrono::duration_cast<chrono::hours>(startingPoint.time_since_epoch()).count() / 24;
    auto startDayPoint = chrono::system_clock::time_point{chrono::hours(daysSinceEpoch * 24)};
    auto timeOfDay = startingPoint - startDayPoint;
    Weekday startWeekday = weekdayFromTimePoint(startingPoint);

    long long weekIndex = 0;
    if (after > startingPoint)
    {
        auto diff = after - startDayPoint;
        auto diffWeeks = chrono::duration_cast<chrono::hours>(diff).count() / (24 * 7);
        weekIndex = diffWeeks / repeatingInterval;
    }

    long long occurrencesChecked = weekIndex * static_cast<long long>(daysOfTheWeek.size());
    int generated = 0;

    while (generated < n)
    {
        for (Weekday w : daysOfTheWeek)
        {
            long long offsetDays = weekIndex * repeatingInterval * 7 + (static_cast<int>(w) - static_cast<int>(startWeekday));
            auto candidate = startDayPoint + chrono::hours(24 * offsetDays) + timeOfDay;

            if (candidate < startingPoint)
                continue;

            if (candidate > endDate)
                return result;

            if (maxOccurrences != -1 && occurrencesChecked >= maxOccurrences)
                return result;

            if (candidate > after)
            {
                result.push_back(candidate);
                ++generated;
                if (generated >= n)
                    return result;
            }

            ++occurrencesChecked;
        }
        ++weekIndex;
    }

    return result;
}

bool WeeklyRecurrence::isDueOn(chrono::system_clock::time_point date) const
{
    auto prevMoment = date - chrono::seconds(1);
    auto next = getNextNOccurrences(prevMoment, 1);
    return !next.empty() && next.front() == date;
}