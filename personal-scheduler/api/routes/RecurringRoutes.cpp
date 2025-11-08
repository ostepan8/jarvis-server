#include "RecurringRoutes.h"
#include "Serialization.h"
#include "../../utils/TimeUtils.h"
#include "../../model/RecurringEvent.h"
#include "../../model/recurrence/DailyRecurrence.h"
#include "../../model/recurrence/WeeklyRecurrence.h"
#include "../../model/recurrence/MonthlyRecurrence.h"
#include "../../model/recurrence/YearlyRecurrence.h"
#include "../../utils/WeekDay.h"
#include "../../utils/Sanitize.h"
#include <iostream>

using namespace std::chrono;
using ApiSerialization::eventToJson;

namespace RecurringRoutes {

static std::shared_ptr<RecurrencePattern> parsePattern(const nlohmann::json &j,
                                                       system_clock::time_point start) {
    std::string type = j.at("type");
    int interval = j.value("interval", 1);
    int maxOcc = j.value("max", -1);
    std::string endStr = j.value("end", "");
    auto end = endStr.empty() ? system_clock::time_point::max()
                              : TimeUtils::parseTimePoint(endStr);

    if (type == "daily") {
        return std::make_shared<DailyRecurrence>(start, interval, maxOcc, end);
    } else if (type == "weekly") {
        std::vector<Weekday> days;
        if (j.contains("days")) {
            for (const auto &d : j["days"]) {
                days.push_back(static_cast<Weekday>(d.get<int>()));
            }
        }
        return std::make_shared<WeeklyRecurrence>(start, days, interval, maxOcc, end);
    } else if (type == "monthly") {
        return std::make_shared<MonthlyRecurrence>(start, interval, maxOcc, end);
    } else if (type == "yearly") {
        return std::make_shared<YearlyRecurrence>(start, interval, maxOcc, end);
    }
    throw std::runtime_error("Unknown recurrence type");
}

void registerRoutes(httplib::Server &server, Model &model) {
    server.Get("/recurring", [&model](const httplib::Request &, httplib::Response &res) {
        nlohmann::json out;
        try {
            auto horizon = system_clock::now() + hours(24 * 365 * 5);
            auto events = model.getEvents(-1, horizon);
            nlohmann::json data = nlohmann::json::array();
            for (const auto &ev : events) {
                if (ev.isRecurring()) data.push_back(eventToJson(ev));
            }
            out["status"] = "ok";
            out["data"] = data;
        } catch (const std::exception &ex) {
            out = { {"status","error"},{"message","Invalid input"} };
        }
        res.set_content(out.dump(), "application/json");
    });

    server.Post("/recurring", [&model](const httplib::Request &req, httplib::Response &res) {
        nlohmann::json out;
        try {
            auto body = nlohmann::json::parse(req.body);
            std::string id = model.generateUniqueId();
            std::string title = sanitize(body.value("title", ""));
            std::string description = sanitize(body.value("description", ""), 500);
            std::string startStr = body.at("start");
            int durationSec = body.value("duration", 3600);
            std::string category = sanitize(body.value("category", ""));
            auto start = TimeUtils::parseTimePoint(startStr);
            auto pattern = parsePattern(body.at("pattern"), start);
            RecurringEvent e(id, description, title, start, seconds(durationSec), pattern, category);
            if (!model.addEvent(e)) throw std::runtime_error("Failed to add event");
            out["status"] = "ok";
            out["data"] = eventToJson(e);
        } catch (const std::exception &ex) {
            out = { {"status","error"},{"message","Invalid input"} };
        }
        res.set_content(out.dump(), "application/json");
    });

    server.Put(R"(/recurring/(.+))", [&model](const httplib::Request &req, httplib::Response &res) {
        nlohmann::json out;
        try {
            std::string id = req.matches[1];
            auto body = nlohmann::json::parse(req.body);
            std::string title = sanitize(body.at("title"));
            std::string description = sanitize(body.value("description", ""), 500);
            std::string startStr = body.at("start");
            int durationSec = body.value("duration", 3600);
            std::string category = sanitize(body.value("category", ""));
            auto start = TimeUtils::parseTimePoint(startStr);
            auto pattern = parsePattern(body.at("pattern"), start);
            RecurringEvent updated(id, description, title, start, seconds(durationSec), pattern, category);
            if (!model.updateEvent(id, updated)) throw std::runtime_error("Failed to update event");
            out["status"] = "ok";
            out["data"] = eventToJson(updated);
        } catch (const std::exception &ex) {
            out = { {"status","error"},{"message","Invalid input"} };
        }
        res.set_content(out.dump(), "application/json");
    });

    server.Delete(R"(/recurring/(.+))", [&model](const httplib::Request &req, httplib::Response &res) {
        nlohmann::json out;
        try {
            std::string id = req.matches[1];
            if (!model.removeEvent(id)) throw std::runtime_error("ID not found");
            out["status"] = "ok";
        } catch (const std::exception &ex) {
            out = { {"status","error"},{"message","Invalid input"} };
        }
        res.set_content(out.dump(), "application/json");
    });
}

} // namespace RecurringRoutes
