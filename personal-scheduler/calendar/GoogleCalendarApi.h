#pragma once

#include "CalendarApi.h"
#include <cstdlib>
#include <sstream>
#include <stdexcept>
#include <memory>
#include <array>
#include <iostream>
#include <iomanip>
#include <chrono>
#include <map>
#include <fstream>

#ifdef _WIN32
#include <windows.h>
#define popen _popen
#define pclose _pclose
#define setenv(name, value, overwrite) _putenv_s(name, value)
#define WEXITSTATUS(x) (x)
#else
#include <unistd.h>
#include <sys/wait.h>
#endif

class GoogleCalendarApi : public CalendarApi
{
private:
    std::string credentials_file_;
    std::string calendar_id_;
    std::string python_script_path_;

    // Helper to format datetime for Google Calendar (RFC3339)
    std::string formatDateTime(std::chrono::system_clock::time_point tp,
                               const std::string &timezone = "UTC") const;

    // Helper to execute Python script with environment variables
    // If out is provided, captures combined stdout/stderr output
    bool executePythonScript(const std::map<std::string, std::string> &env_vars, std::string *out = nullptr) const;

    // Convert Event recurrence pattern to Google Calendar RRULE
    std::string convertRecurrence(const Event &event) const;

    bool isTask(const Event &event) const;

public:
    GoogleCalendarApi(const std::string &credentials_file,
                      const std::string &calendar_id = "primary",
                      const std::string &python_script_path = "calendar_integration/gcal_service.py");

    ProviderIds addEvent(const Event &event) override;
    ProviderIds updateEvent(const Event &oldEvent, const Event &newEvent) override;
    void deleteEvent(const Event &event) override;

    // Optional: Add a method to test the connection
    bool testConnection() const;
};
