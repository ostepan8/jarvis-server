#include <cassert>
#include <algorithm>
#include "../../utils/NotificationRegistry.h"
#include <iostream>

using namespace std;

static void testRegisterAndExecute() {
    int counter = 0;
    NotificationRegistry::registerNotifier("count", [&](const string&, const string&){ counter++; });
    auto n = NotificationRegistry::getNotifier("count");
    assert(n);
    n("id","title");
    assert(counter == 1);
    auto names = NotificationRegistry::availableNotifiers();
    assert(find(names.begin(), names.end(), "count") != names.end());
}

int main() {
    testRegisterAndExecute();
    cout << "NotificationRegistry tests passed\n";
    return 0;
}
