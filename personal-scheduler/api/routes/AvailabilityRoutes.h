#pragma once
#include "httplib.h"
#include "../../model/Model.h"

namespace AvailabilityRoutes {
    void registerRoutes(httplib::Server &server, Model &model);
}
