#include "WakeScheduler.h"
#include "../utils/BuiltinActions.h"
#include "../utils/TimeUtils.h"
#include "../scheduler/ScheduledTask.h"
#include "nlohmann/json.hpp"
#include <ctime>
#include <algorithm>
#include <sstream>
#include "../utils/Logger.h"

using namespace std;
using namespace std::chrono;

WakeScheduler::WakeScheduler(Model &model, EventLoop &loop, SettingsStore &settings)
    : model_(model), loop_(loop), settings_(settings) {}

system_clock::time_point WakeScheduler::localMidnight(system_clock::time_point tp) const {
    time_t t = system_clock::to_time_t(tp);
    std::tm tm{};
#if defined(_MSC_VER)
    localtime_s(&tm, &t);
#else
    localtime_r(&t, &tm);
#endif
    tm.tm_hour = 0; tm.tm_min = 0; tm.tm_sec = 0;
    return system_clock::from_time_t(mktime(&tm));
}

system_clock::time_point WakeScheduler::parseLocalTimeHM(system_clock::time_point day, const std::string &hm) const {
    int hh = 2, mm = 0;
    if (!hm.empty()) {
        std::sscanf(hm.c_str(), "%d:%d", &hh, &mm);
    }
    time_t t = system_clock::to_time_t(day);
    std::tm tm{};
#if defined(_MSC_VER)
    localtime_s(&tm, &t);
#else
    localtime_r(&t, &tm);
#endif
    tm.tm_hour = hh; tm.tm_min = mm; tm.tm_sec = 0;
    return system_clock::from_time_t(mktime(&tm));
}

system_clock::time_point WakeScheduler::nextLocalMidnight(system_clock::time_point now) const {
    // Compute local time components and roll day by one
    time_t t = system_clock::to_time_t(now);
    std::tm tm{};
#if defined(_MSC_VER)
    localtime_s(&tm, &t);
#else
    localtime_r(&t, &tm);
#endif
    tm.tm_mday += 1;
    tm.tm_hour = 0; tm.tm_min = 0; tm.tm_sec = 0;
    return system_clock::from_time_t(mktime(&tm));
}

system_clock::time_point WakeScheduler::computeWakeTime(system_clock::time_point day,
                                                        std::string &reason,
                                                        std::vector<Event> &firstEvents) const {
    Logger::debug("[wake] compute start day=", TimeUtils::formatTimePoint(day));
    // Load config
    // Default baseline is 14:00 (2 PM) unless overridden via settings
    auto baselineStr = settings_.getString("wake.baseline_time").value_or("14:00");
    int lead = settings_.getInt("wake.lead_minutes").value_or(45);
    bool onlyWhenEvents = settings_.getBool("wake.only_when_events").value_or(false);
    bool skipWeekends = settings_.getBool("wake.skip_weekends").value_or(false);
    Logger::debug("[wake] cfg baseline=", baselineStr, " lead=", lead, " onlyWhenEvents=", onlyWhenEvents, " skipWeekends=", skipWeekends);

    auto base = parseLocalTimeHM(day, baselineStr);
    Logger::debug("[wake] base=", TimeUtils::formatTimePoint(base));
    // Collect first few events on day
    auto events = model_.getEventsOnDay(day);
    Logger::debug("[wake] events on day=", events.size());
    if (!events.empty()) {
        Logger::debug("[wake] first raw event id=", events[0].getId(), " title.len=", events[0].getTitle().size(), " desc.len=", events[0].getDescription().size());
    }
    std::sort(events.begin(), events.end(), [](const Event &a, const Event &b){ return a.getTime() < b.getTime(); });
    if (!events.empty()) {
        Logger::debug("[wake] earliest after sort id=", events[0].getId(), " time=", TimeUtils::formatTimePoint(events[0].getTime()));
    }
    firstEvents.clear();
    for (size_t i = 0; i < events.size() && i < 3; ++i) firstEvents.push_back(events[i]);

    // Weekend skip logic
    if (events.empty()) {
        if (onlyWhenEvents) {
            reason = "no-events-skip";
            return system_clock::time_point::min();
        }
        if (skipWeekends) {
            time_t t = system_clock::to_time_t(day);
            std::tm tm{};
#if defined(_MSC_VER)
            localtime_s(&tm, &t);
#else
            localtime_r(&t, &tm);
#endif
        if (tm.tm_wday == 0 || tm.tm_wday == 6) { // Sun/Sat
            reason = "weekend-skip";
            return system_clock::time_point::min();
        }
        }
        reason = "baseline";
        return base;
    }

    auto earliest = events.front().getTime();
    auto candidate = earliest - minutes(lead);
    if (onlyWhenEvents) {
        reason = "earliest-minus-lead";
        return candidate;
    }
    // Adjust only if the earliest event occurs before the baseline time
    time_t t = system_clock::to_time_t(earliest);
    std::tm tm_earliest{};
#if defined(_MSC_VER)
    localtime_s(&tm_earliest, &t);
#else
    localtime_r(&t, &tm_earliest);
#endif
    // Baseline comparison uses local day hours/mins; compare absolute instants for safety
    if (earliest < base) {
        reason = "earliest-minus-lead";
        return candidate;
    }
    reason = "baseline";
    return base;
}

