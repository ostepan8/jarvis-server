#include "EventRoutes.h"
#include "Serialization.h"
#include "../../utils/TimeUtils.h"
#include "../../utils/Sanitize.h"
#include "../../model/OneTimeEvent.h"
#include <climits>
#include <iostream>

using namespace std::chrono;
using ApiSerialization::eventToJson;

namespace EventRoutes
{

    void registerRoutes(httplib::Server &server, Model &model, WakeScheduler *wake)
    {
        // All events (optionally expanded occurrences)
        server.Get("/events", [&model](const httplib::Request &req, httplib::Response &res)
                   {
        
        nlohmann::json out;
        try {
            bool expanded = req.has_param("expanded") && (req.get_param_value("expanded") == "true" || req.get_param_value("expanded") == "1");
            auto now = system_clock::now();
            auto defaultEnd = now + hours(24 * 365);
            auto start = now;
            auto end = defaultEnd;
            if (req.has_param("start")) start = TimeUtils::parseTimePoint(req.get_param_value("start"));
            if (req.has_param("end")) end = TimeUtils::parseTimePoint(req.get_param_value("end"));

            nlohmann::json data = nlohmann::json::array();
            if (expanded) {
                auto events = model.getEventsInRangeExpanded(start, end);
                for (const auto &ev : events) data.push_back(eventToJson(ev));
            } else {
                // Seed view (non-expanded), use far-future cutoff as before
                auto events = model.getEvents(-1, defaultEnd);
                for (const auto &ev : events) data.push_back(eventToJson(ev));
            }
            out["status"] = "ok";
            out["data"] = data;
        } catch (const std::exception &ex) {
            out = { {"status","error"},{"message","Invalid input"} };
        }
        res.set_content(out.dump(), "application/json"); });

        // Next event
        server.Get("/events/next", [&model](const httplib::Request &, httplib::Response &res)
                   {
        
        nlohmann::json out;
        try {
            auto ev = model.getNextEvent();
            out["status"] = "ok";
            out["data"] = eventToJson(ev);
        } catch (const std::runtime_error &) {
            out["status"] = "ok";
            out["data"] = nullptr;
        } catch (const std::exception &ex) {
            out = { {"status","error"},{"message","Invalid input"} };
        }
        res.set_content(out.dump(), "application/json"); });

        // Search events
        server.Get("/events/search", [&model](const httplib::Request &req, httplib::Response &res)
                   {
        
        nlohmann::json out;
        try {
            std::string query = req.get_param_value("q");
            int maxResults = -1;
            if (req.has_param("max")) {
                maxResults = std::stoi(req.get_param_value("max"));
            }
            auto events = model.searchEvents(query, maxResults);
            nlohmann::json data = nlohmann::json::array();
            for (const auto &ev : events) {
                data.push_back(eventToJson(ev));
            }
            out["status"] = "ok";
            out["data"] = data;
        } catch (const std::exception &ex) {
            out = { {"status","error"},{"message","Invalid input"} };
        }
        res.set_content(out.dump(), "application/json"); });

        // Events in range
        server.Get(R"(/events/range/(\d{4}-\d{2}-\d{2})/(\d{4}-\d{2}-\d{2}))", [&model](const httplib::Request &req, httplib::Response &res)
                   {
        
        nlohmann::json out;
        try {
            auto start = TimeUtils::parseDate(req.matches[1]);
            auto end = TimeUtils::parseDate(req.matches[2]) + hours(24);
            auto events = model.getEventsInRangeExpanded(start, end);
            nlohmann::json data = nlohmann::json::array();
            for (const auto &ev : events) {
                data.push_back(eventToJson(ev));
            }
            out["status"] = "ok";
            out["data"] = data;
        } catch (const std::exception &ex) {
            out = { {"status","error"},{"message","Invalid input"} };
        }
        res.set_content(out.dump(), "application/json"); });

        // Events by duration
        server.Get("/events/duration", [&model](const httplib::Request &req, httplib::Response &res)
                   {
        
        nlohmann::json out;
        try {
            int minMinutes = 0;
            int maxMinutes = INT_MAX;
            if (req.has_param("min")) minMinutes = std::stoi(req.get_param_value("min"));
            if (req.has_param("max")) maxMinutes = std::stoi(req.get_param_value("max"));
            auto events = model.getEventsByDuration(minMinutes, maxMinutes);
            nlohmann::json data = nlohmann::json::array();
            for (const auto &ev : events) data.push_back(eventToJson(ev));
            out["status"] = "ok";
            out["data"] = data;
        } catch (const std::exception &ex) {
            out = { {"status","error"},{"message","Invalid input"} };
        }
        res.set_content(out.dump(), "application/json"); });

        // Categories list
        server.Get("/categories", [&model](const httplib::Request &, httplib::Response &res)
                   {
        
        nlohmann::json out;
        try {
            auto categories = model.getCategories();
            nlohmann::json data = nlohmann::json::array();
            for (const auto &cat : categories) data.push_back(cat);
            out["status"] = "ok";
            out["data"] = data;
        } catch (const std::exception &ex) {
            out = { {"status","error"},{"message","Invalid input"} };
        }
        res.set_content(out.dump(), "application/json"); });

        // Events by category
        server.Get(R"(/events/category/(.+))", [&model](const httplib::Request &req, httplib::Response &res)
                   {
        
        nlohmann::json out;
        try {
            std::string category = req.matches[1];
            auto events = model.getEventsByCategory(category);
            nlohmann::json data = nlohmann::json::array();
            for (const auto &ev : events) data.push_back(eventToJson(ev));
            out["status"] = "ok";
            out["data"] = data;
        } catch (const std::exception &ex) {
            out = { {"status","error"},{"message","Invalid input"} };
        }
        res.set_content(out.dump(), "application/json"); });

        // Events by day
        server.Get(R"(/events/day/(\d{4}-\d{2}-\d{2}))", [&model](const httplib::Request &req, httplib::Response &res)
                   {
        
        nlohmann::json out;
        try {
            auto day = TimeUtils::parseDate(req.matches[1]);
            auto events = model.getEventsOnDay(day);
            nlohmann::json data = nlohmann::json::array();
            for (const auto &ev : events) data.push_back(eventToJson(ev));
            out["status"] = "ok";
            out["data"] = data;
        } catch (const std::exception &ex) {
            out = { {"status","error"},{"message","Invalid input"} };
        }
        res.set_content(out.dump(), "application/json"); });

        // Events by week
        server.Get(R"(/events/week/(\d{4}-\d{2}-\d{2}))", [&model](const httplib::Request &req, httplib::Response &res)
                   {
        
        nlohmann::json out;
        try {
            auto day = TimeUtils::parseDate(req.matches[1]);
            auto events = model.getEventsInWeek(day);
            nlohmann::json data = nlohmann::json::array();
            for (const auto &ev : events) data.push_back(eventToJson(ev));
            out["status"] = "ok";
            out["data"] = data;
        } catch (const std::exception &ex) {
            out = { {"status","error"},{"message","Invalid input"} };
        }
        res.set_content(out.dump(), "application/json"); });

        // Events by month
        server.Get(R"(/events/month/(\d{4}-\d{2}))", [&model](const httplib::Request &req, httplib::Response &res)
                   {
        
        nlohmann::json out;
        try {
            auto month = TimeUtils::parseMonth(req.matches[1]);
            auto events = model.getEventsInMonth(month);
            nlohmann::json data = nlohmann::json::array();
            for (const auto &ev : events) data.push_back(eventToJson(ev));
            out["status"] = "ok";
            out["data"] = data;
        } catch (const std::exception &ex) {
            out = { {"status","error"},{"message","Invalid input"} };
        }
        res.set_content(out.dump(), "application/json"); });

        // Create new event
        server.Post("/events", [&model, wake](const httplib::Request &req, httplib::Response &res)
                    {
        
        nlohmann::json out;
        try {
            auto body = nlohmann::json::parse(req.body);
            std::string id = model.generateUniqueId();
            std::string title = sanitize(body.value("title", ""));
            std::string description = sanitize(body.value("description", ""), 500);
            std::string timeStr = body.at("time");
            int durationSec = body.value("duration", 0);
            std::string category = sanitize(body.value("category", ""));
            auto time = TimeUtils::parseTimePoint(timeStr);
            OneTimeEvent e(id, description, title, time, seconds(durationSec), category);
            if (!model.addEvent(e)) {
                throw std::runtime_error("Failed to add event");
            }
            out["status"] = "ok";
            out["data"] = eventToJson(e);
            if (wake) {
                auto day = TimeUtils::parseDate(TimeUtils::formatTimePoint(e.getTime()).substr(0,10));
                wake->scheduleForDate(day);
            }
        } catch (const std::exception &ex) {
            out = { {"status","error"},{"message","Invalid input"} };
        }
        res.set_content(out.dump(), "application/json"); });

        // Update event
        server.Put(R"(/events/(.+))", [&model, wake](const httplib::Request &req, httplib::Response &res)
                   {
        
        nlohmann::json out;
        try {
            std::string id = req.matches[1];
            auto body = nlohmann::json::parse(req.body);
            std::string title = sanitize(body.at("title"));
            std::string description = sanitize(body.value("description", ""), 500);
            std::string timeStr = body.at("time");
            int durationSec = body.value("duration", 3600);
            std::string category = sanitize(body.value("category", ""));
            auto time = TimeUtils::parseTimePoint(timeStr);
            OneTimeEvent updated(id, description, title, time, seconds(durationSec));
            updated.setCategory(category);
            if (!model.updateEvent(id, updated)) {
                throw std::runtime_error("Failed to update event");
            }
            out["status"] = "ok";
            out["data"] = eventToJson(updated);
            if (wake) {
                auto day = TimeUtils::parseDate(TimeUtils::formatTimePoint(updated.getTime()).substr(0,10));
                wake->scheduleForDate(day);
            }
        } catch (const std::exception &ex) {
            out = { {"status","error"},{"message","Invalid input"} };
        }
        res.set_content(out.dump(), "application/json"); });

        // Patch event
        server.Patch(R"(/events/(.+))", [&model, wake](const httplib::Request &req, httplib::Response &res)
                     {
        
        nlohmann::json out;
        try {
            std::string id = req.matches[1];
            auto body = nlohmann::json::parse(req.body);
            auto existing = model.getEventById(id);
            if (!existing) throw std::runtime_error("Event not found");
            std::string title = sanitize(body.value("title", existing->getTitle()));
            std::string description = sanitize(body.value("description", existing->getDescription()), 500);
            std::string timeStr = body.value("time", TimeUtils::formatTimePoint(existing->getTime()));
            int durationSec = body.value("duration", (int)duration_cast<seconds>(existing->getDuration()).count());
            std::string category = sanitize(body.value("category", existing->getCategory()));
            auto time = TimeUtils::parseTimePoint(timeStr);
            OneTimeEvent updated(id, description, title, time, seconds(durationSec));
            updated.setCategory(category);
            if (!model.updateEvent(id, updated)) {
                throw std::runtime_error("Failed to update event");
            }
            out["status"] = "ok";
            out["data"] = eventToJson(updated);
            if (wake) {
                auto day = TimeUtils::parseDate(TimeUtils::formatTimePoint(updated.getTime()).substr(0,10));
                wake->scheduleForDate(day);
            }
        } catch (const std::exception &ex) {
            out = { {"status","error"},{"message","Invalid input"} };
        }
        res.set_content(out.dump(), "application/json"); });

        // Deleted events
        server.Get("/events/deleted", [&model](const httplib::Request &, httplib::Response &res)
                   {
        
        nlohmann::json out;
        try {
            auto events = model.getDeletedEvents();
            nlohmann::json data = nlohmann::json::array();
            for (const auto &ev : events) data.push_back(eventToJson(ev));
            out["status"] = "ok";
            out["data"] = data;
        } catch (const std::exception &ex) {
            out = { {"status","error"},{"message","Invalid input"} };
        }
        res.set_content(out.dump(), "application/json"); });

        // Restore event
        server.Post(R"(/events/(.+)/restore)", [&model](const httplib::Request &req, httplib::Response &res)
                    {
        
        nlohmann::json out;
        try {
            std::string id = req.matches[1];
            bool restored = model.restoreEvent(id);
            if (!restored) throw std::runtime_error("Event not found in deleted events");
            out["status"] = "ok";
            out["message"] = "Event restored successfully";
        } catch (const std::exception &ex) {
            out = { {"status","error"},{"message","Invalid input"} };
        }
        res.set_content(out.dump(), "application/json"); });

        // Delete all events
        server.Delete("/events", [&model, wake](const httplib::Request &, httplib::Response &res)
                      {
        
        nlohmann::json out;
        try {
            model.removeAllEvents();
            out["status"] = "ok";
            if (wake) wake->scheduleToday();
        } catch (const std::exception &ex) {
            out = { {"status","error"},{"message","Invalid input"} };
        }
        res.set_content(out.dump(), "application/json"); });

        // Delete day
        server.Delete(R"(/events/day/(\d{4}-\d{2}-\d{2}))", [&model, wake](const httplib::Request &req, httplib::Response &res)
                      {
        
        nlohmann::json out;
        try {
            auto day = TimeUtils::parseDate(req.matches[1]);
            int n = model.removeEventsOnDay(day);
            out["status"] = "ok";
            out["removed"] = n;
            if (wake) wake->scheduleForDate(day);
        } catch (const std::exception &ex) {
            out = { {"status","error"},{"message","Invalid input"} };
        }
        res.set_content(out.dump(), "application/json"); });

        // Delete week
        server.Delete(R"(/events/week/(\d{4}-\d{2}-\d{2}))", [&model, wake](const httplib::Request &req, httplib::Response &res)
                      {
        
        nlohmann::json out;
        try {
            auto day = TimeUtils::parseDate(req.matches[1]);
            int n = model.removeEventsInWeek(day);
            out["status"] = "ok";
            out["removed"] = n;
            if (wake) wake->scheduleToday();
        } catch (const std::exception &ex) {
            out = { {"status","error"},{"message","Invalid input"} };
        }
        res.set_content(out.dump(), "application/json"); });

        // Delete before time
        server.Delete(R"(/events/before/(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}))", [&model, wake](const httplib::Request &req, httplib::Response &res)
                      {
        
        nlohmann::json out;
        try {
            std::string ts = req.matches[1];
            for (auto &c : ts) if (c == 'T') c = ' ';
            auto tp = TimeUtils::parseTimePoint(ts);
            int n = model.removeEventsBefore(tp);
            out["status"] = "ok";
            out["removed"] = n;
            if (wake) wake->scheduleToday();
        } catch (const std::exception &ex) {
            out = { {"status","error"},{"message","Invalid input"} };
        }
        res.set_content(out.dump(), "application/json"); });

        // Delete single event
        server.Delete(R"(/events/(.+))", [&model, wake](const httplib::Request &req, httplib::Response &res)
                      {
        
        nlohmann::json out;
        try {
            std::string id = req.matches[1];
            bool softDelete = req.has_param("soft") && req.get_param_value("soft") == "true";
            bool ok = model.removeEvent(id, softDelete);
            if (!ok) throw std::runtime_error("ID not found");
            out["status"] = "ok";
            out["soft_delete"] = softDelete;
            if (wake) wake->scheduleToday();
        } catch (const std::exception &ex) {
            out = { {"status","error"},{"message","Invalid input"} };
        }
        res.set_content(out.dump(), "application/json"); });
    }

} // namespace EventRoutes
