#include "Model.h"
#include "../calendar/CalendarApi.h"
#include "RecurringEvent.h"
#include <algorithm>
#include <stdexcept>
#include <random>
#include <sstream>
#include <memory>
#include <cctype>
#include <regex>
#include <vector>
#include <string>
#include <iostream>
#include <cstdlib>
#include "../utils/Logger.h"

// Helper utilities for fuzzy searching
namespace
{
    std::string toLowerCopy(std::string s)
    {
        std::transform(s.begin(), s.end(), s.begin(), ::tolower);
        return s;
    }

    int levenshteinDistance(const std::string &s1, const std::string &s2)
    {
        const size_t len1 = s1.size(), len2 = s2.size();
        std::vector<int> col(len2 + 1), prevCol(len2 + 1);

        for (size_t i = 0; i <= len2; ++i)
            prevCol[i] = static_cast<int>(i);

        for (size_t i = 0; i < len1; ++i)
        {
            col[0] = static_cast<int>(i + 1);
            for (size_t j = 0; j < len2; ++j)
                col[j + 1] = std::min({prevCol[j + 1] + 1,
                                       col[j] + 1,
                                       prevCol[j] + (s1[i] == s2[j] ? 0 : 1)});
            prevCol.swap(col);
        }
        return prevCol[len2];
    }

    double similarityRatio(const std::string &a, const std::string &b)
    {
        int dist = levenshteinDistance(a, b);
        int maxLen = static_cast<int>(std::max(a.size(), b.size()));
        if (maxLen == 0)
            return 1.0;
        return 1.0 - static_cast<double>(dist) / static_cast<double>(maxLen);
    }
} // namespace

bool Model::eventExists(const std::string &id) const
{
    return std::any_of(events.begin(), events.end(), [&](const auto &pair)
                       { return pair.second->getId() == id; });
}

std::string Model::generateUniqueId() const
{
    static std::mt19937_64 gen(std::random_device{}());
    static std::uniform_int_distribution<uint64_t> dist;
    std::string id;
    std::lock_guard<std::mutex> lock(mutex_);
    do
    {
        std::stringstream ss;
        ss << std::hex << dist(gen);
        id = ss.str();
    } while (eventExists(id));
    return id;
}

Model::Model(IScheduleDatabase *db, int preloadDaysAhead)
    : db_(db)
{
    if (preloadDaysAhead < 0)
        preloadEnd_ = std::chrono::system_clock::time_point::max();
    else
        preloadEnd_ = std::chrono::system_clock::now() +
                      std::chrono::hours(24 * preloadDaysAhead);

    if (db_)
    {
        auto loaded = db_->getAllEvents();
        for (auto &e : loaded)
        {
            if (preloadDaysAhead >= 0 && e->getTime() > preloadEnd_)
                continue;
            // Track categories for loaded events
            if (!e->getCategory().empty())
            {
                categories_.insert(e->getCategory());
            }
            events.emplace(e->getTime(), std::move(e));
        }
    }
}

void Model::addCalendarApi(std::shared_ptr<CalendarApi> api)
{
    std::lock_guard<std::mutex> lock(mutex_);
    apis_.push_back(std::move(api));
}

std::vector<Event>
Model::getEvents(int maxOccurrences,
                 std::chrono::system_clock::time_point endDate) const
{
    std::vector<Event> result;
    std::lock_guard<std::mutex> lock(mutex_);
    result.reserve(events.size());


    for (const auto &kv : events)
    {
        const Event &e = *kv.second;
        if (e.getTime() > endDate)
        {
            break;
        }
        result.push_back(e);
        if (maxOccurrences > 0 && static_cast<int>(result.size()) >= maxOccurrences)
        {
            break;
        }
    }
    return result;
}