void WakeScheduler::scheduleToday() {
    Logger::debug("[wake] scheduleToday enter");
    if (!settings_.getBool("wake.enabled").value_or(true)) return;
    auto now = system_clock::now();
    auto day = localMidnight(now);
    std::string reason;
    std::vector<Event> first;
    auto wakeTime = computeWakeTime(day, reason, first);
    Logger::debug("[wake] computed reason=", reason, " wakeTime=", TimeUtils::formatTimePoint(wakeTime));
    if (wakeTime == system_clock::time_point::min()) return; // skip
    if (wakeTime <= now) return; // already passed

    // Build action that posts to external JARVIS/GoodMorning endpoint
    std::string url = settings_.getString("wake.server_url").value_or("");
    std::string userId = settings_.getString("user.id").value_or(std::getenv("USER_ID") ? std::getenv("USER_ID") : "unknown");
    std::string tzName = settings_.getString("user.timezone").value_or(std::getenv("USER_TIMEZONE") ? std::getenv("USER_TIMEZONE") : "Local");
    int lead = settings_.getInt("wake.lead_minutes").value_or(45);
    std::string baselineStr = settings_.getString("wake.baseline_time").value_or("14:00");
    auto action = [url, day, wakeTime, reason, first, userId, tzName, lead, baselineStr]() {
        if (url.empty()) { Logger::warn("[wake] No WAKE_SERVER_URL; skipping call"); return; }
        nlohmann::json payload;
        payload["user_id"] = userId;
        payload["wake_time"] = TimeUtils::formatRFC3339Local(wakeTime);
        payload["timezone"] = tzName;
        nlohmann::json ctx;
        ctx["source"] = "scheduler";
        ctx["reason"] = reason;
        ctx["baseline_time"] = baselineStr;
        ctx["lead_minutes"] = lead;
        ctx["date"] = TimeUtils::formatTimePoint(day);
        ctx["job_id"] = std::string("wake:") + TimeUtils::formatTimePoint(day).substr(0,10);
        if (!first.empty()) {
            nlohmann::json earliest;
            earliest["id"] = first[0].getId();
            earliest["title"] = first[0].getTitle();
            earliest["description"] = first[0].getDescription();
            earliest["start"] = TimeUtils::formatRFC3339Local(first[0].getTime());
            earliest["duration_sec"] = std::chrono::duration_cast<std::chrono::seconds>(first[0].getDuration()).count();
            ctx["earliest_event"] = earliest;
        } else {
            ctx["earliest_event"] = nullptr;
        }
        nlohmann::json brief = nlohmann::json::array();
        for (const auto &e : first) {
            brief.push_back({ {"id", e.getId()}, {"title", e.getTitle()}, {"start", TimeUtils::formatRFC3339Local(e.getTime())} });
        }
        ctx["first_events"] = brief;
        payload["context"] = ctx;
        Logger::info("[wake] POST ", url);
        BuiltinActions::httpPostJson(url, payload.dump());
    };

    // Build task with deterministic ID
    char datebuf[11]; // YYYY-MM-DD + null
    auto ds = TimeUtils::formatTimePoint(day);
    std::snprintf(datebuf, sizeof(datebuf), "%.*s", 10, ds.c_str());
    std::string id = std::string("wake:") + datebuf;
    std::string title = std::string("Wake for ") + datebuf;
    auto task = std::make_shared<ScheduledTask>(id, "wake task", title, wakeTime, seconds(0),
                                                std::vector<system_clock::time_point>{}, []{}, action);
    task->setCategory("internal");
    Logger::debug("[wake] adding task");
    loop_.addTask(task);
}

