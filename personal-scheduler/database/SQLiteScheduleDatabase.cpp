#include "SQLiteScheduleDatabase.h"
#include "../model/OneTimeEvent.h"
#include "../model/RecurringEvent.h"
#include "../model/recurrence/DailyRecurrence.h"
#include "../model/recurrence/WeeklyRecurrence.h"
#include "../model/recurrence/MonthlyRecurrence.h"
#include "../model/recurrence/YearlyRecurrence.h"
#include "../utils/WeekDay.h"
#include "nlohmann/json.hpp"
#include <stdexcept>

SQLiteScheduleDatabase::SQLiteScheduleDatabase(const std::string &path)
    : db_(nullptr, sqlite3_close)
{
    sqlite3 *raw = nullptr;
    if (sqlite3_open(path.c_str(), &raw) != SQLITE_OK)
    {
        throw std::runtime_error("Failed to open database");
    }
    db_.reset(raw);

    const char *createSql =
        "CREATE TABLE IF NOT EXISTS events ("
        "id TEXT PRIMARY KEY,"
        "description TEXT,"
        "title TEXT,"
        "time INTEGER,"
        "duration INTEGER,"
        "recurrence TEXT,"
        "category TEXT,"
        "notifier TEXT,"
        "action TEXT,"
        "google_event_id TEXT,"
        "google_task_id TEXT);";
    char *errMsg = nullptr;
    if (sqlite3_exec(db_.get(), createSql, nullptr, nullptr, &errMsg) != SQLITE_OK)
    {
        std::string msg = errMsg ? errMsg : "error creating table";
        sqlite3_free(errMsg);
        throw std::runtime_error(msg);
    }

    // Migration: add missing columns if an existing DB lacks them
    bool hasCategory = false;
    bool hasNotifier = false;
    bool hasAction = false;
    bool hasGoogleEventId = false;
    bool hasGoogleTaskId = false;
    const char *pragmaSql = "PRAGMA table_info(events);";
    sqlite3_stmt *pragmaStmt = nullptr;
    if (sqlite3_prepare_v2(db_.get(), pragmaSql, -1, &pragmaStmt, nullptr) == SQLITE_OK)
    {
        while (sqlite3_step(pragmaStmt) == SQLITE_ROW)
        {
            // PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
            const unsigned char *name = sqlite3_column_text(pragmaStmt, 1);
            if (name)
            {
                std::string col = reinterpret_cast<const char *>(name);
                if (col == "category") hasCategory = true;
                else if (col == "notifier") hasNotifier = true;
                else if (col == "action") hasAction = true;
                else if (col == "google_event_id") hasGoogleEventId = true;
                else if (col == "google_task_id") hasGoogleTaskId = true;
            }
        }
    }
    sqlite3_finalize(pragmaStmt);

    if (!hasCategory)
    {
        const char *alterSql = "ALTER TABLE events ADD COLUMN category TEXT;";
        if (sqlite3_exec(db_.get(), alterSql, nullptr, nullptr, &errMsg) != SQLITE_OK)
        {
            std::string msg = errMsg ? errMsg : "error adding category column";
            if (!msg.empty() && msg.find("duplicate column name") == std::string::npos)
            {
                sqlite3_free(errMsg);
                throw std::runtime_error(msg);
            }
            if (errMsg) sqlite3_free(errMsg);
        }
    }

    if (!hasNotifier)
    {
        const char *alterSql = "ALTER TABLE events ADD COLUMN notifier TEXT;";
        if (sqlite3_exec(db_.get(), alterSql, nullptr, nullptr, &errMsg) != SQLITE_OK)
        {
            std::string msg = errMsg ? errMsg : "error adding notifier column";
            if (!msg.empty() && msg.find("duplicate column name") == std::string::npos)
            {
                sqlite3_free(errMsg);
                throw std::runtime_error(msg);
            }
            if (errMsg) sqlite3_free(errMsg);
        }
    }

    if (!hasAction)
    {
        const char *alterSql = "ALTER TABLE events ADD COLUMN action TEXT;";
        if (sqlite3_exec(db_.get(), alterSql, nullptr, nullptr, &errMsg) != SQLITE_OK)
        {
            std::string msg = errMsg ? errMsg : "error adding action column";
            if (!msg.empty() && msg.find("duplicate column name") == std::string::npos)
            {
                sqlite3_free(errMsg);
                throw std::runtime_error(msg);
            }
            if (errMsg) sqlite3_free(errMsg);
        }
    }

    if (!hasGoogleEventId)
    {
        const char *alterSql = "ALTER TABLE events ADD COLUMN google_event_id TEXT;";
        if (sqlite3_exec(db_.get(), alterSql, nullptr, nullptr, &errMsg) != SQLITE_OK)
        {
            std::string msg = errMsg ? errMsg : "error adding google_event_id column";
            if (!msg.empty() && msg.find("duplicate column name") == std::string::npos)
            {
                sqlite3_free(errMsg);
                throw std::runtime_error(msg);
            }
            if (errMsg) sqlite3_free(errMsg);
        }
    }
    if (!hasGoogleTaskId)
    {
        const char *alterSql = "ALTER TABLE events ADD COLUMN google_task_id TEXT;";
        if (sqlite3_exec(db_.get(), alterSql, nullptr, nullptr, &errMsg) != SQLITE_OK)
        {
            std::string msg = errMsg ? errMsg : "error adding google_task_id column";
            if (!msg.empty() && msg.find("duplicate column name") == std::string::npos)
            {
                sqlite3_free(errMsg);
                throw std::runtime_error(msg);
            }
            if (errMsg) sqlite3_free(errMsg);
        }
    }
}

