#include "Logger.h"

std::atomic<int> Logger::level_{static_cast<int>(LogLevel::INFO)};

