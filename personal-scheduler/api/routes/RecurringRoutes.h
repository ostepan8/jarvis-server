#pragma once
#include "httplib.h"
#include "../../model/Model.h"

namespace RecurringRoutes {
    void registerRoutes(httplib::Server &server, Model &model);
}
