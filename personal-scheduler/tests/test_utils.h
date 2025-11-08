#pragma once
#include <chrono>
#include <ctime>
#include "../view/View.h"
#include "../model/ReadOnlyModel.h"
#include "../model/recurrence/RecurrencePattern.h"

inline std::chrono::system_clock::time_point makeTime(int year, int month, int day,
                                                      int hour=0, int min=0, int sec=0)
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
    return std::chrono::system_clock::from_time_t(tt);
}

class StubView : public View
{
public:
    explicit StubView(const ReadOnlyModel &m) : View(m) {}
    void render() override {}
    void renderEvents(const std::vector<Event>&) override {}
};

class FakePattern : public RecurrencePattern
{
public:
    mutable bool isDueCalled = false;
    mutable bool getNextCalled = false;
    bool dueResult = false;
    std::vector<std::chrono::system_clock::time_point> nextResult;

    std::vector<std::chrono::system_clock::time_point> getNextNOccurrences(
            std::chrono::system_clock::time_point, int) const override
    {
        getNextCalled = true;
        return nextResult;
    }
    bool isDueOn(std::chrono::system_clock::time_point) const override
    {
        isDueCalled = true;
        return dueResult;
    }

    std::string type() const override { return "fake"; }
};
