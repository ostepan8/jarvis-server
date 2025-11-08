#include "GoogleCalendarApi.h"
#include <iostream>
#include <fstream>
#include <sstream>
#include <cstdlib>
#include <array>
#include <memory>
#include "../model/recurrence/DailyRecurrence.h"
#include "../model/recurrence/MonthlyRecurrence.h"
#include "../model/recurrence/WeeklyRecurrence.h"
#include "../model/recurrence/YearlyRecurrence.h"
#include "../model/RecurringEvent.h"
#include "nlohmann/json.hpp"

// Implementation of GoogleCalendarApi methods

GoogleCalendarApi::GoogleCalendarApi(const std::string &credentials_file,
                                     const std::string &calendar_id,
                                     const std::string &python_script_path)
    : credentials_file_(credentials_file),
      calendar_id_(calendar_id),
      python_script_path_(python_script_path)
{
    // Constructor implementation
    std::cout << "GoogleCalendarApi initialized with:" << std::endl;
    std::cout << "  Credentials: " << credentials_file_ << std::endl;
    std::cout << "  Calendar ID: " << calendar_id_ << std::endl;
    std::cout << "  Python Script: " << python_script_path_ << std::endl;
}

std::string GoogleCalendarApi::formatDateTime(std::chrono::system_clock::time_point tp,
                                              const std::string &timezone) const
{
    auto time_t = std::chrono::system_clock::to_time_t(tp);
    std::tm tm;
#ifdef _WIN32
    gmtime_s(&tm, &time_t);
#else
    gmtime_r(&time_t, &tm);
#endif

    std::ostringstream oss;
    oss << std::put_time(&tm, "%Y-%m-%dT%H:%M:%S");

    if (timezone == "UTC")
    {
        oss << "Z";
    }
    else
    {
        // For other timezones, you'd need to add proper offset
        oss << "+00:00"; // Simplified for now
    }

    return oss.str();
}

bool GoogleCalendarApi::executePythonScript(const std::map<std::string, std::string> &env_vars, std::string *outStr) const
{
    // Helper that escapes values for use in a shell command. We use single
    // quotes to avoid interpretation of special characters and escape
    // embedded single quotes using the standard `'"'"'` sequence.
    auto shellEscape = [](const std::string &in) {
        std::string out = "'";
        for (char c : in)
        {
            if (c == '\'')
                out += "'\"'\"'"; // end quote, escape single quote, reopen
            else
                out += c;
        }
        out += "'";
        return out;
    };

    // Construct command with environment assignments instead of modifying the
    // process environment. This avoids races when multiple API calls occur
    // concurrently and prevents credentials from leaking into the parent
    // process environment.
    std::string command = "env";
    for (const auto &pair : env_vars)
    {
        command += " " + pair.first + "=" + shellEscape(pair.second);
    }
    command += " python3 " + python_script_path_ + " 2>&1"; // Redirect stderr to stdout

    // Log the command and environment for debugging
    std::cout << "Executing: " << command << std::endl;
    std::cout << "Environment variables:" << std::endl;
    for (const auto &pair : env_vars)
    {
        if (pair.first != "GCAL_CREDS")
        { // Don't log sensitive credentials
            std::cout << "  " << pair.first << "=" << pair.second << std::endl;
        }
    }

    // Execute the command
    std::array<char, 128> buffer;
    std::string result;
    std::unique_ptr<FILE, decltype(&pclose)> pipe(popen(command.c_str(), "r"), pclose);

    if (!pipe)
    {
        std::cerr << "Failed to execute Python script" << std::endl;
        return false;
    }

    while (fgets(buffer.data(), buffer.size(), pipe.get()) != nullptr)
    {
        result += buffer.data();
    }

    // Get the return code before closing
    int status = pclose(pipe.release());
    int return_code = WEXITSTATUS(status);

    // Print the output and optionally return it
    if (!result.empty())
    {
        std::cout << "Python script output:" << std::endl;
        std::cout << result << std::endl;
        if (outStr) *outStr = result;
    }

    if (return_code != 0)
    {
        std::cerr << "Python script failed with return code: " << return_code << std::endl;
        return false;
    }

    return true;
}

