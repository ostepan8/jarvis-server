#pragma once
#include "ScheduledTask.h"
#include "../model/Model.h"
#include <queue>
#include <mutex>
#include <condition_variable>
#include <thread>
#include <atomic>

class EventLoop {
    struct Compare {
        bool operator()(const std::shared_ptr<ScheduledTask> &a,
                        const std::shared_ptr<ScheduledTask> &b) const {
            return a->getTime() > b->getTime();
        }
    };

    Model &model_;
    std::priority_queue<std::shared_ptr<ScheduledTask>,
                        std::vector<std::shared_ptr<ScheduledTask>>, Compare>
        queue_;
    std::mutex mtx_;
    std::condition_variable cv_;
    std::thread worker_;
    std::atomic<bool> running_{false};

    void threadFunc();

public:
    explicit EventLoop(Model &m);
    ~EventLoop();

    void start();
    void stop();
    void addTask(const std::shared_ptr<ScheduledTask> &task);
};
