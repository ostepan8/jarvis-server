#include "OneTimeEvent.h"

OneTimeEvent::OneTimeEvent(const std::string &id,
                           const std::string &desc,
                           const std::string &title,
                           std::chrono::system_clock::time_point time,
                           std::chrono::seconds duration,
                           const std::string &category)
    : Event(id, desc, title, time, duration, category)
{
    // OneTimeEvent is explicitly not recurring
    setRecurring(false);
}

// Clone implementation
std::unique_ptr<Event> OneTimeEvent::clone() const
{
    auto ptr = std::make_unique<OneTimeEvent>(
        getId(),
        getDescription(),
        getTitle(),
        getTime(),
        std::chrono::duration_cast<std::chrono::seconds>(getDuration()),
        getCategory());
    ptr->setNotifierName(getNotifierName());
    ptr->setActionName(getActionName());
    ptr->setProviderEventId(getProviderEventId());
    ptr->setProviderTaskId(getProviderTaskId());
    return ptr;
}
// Notify implementation (optional - can be customized)
void OneTimeEvent::notify()
{
    // Default implementation - can be overridden or extended
    // Examples:
    // - Send email notification
    // - Push mobile notification
    // - Log to notification system
    // - Trigger webhook

    // For now, just call base class implementation
    Event::notify();
}

// Execute implementation (optional - can be customized)
void OneTimeEvent::execute()
{
    // Default implementation - can be overridden or extended
    // Examples:
    // - Run associated script
    // - Update event status
    // - Trigger automation
    // - Record execution in audit log

    // For now, just call base class implementation
    Event::execute();
}
