#pragma once

#include <string>
#include <optional>
#include <mutex>

// Very small key/value settings store backed by SQLite in events.db.
// Table: settings(key TEXT PRIMARY KEY, value TEXT)
class SettingsStore {
public:
    explicit SettingsStore(const std::string &db_path = "events.db");
    ~SettingsStore();

    bool setString(const std::string &key, const std::string &value);
    bool setInt(const std::string &key, int value);
    bool setBool(const std::string &key, bool value);

    std::optional<std::string> getString(const std::string &key) const;
    std::optional<int> getInt(const std::string &key) const;
    std::optional<bool> getBool(const std::string &key) const;

private:
    void *db_; // sqlite3*
    std::string path_;
    mutable std::mutex mtx_;
};