std::vector<Event> Model::getNextNEvents(int n) const
{
    std::vector<Event> occurrences;
    if (n <= 0)
        return occurrences;

    auto now = std::chrono::system_clock::now();
    auto start = now - std::chrono::seconds(1);

    std::lock_guard<std::mutex> lock(mutex_);
    if (events.empty())
        return occurrences;

    for (const auto &kv : events)
    {
        const Event &e = *kv.second;
        if (!e.isRecurring())
        {
            if (e.getTime() > now)
            {
                occurrences.push_back(e);
            }
        }
        else
        {
            const auto *re = dynamic_cast<const RecurringEvent *>(kv.second.get());
            if (!re)
                continue;

            auto times = re->getNextNOccurrences(start, n);
            for (auto t : times)
            {
                RecurringEvent occ(re->getId(), re->getDescription(), re->getTitle(),
                                   t, re->getDuration(), re->getRecurrencePattern());
                occurrences.push_back(occ);
            }
        }
    }

    std::sort(occurrences.begin(), occurrences.end(),
              [](const Event &a, const Event &b)
              { return a.getTime() < b.getTime(); });

    if (static_cast<int>(occurrences.size()) > n)
        occurrences.erase(occurrences.begin() + n, occurrences.end());
    return occurrences;
}

Event Model::getNextEvent() const
{
    auto list = getNextNEvents(1);
    if (list.empty())
        throw std::runtime_error("No upcoming events.");
    return list.front();
}

// ===== Mutation methods with proper API integration =====

bool Model::addEvent(const Event &e)
{
    std::vector<std::shared_ptr<CalendarApi>> apisCopy;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (eventExists(e.getId()))
        {
            return false;
        }
        events.emplace(e.getTime(), e.clone());

        // Track category if event has one
        std::string category = e.getCategory();
        if (!category.empty())
        {
            categories_.insert(category);
        }

        if (db_)
        {
            db_->addEvent(e);
        }
        apisCopy = apis_;
    }

    // Notify all calendar APIs and capture provider IDs
    ProviderIds collected;
    for (auto &api : apisCopy)
    {
        try
        {
            auto ids = api->addEvent(e);
            if (!ids.eventId.empty()) collected.eventId = ids.eventId;
            if (!ids.taskId.empty()) collected.taskId = ids.taskId;
        }
        catch (const std::exception &ex)
        {
            // Log error but don't fail the entire operation
        }
    }
    if (!collected.eventId.empty() || !collected.taskId.empty())
    {
        std::unordered_map<std::string, std::string> fields;
        if (!collected.eventId.empty()) fields["provider_event_id"] = collected.eventId;
        if (!collected.taskId.empty()) fields["provider_task_id"] = collected.taskId;
        updateEventFields(e.getId(), fields);
    }
    return true;
}

void Model::removeAllEvents()
{
    std::vector<std::unique_ptr<Event>> removed;
    std::vector<std::shared_ptr<CalendarApi>> apisCopy;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        for (auto &kv : events)
            removed.push_back(kv.second->clone());

        events.clear();
        categories_.clear();
        if (db_)
        {
            db_->removeAllEvents();
        }
        apisCopy = apis_;
    }

    // Notify all calendar APIs
    for (const auto &e : removed)
    {
        for (auto &api : apisCopy)
        {
            try
            {
                api->deleteEvent(*e);
            }
            catch (const std::exception &ex)
            {
                // Log error but continue with other events
            }
        }
    }
}

static std::chrono::system_clock::time_point startOfLocalDay(std::chrono::system_clock::time_point tp)
{
    time_t t = std::chrono::system_clock::to_time_t(tp);
    std::tm tm_buf;
#if defined(_MSC_VER)
    localtime_s(&tm_buf, &t);
#else
    localtime_r(&t, &tm_buf);
#endif
    tm_buf.tm_hour = 0;
    tm_buf.tm_min = 0;
    tm_buf.tm_sec = 0;
#if defined(_MSC_VER)
    time_t start_t = mktime(&tm_buf);
#else
    time_t start_t = mktime(&tm_buf);
#endif
    return std::chrono::system_clock::from_time_t(start_t);
}

std::vector<Event> Model::getEventsOnDay(std::chrono::system_clock::time_point day) const
{
    auto start = startOfLocalDay(day);
    auto end = start + std::chrono::hours(24);
    std::vector<Event> result;
    std::lock_guard<std::mutex> lock(mutex_);
    for (const auto &kv : events)
    {
        const Event &e = *kv.second;
        if (!e.isRecurring())
        {
            if (e.getTime() < start)
                continue;
            if (e.getTime() >= end)
                break;
            result.push_back(e);
        }
        else
        {
            const auto *re = dynamic_cast<const RecurringEvent *>(kv.second.get());
            if (!re)
                continue;
            auto times = re->getNextNOccurrences(start - std::chrono::seconds(1), 1000);
            for (auto t : times)
            {
                if (t >= end)
                    break;
                if (t >= start)
                {
                    RecurringEvent occ(re->getId(), re->getDescription(), re->getTitle(),
                                       t, re->getDuration(), re->getRecurrencePattern(),
                                       re->getCategory());
                    result.push_back(occ);
                }
            }
        }
    }
    std::sort(result.begin(), result.end(),
              [](const Event &a, const Event &b) { return a.getTime() < b.getTime(); });
    return result;
}

