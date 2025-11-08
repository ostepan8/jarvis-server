#pragma once
#include "RecurrencePattern.h"
#include <chrono>
#include <vector>
#include <string>

// Handles events that repeat every fixed number of years.
// Use `YearlyRecurrence` for anniversaries or other annual events.
// This implementation automatically adjusts for leap years when
// the initial date falls on February 29th.
class YearlyRecurrence : public RecurrencePattern {
private:
    std::chrono::system_clock::time_point startingPoint;
    int repeatingInterval;
    int maxOccurrences;
    std::chrono::system_clock::time_point endDate;
public:
    YearlyRecurrence(std::chrono::system_clock::time_point start,
                     int interval,
                     int maxOccurrences = -1,
                     std::chrono::system_clock::time_point endDate = std::chrono::system_clock::time_point::max());

    std::vector<std::chrono::system_clock::time_point> getNextNOccurrences(
        std::chrono::system_clock::time_point after, int n) const override;

    bool isDueOn(std::chrono::system_clock::time_point date) const override;

    std::string type() const override { return "yearly"; }
    int getInterval() const { return repeatingInterval; }
    int getMaxOccurrences() const { return maxOccurrences; }
    std::chrono::system_clock::time_point getEndDate() const { return endDate; }

    ~YearlyRecurrence() override = default;
};