static std::string weekdayIntToStr(int d)
{
    static const char *names[] = {"SU", "MO", "TU", "WE", "TH", "FR", "SA"};
    return (d >= 0 && d < 7) ? names[d] : "MO";
}

static std::string formatRFC5545UTC(std::chrono::system_clock::time_point tp)
{
    std::time_t t = std::chrono::system_clock::to_time_t(tp);
    std::tm tm{};
#ifdef _MSC_VER
    gmtime_s(&tm, &t);
#else
    gmtime_r(&t, &tm);
#endif
    char buf[17];
    std::strftime(buf, sizeof(buf), "%Y%m%dT%H%M%SZ", &tm);
    return buf;
}

std::string GoogleCalendarApi::convertRecurrence(const Event &event) const
{
    if (!event.isRecurring())
        return "";

    auto recEv = dynamic_cast<const RecurringEvent *>(&event);
    if (!recEv)
        return "";

    auto pat = recEv->getRecurrencePattern();
    std::ostringstream rrule;

    std::string type = pat->type();
    rrule << "RRULE:FREQ=" << (type == "daily" ? "DAILY" : type == "weekly" ? "WEEKLY"
                                                       : type == "monthly"  ? "MONTHLY"
                                                       : type == "yearly"   ? "YEARLY"
                                                                            : "");

    // interval
    int interval = 1;
    if (type == "daily")
        interval = static_cast<DailyRecurrence *>(pat.get())->getInterval();
    else if (type == "weekly")
        interval = static_cast<WeeklyRecurrence *>(pat.get())->getInterval();
    else if (type == "monthly")
        interval = static_cast<MonthlyRecurrence *>(pat.get())->getInterval();
    else if (type == "yearly")
        interval = static_cast<YearlyRecurrence *>(pat.get())->getInterval();
    if (interval > 1)
        rrule << ";INTERVAL=" << interval;

    // weekly BYDAY
    if (type == "weekly")
    {
        auto days = static_cast<WeeklyRecurrence *>(pat.get())->getDaysOfWeek();
        if (!days.empty())
        {
            rrule << ";BYDAY=";
            for (size_t i = 0; i < days.size(); ++i)
            {
                if (i)
                    rrule << ",";
                rrule << weekdayIntToStr(static_cast<int>(days[i]));
            }
        }
    }

    // count or until
    int count = -1;
    auto endPt = std::chrono::system_clock::time_point::max();
    if (type == "daily")
    {
        count = static_cast<DailyRecurrence *>(pat.get())->getMaxOccurrences();
        endPt = static_cast<DailyRecurrence *>(pat.get())->getEndDate();
    }
    else if (type == "weekly")
    {
        count = static_cast<WeeklyRecurrence *>(pat.get())->getMaxOccurrences();
        endPt = static_cast<WeeklyRecurrence *>(pat.get())->getEndDate();
    }
    else if (type == "monthly")
    {
        count = static_cast<MonthlyRecurrence *>(pat.get())->getMaxOccurrences();
        endPt = static_cast<MonthlyRecurrence *>(pat.get())->getEndDate();
    }
    else if (type == "yearly")
    {
        count = static_cast<YearlyRecurrence *>(pat.get())->getMaxOccurrences();
        endPt = static_cast<YearlyRecurrence *>(pat.get())->getEndDate();
    }
    if (count > 0)
    {
        rrule << ";COUNT=" << count;
    }
    else if (endPt != std::chrono::system_clock::time_point::max())
    {
        rrule << ";UNTIL=" << formatRFC5545UTC(endPt);
    }

    return rrule.str();
}

