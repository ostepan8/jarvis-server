#!/bin/bash
set -e

# Use a fixed timezone so results are deterministic across environments
export TZ=UTC

# Build all test executables
make recurrence_tests event_tests model_tests model_comprehensive_tests controller_tests view_tests api_tests database_tests action_registry_tests builtin_actions_tests notification_registry_tests builtin_notifiers_tests google_calendar_api_tests integration_tests

# Run each test executable sequentially
for t in recurrence_tests event_tests model_tests model_comprehensive_tests controller_tests view_tests api_tests database_tests action_registry_tests builtin_actions_tests notification_registry_tests builtin_notifiers_tests google_calendar_api_tests integration_tests; do
    echo "Running $t"
    ./$t
    echo
done
