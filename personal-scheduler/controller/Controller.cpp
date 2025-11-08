// Controller.cpp
#include "Controller.h"
#include "../model/OneTimeEvent.h"
#include "../model/RecurringEvent.h"
#include "../model/recurrence/DailyRecurrence.h"
#include "../model/recurrence/WeeklyRecurrence.h"
#include "../utils/WeekDay.h"
#include <iostream>
#include <iomanip>
#include <sstream>
#include <chrono>
#include <ctime>
#include <unordered_map>
#include <functional>
#include <algorithm>
#include <cctype>
#include "../utils/TimeUtils.h"
#include <stdexcept>
#include "../scheduler/ScheduledTask.h"
#include "../utils/ActionRegistry.h"
#include "../utils/BuiltinActions.h"
#include "../utils/NotificationRegistry.h"
#include "../utils/BuiltinNotifiers.h"
#include <memory>
#include "../database/SettingsStore.h"
#include "../utils/CommandRegistry.h"
#include "../utils/TimeUtils.h"
#include "../utils/Logger.h"
#include "nlohmann/json.hpp"

using namespace std;
using namespace std::chrono;

Controller::Controller(Model &model, View &view, EventLoop *loop)
    : model_(model), view_(view), loop_(loop)
{
}


void Controller::printNextEvent()
{
    try
    {
        Event next = model_.getNextEvent();
        cout << "Next event: ["
             << next.getId() << "] \""
             << next.getTitle() << "\" @ "
            << TimeUtils::formatTimePoint(next.getTime())
             << "\n";
    }
    catch (const exception &)
    {
        cout << "(no upcoming events)\n";
    }
}

string Controller::addRecurringEvent(const string &title,
                                     const string &desc,
                                     system_clock::time_point start,
                                     system_clock::duration dur,
                                     std::shared_ptr<RecurrencePattern> pattern)
{
    string idCopy = model_.generateUniqueId();
    string descCopy = desc;
    string titleCopy = title;
    RecurringEvent e(idCopy, descCopy, titleCopy, start, dur, std::move(pattern));
    model_.addEvent(e);
    return idCopy;
}

