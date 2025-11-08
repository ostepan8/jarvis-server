#include <cassert>
#include <algorithm>
#include "../../utils/ActionRegistry.h"
#include <iostream>

using namespace std;

static void testRegisterAndExecute() {
    int counter = 0;
    ActionRegistry::registerAction("inc", [&]{ counter++; });
    auto act = ActionRegistry::getAction("inc");
    assert(act);
    act();
    assert(counter == 1);
    auto names = ActionRegistry::availableActions();
    assert(find(names.begin(), names.end(), "inc") != names.end());
}

int main() {
    testRegisterAndExecute();
    cout << "ActionRegistry tests passed\n";
    return 0;
}