std::vector<Event> Model::getEventsInWeek(std::chrono::system_clock::time_point day) const
{
    time_t t = std::chrono::system_clock::to_time_t(day);
    std::tm tm_buf;
#if defined(_MSC_VER)
    localtime_s(&tm_buf, &t);
#else
    localtime_r(&t, &tm_buf);
#endif
    int wday = tm_buf.tm_wday; // 0=Sunday
    int diff = (wday + 6) % 7; // days since Monday
    auto start = startOfLocalDay(day) - std::chrono::hours(24 * diff);
    auto end = start + std::chrono::hours(24 * 7);
    std::vector<Event> result;
    std::lock_guard<std::mutex> lock(mutex_);
    for (const auto &kv : events)
    {
        const Event &e = *kv.second;
        if (!e.isRecurring())
        {
            if (e.getTime() < start)
                continue;
            if (e.getTime() >= end)
                break;
            result.push_back(e);
        }
        else
        {
            const auto *re = dynamic_cast<const RecurringEvent *>(kv.second.get());
            if (!re)
                continue;
            auto times = re->getNextNOccurrences(start - std::chrono::seconds(1), 1000);
            for (auto t : times)
            {
                if (t >= end)
                    break;
                if (t >= start)
                {
                    RecurringEvent occ(re->getId(), re->getDescription(), re->getTitle(),
                                       t, re->getDuration(), re->getRecurrencePattern(),
                                       re->getCategory());
                    result.push_back(occ);
                }
            }
        }
    }
    std::sort(result.begin(), result.end(),
              [](const Event &a, const Event &b) { return a.getTime() < b.getTime(); });
    return result;
}

std::vector<Event> Model::getEventsInMonth(std::chrono::system_clock::time_point day) const
{
    time_t t = std::chrono::system_clock::to_time_t(day);
    std::tm tm_buf;
#if defined(_MSC_VER)
    localtime_s(&tm_buf, &t);
#else
    localtime_r(&t, &tm_buf);
#endif
    tm_buf.tm_mday = 1;
    tm_buf.tm_hour = 0;
    tm_buf.tm_min = 0;
    tm_buf.tm_sec = 0;
#if defined(_MSC_VER)
    time_t start_t = mktime(&tm_buf);
#else
    time_t start_t = mktime(&tm_buf);
#endif
    auto start = std::chrono::system_clock::from_time_t(start_t);
    tm_buf.tm_mon += 1;
#if defined(_MSC_VER)
    time_t end_t = mktime(&tm_buf);
#else
    time_t end_t = mktime(&tm_buf);
#endif
    auto end = std::chrono::system_clock::from_time_t(end_t);

    std::vector<Event> result;
    std::lock_guard<std::mutex> lock(mutex_);
    for (const auto &kv : events)
    {
        const Event &e = *kv.second;
        if (!e.isRecurring())
        {
            if (e.getTime() < start)
                continue;
            if (e.getTime() >= end)
                break;
            result.push_back(e);
        }
        else
        {
            const auto *re = dynamic_cast<const RecurringEvent *>(kv.second.get());
            if (!re)
                continue;
            auto times = re->getNextNOccurrences(start - std::chrono::seconds(1), 1000);
            for (auto t : times)
            {
                if (t >= end)
                    break;
                if (t >= start)
                {
                    RecurringEvent occ(re->getId(), re->getDescription(), re->getTitle(),
                                       t, re->getDuration(), re->getRecurrencePattern(),
                                       re->getCategory());
                    result.push_back(occ);
                }
            }
        }
    }
    std::sort(result.begin(), result.end(),
              [](const Event &a, const Event &b) { return a.getTime() < b.getTime(); });
    return result;
}