void Controller::run()
{
    cout << "=== Scheduler CLI ===\n";
    cout << "(All times are entered and displayed in local time,\n"
            " but stored internally in UTC.)\n";

    // Register built-in actions. Additional actions can be registered
    // elsewhere before Controller::run is invoked.
    BuiltinActions::registerAll();
    BuiltinNotifiers::registerAll();


    // Sophisticated CLI command registry: map command name -> function + description.
    CommandRegistry::clear();

    CommandRegistry::registerCommand("add", [&]() {
        string id = model_.generateUniqueId();
        cout << "Enter title: ";
        string title; getline(cin, title);
        cout << "Enter description: ";
        string desc; getline(cin, desc);
        cout << "Enter hours from now (integer): ";
        int hrs; cin >> hrs; cin.ignore(numeric_limits<streamsize>::max(), '\n');
        auto now = system_clock::now();
        auto tp = now + hours(hrs);
        OneTimeEvent e{id, desc, title, tp, hours(1)};
        model_.addEvent(e);
        scheduleTask(e);
        cout << "Added event [" << id << "]\n";
    }, "Add one-time event in N hours");

    CommandRegistry::registerCommand("addat", [&]() {
        string id = model_.generateUniqueId();
        cout << "Enter title: ";
        string title; getline(cin, title);
        cout << "Enter description: ";
        string desc; getline(cin, desc);
        cout << "Enter time (YYYY-MM-DD HH:MM): ";
        string timestr; getline(cin, timestr);
        system_clock::time_point tp;
        try { tp = TimeUtils::parseTimePoint(timestr); }
        catch(const exception &e) { cout << e.what() << "\n"; return; }
        OneTimeEvent e{id, desc, title, tp, hours(1)};
        model_.addEvent(e);
        scheduleTask(e);
        cout << "Added event [" << id << "]\n";
    }, "Add one-time event at timestamp");

    CommandRegistry::registerCommand("addrec", [&]() {
        string title, desc, timestr, rtype;
        cout << "Enter title: "; getline(cin, title);
        cout << "Enter description: "; getline(cin, desc);
        cout << "Enter start time (YYYY-MM-DD HH:MM): "; getline(cin, timestr);
        system_clock::time_point start;
        try { start = TimeUtils::parseTimePoint(timestr); }
        catch(const exception &e) { cout << e.what() << "\n"; return; }
        // Ask for duration (minutes)
        cout << "Enter duration in minutes (default 60): ";
        string durStr; getline(cin, durStr);
        int durMin = 60;
        if (!durStr.empty()) {
            try { durMin = stoi(durStr); }
            catch(const exception &) { cout << "Invalid duration, using 60 minutes.\n"; durMin = 60; }
            if (durMin <= 0) { cout << "Duration must be positive, using 60 minutes.\n"; durMin = 60; }
        }
        cout << "Recurrence type (daily/weekly): "; getline(cin, rtype);
        shared_ptr<RecurrencePattern> pat;
        if (rtype == "weekly" || rtype == "w") {
            cout << "Interval in weeks: "; int weeks; cin >> weeks;
            cin.ignore(numeric_limits<streamsize>::max(), '\n');
            cout << "Days of week (0=Sun..6=Sat comma separated): ";
            string daysStr; getline(cin, daysStr);
            vector<Weekday> days; string tmp; istringstream ds(daysStr);
            while (getline(ds,tmp,',')) { int d=stoi(tmp); days.push_back(static_cast<Weekday>(d)); }
            pat = make_shared<WeeklyRecurrence>(start, days, weeks);
        } else {
            cout << "Interval in days: "; int days; cin >> days;
            cin.ignore(numeric_limits<streamsize>::max(), '\n');
            pat = make_shared<DailyRecurrence>(start, days);
        }
        string id = addRecurringEvent(title, desc, start, std::chrono::minutes(durMin), pat);
        cout << "Added recurring event [" << id << "]\n";
    }, "Add a recurring event");

    CommandRegistry::registerCommand("addtask", [&]() {
        if (!loop_) { std::cout << "(event loop not running)\n"; return; }
        string title, desc, timestr, notifierName, actionName;
        cout << "Enter title: "; getline(cin, title);
        cout << "Enter description: "; getline(cin, desc);
        cout << "Enter time (YYYY-MM-DD HH:MM): "; getline(cin, timestr);
        system_clock::time_point tp;
        try { tp = TimeUtils::parseTimePoint(timestr); } catch(const exception &e) {
            cout << e.what() << "\n"; return; }
        auto notifiers = NotificationRegistry::availableNotifiers();
        if(notifiers.empty()) {
            cout << "No notifiers registered\n"; return; }
        cout << "Available notifiers:";
        for(const auto &n : notifiers) cout << " " << n;
        cout << "\nEnter notifier name: ";
        getline(cin, notifierName);
        auto note = NotificationRegistry::getNotifier(notifierName);
        if(!note) { cout << "Unknown notifier\n"; return; }

        auto actions = ActionRegistry::availableActions();
        if(actions.empty()) {
            cout << "No actions registered\n"; return; }
        cout << "Available actions:";
        for(const auto &n : actions) cout << " " << n;
        cout << "\nEnter action name: ";
        getline(cin, actionName);
        auto act = ActionRegistry::getAction(actionName);
        if(!act) { cout << "Unknown action\n"; return; }

        cout << "Enter notification lead times (e.g. 60m,30m or 1h). Blank for 10m: ";
        string notifyStr; getline(cin, notifyStr);
        std::vector<std::chrono::system_clock::duration> leadTimes;
        if(notifyStr.empty()) {
            leadTimes.push_back(std::chrono::minutes(10));
        } else {
            std::istringstream ns(notifyStr); string tok;
            auto parseDur = [](std::string t){
                t.erase(std::remove_if(t.begin(), t.end(), ::isspace), t.end());
                if(t.empty()) return std::chrono::minutes(0);
                char suf = t.back();
                int val;
                if(suf=='h' || suf=='H') { val = std::stoi(t.substr(0,t.size()-1)); return std::chrono::minutes(val*60); }
                if(suf=='m' || suf=='M') { val = std::stoi(t.substr(0,t.size()-1)); return std::chrono::minutes(val); }
                val = std::stoi(t); return std::chrono::minutes(val);
            };
            while(getline(ns,tok,',')) {
                if(tok.empty()) continue;
                leadTimes.push_back(parseDur(tok));
            }
            if(leadTimes.empty()) leadTimes.push_back(std::chrono::minutes(10));
        }

        string id = model_.generateUniqueId();
        auto notifyCb = [note,id,title](){ note(id,title); };
        OneTimeEvent e{id, desc, title, tp, std::chrono::seconds(0), "task"};
        // Stash names so ScheduledTask clone persists them to DB
        e.setNotifierName(notifierName);
        e.setActionName(actionName);
        scheduleTask(e, leadTimes, notifyCb, act);
        cout << "Added task [" << id << "]\n";
    }, "Add a scheduled task with notifier+action");

    CommandRegistry::registerCommand("remove", [&]() {
        cout << "Enter event ID to remove: ";
        string id; getline(cin, id);
        if (model_.removeEvent(id))
            cout << "Removed event [" << id << "]\n";
        else
            cout << "No event with ID [" << id << "] found.\n";
    }, "Remove event by ID");

    CommandRegistry::registerCommand("removeday", [&]() {
        cout << "Enter date (YYYY-MM-DD): ";
        string d; getline(cin, d);
        system_clock::time_point day;
        try { day = TimeUtils::parseDate(d); } catch(const exception &e) { cout << e.what() << "\n"; return; }
        int n = model_.removeEventsOnDay(day);
        cout << "Removed " << n << " events.\n";
    }, "Remove all events on a day");

    CommandRegistry::registerCommand("removeweek", [&]() {
        cout << "Enter date within week (YYYY-MM-DD): ";
        string d; getline(cin, d);
        system_clock::time_point day;
        try { day = TimeUtils::parseDate(d); } catch(const exception &e) { cout << e.what() << "\n"; return; }
        int n = model_.removeEventsInWeek(day);
        cout << "Removed " << n << " events.\n";
    }, "Remove all events in the week containing date");

    CommandRegistry::registerCommand("removebefore", [&]() {
        cout << "Enter time (YYYY-MM-DD HH:MM): ";
        string ts; getline(cin, ts);
        system_clock::time_point tp;
        try { tp = TimeUtils::parseTimePoint(ts); } catch(const exception &e) { cout << e.what() << "\n"; return; }
        int n = model_.removeEventsBefore(tp);
        cout << "Removed " << n << " events.\n";
    }, "Remove all events before a time");

    CommandRegistry::registerCommand("clear", [&]() {
        removeAllEvents();
        cout << "All events removed.\n";
    }, "Clear all events");

    CommandRegistry::registerCommand("list", [&]() { view_.render(); }, "List all events (seeds)");
    CommandRegistry::registerCommand("next", [&]() { printNextEvent(); }, "Show next event");

    CommandRegistry::registerCommand("day", [&]() {
        cout << "Enter date (YYYY-MM-DD): ";
        string d; getline(cin, d);
        system_clock::time_point day;
        try { day = TimeUtils::parseDate(d); } catch(const exception &e) { cout << e.what() << "\n"; return; }
        auto evs = model_.getEventsOnDay(day);
        view_.renderEvents(evs);
    }, "List events on a day");

    CommandRegistry::registerCommand("week", [&]() {
        cout << "Enter date within week (YYYY-MM-DD): ";
        string d; getline(cin, d);
        system_clock::time_point day;
        try { day = TimeUtils::parseDate(d); } catch(const exception &e) { cout << e.what() << "\n"; return; }
        auto evs = model_.getEventsInWeek(day);
        view_.renderEvents(evs);
    }, "List events in a week");

    CommandRegistry::registerCommand("month", [&]() {
        cout << "Enter month (YYYY-MM): ";
        string m; getline(cin, m);
        system_clock::time_point mo;
        try { mo = TimeUtils::parseMonth(m); } catch(const exception &e) { cout << e.what() << "\n"; return; }
        auto evs = model_.getEventsInMonth(mo);
        view_.renderEvents(evs);
    }, "List events in a month");

    CommandRegistry::registerCommand("nextn", [&]() {
        cout << "Enter number of events: ";
        int n; cin >> n; cin.ignore(numeric_limits<streamsize>::max(), '\n');
        auto evs = model_.getNextNEvents(n);
        view_.renderEvents(evs);
    }, "List next N events");

    // Preview wake-up time for a day (default today)
    CommandRegistry::registerCommand("wake", [&]() {
        using namespace std::chrono;
        cout << "Enter date (YYYY-MM-DD) or leave blank for today: ";
        string d; getline(cin, d);
        system_clock::time_point day;
        try {
            if (d.empty()) {
                day = TimeUtils::parseDate(TimeUtils::formatTimePoint(system_clock::now()).substr(0,10));
            } else {
                day = TimeUtils::parseDate(d);
            }
        } catch(const exception &e) { cout << e.what() << "\n"; return; }

        SettingsStore settings("events.db");
        string baselineStr = settings.getString("wake.baseline_time").value_or("14:00");
        int lead = settings.getInt("wake.lead_minutes").value_or(45);
        bool onlyWhen = settings.getBool("wake.only_when_events").value_or(false);
        bool skipWeekends = settings.getBool("wake.skip_weekends").value_or(false);

        // Compute baseline time on the given day
        auto base = [&](){
            int hh = 2, mm = 0;
            if (!baselineStr.empty()) {
                std::sscanf(baselineStr.c_str(), "%d:%d", &hh, &mm);
            }
            time_t t = system_clock::to_time_t(day);
            std::tm tm_buf{};
#if defined(_MSC_VER)
            localtime_s(&tm_buf, &t);
#else
            localtime_r(&t, &tm_buf);
#endif
            tm_buf.tm_hour = hh; tm_buf.tm_min = mm; tm_buf.tm_sec = 0;
            return system_clock::from_time_t(mktime(&tm_buf));
        }();

        auto events = model_.getEventsOnDay(day);
        if (events.empty()) {
            if (onlyWhen) { cout << "Wake: skipped (no events)\n"; return; }
            if (skipWeekends) {
                time_t t = system_clock::to_time_t(day);
                std::tm tm_buf{};
#if defined(_MSC_VER)
                localtime_s(&tm_buf, &t);
#else
                localtime_r(&t, &tm_buf);
#endif
                if (tm_buf.tm_wday == 0 || tm_buf.tm_wday == 6) { cout << "Wake: skipped (weekend)\n"; return; }
            }
            cout << "Wake: " << TimeUtils::formatTimePoint(base) << " (baseline)\n";
            return;
        }
        auto earliest = std::min_element(events.begin(), events.end(), [](const Event &a, const Event &b){ return a.getTime() < b.getTime(); })->getTime();
        auto candidate = earliest - minutes(lead);
        auto chosen = base;
        string reason = "baseline";
        if (onlyWhen || earliest < base) { chosen = candidate; reason = "earliest-minus-lead"; }
        cout << "Wake: " << TimeUtils::formatTimePoint(chosen) << " (" << reason << ")\n";
    }, "Preview wake-up time for a day");

    // Configure wake settings interactively
    CommandRegistry::registerCommand("wakeconfig", [&]() {
        SettingsStore settings("events.db");
        string baseline = settings.getString("wake.baseline_time").value_or("09:00");
        int lead = settings.getInt("wake.lead_minutes").value_or(45);
        bool onlyWhen = settings.getBool("wake.only_when_events").value_or(false);
        bool skipWeekends = settings.getBool("wake.skip_weekends").value_or(false);
        cout << "Current wake config:\n";
        cout << "  baseline_time: " << baseline << "\n";
        cout << "  lead_minutes: " << lead << "\n";
        cout << "  only_when_events: " << (onlyWhen?"true":"false") << "\n";
        cout << "  skip_weekends: " << (skipWeekends?"true":"false") << "\n";
        cout << "Enter new baseline_time (HH:MM) or blank to keep: ";
        string in; getline(cin, in);
        if (!in.empty()) settings.setString("wake.baseline_time", in);
        cout << "Enter new lead_minutes or blank to keep: ";
        string inLead; getline(cin, inLead);
        if (!inLead.empty()) { try { settings.setInt("wake.lead_minutes", stoi(inLead)); } catch(...) { cout << "Invalid lead, keeping.\n"; } }
        cout << "only_when_events (true/false) or blank to keep: ";
        string inOnly; getline(cin, inOnly);
        if (!inOnly.empty()) { for (auto &c: inOnly) c=tolower(c); settings.setBool("wake.only_when_events", (inOnly=="true"||inOnly=="1"||inOnly=="yes")); }
        cout << "skip_weekends (true/false) or blank to keep: ";
        string inSkip; getline(cin, inSkip);
        if (!inSkip.empty()) { for (auto &c: inSkip) c=tolower(c); settings.setBool("wake.skip_weekends", (inSkip=="true"||inSkip=="1"||inSkip=="yes")); }
        cout << "Updated wake settings.\n";
    }, "Configure wake baseline/lead/weekend behavior");

    // Send a fake GoodMorning request with an example event
    CommandRegistry::registerCommand("wakeping", [&]() {
        SettingsStore settings("events.db");
        std::string url = settings.getString("wake.server_url").value_or("");
        if (url.empty()) {
            const char* envUrl = std::getenv("WAKE_SERVER_URL");
            if (envUrl) url = envUrl;
        }
        if (url.empty()) {
            cout << "WAKE_SERVER_URL not configured. Set it in .env or via wakeconfig.\n";
            return;
        }
        std::string userId = settings.getString("user.id").value_or(std::getenv("USER_ID") ? std::getenv("USER_ID") : "user-123");
        std::string tzName = settings.getString("user.timezone").value_or(std::getenv("USER_TIMEZONE") ? std::getenv("USER_TIMEZONE") : "America/New_York");
        int lead = settings.getInt("wake.lead_minutes").value_or(45);
        std::string baseline = settings.getString("wake.baseline_time").value_or("14:00");

        using namespace std::chrono;
        auto now = system_clock::now();
        // Example earliest event tomorrow at 11:45
        auto tomorrow = TimeUtils::parseDate(TimeUtils::formatTimePoint(now).substr(0,10)) + hours(24);
        auto earliestStart = tomorrow + hours(11) + minutes(45);
        // Example wake time at earliest - lead
        auto wakeTime = earliestStart - minutes(lead);

        nlohmann::json payload;
        payload["user_id"] = userId;
        payload["wake_time"] = TimeUtils::formatRFC3339Local(wakeTime);
        payload["timezone"] = tzName;
        nlohmann::json ctx;
        ctx["source"] = "scheduler-cli";
        ctx["reason"] = "earliest-minus-lead";
        ctx["baseline_time"] = baseline;
        ctx["lead_minutes"] = lead;
        ctx["date"] = TimeUtils::formatTimePoint(tomorrow);
        ctx["job_id"] = std::string("wake:") + TimeUtils::formatTimePoint(tomorrow).substr(0,10);
        nlohmann::json earliest;
        earliest["id"] = "sample-recurring";
        earliest["title"] = "Robot Dynamics and Control";
        earliest["description"] = "Example class";
        earliest["start"] = TimeUtils::formatRFC3339Local(earliestStart);
        earliest["duration_sec"] = 3600;
        ctx["earliest_event"] = earliest;
        ctx["first_events"] = nlohmann::json::array({
            { {"id","sample-recurring"}, {"title","Robot Dynamics and Control"}, {"start", TimeUtils::formatRFC3339Local(earliestStart)} }
        });
        payload["context"] = ctx;

        Logger::info("[wakeping] POST ", url);
        BuiltinActions::httpPostJson(url, payload.dump());
        cout << "Sent test GoodMorning request to " << url << "\n";
    }, "Send a test GoodMorning request with an example event");

    bool done = false;
    string line;
    cout << "Type 'help' to list commands. Type 'quit' to exit.\n";
    while (!done)
    {
        cout << "> ";
        if (!getline(cin, line)) break;
        istringstream iss(line); string cmd; iss >> cmd;
        if (cmd == "help")
        {
            auto list = CommandRegistry::available();
            cout << "Commands (" << list.size() << "):\n";
            for (const auto &p : list) {
                cout << "  " << p.first;
                if (!p.second.empty()) cout << " - " << p.second;
                cout << "\n";
            }
            continue;
        }
        if (cmd == "quit")
        {
            done = true;
        }
        else
        {
            if (auto c = CommandRegistry::getCommand(cmd)) {
                c->fn();
            } else {
                cout << "Unknown command. Type 'help'.\n";
            }
        }
    }

    cout << "Exiting scheduler.\n";
}

