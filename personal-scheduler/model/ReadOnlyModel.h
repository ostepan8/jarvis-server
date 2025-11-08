// ReadOnlyModel.h
#pragma once

#include <vector>
#include <chrono>
#include "Event.h"

/*
  A purely “read‐only” interface for any scheduler‐style model.
  It only exposes query methods; no add/remove mutations.
*/
class ReadOnlyModel
{
public:
    virtual ~ReadOnlyModel() = default;

    // Return up to maxOccurrences Events occurring before endDate.
    // (maxOccurrences == -1 means “no limit.”)
    virtual std::vector<Event>
    getEvents(int maxOccurrences,
              std::chrono::system_clock::time_point endDate) const = 0;

    // Return the next Event in chronological order (throws if none).
    virtual Event getNextEvent() const = 0;
};
