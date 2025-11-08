#include "DailyRecurrence.h"

DailyRecurrence::DailyRecurrence(
    chrono::system_clock::time_point start,
    int interval,
    int maxOccurrences,
    chrono::system_clock::time_point endDate)
    : startingPoint(start),
      repeatingInterval(interval),
      maxOccurrences(maxOccurrences),
      endDate(endDate)
{
}

vector<chrono::system_clock::time_point> DailyRecurrence::getNextNOccurrences(
    chrono::system_clock::time_point after, int n) const
{
    vector<chrono::system_clock::time_point> result;
    if (n <= 0)
    {
        return result;
    }

    auto dayDur = chrono::hours(24 * repeatingInterval);

    // Determine the first occurrence index
    long long index = 0;
    if (after > startingPoint)
    {
        auto diff = after - startingPoint;
        auto diffDays = chrono::duration_cast<chrono::hours>(diff).count() / 24;
        index = diffDays / repeatingInterval + 1;
    }

    int occurrencesGenerated = 0;
    while (occurrencesGenerated < n)
    {
        auto nextTime = startingPoint + dayDur * index;
        if (nextTime > endDate)
            break;
        if (maxOccurrences != -1 && index >= maxOccurrences)
            break;
        if (nextTime > after)
        {
            result.push_back(nextTime);
            ++occurrencesGenerated;
        }
        ++index;
    }

    return result;
}

bool DailyRecurrence::isDueOn(chrono::system_clock::time_point date) const
{
    if (date < startingPoint || date > endDate)
    {
        return false;
    }

    auto diff = date - startingPoint;
    auto diffHours = chrono::duration_cast<chrono::hours>(diff).count();
    if (diffHours % (24 * repeatingInterval) != 0)
    {
        return false;
    }
    auto index = diffHours / (24 * repeatingInterval);
    if (maxOccurrences != -1 && index >= maxOccurrences)
    {
        return false;
    }
    return true;
}