#pragma once
#include "RecurrencePattern.h"
#include <chrono>
#include <vector>
#include <string>

// Handles events that repeat every fixed number of months.
// Use `MonthlyRecurrence` when you need a monthly cadence where the day
// of the month matters. For example, paying rent on the 1st of every month
// or a meeting on the last day of the month.
class MonthlyRecurrence : public RecurrencePattern {
private:
    std::chrono::system_clock::time_point startingPoint;
    int repeatingInterval;
    int maxOccurrences;
    std::chrono::system_clock::time_point endDate;
public:
    MonthlyRecurrence(std::chrono::system_clock::time_point start,
                      int interval,
                      int maxOccurrences = -1,
                      std::chrono::system_clock::time_point endDate = std::chrono::system_clock::time_point::max());

    std::vector<std::chrono::system_clock::time_point> getNextNOccurrences(
        std::chrono::system_clock::time_point after, int n) const override;

    bool isDueOn(std::chrono::system_clock::time_point date) const override;

    std::string type() const override { return "monthly"; }
    int getInterval() const { return repeatingInterval; }
    int getMaxOccurrences() const { return maxOccurrences; }
    std::chrono::system_clock::time_point getEndDate() const { return endDate; }

    ~MonthlyRecurrence() override = default;
};
