#pragma once
#include <string>

// Simple loader for .env style configuration files.
// Each line should be KEY=VALUE and comments starting with '#'.
class EnvLoader {
public:
    // Load variables from the given file and set them with setenv.
    static void load(const std::string &path = ".env");
};
