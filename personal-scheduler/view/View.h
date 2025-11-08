#pragma once

#include <vector>
#include "../model/Event.h"
#include "../model/ReadOnlyModel.h"

/*
  A “passive” View that only knows how to display the events in some ReadOnlyModel.
  It stores a reference to a ReadOnlyModel, and subclasses override render() to fetch
  data from model_ and print it.  No mutations are allowed from the View.
*/
class View
{
protected:
    // Reference to a ReadOnlyModel (so View can fetch events but never modify them)
    const ReadOnlyModel &model_;

    // Only subclasses may call this constructor, passing in a ReadOnlyModel reference.
    explicit View(const ReadOnlyModel &model)
        : model_(model)
    {
    }

public:
    virtual ~View() = default;

    // Every concrete View must implement this method.
    // It should pull events from model_ and display them.
    virtual void render() = 0;

    // Display the provided list of events.
    virtual void renderEvents(const std::vector<Event> &events) = 0;
};