int Model::removeEventsOnDay(std::chrono::system_clock::time_point day)
{
    auto start = startOfLocalDay(day);
    auto end = start + std::chrono::hours(24);
    std::vector<std::string> removedIds;
    std::vector<std::unique_ptr<Event>> removedEvents;
    std::vector<std::shared_ptr<CalendarApi>> apisCopy;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        for (auto it = events.begin(); it != events.end();)
        {
            auto t = it->second->getTime();
            if (t >= start && t < end)
            {
                removedIds.push_back(it->second->getId());
                removedEvents.push_back(it->second->clone());
                it = events.erase(it);
            }
            else
            {
                ++it;
            }
        }
        if (db_)
        {
            for (const auto &id : removedIds)
                db_->removeEvent(id);
        }
        apisCopy = apis_;
    }

    // Notify all calendar APIs
    for (const auto &e : removedEvents)
    {
        for (auto &api : apisCopy)
        {
            try
            {
                api->deleteEvent(*e);
            }
            catch (const std::exception &ex)
            {
                // Log error but continue
            }
        }
    }
    return static_cast<int>(removedIds.size());
}

int Model::removeEventsInWeek(std::chrono::system_clock::time_point day)
{
    time_t t = std::chrono::system_clock::to_time_t(day);
    std::tm tm_buf;
#if defined(_MSC_VER)
    localtime_s(&tm_buf, &t);
#else
    localtime_r(&t, &tm_buf);
#endif
    int wday = tm_buf.tm_wday;
    int diff = (wday + 6) % 7;
    auto start = startOfLocalDay(day) - std::chrono::hours(24 * diff);
    auto end = start + std::chrono::hours(24 * 7);
    std::vector<std::string> removedIds;
    std::vector<std::unique_ptr<Event>> removedEvents;
    std::vector<std::shared_ptr<CalendarApi>> apisCopy;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        for (auto it = events.begin(); it != events.end();)
        {
            auto t2 = it->second->getTime();
            if (t2 >= start && t2 < end)
            {
                removedIds.push_back(it->second->getId());
                removedEvents.push_back(it->second->clone());
                it = events.erase(it);
            }
            else
            {
                ++it;
            }
        }
        if (db_)
        {
            for (const auto &id : removedIds)
                db_->removeEvent(id);
        }
        apisCopy = apis_;
    }

    // Notify all calendar APIs
    for (const auto &e : removedEvents)
    {
        for (auto &api : apisCopy)
        {
            try
            {
                api->deleteEvent(*e);
            }
            catch (const std::exception &ex)
            {
                // Log error but continue
            }
        }
    }
    return static_cast<int>(removedIds.size());
}

int Model::removeEventsBefore(std::chrono::system_clock::time_point time)
{
    std::vector<std::string> removedIds;
    std::vector<std::unique_ptr<Event>> removedEvents;
    std::vector<std::shared_ptr<CalendarApi>> apisCopy;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        for (auto it = events.begin(); it != events.end();)
        {
            if (it->second->getTime() < time)
            {
                removedIds.push_back(it->second->getId());
                removedEvents.push_back(it->second->clone());
                it = events.erase(it);
            }
            else
            {
                ++it;
            }
        }
        if (db_)
        {
            for (const auto &id : removedIds)
                db_->removeEvent(id);
        }
        apisCopy = apis_;
    }

    // Notify all calendar APIs
    for (const auto &e : removedEvents)
    {
        for (auto &api : apisCopy)
        {
            try
            {
                api->deleteEvent(*e);
            }
            catch (const std::exception &ex)
            {
                // Log error but continue
            }
        }
    }
    return static_cast<int>(removedIds.size());
}

// ====== SEARCH AND QUERY METHODS ======

std::vector<Event> Model::searchEvents(const std::string &query, int maxResults) const
{
    // 1) Normalize: lowercase & drop punctuation
    static const std::regex dropPunct(R"([^a-z0-9\s])");
    auto normalize = [&](const std::string &s)
    {
        std::string lower = toLowerCopy(s);
        return std::regex_replace(lower, dropPunct, "");
    };

    // 2) Tokenize helper
    auto tokenize = [&](const std::string &s)
    {
        std::istringstream iss(s);
        std::vector<std::string> toks;
        for (std::string w; iss >> w;)
            toks.push_back(w);
        return toks;
    };

    std::string normQuery = normalize(query);
    auto qToks = tokenize(normQuery);

    std::vector<Event> results;
    std::lock_guard<std::mutex> lock(mutex_);

    for (const auto &kv : events)
    {
        const auto &evt = kv.second;
        std::string combined = evt->getTitle() + " " + evt->getDescription();
        std::string normCombined = normalize(combined);
        auto cToks = tokenize(normCombined);

        bool allMatch = true;
        for (auto &qt : qToks)
        {
            bool found = false;
            for (auto &ct : cToks)
            {
                // exact substring or fuzzy similarity
                if (ct.find(qt) != std::string::npos || similarityRatio(qt, ct) >= 0.5)
                {
                    found = true;
                    break;
                }
            }
            if (!found)
            {
                allMatch = false;
                break;
            }
        }

        if (allMatch)
        {
            results.push_back(*evt);
            if (maxResults > 0 && (int)results.size() >= maxResults)
                break;
        }
    }
    return results;
}

