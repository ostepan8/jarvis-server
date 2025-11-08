#pragma once
#include "../../model/Event.h"
#include "../../model/OneTimeEvent.h"
#include "../../utils/TimeUtils.h"
#include "nlohmann/json.hpp"
#include <chrono>

namespace ApiSerialization {
    using json = nlohmann::json;
    using namespace std::chrono;

    inline json eventToJson(const Event &e) {
        json j;
        j["id"] = e.getId();
        j["title"] = e.getTitle();
        j["description"] = e.getDescription();
        j["time"] = TimeUtils::formatTimePoint(e.getTime());
        j["duration"] = duration_cast<seconds>(e.getDuration()).count();
        j["category"] = e.getCategory();
        return j;
    }

    inline json timeSlotToJson(const TimeSlot &slot) {
        json j;
        j["start"] = TimeUtils::formatTimePoint(slot.start);
        j["end"] = TimeUtils::formatTimePoint(slot.end);
        j["duration_minutes"] = slot.duration.count();
        return j;
    }
} // namespace ApiSerialization
