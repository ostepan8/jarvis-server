#pragma once
#include <string>
#include <chrono>
#include <iomanip>
#include <sstream>
#include <ctime>

namespace TimeUtils {
inline std::string formatTimePoint(const std::chrono::system_clock::time_point &tp) {
    using namespace std::chrono;
    time_t t_c = system_clock::to_time_t(tp);
    std::tm tm_buf;
#if defined(_MSC_VER)
    localtime_s(&tm_buf, &t_c);
#else
    localtime_r(&t_c, &tm_buf);
#endif
    char buf[32];
    strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M", &tm_buf);
    return std::string(buf);
}

inline std::chrono::system_clock::time_point parseTimePoint(const std::string &timestamp) {
    using namespace std::chrono;
    std::tm tm_buf{};
    std::istringstream ss(timestamp);
    ss >> std::get_time(&tm_buf, "%Y-%m-%d %H:%M");
    if (ss.fail())
        throw std::runtime_error("Invalid timestamp format");
    tm_buf.tm_isdst = -1;
    time_t time_c = std::mktime(&tm_buf);
    return system_clock::from_time_t(time_c);
}

inline std::chrono::system_clock::time_point parseDate(const std::string &dateStr) {
    return parseTimePoint(dateStr + " 00:00");
}

inline std::chrono::system_clock::time_point parseMonth(const std::string &monthStr) {
    return parseTimePoint(monthStr + "-01 00:00");
}

inline std::string formatRFC3339UTC(const std::chrono::system_clock::time_point &tp) {
    using namespace std::chrono;
    time_t t_c = system_clock::to_time_t(tp);
    std::tm tm_buf;
#if defined(_MSC_VER)
    gmtime_s(&tm_buf, &t_c);
#else
    gmtime_r(&t_c, &tm_buf);
#endif
    char buf[32];
    strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &tm_buf);
    return std::string(buf);
}

// Format as RFC3339 in local time with numeric offset (e.g., 2025-09-05T07:30:00-04:00)
inline std::string formatRFC3339Local(const std::chrono::system_clock::time_point &tp) {
    using namespace std::chrono;
    time_t t_c = system_clock::to_time_t(tp);
    std::tm tm_local;
#if defined(_MSC_VER)
    localtime_s(&tm_local, &t_c);
#else
    localtime_r(&t_c, &tm_local);
#endif
    char datetime[32];
    strftime(datetime, sizeof(datetime), "%Y-%m-%dT%H:%M:%S", &tm_local);

    // Compute offset minutes between local and UTC
    std::tm tm_utc;
#if defined(_MSC_VER)
    gmtime_s(&tm_utc, &t_c);
#else
    gmtime_r(&t_c, &tm_utc);
#endif
    // Convert tm structs back to epoch to compute offset
#if defined(_WIN32)
    auto local_epoch = _mkgmtime(&tm_local); // Not available; fallback: assume _mkgmtime exists
    auto utc_epoch = _mkgmtime(&tm_utc);
#else
    auto local_epoch = mktime(&tm_local); // interprets tm as local time
    auto utc_epoch = timegm(&tm_utc);     // interprets tm as UTC (POSIX extension)
#endif
    long offset_sec = static_cast<long>(difftime(local_epoch, utc_epoch));
    int off_min = static_cast<int>(offset_sec / 60);
    int sign = off_min < 0 ? -1 : 1;
    off_min = std::abs(off_min);
    int off_h = off_min / 60;
    int off_m = off_min % 60;
    char offset[8];
    std::snprintf(offset, sizeof(offset), "%c%02d:%02d", sign < 0 ? '-' : '+', off_h, off_m);

    std::string out(datetime);
    out += offset;
    return out;
}
}
