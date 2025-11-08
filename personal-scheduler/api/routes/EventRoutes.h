#pragma once
#include "httplib.h"
#include "../../model/Model.h"
#include "../../processing/WakeScheduler.h"

namespace EventRoutes {
    void registerRoutes(httplib::Server &server, Model &model, WakeScheduler *wake = nullptr);
}
