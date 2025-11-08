#include <cassert>
#include "../../utils/BuiltinNotifiers.h"
#include "../../utils/NotificationRegistry.h"
#include <iostream>

static void testRegistration() {
    BuiltinNotifiers::registerAll();
    auto n = NotificationRegistry::getNotifier("console");
    assert(n);
}

int main() {
    testRegistration();
    std::cout << "BuiltinNotifiers tests passed\n";
    return 0;
}
