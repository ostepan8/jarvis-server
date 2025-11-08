#include <cassert>
#include <cstdio>
#include <memory>
#include "../../database/SQLiteScheduleDatabase.h"
#include "../../model/Model.h"
#include "../../model/RecurringEvent.h"
#include "../../model/OneTimeEvent.h"
#include "../../model/recurrence/DailyRecurrence.h"
#include "../../model/recurrence/WeeklyRecurrence.h"
#include "../../model/recurrence/MonthlyRecurrence.h"
#include "../../model/recurrence/YearlyRecurrence.h"
#include "../test_utils.h"
#include <iostream>
#include <sqlite3.h>

using namespace std;
using namespace chrono;

static void testRecurringPersistence()
{
    const char *path = "test_persist.db";
    std::remove(path);
    {
        SQLiteScheduleDatabase db(path);
        Model m(&db);
        auto start = makeTime(2025, 6, 9, 8);
        auto pat = std::make_shared<DailyRecurrence>(start, 1);
        RecurringEvent r("R", "d", "t", start, hours(1), pat);
        m.addEvent(r);
    }
    {
        SQLiteScheduleDatabase db(path);
        Model m(&db);
        auto events = m.getNextNEvents(3);
        assert(events.size() == 3);
        for (int i = 0; i < 3; i++)
        {
            assert(events[i].getId() == "R");
            assert(events[i].isRecurring());
        }
    }
    // ensure only one row stored
    std::unique_ptr<sqlite3, decltype(&sqlite3_close)> conn(nullptr, sqlite3_close);
    sqlite3 *rawConn = nullptr;
    if (sqlite3_open(path, &rawConn) != SQLITE_OK)
    {
        assert(false && "failed to open db");
    }
    conn.reset(rawConn);
    sqlite3_stmt *st = nullptr;
    sqlite3_prepare_v2(conn.get(), "SELECT COUNT(*) FROM events", -1, &st, nullptr);
    int rows = 0;
    if (sqlite3_step(st) == SQLITE_ROW)
        rows = sqlite3_column_int(st, 0);
    sqlite3_finalize(st);
    assert(rows == 1);
    std::remove(path);
}

static void testOneTimePersistence()
{
    const char *path = "test_persist1.db";
    std::remove(path);
    {
        SQLiteScheduleDatabase db(path);
        Model m(&db);
        auto time = makeTime(2025, 6, 10, 12);
        OneTimeEvent e("O", "desc", "title", time, hours(1));
        m.addEvent(e);
    }
    {
        SQLiteScheduleDatabase db(path);
        Model m(&db);
        auto events = m.getEvents(-1, makeTime(2026, 1, 1, 0));
        assert(events.size() == 1);
        assert(events[0].getId() == "O");
        assert(!events[0].isRecurring());
    }
    std::remove(path);
}

static void testWeeklyPersistence()
{
    const char *path = "test_persist.db";
    std::remove(path);
    {
        SQLiteScheduleDatabase db(path);
        Model m(&db);
        auto start = makeTime(2025, 6, 9, 9); // Monday 9 AM
        std::vector<Weekday> days{Weekday::Monday, Weekday::Wednesday};
        auto pat = std::make_shared<WeeklyRecurrence>(start, days, 1);
        RecurringEvent r("W", "desc", "title", start, hours(1), pat);
        m.addEvent(r);
    }
    {
        SQLiteScheduleDatabase db(path);
        Model m(&db);
        auto events = m.getNextNEvents(4);
        assert(events.size() == 4);
        for (const auto &e : events)
        {
            assert(e.getId() == "W");
            assert(e.isRecurring());
        }
    }
    std::unique_ptr<sqlite3, decltype(&sqlite3_close)> conn(nullptr, sqlite3_close);
    sqlite3 *raw = nullptr;
    if (sqlite3_open(path, &raw) != SQLITE_OK)
    {
        assert(false && "failed to open db");
    }
    conn.reset(raw);
    sqlite3_stmt *st = nullptr;
    sqlite3_prepare_v2(conn.get(), "SELECT COUNT(*) FROM events", -1, &st, nullptr);
    int rows = 0;
    if (sqlite3_step(st) == SQLITE_ROW)
        rows = sqlite3_column_int(st, 0);
    sqlite3_finalize(st);
    assert(rows == 1);
    std::remove(path);
}

