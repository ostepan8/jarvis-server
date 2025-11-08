#pragma once
#include <vector>
#include <chrono>
#include <string>
using namespace std;

// Base interface for all recurrence patterns used by `RecurringEvent`.
// Implementations provide scheduling logic for daily, weekly, monthly or
// yearly repetition rules.
class RecurrencePattern
{
public:
    virtual vector<chrono::system_clock::time_point> getNextNOccurrences(chrono::system_clock::time_point after,
                                                                         int n) const = 0;
    virtual bool isDueOn(chrono::system_clock::time_point date) const = 0;
    virtual std::string type() const = 0;
    virtual ~RecurrencePattern() = default;
};