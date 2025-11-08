#include "SettingsStore.h"
#include <sqlite3.h>
#include <stdexcept>

SettingsStore::SettingsStore(const std::string &db_path) : db_(nullptr), path_(db_path) {
    sqlite3 *raw = nullptr;
    if (sqlite3_open(db_path.c_str(), &raw) != SQLITE_OK) {
        throw std::runtime_error("SettingsStore: failed to open database");
    }
    db_ = raw;
    const char *sql = "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);";
    char *err = nullptr;
    if (sqlite3_exec(static_cast<sqlite3 *>(db_), sql, nullptr, nullptr, &err) != SQLITE_OK) {
        std::string msg = err ? err : "error creating settings table";
        sqlite3_free(err);
        throw std::runtime_error(msg);
    }
}

SettingsStore::~SettingsStore() {
    if (db_) sqlite3_close(static_cast<sqlite3 *>(db_));
}

bool SettingsStore::setString(const std::string &key, const std::string &value) {
    std::lock_guard<std::mutex> lock(mtx_);
    const char *sql = "INSERT OR REPLACE INTO settings(key,value) VALUES(?,?);";
    sqlite3_stmt *st = nullptr;
    if (sqlite3_prepare_v2(static_cast<sqlite3 *>(db_), sql, -1, &st, nullptr) != SQLITE_OK) return false;
    sqlite3_bind_text(st, 1, key.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(st, 2, value.c_str(), -1, SQLITE_TRANSIENT);
    bool ok = (sqlite3_step(st) == SQLITE_DONE);
    sqlite3_finalize(st);
    return ok;
}

bool SettingsStore::setInt(const std::string &key, int value) {
    return setString(key, std::to_string(value));
}

bool SettingsStore::setBool(const std::string &key, bool value) {
    return setString(key, value ? "true" : "false");
}

std::optional<std::string> SettingsStore::getString(const std::string &key) const {
    std::lock_guard<std::mutex> lock(mtx_);
    const char *sql = "SELECT value FROM settings WHERE key=?;";
    sqlite3_stmt *st = nullptr;
    if (sqlite3_prepare_v2(static_cast<sqlite3 *>(db_), sql, -1, &st, nullptr) != SQLITE_OK) return std::nullopt;
    sqlite3_bind_text(st, 1, key.c_str(), -1, SQLITE_TRANSIENT);
    std::optional<std::string> out;
    if (sqlite3_step(st) == SQLITE_ROW) {
        const unsigned char *txt = sqlite3_column_text(st, 0);
        if (txt) out = reinterpret_cast<const char *>(txt);
    }
    sqlite3_finalize(st);
    return out;
}

std::optional<int> SettingsStore::getInt(const std::string &key) const {
    auto s = getString(key);
    if (!s) return std::nullopt;
    try { return std::stoi(*s); } catch (...) { return std::nullopt; }
}

std::optional<bool> SettingsStore::getBool(const std::string &key) const {
    auto s = getString(key);
    if (!s) return std::nullopt;
    std::string v = *s;
    for (auto &c : v) c = static_cast<char>(::tolower(c));
    if (v == "true" || v == "1" || v == "yes") return true;
    if (v == "false" || v == "0" || v == "no") return false;
    return std::nullopt;
}
