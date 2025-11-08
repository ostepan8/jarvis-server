#pragma once
#include "httplib.h"
#include "../../model/Model.h"
#include "../../processing/WakeScheduler.h"
#include "../../database/SettingsStore.h"

namespace WakeRoutes {
    void registerRoutes(httplib::Server &server, Model &model, WakeScheduler *wake, SettingsStore *settings);
}

