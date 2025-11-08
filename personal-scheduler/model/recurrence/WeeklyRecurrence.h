#include "RecurrencePattern.h"
#include <vector>
#include <chrono>
#include <algorithm>
#include <string>
#include "../../utils/WeekDay.h"
// This pattern handles the "every X weeks on specific days" use case.
// Use `WeeklyRecurrence` when an event repeats on one or more weekdays
// with a weekly interval.
// For example, every week on Tuesday and Thursday I have Object Oriented Design class.
// For example, every 2 weeks I go to Church on Sunday.
class WeeklyRecurrence : public RecurrencePattern
{
private:
    // First date/time of the recurrence (UTC)
    chrono::system_clock::time_point startingPoint;
    vector<Weekday> daysOfTheWeek;                  // Which days of the week should this event run?
    int repeatingInterval;                          // This is the x in every x weeks.
    int maxOccurrences;                             // optional: stop after N times (-1 = unlimited)
    chrono::system_clock::time_point endDate;       // optional: stop by a certain date
public:
    WeeklyRecurrence(chrono::system_clock::time_point start,
                     vector<Weekday> daysOfTheWeek,
                     int repeatingInterval,
                     int maxOccurrences = -1,
                     chrono::system_clock::time_point endDate = chrono::system_clock::time_point::max());

    std::vector<chrono::system_clock::time_point> getNextNOccurrences(
        chrono::system_clock::time_point after, int n) const override;

    bool isDueOn(chrono::system_clock::time_point date) const override;

    std::string type() const override { return "weekly"; }
    int getInterval() const { return repeatingInterval; }
    const std::vector<Weekday> &getDaysOfWeek() const { return daysOfTheWeek; }
    int getMaxOccurrences() const { return maxOccurrences; }
    chrono::system_clock::time_point getEndDate() const { return endDate; }

    ~WeeklyRecurrence() override = default;
};
