#include "TaskRoutes.h"
#include "Serialization.h"
#include "../../utils/TimeUtils.h"
#include "../../utils/Sanitize.h"
#include "../../utils/NotificationRegistry.h"
#include "../../utils/ActionRegistry.h"
#include "../../scheduler/ScheduledTask.h"
#include <iostream>
#include <algorithm>

using namespace std::chrono;
using ApiSerialization::eventToJson;

namespace TaskRoutes
{

    static std::chrono::minutes parseDuration(const std::string &t)
    {
        std::string s = t;
        s.erase(std::remove_if(s.begin(), s.end(), ::isspace), s.end());
        if (s.empty())
            return std::chrono::minutes(0);
        char suf = s.back();
        int val;
        if (suf == 'h' || suf == 'H')
        {
            val = std::stoi(s.substr(0, s.size() - 1));
            return std::chrono::minutes(val * 60);
        }
        if (suf == 'm' || suf == 'M')
        {
            val = std::stoi(s.substr(0, s.size() - 1));
            return std::chrono::minutes(val);
        }
        val = std::stoi(s);
        return std::chrono::minutes(val);
    }

    void registerRoutes(httplib::Server &server, Model &model, EventLoop *loop)
    {
        // Registering task routes

        server.Get("/notifiers", [](const httplib::Request &, httplib::Response &res)
                   {
        nlohmann::json out;
        try {
            auto names = NotificationRegistry::availableNotifiers();
            out["status"] = "ok";
            out["data"] = names;
        } catch (const std::exception &e) {
            out = {{"status","error"},{"message","Invalid input"}};
        }
        res.set_content(out.dump(), "application/json"); });

        server.Get("/actions", [](const httplib::Request &, httplib::Response &res)
                   {
        nlohmann::json out;
        try {
            auto names = ActionRegistry::availableActions();
            out["status"] = "ok";
            out["data"] = names;
        } catch (const std::exception &e) {
            out = {{"status","error"},{"message","Invalid input"}};
        }
        res.set_content(out.dump(), "application/json"); });

        server.Get("/tasks", [&model](const httplib::Request &, httplib::Response &res)
                   {
        nlohmann::json out;
        try {
            auto horizon = system_clock::now() + hours(24 * 365 * 5);
            auto events = model.getEvents(-1, horizon);
            nlohmann::json data = nlohmann::json::array();
            int taskCount = 0;
            for (const auto &ev : events) {
                if (ev.getCategory() == "task") {
                    data.push_back(eventToJson(ev));
                    taskCount++;
                }
            }
            out["status"] = "ok";
            out["data"] = data;
        } catch (const std::exception &e) {
            out = {{"status","error"},{"message","Invalid input"}};
        }
        res.set_content(out.dump(), "application/json"); });

        if (loop)
        {
            // Event loop provided, registering POST /tasks endpoint
            server.Post("/tasks", [loop, &model](const httplib::Request &req, httplib::Response &res)
                        {
            nlohmann::json out;
            try {
                auto body = nlohmann::json::parse(req.body);
                std::string title = sanitize(body.value("title", ""));
                std::string description = sanitize(body.value("description", ""), 500);
                std::string timeStr = body.at("time");
                std::string notifierName = body.at("notifier");
                std::string actionName = body.at("action");
                
                
                auto time = TimeUtils::parseTimePoint(timeStr);
                
                std::vector<std::chrono::system_clock::duration> notifyDur;
                if (body.contains("notify") && body["notify"].is_array()) {
                    for (const auto &el : body["notify"]) {
                        auto duration = parseDuration(el.get<std::string>());
                        notifyDur.push_back(duration);
                    }
                    if (notifyDur.empty()) {
                        notifyDur.push_back(std::chrono::minutes(10));
                    }
                } else {
                    notifyDur.push_back(std::chrono::minutes(10));
                }
                
                auto notifier = NotificationRegistry::getNotifier(notifierName);
                auto action = ActionRegistry::getAction(actionName);
                
                if (!notifier) {
                    throw std::runtime_error("invalid notifier");
                }
                if (!action) {
                    throw std::runtime_error("invalid action");
                }
                
                std::string id = model.generateUniqueId();
                
                auto notifyCb = [notifier,id,title](){ 
                    notifier(id,title); 
                };
                
                OneTimeEvent e(id, description, title, time, seconds(0), "task");
                auto now = system_clock::now();
                std::vector<system_clock::time_point> notifyTimes;
                
                if (e.getTime() - now >= std::chrono::minutes(10)) {
                    for (auto d : notifyDur) {
                        auto tp = e.getTime() - d;
                        if (tp > now) {
                            notifyTimes.push_back(tp);
                        }
                    }
                }
                
                auto task = std::make_shared<ScheduledTask>(id, description, title,
                                            e.getTime(), e.getDuration(), notifyTimes,
                                            notifyCb, action);
                task->setCategory("task");
                // Persist notifier/action names for re-enqueue after restart
                task->setNotifierName(notifierName);
                task->setActionName(actionName);
                loop->addTask(task);
                
                out["status"] = "ok";
                out["data"] = eventToJson(e);
            } catch (const std::exception &e) {
                out = {{"status","error"},{"message","Invalid input"}};
            }
            res.set_content(out.dump(), "application/json"); });
        }
        else
        {
            // Warning: No event loop provided, POST /tasks endpoint not registered
        }

        // Task routes registered successfully
    }

} // namespace TaskRoutes
