#pragma once

#include "httplib.h"

// Interface Segregation Principle: Small, focused interface
class IRequestHandler {
public:
    virtual ~IRequestHandler() = default;
    virtual void handle(const httplib::Request& req, httplib::Response& res) = 0;
};