std::vector<Event> Model::getEventsInRange(
    std::chrono::system_clock::time_point start,
    std::chrono::system_clock::time_point end) const
{
    std::vector<Event> results;
    std::lock_guard<std::mutex> lock(mutex_);

    auto it_start = events.lower_bound(start);
    auto it_end = events.upper_bound(end);

    for (auto it = it_start; it != it_end; ++it)
    {
        results.push_back(*it->second);
    }
    return results;
}

std::vector<Event> Model::getEventsInRangeExpanded(
    std::chrono::system_clock::time_point start,
    std::chrono::system_clock::time_point end,
    int maxOccurrencesPerSeries) const
{
    std::vector<Event> results;

    std::lock_guard<std::mutex> lock(mutex_);

    // Iterate all events that could affect the window. Use lower_bound(start)
    // so we don't consider events strictly before the start unless recurring.
    // For recurring events that begin before start, we still need occurrences
    // within [start, end), so we just walk the whole container.
    for (const auto &kv : events)
    {
        const Event &e = *kv.second;
        if (!e.isRecurring())
        {
            if (e.getTime() >= start && e.getTime() < end)
            {
                results.push_back(e);
            }
        }
        else
        {
            const auto *re = dynamic_cast<const RecurringEvent *>(kv.second.get());
            if (!re)
                continue;

            // Generate occurrences starting just before 'start'
            auto times = re->getNextNOccurrences(start - std::chrono::seconds(1), maxOccurrencesPerSeries);
            for (auto t : times)
            {
                if (t >= end)
                    break;
                if (t >= start)
                {
                    RecurringEvent occ(re->getId(), re->getDescription(), re->getTitle(),
                                       t, re->getDuration(), re->getRecurrencePattern(),
                                       re->getCategory());
                    results.push_back(occ);
                }
            }
        }
    }

    std::sort(results.begin(), results.end(),
              [](const Event &a, const Event &b) { return a.getTime() < b.getTime(); });
    return results;
}

std::vector<Event> Model::getEventsByDuration(int minMinutes, int maxMinutes) const
{
    std::vector<Event> results;
    std::lock_guard<std::mutex> lock(mutex_);

    for (auto it = events.begin(); it != events.end(); ++it)
    {
        const auto &event = it->second;
        auto durationMin = std::chrono::duration_cast<std::chrono::minutes>(event->getDuration()).count();
        if (durationMin >= minMinutes && durationMin <= maxMinutes)
        {
            results.push_back(*event);
        }
    }
    return results;
}

std::vector<Event> Model::getEventsByCategory(const std::string &category) const
{
    std::vector<Event> results;
    std::lock_guard<std::mutex> lock(mutex_);

    for (auto it = events.begin(); it != events.end(); ++it)
    {
        const auto &event = it->second;
        if (event->getCategory() == category)
        {
            results.push_back(*event);
        }
    }
    return results;
}

std::set<std::string> Model::getCategories() const
{
    std::lock_guard<std::mutex> lock(mutex_);
    return categories_;
}

std::vector<Event> Model::getConflicts(
    std::chrono::system_clock::time_point time,
    std::chrono::minutes duration) const
{
    std::vector<Event> conflicts;
    auto eventEnd = time + duration;

    std::lock_guard<std::mutex> lock(mutex_);
    for (auto it = events.begin(); it != events.end(); ++it)
    {
        const auto &existingTime = it->first;
        const auto &event = it->second;
        auto existingEnd = existingTime + event->getDuration();

        // Check if times overlap
        if (!(eventEnd <= existingTime || time >= existingEnd))
        {
            conflicts.push_back(*event);
        }
    }
    return conflicts;
}