void WakeScheduler::scheduleDailyMaintenance() {
    // Compute next local midnight and schedule a task to reschedule today's wake
    auto now = system_clock::now();
    auto nextMid = nextLocalMidnight(now);
    auto task = std::make_shared<ScheduledTask>(
        "wake:maintenance", "wake maintenance", "Wake Maintenance",
        nextMid, seconds(0), std::vector<system_clock::time_point>{}, []{},
        [this]() { const_cast<WakeScheduler*>(this)->scheduleToday(); const_cast<WakeScheduler*>(this)->scheduleDailyMaintenance(); }
    );
    task->setCategory("internal");
    loop_.addTask(task);
}

void WakeScheduler::scheduleForDate(system_clock::time_point day) {
    if (!settings_.getBool("wake.enabled").value_or(true)) return;
    std::string reason;
    std::vector<Event> first;
    auto wakeTime = computeWakeTime(day, reason, first);
    auto now = system_clock::now();
    if (wakeTime == system_clock::time_point::min() || wakeTime <= now) return;

    // Construct deterministic ID based on date
    char datebuf[11];
    auto ds = TimeUtils::formatTimePoint(day);
    std::snprintf(datebuf, sizeof(datebuf), "%.*s", 10, ds.c_str());
    std::string id = std::string("wake:") + datebuf;
    std::string title = std::string("Wake for ") + datebuf;

    std::string url2 = settings_.getString("wake.server_url").value_or("");
    std::string userId2 = settings_.getString("user.id").value_or(std::getenv("USER_ID") ? std::getenv("USER_ID") : "unknown");
    std::string tzName2 = settings_.getString("user.timezone").value_or(std::getenv("USER_TIMEZONE") ? std::getenv("USER_TIMEZONE") : "Local");
    int lead2 = settings_.getInt("wake.lead_minutes").value_or(45);
    std::string baselineStr2 = settings_.getString("wake.baseline_time").value_or("14:00");
    auto action = [url2, day, wakeTime, reason, first, userId2, tzName2, lead2, baselineStr2]() {
        if (url2.empty()) return;
        nlohmann::json payload;
        payload["user_id"] = userId2;
        payload["wake_time"] = TimeUtils::formatRFC3339Local(wakeTime);
        payload["timezone"] = tzName2;
        nlohmann::json ctx;
        ctx["source"] = "scheduler";
        ctx["reason"] = reason;
        ctx["baseline_time"] = baselineStr2;
        ctx["lead_minutes"] = lead2;
        ctx["date"] = TimeUtils::formatTimePoint(day);
        ctx["job_id"] = std::string("wake:") + TimeUtils::formatTimePoint(day).substr(0,10);
        if (!first.empty()) {
            nlohmann::json earliest;
            earliest["id"] = first[0].getId();
            earliest["title"] = first[0].getTitle();
            earliest["description"] = first[0].getDescription();
            earliest["start"] = TimeUtils::formatRFC3339Local(first[0].getTime());
            earliest["duration_sec"] = std::chrono::duration_cast<std::chrono::seconds>(first[0].getDuration()).count();
            ctx["earliest_event"] = earliest;
        } else {
            ctx["earliest_event"] = nullptr;
        }
        nlohmann::json brief = nlohmann::json::array();
        for (const auto &e : first) {
            brief.push_back({ {"id", e.getId()}, {"title", e.getTitle()}, {"start", TimeUtils::formatRFC3339Local(e.getTime())} });
        }
        ctx["first_events"] = brief;
        payload["context"] = ctx;
        BuiltinActions::httpPostJson(url2, payload.dump());
    };

    auto task = std::make_shared<ScheduledTask>(id, "wake task", title, wakeTime, seconds(0),
                                                std::vector<system_clock::time_point>{}, []{}, action);
    task->setCategory("internal");
    Logger::debug("[wake] adding task for date-specific");
    loop_.addTask(task);
}

std::chrono::system_clock::time_point WakeScheduler::previewForDate(system_clock::time_point day,
                                                                    std::string &reason,
                                                                    std::vector<Event> &firstEvents) const {
    return computeWakeTime(day, reason, firstEvents);
}
