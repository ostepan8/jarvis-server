#pragma once
#include "NotificationRegistry.h"
#include <iostream>

class BuiltinNotifiers {
public:
    static void console(const std::string& id, const std::string& title) {
    }

    static void registerAll() {
        NotificationRegistry::registerNotifier("console", &BuiltinNotifiers::console);
    }
};