std::vector<TimeSlot> Model::findFreeSlots(
    std::chrono::system_clock::time_point date,
    int startHour,
    int endHour,
    int minDurationMinutes) const
{
    std::vector<TimeSlot> freeSlots;

    // Get start and end of working hours
    auto dayStart = startOfLocalDay(date);
    auto workStart = dayStart + std::chrono::hours(startHour);
    auto workEnd = dayStart + std::chrono::hours(endHour);

    // Get all events for this day
    auto dayEvents = getEventsOnDay(date);

    // Sort events by time
    std::sort(dayEvents.begin(), dayEvents.end(),
              [](const Event &a, const Event &b)
              { return a.getTime() < b.getTime(); });

    // Find gaps
    auto currentTime = workStart;

    for (const auto &event : dayEvents)
    {
        if (event.getTime() > currentTime && event.getTime() < workEnd)
        {
            auto gap = std::chrono::duration_cast<std::chrono::minutes>(
                event.getTime() - currentTime);

            if (gap.count() >= minDurationMinutes)
            {
                TimeSlot slot;
                slot.start = currentTime;
                slot.end = event.getTime();
                slot.duration = gap;
                freeSlots.push_back(slot);
            }
        }

        auto eventEnd = event.getTime() + event.getDuration();
        if (eventEnd > currentTime)
        {
            currentTime = eventEnd;
        }
    }

    // Check for free time after last event
    if (currentTime < workEnd)
    {
        auto gap = std::chrono::duration_cast<std::chrono::minutes>(workEnd - currentTime);
        if (gap.count() >= minDurationMinutes)
        {
            TimeSlot slot;
            slot.start = currentTime;
            slot.end = workEnd;
            slot.duration = gap;
            freeSlots.push_back(slot);
        }
    }

    return freeSlots;
}

TimeSlot Model::findNextAvailableSlot(
    std::chrono::minutes duration,
    std::chrono::system_clock::time_point after,
    int startHour,
    int endHour) const
{
    auto currentDate = after;
    const int maxDaysToSearch = 30; // Don't search forever

    for (int days = 0; days < maxDaysToSearch; ++days)
    {
        auto slots = findFreeSlots(currentDate, startHour, endHour, duration.count());

        for (const auto &slot : slots)
        {
            if (slot.start >= after && slot.duration >= duration)
            {
                TimeSlot result;
                result.start = slot.start;
                result.end = slot.start + duration;
                result.duration = duration;
                return result;
            }
        }

        currentDate += std::chrono::hours(24);
    }

    // If no slot found, return a slot far in the future
    TimeSlot result;
    result.start = after + std::chrono::hours(24 * maxDaysToSearch);
    result.end = result.start + duration;
    result.duration = duration;
    return result;
}

EventStats Model::getEventStats(
    std::chrono::system_clock::time_point start,
    std::chrono::system_clock::time_point end) const
{
    EventStats stats;
    stats.totalEvents = 0;
    stats.totalMinutes = 0;

    std::map<std::chrono::system_clock::time_point, int> eventsByDay;
    std::map<int, int> eventsByHour;

    auto events = getEventsInRangeExpanded(start, end);

    for (const auto &event : events)
    {
        stats.totalEvents++;
        stats.totalMinutes += std::chrono::duration_cast<std::chrono::minutes>(
                                  event.getDuration())
                                  .count();

        // Count by category
        std::string category = event.getCategory();
        if (category.empty())
            category = "Uncategorized";
        stats.eventsByCategory[category]++;

        // Count by day
        auto dayStart = startOfLocalDay(event.getTime());
        eventsByDay[dayStart]++;

        // Count by hour
        time_t t = std::chrono::system_clock::to_time_t(event.getTime());
        std::tm tm_buf;
#if defined(_MSC_VER)
        localtime_s(&tm_buf, &t);
#else
        localtime_r(&t, &tm_buf);
#endif
        eventsByHour[tm_buf.tm_hour]++;
    }

    // Find busiest days (top 5)
    std::vector<std::pair<std::chrono::system_clock::time_point, int>> dayPairs(
        eventsByDay.begin(), eventsByDay.end());
    std::sort(dayPairs.begin(), dayPairs.end(),
              [](const auto &a, const auto &b)
              { return a.second > b.second; });

    for (size_t i = 0; i < std::min(size_t(5), dayPairs.size()); ++i)
    {
        stats.busiestDays.push_back(dayPairs[i]);
    }

    // Find busiest hours
    for (auto it = eventsByHour.begin(); it != eventsByHour.end(); ++it)
    {
        stats.busiestHours.push_back({it->first, it->second});
    }
    std::sort(stats.busiestHours.begin(), stats.busiestHours.end(),
              [](const auto &a, const auto &b)
              { return a.second > b.second; });

    return stats;
}

