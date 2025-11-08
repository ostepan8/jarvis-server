#include "AvailabilityRoutes.h"
#include "Serialization.h"
#include "../../utils/TimeUtils.h"
#include "../../model/OneTimeEvent.h"
#include <iostream>

using namespace std::chrono;
using ApiSerialization::eventToJson;
using ApiSerialization::timeSlotToJson;

namespace AvailabilityRoutes
{

    void registerRoutes(httplib::Server &server, Model &model)
    {
        server.Get("/events/conflicts", [&model](const httplib::Request &req, httplib::Response &res)
                   {
        nlohmann::json out;
        try {
            std::string timeStr = req.get_param_value("time");
            int durationMin = 60;
            if (req.has_param("duration")) durationMin = std::stoi(req.get_param_value("duration"));
            auto time = TimeUtils::parseTimePoint(timeStr);
            auto conflicts = model.getConflicts(time, minutes(durationMin));
            nlohmann::json data = nlohmann::json::array();
            for (const auto &ev : conflicts) data.push_back(eventToJson(ev));
            out["status"] = "ok";
            out["has_conflicts"] = !conflicts.empty();
            out["data"] = data;
        } catch (const std::exception &ex) {
            out = { {"status","error"},{"message","Invalid input"} };
        }
        res.set_content(out.dump(), "application/json"); });

        server.Post("/events/validate", [&model](const httplib::Request &req, httplib::Response &res)
                    {
        nlohmann::json out;
        try {
            auto body = nlohmann::json::parse(req.body);
            std::string timeStr = body.at("time");
            int durationSec = body.value("duration", 3600);
            std::string title = body.value("title", "Test Event");
            auto time = TimeUtils::parseTimePoint(timeStr);
            OneTimeEvent testEvent("temp", "", title, time, seconds(durationSec));
            bool valid = model.validateEventTime(testEvent);
            out["status"] = "ok";
            out["valid"] = valid;
            if (!valid) {
                auto conflicts = model.getConflicts(time, duration_cast<minutes>(seconds(durationSec)));
                nlohmann::json conflictData = nlohmann::json::array();
                for (const auto &ev : conflicts) conflictData.push_back(eventToJson(ev));
                out["conflicts"] = conflictData;
            }
        } catch (const std::exception &ex) {
            out = { {"status","error"},{"message","Invalid input"} };
        }
        res.set_content(out.dump(), "application/json"); });

        server.Get(R"(/free-slots/(\d{4}-\d{2}-\d{2}))", [&model](const httplib::Request &req, httplib::Response &res)
                   {
        nlohmann::json out;
        try {
            auto date = TimeUtils::parseDate(req.matches[1]);
            int startHour = 9;
            int endHour = 17;
            int minDuration = 30;
            if (req.has_param("start")) startHour = std::stoi(req.get_param_value("start"));
            if (req.has_param("end")) endHour = std::stoi(req.get_param_value("end"));
            if (req.has_param("duration")) minDuration = std::stoi(req.get_param_value("duration"));
            auto slots = model.findFreeSlots(date, startHour, endHour, minDuration);
            nlohmann::json data = nlohmann::json::array();
            for (const auto &slot : slots) data.push_back(timeSlotToJson(slot));
            out["status"] = "ok";
            out["data"] = data;
        } catch (const std::exception &ex) {
            out = { {"status","error"},{"message","Invalid input"} };
        }
        res.set_content(out.dump(), "application/json"); });

        server.Get("/free-slots/next", [&model](const httplib::Request &req, httplib::Response &res)
                   {
        nlohmann::json out;
        try {
            int durationMin = 60;
            auto after = system_clock::now();
            if (req.has_param("duration")) durationMin = std::stoi(req.get_param_value("duration"));
            if (req.has_param("after")) after = TimeUtils::parseTimePoint(req.get_param_value("after"));
            auto slot = model.findNextAvailableSlot(minutes(durationMin), after);
            out["status"] = "ok";
            out["data"] = timeSlotToJson(slot);
        } catch (const std::exception &ex) {
            out = { {"status","error"},{"message","Invalid input"} };
        }
        res.set_content(out.dump(), "application/json"); });
    }

} // namespace AvailabilityRoutes
