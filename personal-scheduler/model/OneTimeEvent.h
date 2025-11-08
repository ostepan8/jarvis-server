#pragma once

#include "Event.h"
#include <chrono>
#include <memory>
#include <string>

class OneTimeEvent : public Event
{
public:
    // Constructor with optional category
    OneTimeEvent(const std::string &id,
                 const std::string &description,
                 const std::string &title,
                 std::chrono::system_clock::time_point time,
                 std::chrono::seconds duration,
                 const std::string &category = "");

    // Clone method that preserves all data including category
    std::unique_ptr<Event> clone() const override;

    // Optional: Override notify and execute if you want specific behavior
    void notify() override;
    void execute() override;
};