#include <cassert>
#include "../../utils/BuiltinActions.h"
#include "../../utils/ActionRegistry.h"
#include <iostream>

static void testRegistration() {
    BuiltinActions::registerAll();
    auto act = ActionRegistry::getAction("hello");
    assert(act);
}

int main() {
    testRegistration();
    std::cout << "BuiltinActions tests passed\n";
    return 0;
}