// ====== UPDATE AND MODIFICATION METHODS WITH PROPER API INTEGRATION ======

bool Model::updateEvent(const std::string &id, const Event &updatedEvent)
{
    std::unique_ptr<Event> oldEvent;
    std::vector<std::shared_ptr<CalendarApi>> apisCopy;
    {
        std::lock_guard<std::mutex> lock(mutex_);

        // Find and remove the old event
        for (auto it = events.begin(); it != events.end(); ++it)
        {
            if (it->second->getId() == id)
            {
                oldEvent = std::move(it->second);
                events.erase(it);
                break;
            }
        }

        if (!oldEvent)
        {
            return false;
        }

        // Add the updated event with the same ID
        auto newEvent = updatedEvent.clone();
        events.emplace(updatedEvent.getTime(), std::move(newEvent));

        // Update category tracking
        std::string newCategory = updatedEvent.getCategory();
        if (!newCategory.empty())
        {
            categories_.insert(newCategory);
        }

        if (db_)
        {
            db_->removeEvent(id);
            db_->addEvent(updatedEvent);
        }

        apisCopy = apis_;
    }

    // Notify APIs and collect provider IDs
    ProviderIds collectedIds;
    for (auto &api : apisCopy)
    {
        try
        {
            auto ids = api->updateEvent(*oldEvent, updatedEvent);
            if (!ids.eventId.empty()) collectedIds.eventId = ids.eventId;
            if (!ids.taskId.empty()) collectedIds.taskId = ids.taskId;
        }
        catch (const std::exception &ex)
        {
            // Log error but don't fail the entire operation
        }
    }
    if (!collectedIds.eventId.empty() || !collectedIds.taskId.empty())
    {
        std::unordered_map<std::string, std::string> f;
        if (!collectedIds.eventId.empty()) f["provider_event_id"] = collectedIds.eventId;
        if (!collectedIds.taskId.empty()) f["provider_task_id"] = collectedIds.taskId;
        updateEventFields(id, f);
    }

    return true;
}

bool Model::updateEventFields(const std::string &id,
                             const std::unordered_map<std::string, std::string> &fields)
{
    std::unique_ptr<Event> oldEventCopy;
    std::vector<std::shared_ptr<CalendarApi>> apisCopy;
    Event *eventToUpdate = nullptr;
    {
        std::lock_guard<std::mutex> lock(mutex_);

        for (auto it = events.begin(); it != events.end(); ++it)
        {
            const auto &event = it->second;
            if (event->getId() == id)
            {
                // Make a copy of the old event for API notification
                oldEventCopy = event->clone();
                eventToUpdate = event.get();

                // Update each field if present
                if (fields.count("title"))
                {
                    event->setTitle(fields.at("title"));
                }
                if (fields.count("description"))
                {
                    event->setDescription(fields.at("description"));
                }
                if (fields.count("category"))
                {
                    event->setCategory(fields.at("category"));
                    categories_.insert(fields.at("category"));
                }
                if (fields.count("provider_event_id"))
                {
                    event->setProviderEventId(fields.at("provider_event_id"));
                }
                if (fields.count("provider_task_id"))
                {
                    event->setProviderTaskId(fields.at("provider_task_id"));
                }

                // Update database
                if (db_)
                {
                    db_->removeEvent(id);
                    db_->addEvent(*event);
                }

                apisCopy = apis_;
                break;
            }
        }
    }

    // Skip provider updates if we only updated provider IDs (avoid recursion)
    bool providerOnly = true;
    for (const auto &kv : fields)
    {
        if (kv.first != "provider_event_id" && kv.first != "provider_task_id")
        {
            providerOnly = false; break;
        }
    }

    if (providerOnly) return true;

    // Notify APIs
    if (eventToUpdate && oldEventCopy)
    {
        for (auto &api : apisCopy)
        {
            try
            {
                api->updateEvent(*oldEventCopy, *eventToUpdate);
            }
            catch (const std::exception &ex)
            {
                // Log error but continue
            }
        }
        return true;
    }
    return false;
}

