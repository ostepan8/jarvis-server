#pragma once

#include "View.h"
#include <iostream>
#include <chrono>
#include <ctime>

/*
  A simple textual (CLI) View. It uses the ReadOnlyModel reference inherited
  from View to fetch events, then prints their ID, title, and timestamp.
*/
class TextualView : public View
{
public:
    explicit TextualView(const ReadOnlyModel &model);
    ~TextualView() override;

    // Override: fetch from model_ and print all events
    void render() override;

    // Print a provided list of events
    void renderEvents(const std::vector<Event> &events) override;
};