static void testMonthlyPersistence()
{
    const char *path = "test_persist.db";
    std::remove(path);
    {
        SQLiteScheduleDatabase db(path);
        Model m(&db);
        auto start = makeTime(2024, 1, 31, 9);
        auto pat = std::make_shared<MonthlyRecurrence>(start, 1);
        RecurringEvent r("M", "desc", "title", start, hours(1), pat);
        m.addEvent(r);
    }
    {
        SQLiteScheduleDatabase db(path);
        Model m(&db);
        auto events = m.getNextNEvents(3);
        assert(events.size() == 3);
        for (const auto &e : events)
        {
            assert(e.getId() == "M");
            assert(e.isRecurring());
        }
    }
    std::unique_ptr<sqlite3, decltype(&sqlite3_close)> conn(nullptr, sqlite3_close);
    sqlite3 *raw = nullptr;
    if (sqlite3_open(path, &raw) != SQLITE_OK)
    {
        assert(false && "failed to open db");
    }
    conn.reset(raw);
    sqlite3_stmt *st = nullptr;
    sqlite3_prepare_v2(conn.get(), "SELECT COUNT(*) FROM events", -1, &st, nullptr);
    int rows = 0;
    if (sqlite3_step(st) == SQLITE_ROW)
        rows = sqlite3_column_int(st, 0);
    sqlite3_finalize(st);
    assert(rows == 1);
    std::remove(path);
}

static void testYearlyPersistence()
{
    const char *path = "test_persist.db";
    std::remove(path);
    {
        SQLiteScheduleDatabase db(path);
        Model m(&db);
        auto start = makeTime(2024, 2, 29, 10);
        auto pat = std::make_shared<YearlyRecurrence>(start, 1);
        RecurringEvent r("Y", "desc", "title", start, hours(1), pat);
        m.addEvent(r);
    }
    {
        SQLiteScheduleDatabase db(path);
        Model m(&db);
        auto events = m.getNextNEvents(2);
        assert(events.size() == 2);
        for (const auto &e : events)
        {
            assert(e.getId() == "Y");
            assert(e.isRecurring());
        }
    }
    std::unique_ptr<sqlite3, decltype(&sqlite3_close)> conn(nullptr, sqlite3_close);
    sqlite3 *raw = nullptr;
    if (sqlite3_open(path, &raw) != SQLITE_OK)
    {
        assert(false && "failed to open db");
    }
    conn.reset(raw);
    sqlite3_stmt *st = nullptr;
    sqlite3_prepare_v2(conn.get(), "SELECT COUNT(*) FROM events", -1, &st, nullptr);
    int rows = 0;
    if (sqlite3_step(st) == SQLITE_ROW)
        rows = sqlite3_column_int(st, 0);
    sqlite3_finalize(st);
    assert(rows == 1);
    std::remove(path);
}

static void testRemoveAllDatabase()
{
    const char *path = "test_persist.db";
    std::remove(path);
    {
        SQLiteScheduleDatabase db(path);
        Model m(&db);
        auto time = makeTime(2025, 6, 10, 12);
        OneTimeEvent e("O", "desc", "title", time, hours(1));
        m.addEvent(e);
        m.removeAllEvents();
    }
    {
        SQLiteScheduleDatabase db(path);
        Model m(&db);
        auto events = m.getNextNEvents(1);
        assert(events.empty());
    }
    std::remove(path);
}

static void testRemoveBeforeDatabase()
{
    const char *path = "test_persist.db";
    std::remove(path);
    {
        SQLiteScheduleDatabase db(path);
        Model m(&db);
        OneTimeEvent e1("1", "d", "t", makeTime(2025, 6, 1, 9), hours(1));
        OneTimeEvent e2("2", "d", "t", makeTime(2025, 6, 3, 9), hours(1));
        m.addEvent(e1);
        m.addEvent(e2);
        m.removeEventsBefore(makeTime(2025, 6, 2, 0));
    }
    {
        SQLiteScheduleDatabase db(path);
        Model m(&db);
        auto events = m.getEvents(-1, makeTime(2025, 6, 4, 0));
        assert(events.size() == 1 && events[0].getId() == "2");
    }
    std::remove(path);
}

int main()
{
    testRecurringPersistence();
    testOneTimePersistence();
    testWeeklyPersistence();
    testMonthlyPersistence();
    testYearlyPersistence();
    testRemoveAllDatabase();
    testRemoveBeforeDatabase();
    cout << "Database tests passed\n";
    return 0;
}
