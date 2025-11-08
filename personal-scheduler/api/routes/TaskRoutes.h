#pragma once
#include "httplib.h"
#include "../../model/Model.h"
#include "../../scheduler/EventLoop.h"

namespace TaskRoutes {
    void registerRoutes(httplib::Server &server, Model &model, EventLoop *loop);
}
