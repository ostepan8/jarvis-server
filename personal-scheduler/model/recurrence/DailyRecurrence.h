#include "RecurrencePattern.h"
#include <chrono>
#include <vector>
#include <string>

// This pattern handles events that repeat every fixed number of days.
// Use `DailyRecurrence` when an activity follows a simple daily cadence.
// Example: every 7 days I want to order Nandos.
// Example: every other day I want to go to the gym.
class DailyRecurrence : public RecurrencePattern
{
private:
    // First date/time of the recurrence (UTC)
    chrono::system_clock::time_point startingPoint;
    int repeatingInterval;                          // This is the x in every x days.
    int maxOccurrences;                             // optional: stop after N times (-1 = unlimited)
    chrono::system_clock::time_point endDate;       // optional: stop by a certain date
public:
    DailyRecurrence(chrono::system_clock::time_point start,
                    int interval,
                    int maxOccurrences = -1,
                    chrono::system_clock::time_point endDate = chrono::system_clock::time_point::max());

    std::vector<chrono::system_clock::time_point> getNextNOccurrences(
        chrono::system_clock::time_point after, int n) const override;

    bool isDueOn(chrono::system_clock::time_point date) const override;

    std::string type() const override { return "daily"; }
    int getInterval() const { return repeatingInterval; }
    int getMaxOccurrences() const { return maxOccurrences; }
    chrono::system_clock::time_point getEndDate() const { return endDate; }

    ~DailyRecurrence() override = default;
};