bool GoogleCalendarApi::isTask(const Event &event) const
{
    auto cat = event.getCategory();
    std::transform(cat.begin(), cat.end(), cat.begin(), ::tolower);
    // Skip internal tasks (e.g., wake or maintenance) and only sync real tasks
    if (cat == "internal") return false;
    if (event.getId().rfind("wake:", 0) == 0) return false;
    return cat == "task" || event.getDuration() == std::chrono::seconds(0);
}

ProviderIds GoogleCalendarApi::addEvent(const Event &event)
{
    ProviderIds ids;
    std::cout << "\n=== GoogleCalendarApi::addEvent ===" << std::endl;
    std::cout << "Adding event: " << event.getTitle() << std::endl;

    auto start_time = formatDateTime(event.getTime());
    auto end_time = formatDateTime(event.getTime() + event.getDuration());

    std::map<std::string, std::string> env_vars;
    if (isTask(event))
    {
        env_vars = {
            {"GCAL_ACTION", "add_task"},
            {"GCAL_CREDS", credentials_file_},
            {"GCAL_TASKLIST_ID", calendar_id_},
            {"GCAL_TITLE", event.getTitle()},
            {"GCAL_DESC", event.getDescription()},
            {"GCAL_DUE", start_time},
            {"GCAL_TASK_ID", event.getId()}};
    }
    else
    {
        env_vars = {
            {"GCAL_ACTION", "add"},
            {"GCAL_CREDS", credentials_file_},
            {"GCAL_CALENDAR_ID", calendar_id_},
            {"GCAL_TITLE", event.getTitle()},
            {"GCAL_START", start_time},
            {"GCAL_END", end_time},
            {"GCAL_DESC", event.getDescription()},
            {"GCAL_TZ", "UTC"},
            {"GCAL_EVENT_ID", event.getId()}};
    }

    // Add recurrence if applicable for calendar events only
    if (!isTask(event) && event.isRecurring())
    {
        env_vars["GCAL_RECURRENCE"] = convertRecurrence(event);
    }

    std::string output;
    if (!executePythonScript(env_vars, &output))
    {
        throw std::runtime_error("Failed to add event to Google Calendar");
    }
    // Prefer machine-readable JSON lines emitted as GCAL_JSON: {...}
    try {
        std::istringstream iss(output);
        std::string line;
        nlohmann::json last;
        while (std::getline(iss, line)) {
            auto pos = line.find("GCAL_JSON:");
            if (pos != std::string::npos) {
                std::string jsonPart = line.substr(pos + std::string("GCAL_JSON:").size());
                try { last = nlohmann::json::parse(jsonPart); } catch (...) {}
            }
        }
        if (!last.is_null() && last.is_object()) {
            if (last.value("status", "") == "ok") {
                if (last.contains("event_id")) ids.eventId = last["event_id"].get<std::string>();
                if (last.contains("task_id")) ids.taskId = last["task_id"].get<std::string>();
            } else if (last.value("status", "") == "error") {
                std::cerr << "Google addEvent error: " << last.dump() << "\n";
            }
        }
    } catch (...) {}
    return ids;
}

