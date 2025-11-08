#include "StatsRoutes.h"
#include "Serialization.h"
#include "../../utils/TimeUtils.h"
#include <iostream>

using namespace std::chrono;

namespace StatsRoutes {

void registerRoutes(httplib::Server &server, Model &model) {
    server.Get(R"(/stats/events/(\d{4}-\d{2}-\d{2})/(\d{4}-\d{2}-\d{2}))", [&model](const httplib::Request &req, httplib::Response &res) {
        nlohmann::json out;
        try {
            auto start = TimeUtils::parseDate(req.matches[1]);
            auto end = TimeUtils::parseDate(req.matches[2]) + hours(24);
            auto stats = model.getEventStats(start, end);
            nlohmann::json data;
            data["total_events"] = stats.totalEvents;
            data["total_minutes"] = stats.totalMinutes;
            data["events_by_category"] = stats.eventsByCategory;
            nlohmann::json busyDays = nlohmann::json::array();
            for (const auto &[date, count] : stats.busiestDays) {
                nlohmann::json day;
                day["date"] = TimeUtils::formatTimePoint(date);
                day["event_count"] = count;
                busyDays.push_back(day);
            }
            data["busiest_days"] = busyDays;
            nlohmann::json busyHours = nlohmann::json::array();
            for (const auto &[hour, count] : stats.busiestHours) {
                nlohmann::json h;
                h["hour"] = hour;
                h["event_count"] = count;
                busyHours.push_back(h);
            }
            data["busiest_hours"] = busyHours;
            out["status"] = "ok";
            out["data"] = data;
        } catch (const std::exception &ex) {
            out = { {"status","error"},{"message","Invalid input"} };
        }
        res.set_content(out.dump(), "application/json");
    });
}

} // namespace StatsRoutes
