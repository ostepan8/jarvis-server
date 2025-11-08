#include "TextualView.h"
#include <iomanip>
#include "../utils/TimeUtils.h"

TextualView::TextualView(const ReadOnlyModel &model)
    : View(model)
{
}

TextualView::~TextualView() = default;

void TextualView::render()
{
    // Fetch “everything” by using a far‑future cutoff.
    auto farFuture = std::chrono::system_clock::now() + std::chrono::hours(24 * 365);
    auto events = model_.getEvents(-1, farFuture);
    renderEvents(events);
}

void TextualView::renderEvents(const std::vector<Event> &events)
{
    if (events.empty())
    {
        std::cout << "(no scheduled events)\n";
        return;
    }

    for (const auto &e : events)
    {
        auto tp = e.getTime();
        std::string ts = TimeUtils::formatTimePoint(tp);

        std::cout << "[" << e.getId() << "] \""
                  << e.getTitle() << "\" @ " << ts;
        if (e.isRecurring())
            std::cout << " (recurring)";
        std::cout << "\n";
    }
}

