#pragma once
#include "httplib.h"
#include "../../model/Model.h"

namespace StatsRoutes {
    void registerRoutes(httplib::Server &server, Model &model);
}
