#include "model/Model.h"
#include "database/SQLiteScheduleDatabase.h"
#include <chrono>
#include <iostream>

int main() {
    // Test Model performance in isolation
    auto db = std::make_unique<SQLiteScheduleDatabase>(":memory:");
    Model model(db.get());
    
    auto start = std::chrono::high_resolution_clock::now();
    
    // Add 10 events to test speed
    for (int i = 0; i < 10; i++) {
        auto now = std::chrono::system_clock::now() + std::chrono::minutes(i);
        Event e(std::to_string(i), "test desc", "Test Event " + std::to_string(i), 
                now, std::chrono::minutes(60), "Test");
        bool success = model.addEvent(e);
        if (!success) {
            std::cout << "Failed to add event " << i << std::endl;
        }
    }
    
    auto end = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(end - start);
    
    std::cout << "Added 10 events in " << duration.count() << "ms" << std::endl;
    std::cout << "Average per event: " << (duration.count() / 10.0) << "ms" << std::endl;
    
    return 0;
}