std::unique_ptr<Event> Model::getEventById(const std::string &id) const
{
    std::lock_guard<std::mutex> lock(mutex_);

    for (auto it = events.begin(); it != events.end(); ++it)
    {
        const auto &event = it->second;
        if (event->getId() == id)
        {
            return event->clone();
        }
    }
    return nullptr;
}

bool Model::validateEventTime(const Event &e) const
{
    auto conflicts = getConflicts(e.getTime(),
                                  std::chrono::duration_cast<std::chrono::minutes>(e.getDuration()));
    return conflicts.empty();
}

std::vector<bool> Model::addEvents(const std::vector<Event> &newEvents)
{
    std::vector<bool> results;
    results.reserve(newEvents.size());

    for (const auto &event : newEvents)
    {
        results.push_back(addEvent(event));
    }

    return results;
}

int Model::removeEvents(const std::vector<std::string> &ids)
{
    int removed = 0;
    for (const auto &id : ids)
    {
        if (removeEvent(id, false)) // Use hard delete
        {
            removed++;
        }
    }
    return removed;
}

std::vector<bool> Model::updateEvents(
    const std::vector<std::pair<std::string, Event>> &updates)
{
    std::vector<bool> results;
    results.reserve(updates.size());

    for (auto it = updates.begin(); it != updates.end(); ++it)
    {
        const auto &id = it->first;
        const auto &event = it->second;
        results.push_back(updateEvent(id, event));
    }

    return results;
}

// ====== SOFT DELETE FUNCTIONALITY WITH API INTEGRATION ======

bool Model::removeEvent(const std::string &id, bool softDelete)
{
    if (softDelete)
    {
        std::lock_guard<std::mutex> lock(mutex_);

        // Find and move to deleted events (no API notification for soft delete)
        for (auto it = events.begin(); it != events.end(); ++it)
        {
            if (it->second->getId() == id)
            {
                deletedEvents.emplace(it->first, std::move(it->second));
                events.erase(it);
                return true;
            }
        }
        return false;
    }
    else
    {
        // Regular hard delete with API notification
        std::unique_ptr<Event> removedEvent;
        std::vector<std::shared_ptr<CalendarApi>> apisCopy;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            for (auto it = events.begin(); it != events.end(); ++it)
            {
                if (it->second->getId() == id)
                {
                    removedEvent = it->second->clone();
                    events.erase(it);
                    if (db_)
                    {
                        db_->removeEvent(id);
                    }
                    apisCopy = apis_;
                    break;
                }
            }
        }

        if (removedEvent)
        {
            // Notify all calendar APIs
            for (auto &api : apisCopy)
            {
                try
                {
                    api->deleteEvent(*removedEvent);
                }
                catch (const std::exception &ex)
                {
                    // Log error but continue
                }
            }
            return true;
        }
        return false;
    }
}

bool Model::removeEvent(const Event &event)
{
    return removeEvent(event.getId(), false); // Call the version with softDelete = false
}

std::vector<Event> Model::getDeletedEvents() const
{
    std::vector<Event> results;
    std::lock_guard<std::mutex> lock(mutex_);

    for (auto it = deletedEvents.begin(); it != deletedEvents.end(); ++it)
    {
        const auto &event = it->second;
        results.push_back(*event);
    }
    return results;
}

bool Model::restoreEvent(const std::string &id)
{
    std::unique_ptr<Event> restoredEvent;
    std::vector<std::shared_ptr<CalendarApi>> apisCopy;
    {
        std::lock_guard<std::mutex> lock(mutex_);

        // Find in deleted events
        for (auto it = deletedEvents.begin(); it != deletedEvents.end(); ++it)
        {
            if (it->second->getId() == id)
            {
                restoredEvent = it->second->clone();
                // Move back to active events
                events.emplace(it->first, std::move(it->second));
                deletedEvents.erase(it);

                // Update database
                if (db_)
                {
                    db_->addEvent(*restoredEvent);
                }

                apisCopy = apis_;
                break;
            }
        }
    }

    if (restoredEvent)
    {
        // Notify all calendar APIs about the restored event
        for (auto &api : apisCopy)
        {
            try
            {
                api->addEvent(*restoredEvent);
            }
            catch (const std::exception &ex)
            {
                // Log error but don't fail the entire operation
            }
        }
        return true;
    }
    return false;
}