void Controller::scheduleTask(const Event &e,
                              std::vector<std::chrono::system_clock::duration> notifyBefore,
                              std::function<void()> notifyCb,
                              std::function<void()> actionCb)
{
    if (!loop_) return;
    if (!notifyCb)
        notifyCb = [id = e.getId(), title = e.getTitle()]() {
            std::cout << "[" << id << "] \"" << title << "\" notification\n";
        };
    if (!actionCb)
        actionCb = [id = e.getId(), title = e.getTitle()]() {
            std::cout << "[" << id << "] \"" << title << "\" executing\n";
        };
    auto now = std::chrono::system_clock::now();
    std::vector<std::chrono::system_clock::time_point> notifyTimes;
    if (e.getTime() - now >= std::chrono::minutes(10)) {
        for (auto d : notifyBefore) {
            auto tp = e.getTime() - d;
            if (tp > now)
                notifyTimes.push_back(tp);
        }
    }

    // Use a distinct ID for the scheduled task to avoid collisions with the
    // base calendar event stored in the model/database.
    std::string taskId = model_.generateUniqueId();
    auto task = std::make_shared<ScheduledTask>(
        taskId, e.getDescription(), e.getTitle(), e.getTime(), e.getDuration(),
        notifyTimes, std::move(notifyCb), std::move(actionCb));
    task->setCategory("task");
    task->setNotifierName(e.getNotifierName());
    task->setActionName(e.getActionName());
    loop_->addTask(task);
}

void Controller::removeAllEvents()
{
    model_.removeAllEvents();
}

void Controller::removeEventsOnDay(std::chrono::system_clock::time_point day)
{
    model_.removeEventsOnDay(day);
}

void Controller::removeEventsInWeek(std::chrono::system_clock::time_point day)
{
    model_.removeEventsInWeek(day);
}

void Controller::removeEventsBefore(std::chrono::system_clock::time_point time)
{
    model_.removeEventsBefore(time);
}
