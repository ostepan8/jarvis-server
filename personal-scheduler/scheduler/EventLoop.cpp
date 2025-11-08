#include "EventLoop.h"
#include <algorithm>
#include "../utils/Logger.h"

EventLoop::EventLoop(Model &m) : model_(m) {}

EventLoop::~EventLoop() { stop(); }

void EventLoop::start()
{
    if (running_)
        return;
    running_ = true;
    Logger::debug("[eventloop] starting thread");
    worker_ = std::thread(&EventLoop::threadFunc, this);
}

void EventLoop::stop()
{
    if (!running_)
        return;
    {
        std::lock_guard<std::mutex> lock(mtx_);
        running_ = false;
    }
    cv_.notify_all();
    if (worker_.joinable())
        worker_.join();
}

void EventLoop::addTask(const std::shared_ptr<ScheduledTask> &task)
{
    {
        std::lock_guard<std::mutex> lock(mtx_);
        Logger::debug("[eventloop] addTask id=", task->getId(), " cat=", task->getCategory());
        // For internal tasks (e.g., wake) do not persist to model/DB or sync to providers
        if (task->getCategory() != "internal") {
            // Upsert into model: add or update existing event by ID
            if (!model_.addEvent(*task)) {
                model_.updateEvent(task->getId(), *task);
            }
        }
        queue_.push(task);
    }
    cv_.notify_one();
}

void EventLoop::threadFunc()
{
    Logger::debug("[eventloop] thread running");
    std::unique_lock<std::mutex> lock(mtx_);
    while (running_)
    {
        Logger::debug("[eventloop] loop tick, queue size=", queue_.size());
        if (queue_.empty())
        {
            cv_.wait(lock, [&]
                     { return !running_ || !queue_.empty(); });
            Logger::debug("[eventloop] woke, running=", (int)running_.load(), ", queue size=", queue_.size());
            if (!running_)
                break;
        }

        auto next = queue_.top();
        auto now = std::chrono::system_clock::now();

        // If this queued task is outdated (model has different time for same ID), drop it
        if (auto current = model_.getEventById(next->getId())) {
            if (current->getTime() != next->getTime()) {
                queue_.pop();
                continue;
            }
        }

        if (next->hasPendingNotifications() && now >= next->getNextNotifyTime())
        {
            lock.unlock();
            next->notify();
            lock.lock();
            next->markNotificationSent();
            continue;
        }

        if (now >= next->getTime())
        {
            queue_.pop();
            lock.unlock();
            next->execute();
            // don't remove the events after they execute
            // model_.removeEvent(next->getId());
            lock.lock();
            continue;
        }

        auto wake = next->getTime();
        if (next->hasPendingNotifications())
            wake = std::min(wake, next->getNextNotifyTime());
        cv_.wait_until(lock, wake);
    }
}
