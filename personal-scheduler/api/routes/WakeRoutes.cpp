#include "WakeRoutes.h"
#include "../../utils/TimeUtils.h"
#include "nlohmann/json.hpp"
#include <iostream>

using namespace std;
using namespace std::chrono;

namespace WakeRoutes {

void registerRoutes(httplib::Server &server, Model &model, WakeScheduler *wake, SettingsStore *settings) {
    // GET /wake/config
    server.Get("/wake/config", [settings](const httplib::Request &, httplib::Response &res){
        nlohmann::json out;
        try {
            out["status"] = "ok";
            nlohmann::json cfg;
            cfg["enabled"] = settings->getBool("wake.enabled").value_or(true);
            cfg["baseline_time"] = settings->getString("wake.baseline_time").value_or("02:00");
            cfg["lead_minutes"] = settings->getInt("wake.lead_minutes").value_or(45);
            cfg["only_when_events"] = settings->getBool("wake.only_when_events").value_or(false);
            cfg["skip_weekends"] = settings->getBool("wake.skip_weekends").value_or(false);
            cfg["server_url"] = settings->getString("wake.server_url").value_or("");
            out["data"] = cfg;
        } catch (...) {
            out = {{"status","error"},{"message","Failed to read config"}};
        }
        res.set_content(out.dump(), "application/json");
    });

    // PUT /wake/config
    server.Put("/wake/config", [wake, settings](const httplib::Request &req, httplib::Response &res){
        nlohmann::json out;
        try {
            // Admin-protect: if ADMIN_API_KEY is set, require it
            const char *adm = getenv("ADMIN_API_KEY");
            if (adm && *adm) {
                auto header = req.get_header_value("Authorization");
                if (header != std::string(adm) && header != std::string("Bearer ") + adm) {
                    out = {{"status","error"},{"message","Admin privileges required"}};
                    res.status = 403;
                    res.set_content(out.dump(), "application/json");
                    return;
                }
            }
            auto body = nlohmann::json::parse(req.body);
            if (body.contains("enabled")) settings->setBool("wake.enabled", body["enabled"].get<bool>());
            if (body.contains("baseline_time")) settings->setString("wake.baseline_time", body["baseline_time"].get<std::string>());
            if (body.contains("lead_minutes")) settings->setInt("wake.lead_minutes", body["lead_minutes"].get<int>());
            if (body.contains("only_when_events")) settings->setBool("wake.only_when_events", body["only_when_events"].get<bool>());
            if (body.contains("skip_weekends")) settings->setBool("wake.skip_weekends", body["skip_weekends"].get<bool>());
            if (body.contains("server_url")) settings->setString("wake.server_url", body["server_url"].get<std::string>());
            out["status"] = "ok";
            // Recompute for today
            if (wake) wake->scheduleToday();
        } catch (...) {
            out = {{"status","error"},{"message","Invalid input"}};
        }
        res.set_content(out.dump(), "application/json");
    });

    // POST /wake/preview?day=YYYY-MM-DD
    server.Post(R"(/wake/preview/(\d{4}-\d{2}-\d{2}))", [wake](const httplib::Request &req, httplib::Response &res){
        nlohmann::json out;
        try {
            if (!wake) throw std::runtime_error("wake not available");
            auto day = TimeUtils::parseDate(req.matches[1]);
            std::string reason;
            std::vector<Event> first;
            auto tp = wake->previewForDate(day, reason, first);
            nlohmann::json data;
            if (tp == system_clock::time_point::min()) {
                data["wake_time"] = nullptr;
                data["reason"] = reason;
            } else {
                data["wake_time"] = TimeUtils::formatTimePoint(tp);
                data["reason"] = reason;
            }
            nlohmann::json brief = nlohmann::json::array();
            for (const auto &e : first) {
                brief.push_back({{"id", e.getId()}, {"title", e.getTitle()}, {"time", TimeUtils::formatTimePoint(e.getTime())}});
            }
            data["first_events"] = brief;
            out["status"] = "ok";
            out["data"] = data;
        } catch (...) {
            out = {{"status","error"},{"message","Invalid input"}};
        }
        res.set_content(out.dump(), "application/json");
    });
}

} // namespace WakeRoutes
