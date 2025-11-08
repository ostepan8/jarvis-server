#pragma once
#include "../model/Event.h"
#include <functional>
#include <chrono>
#include <memory>
#include <vector>
#include <algorithm>

class ScheduledTask : public Event {
    std::function<void()> notifyCb_;
    std::function<void()> actionCb_;
    std::vector<std::chrono::system_clock::time_point> notifyTimes_;
    size_t nextNotifyIdx_ = 0;

public:
    // Specify absolute notification times
    ScheduledTask(const std::string &id,
                  const std::string &desc,
                  const std::string &title,
                  std::chrono::system_clock::time_point time,
                  std::chrono::system_clock::duration dur,
                  std::vector<std::chrono::system_clock::time_point> notifyTimes,
                  std::function<void()> notifyCb,
                  std::function<void()> actionCb)
        : Event(id, desc, title, time, dur),
          notifyCb_(std::move(notifyCb)),
          actionCb_(std::move(actionCb)),
          notifyTimes_(std::move(notifyTimes))
    {
        std::sort(notifyTimes_.begin(), notifyTimes_.end());
    }

    // Convenience constructor: notify durations before execution
    ScheduledTask(const std::string &id,
                  const std::string &desc,
                  const std::string &title,
                  std::chrono::system_clock::time_point time,
                  std::chrono::system_clock::duration dur,
                  const std::vector<std::chrono::system_clock::duration> &notifyBefore,
                  std::function<void()> notifyCb,
                  std::function<void()> actionCb)
        : ScheduledTask(id, desc, title, time, dur,
                        std::vector<std::chrono::system_clock::time_point>{},
                        std::move(notifyCb), std::move(actionCb))
    {
        for (auto d : notifyBefore)
            notifyTimes_.push_back(time - d);
        std::sort(notifyTimes_.begin(), notifyTimes_.end());
    }

    std::unique_ptr<Event> clone() const override { return std::make_unique<ScheduledTask>(*this); }

    void notify() override { if (notifyCb_) notifyCb_(); }

    void execute() override { if (actionCb_) actionCb_(); }

    std::chrono::system_clock::time_point getNextNotifyTime() const {
        if (nextNotifyIdx_ >= notifyTimes_.size())
            return std::chrono::system_clock::time_point::max();
        return notifyTimes_[nextNotifyIdx_];
    }

    bool hasPendingNotifications() const { return nextNotifyIdx_ < notifyTimes_.size(); }

    void markNotificationSent() { if (nextNotifyIdx_ < notifyTimes_.size()) ++nextNotifyIdx_; }

};
