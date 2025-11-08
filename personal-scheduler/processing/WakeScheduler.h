#pragma once

#include <string>
#include <chrono>
#include "../model/Model.h"
#include "../scheduler/EventLoop.h"
#include "../database/SettingsStore.h"

class WakeScheduler {
public:
    WakeScheduler(Model &model, EventLoop &loop, SettingsStore &settings);

    // Compute and schedule today's wake task (if applicable)
    void scheduleToday();
    // Schedule a maintenance task that runs daily at local midnight to reschedule today's wake
    void scheduleDailyMaintenance();

    // Recompute and schedule for a specific date (local day start)
    void scheduleForDate(std::chrono::system_clock::time_point day);

    // Compute-only (no mutation), returns wake time or min() if skipped; fills reason and firstEvents
    std::chrono::system_clock::time_point previewForDate(std::chrono::system_clock::time_point day,
                                                         std::string &reason,
                                                         std::vector<Event> &firstEvents) const;

private:
    Model &model_;
    EventLoop &loop_;
    SettingsStore &settings_;

    std::chrono::system_clock::time_point localMidnight(std::chrono::system_clock::time_point tp) const;
    std::chrono::system_clock::time_point nextLocalMidnight(std::chrono::system_clock::time_point now) const;
    std::chrono::system_clock::time_point parseLocalTimeHM(std::chrono::system_clock::time_point day,
                                                           const std::string &hm) const;
    std::chrono::system_clock::time_point computeWakeTime(std::chrono::system_clock::time_point day,
                                                          std::string &reason,
                                                          std::vector<Event> &firstEvents) const;
};
