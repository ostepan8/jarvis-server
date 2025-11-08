#include <cassert>
#include <iostream>
#include "../../services/EventService.h"
#include "../../model/Model.h"
#include "../../model/OneTimeEvent.h"
#include "../../model/RecurringEvent.h"
#include "../../model/recurrence/DailyRecurrence.h"
#include "../../database/SQLiteScheduleDatabase.h"
#include "../test_utils.h"

using namespace std;
using namespace chrono;

static void testEventServiceGetEvents() {
    // Setup in-memory database
    SQLiteScheduleDatabase db(":memory:");
    Model model(&db);
    EventService service(model);
    
    // Add test events
    OneTimeEvent e1("1", "desc1", "Event 1", makeTime(2025, 6, 1, 9), hours(1));
    OneTimeEvent e2("2", "desc2", "Event 2", makeTime(2025, 6, 2, 10), hours(2));
    
    model.addEvent(e1);
    model.addEvent(e2);
    
    // Test getEvents interface
    auto events = service.getEvents(10, makeTime(2025, 7, 1));
    
    assert(events.size() == 2);
    assert(events[0].getId() == "1");
    assert(events[1].getId() == "2");
    
    cout << "EventService getEvents test passed\n";
}

static void testEventServiceAddEvent() {
    SQLiteScheduleDatabase db(":memory:");
    Model model(&db);
    EventService service(model);
    
    OneTimeEvent event("test", "description", "Test Event", makeTime(2025, 6, 1, 12), hours(1));
    
    // Test addEvent interface
    service.addEvent(event);
    
    auto events = service.getEvents(10, makeTime(2025, 7, 1));
    assert(events.size() == 1);
    assert(events[0].getId() == "test");
    assert(events[0].getTitle() == "Test Event");
    
    cout << "EventService addEvent test passed\n";
}

static void testEventServiceWithRecurringEvents() {
    SQLiteScheduleDatabase db(":memory:");
    Model model(&db);
    EventService service(model);
    
    auto start = makeTime(2025, 6, 1, 9);
    auto pattern = make_shared<DailyRecurrence>(start, 1);
    RecurringEvent recurring("rec1", "daily", "Daily Event", start, hours(1), pattern);
    
    service.addEvent(recurring);
    
    // Get events over 3 days
    auto events = service.getEvents(10, makeTime(2025, 6, 4));
    
    // Should have multiple occurrences
    assert(events.size() >= 3);
    
    cout << "EventService recurring events test passed\n";
}

static void testEventServiceInterfaceCompliance() {
    SQLiteScheduleDatabase db(":memory:");
    Model model(&db);
    
    // Test that EventService implements IEventService interface
    IEventService* service = new EventService(model);
    
    OneTimeEvent event("interface", "test", "Interface Test", makeTime(2025, 6, 1), hours(1));
    service->addEvent(event);
    
    auto events = service->getEvents(5, makeTime(2025, 7, 1));
    assert(events.size() == 1);
    assert(events[0].getId() == "interface");
    
    delete service;
    
    cout << "EventService interface compliance test passed\n";
}

int main() {
    testEventServiceGetEvents();
    testEventServiceAddEvent();
    testEventServiceWithRecurringEvents();
    testEventServiceInterfaceCompliance();
    
    cout << "All EventService tests passed!\n";
    return 0;
}