#pragma once

#include "IScheduleDatabase.h"
#include <memory>
#include <sqlite3.h>
#include <string>

class SQLiteScheduleDatabase : public IScheduleDatabase {
public:
    explicit SQLiteScheduleDatabase(const std::string &path);
    ~SQLiteScheduleDatabase() override = default;

    bool addEvent(const Event &e) override;
    bool removeEvent(const std::string &id) override;
    bool removeAllEvents() override;
    std::vector<std::unique_ptr<Event>> getAllEvents() const override;

private:
    std::unique_ptr<sqlite3, decltype(&sqlite3_close)> db_;
};
