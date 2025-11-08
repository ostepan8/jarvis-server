#include "MonthlyRecurrence.h"
#include <algorithm>

namespace {

bool isLeap(int year) {
    return (year % 4 == 0 && year % 100 != 0) || (year % 400 == 0);
}

int daysInMonth(int year, int month) {
    static const int days[] = {31,28,31,30,31,30,31,31,30,31,30,31};
    if (month == 2)
        return days[1] + (isLeap(year) ? 1 : 0);
    return days[month-1];
}

std::tm to_tm(std::chrono::system_clock::time_point tp) {
    time_t t = std::chrono::system_clock::to_time_t(tp);
    std::tm tm_buf;
#if defined(_MSC_VER)
    gmtime_s(&tm_buf, &t);
#else
    gmtime_r(&t, &tm_buf);
#endif
    return tm_buf;
}

std::chrono::system_clock::time_point from_tm(const std::tm& tm_buf) {
    std::tm temp = tm_buf;
#if defined(_MSC_VER)
    time_t t = _mkgmtime(&temp);
#else
    time_t t = timegm(&temp);
#endif
    return std::chrono::system_clock::from_time_t(t);
}

}

MonthlyRecurrence::MonthlyRecurrence(std::chrono::system_clock::time_point start,
                                     int interval,
                                     int max,
                                     std::chrono::system_clock::time_point endDate)
    : startingPoint(start),
      repeatingInterval(interval),
      maxOccurrences(max),
      endDate(endDate) {}

std::vector<std::chrono::system_clock::time_point>
MonthlyRecurrence::getNextNOccurrences(std::chrono::system_clock::time_point after, int n) const {
    std::vector<std::chrono::system_clock::time_point> result;
    if (n <= 0)
        return result;

    auto start_tm = to_tm(startingPoint);
    long long index = 0;
    // find first index with occurrence > after
    while (true) {
        std::tm cand_tm = start_tm;
        int totalMonths = start_tm.tm_mon + index * repeatingInterval;
        cand_tm.tm_year += totalMonths / 12;
        cand_tm.tm_mon = totalMonths % 12;
        int days = daysInMonth(cand_tm.tm_year + 1900, cand_tm.tm_mon + 1);
        if (cand_tm.tm_mday > days)
            cand_tm.tm_mday = days;
        auto candidate = from_tm(cand_tm);
        if (candidate > after || candidate > endDate)
            break;
        ++index;
        if (maxOccurrences != -1 && index >= maxOccurrences)
            return result;
    }

    while (static_cast<int>(result.size()) < n) {
        std::tm cand_tm = start_tm;
        int totalMonths = start_tm.tm_mon + index * repeatingInterval;
        cand_tm.tm_year += totalMonths / 12;
        cand_tm.tm_mon = totalMonths % 12;
        int days = daysInMonth(cand_tm.tm_year + 1900, cand_tm.tm_mon + 1);
        if (cand_tm.tm_mday > days)
            cand_tm.tm_mday = days;
        auto candidate = from_tm(cand_tm);
        if (candidate > endDate)
            break;
        if (maxOccurrences != -1 && index >= maxOccurrences)
            break;
        if (candidate > after)
            result.push_back(candidate);
        ++index;
    }

    return result;
}

bool MonthlyRecurrence::isDueOn(std::chrono::system_clock::time_point date) const {
    auto prev = date - std::chrono::seconds(1);
    auto next = getNextNOccurrences(prev, 1);
    return !next.empty() && next.front() == date;
}