bool SQLiteScheduleDatabase::addEvent(const Event &e)
{
    const char *sql =
        "INSERT OR REPLACE INTO events (id, description, title, time, duration, recurrence, category, notifier, action, google_event_id, google_task_id) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?);";
    sqlite3_stmt *stmt = nullptr;
    if (sqlite3_prepare_v2(db_.get(), sql, -1, &stmt, nullptr) != SQLITE_OK)
        return false;

    sqlite3_bind_text(stmt, 1, e.getId().c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 2, e.getDescription().c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 3, e.getTitle().c_str(), -1, SQLITE_TRANSIENT);
    long long timeSec = std::chrono::duration_cast<std::chrono::seconds>(
                            e.getTime().time_since_epoch())
                            .count();
    sqlite3_bind_int64(stmt, 4, timeSec);
    long long durSec =
        std::chrono::duration_cast<std::chrono::seconds>(e.getDuration()).count();
    sqlite3_bind_int64(stmt, 5, durSec);
    std::string recJson;
    if (e.isRecurring())
    {
        const auto *re = dynamic_cast<const RecurringEvent *>(&e);
        if (re)
        {
            nlohmann::json j;
            auto pat = re->getRecurrencePattern();
            if (auto dr = dynamic_cast<DailyRecurrence *>(pat.get()))
            {
                j["type"] = "daily";
                j["interval"] = dr->getInterval();
                j["max"] = dr->getMaxOccurrences();
                auto endSec = std::chrono::duration_cast<std::chrono::seconds>(dr->getEndDate().time_since_epoch()).count();
                j["end"] = endSec;
            }
            else if (auto wr = dynamic_cast<WeeklyRecurrence *>(pat.get()))
            {
                j["type"] = "weekly";
                j["interval"] = wr->getInterval();
                std::vector<int> days;
                for (auto d : wr->getDaysOfWeek())
                    days.push_back(static_cast<int>(d));
                j["days"] = days;
                j["max"] = wr->getMaxOccurrences();
                auto endSec = std::chrono::duration_cast<std::chrono::seconds>(wr->getEndDate().time_since_epoch()).count();
                j["end"] = endSec;
            }
            else if (auto mr = dynamic_cast<MonthlyRecurrence *>(pat.get()))
            {
                j["type"] = "monthly";
                j["interval"] = mr->getInterval();
                j["max"] = mr->getMaxOccurrences();
                auto endSec = std::chrono::duration_cast<std::chrono::seconds>(mr->getEndDate().time_since_epoch()).count();
                j["end"] = endSec;
            }
            else if (auto yr = dynamic_cast<YearlyRecurrence *>(pat.get()))
            {
                j["type"] = "yearly";
                j["interval"] = yr->getInterval();
                j["max"] = yr->getMaxOccurrences();
                auto endSec = std::chrono::duration_cast<std::chrono::seconds>(yr->getEndDate().time_since_epoch()).count();
                j["end"] = endSec;
            }
            recJson = j.dump();
        }
    }
    if (recJson.empty())
        sqlite3_bind_null(stmt, 6);
    else
        sqlite3_bind_text(stmt, 6, recJson.c_str(), -1, SQLITE_TRANSIENT);

    const std::string &cat = e.getCategory();
    if (cat.empty())
        sqlite3_bind_null(stmt, 7);
    else
        sqlite3_bind_text(stmt, 7, cat.c_str(), -1, SQLITE_TRANSIENT);

    const std::string &notifier = e.getNotifierName();
    if (notifier.empty())
        sqlite3_bind_null(stmt, 8);
    else
        sqlite3_bind_text(stmt, 8, notifier.c_str(), -1, SQLITE_TRANSIENT);

    const std::string &action = e.getActionName();
    if (action.empty())
        sqlite3_bind_null(stmt, 9);
    else
        sqlite3_bind_text(stmt, 9, action.c_str(), -1, SQLITE_TRANSIENT);

    const std::string &gcalId = e.getProviderEventId();
    if (gcalId.empty()) sqlite3_bind_null(stmt, 10);
    else sqlite3_bind_text(stmt, 10, gcalId.c_str(), -1, SQLITE_TRANSIENT);

    const std::string &gtaskId = e.getProviderTaskId();
    if (gtaskId.empty()) sqlite3_bind_null(stmt, 11);
    else sqlite3_bind_text(stmt, 11, gtaskId.c_str(), -1, SQLITE_TRANSIENT);

    bool ok = sqlite3_step(stmt) == SQLITE_DONE;
    sqlite3_finalize(stmt);
    return ok;
}