ProviderIds GoogleCalendarApi::updateEvent(const Event &oldEvent, const Event &newEvent)
{
    ProviderIds ids;
    std::cout << "\n=== GoogleCalendarApi::updateEvent ===" << std::endl;
    std::cout << "Updating event: " << oldEvent.getTitle() << " -> " << newEvent.getTitle() << std::endl;

    if (oldEvent.getId() == newEvent.getId())
    {
        // Update existing event
        auto start_time = formatDateTime(newEvent.getTime());
        auto end_time = formatDateTime(newEvent.getTime() + newEvent.getDuration());

        std::map<std::string, std::string> env_vars;
        if (isTask(newEvent))
        {
            env_vars = {
                {"GCAL_ACTION", "update_task"},
                {"GCAL_CREDS", credentials_file_},
                {"GCAL_TASKLIST_ID", calendar_id_},
                {"GCAL_TASK_ID", newEvent.getId()},
                {"GCAL_TITLE", newEvent.getTitle()},
                {"GCAL_DESC", newEvent.getDescription()},
                {"GCAL_DUE", start_time}};
        }
        else
        {
            env_vars = {
                {"GCAL_ACTION", "update"},
                {"GCAL_CREDS", credentials_file_},
                {"GCAL_CALENDAR_ID", calendar_id_},
                {"GCAL_EVENT_ID", newEvent.getId()},
                {"GCAL_TITLE", newEvent.getTitle()},
                {"GCAL_START", start_time},
                {"GCAL_END", end_time},
                {"GCAL_DESC", newEvent.getDescription()},
                {"GCAL_TZ", "UTC"}};
        }

        std::string output;
        if (!executePythonScript(env_vars, &output))
        {
            throw std::runtime_error("Failed to update event in Google Calendar");
        }
        try {
            std::istringstream iss(output);
            std::string line; nlohmann::json last;
            while (std::getline(iss, line)) {
                auto pos = line.find("GCAL_JSON:");
                if (pos != std::string::npos) {
                    auto jsonPart = line.substr(pos + std::string("GCAL_JSON:").size());
                    try { last = nlohmann::json::parse(jsonPart); } catch (...) {}
                }
            }
            if (!last.is_null() && last.is_object()) {
                if (last.value("status", "") == "error") {
                std::cerr << "Google updateEvent error: " << last.dump() << "\n";
                } else if (last.value("status", "") == "ok") {
                    if (last.contains("event_id")) ids.eventId = last["event_id"].get<std::string>();
                    if (last.contains("task_id")) ids.taskId = last["task_id"].get<std::string>();
                }
            }
        } catch (...) {}
    }
    else
    {
        // Delete old and add new
        deleteEvent(oldEvent);
        ids = addEvent(newEvent);
    }
    return ids;
}

void GoogleCalendarApi::deleteEvent(const Event &event)
{
    std::cout << "\n=== GoogleCalendarApi::deleteEvent ===" << std::endl;
    std::cout << "Deleting event: " << event.getTitle() << std::endl;

    std::map<std::string, std::string> env_vars = {
        {"GCAL_CREDS", credentials_file_}};

    if (isTask(event))
    {
        env_vars["GCAL_ACTION"] = "delete_task";
        env_vars["GCAL_TASKLIST_ID"] = calendar_id_;
        // Prefer provider task ID if available
        std::string taskId = event.getProviderTaskId().empty() ? event.getId() : event.getProviderTaskId();
        env_vars["GCAL_TASK_ID"] = taskId;
    }
    else
    {
        env_vars["GCAL_ACTION"] = "delete";
        env_vars["GCAL_CALENDAR_ID"] = calendar_id_;
        // Prefer provider event ID (exact Google ID), fallback to transformed local ID
        std::string evId = event.getProviderEventId().empty() ? event.getId() : event.getProviderEventId();
        env_vars["GCAL_EVENT_ID"] = evId;
        // Provide helpful context for fallback deletion in the script
        env_vars["GCAL_TITLE"] = event.getTitle();
        env_vars["GCAL_START"] = formatDateTime(event.getTime());
        env_vars["GCAL_END"] = formatDateTime(event.getTime() + event.getDuration());
        env_vars["GCAL_TZ"] = "UTC";
    }

    if (!executePythonScript(env_vars))
    {
        throw std::runtime_error("Failed to delete event from Google Calendar");
    }
}

bool GoogleCalendarApi::testConnection() const
{
    std::cout << "Testing Google Calendar connection..." << std::endl;

    // Check if the Python script exists
    std::ifstream file(python_script_path_);
    if (!file.good())
    {
        std::cerr << "Python script not found at: " << python_script_path_ << std::endl;
        return false;
    }
    file.close();

    // Check if credentials file exists
    std::ifstream creds_file(credentials_file_);
    if (!creds_file.good())
    {
        std::cerr << "Credentials file not found at: " << credentials_file_ << std::endl;
        return false;
    }
    creds_file.close();

    std::cout << "Python script and credentials file found. Connection test passed." << std::endl;
    return true;
}
