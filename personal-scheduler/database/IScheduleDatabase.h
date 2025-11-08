#pragma once

#include <vector>
#include <string>
#include <memory>
#include "../model/Event.h"

class IScheduleDatabase {
public:
    virtual ~IScheduleDatabase() = default;

    virtual bool addEvent(const Event &e) = 0;
    virtual bool removeEvent(const std::string &id) = 0;
    virtual bool removeAllEvents() = 0;
    virtual std::vector<std::unique_ptr<Event>> getAllEvents() const = 0;
};