bool SQLiteScheduleDatabase::removeEvent(const std::string &id)
{
    const char *sql = "DELETE FROM events WHERE id = ?;";
    sqlite3_stmt *stmt = nullptr;
    if (sqlite3_prepare_v2(db_.get(), sql, -1, &stmt, nullptr) != SQLITE_OK)
        return false;
    sqlite3_bind_text(stmt, 1, id.c_str(), -1, SQLITE_TRANSIENT);
    bool ok = sqlite3_step(stmt) == SQLITE_DONE;
    sqlite3_finalize(stmt);
    return ok;
}

bool SQLiteScheduleDatabase::removeAllEvents()
{
    const char *sql = "DELETE FROM events;";
    char *errMsg = nullptr;
    if (sqlite3_exec(db_.get(), sql, nullptr, nullptr, &errMsg) != SQLITE_OK)
    {
        if (errMsg)
            sqlite3_free(errMsg);
        return false;
    }
    return true;
}

std::vector<std::unique_ptr<Event>> SQLiteScheduleDatabase::getAllEvents() const
{
    const char *sql =
        "SELECT id, description, title, time, duration, recurrence, category, notifier, action, google_event_id, google_task_id FROM events ORDER BY time;";
    sqlite3_stmt *stmt = nullptr;
    if (sqlite3_prepare_v2(db_.get(), sql, -1, &stmt, nullptr) != SQLITE_OK)
        return {};

    std::vector<std::unique_ptr<Event>> result;
    auto safeText = [](sqlite3_stmt* s, int col)->std::string {
        const unsigned char *t = sqlite3_column_text(s, col);
        return t ? reinterpret_cast<const char *>(t) : std::string();
    };
    while (sqlite3_step(stmt) == SQLITE_ROW)
    {
        std::string id = safeText(stmt, 0);
        std::string desc = safeText(stmt, 1);
        std::string title = safeText(stmt, 2);
        long long timeSec = sqlite3_column_int64(stmt, 3);
        long long durSec = sqlite3_column_int64(stmt, 4);
        const unsigned char *recText = sqlite3_column_text(stmt, 5);
        std::string category = safeText(stmt, 6);
        std::string notifier = safeText(stmt, 7);
        std::string action = safeText(stmt, 8);
        std::string provEvent = safeText(stmt, 9);
        std::string provTask = safeText(stmt, 10);
        auto tp = std::chrono::system_clock::time_point(std::chrono::seconds(timeSec));
        auto dur = std::chrono::seconds(durSec);

        if (recText)
        {
            try
            {
                nlohmann::json j = nlohmann::json::parse(reinterpret_cast<const char *>(recText));
                std::shared_ptr<RecurrencePattern> pat;
                std::string type = j.value("type", "");
                if (type == "daily")
                {
                    int interval = j.value("interval", 1);
                    int max = j.value("max", -1);
                    long long endSec = j.value("end", std::numeric_limits<long long>::max());
                    auto endTp = std::chrono::system_clock::time_point(std::chrono::seconds(endSec));
                    pat = std::make_shared<DailyRecurrence>(tp, interval, max, endTp);
                }
                else if (type == "weekly")
                {
                    int interval = j.value("interval", 1);
                    std::vector<int> daysVals = j.value("days", std::vector<int>{});
                    std::vector<Weekday> days;
                    for (int d : daysVals)
                        days.push_back(static_cast<Weekday>(d));
                    int max = j.value("max", -1);
                    long long endSec = j.value("end", std::numeric_limits<long long>::max());
                    auto endTp = std::chrono::system_clock::time_point(std::chrono::seconds(endSec));
                    pat = std::make_shared<WeeklyRecurrence>(tp, days, interval, max, endTp);
                }
                else if (type == "monthly")
                {
                    int interval = j.value("interval", 1);
                    int max = j.value("max", -1);
                    long long endSec = j.value("end", std::numeric_limits<long long>::max());
                    auto endTp = std::chrono::system_clock::time_point(std::chrono::seconds(endSec));
                    pat = std::make_shared<MonthlyRecurrence>(tp, interval, max, endTp);
                }
                else if (type == "yearly")
                {
                    int interval = j.value("interval", 1);
                    int max = j.value("max", -1);
                    long long endSec = j.value("end", std::numeric_limits<long long>::max());
                    auto endTp = std::chrono::system_clock::time_point(std::chrono::seconds(endSec));
                    pat = std::make_shared<YearlyRecurrence>(tp, interval, max, endTp);
                }

                if (pat)
                {
                    auto ev = std::make_unique<RecurringEvent>(id, desc, title, tp, dur, pat, category);
                    if (!notifier.empty()) ev->setNotifierName(notifier);
                    if (!action.empty()) ev->setActionName(action);
                    if (!provEvent.empty()) ev->setProviderEventId(provEvent);
                    if (!provTask.empty()) ev->setProviderTaskId(provTask);
                    result.push_back(std::move(ev));
                    continue;
                }
            }
            catch (...)
            {
                // fall back to one-time event
            }
        }
        auto ev = std::make_unique<OneTimeEvent>(id, desc, title, tp, dur, category);
        if (!notifier.empty()) ev->setNotifierName(notifier);
        if (!action.empty()) ev->setActionName(action);
        if (!provEvent.empty()) ev->setProviderEventId(provEvent);
        if (!provTask.empty()) ev->setProviderTaskId(provTask);
        result.push_back(std::move(ev));
    }
    sqlite3_finalize(stmt);
    return result;
}
