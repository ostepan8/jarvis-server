#include "EnvLoader.h"
#include <fstream>
#include <cstdlib>
#include <sstream>

void EnvLoader::load(const std::string &path) {
    std::ifstream file(path);
    if (!file.is_open()) return; // silently ignore if missing
    std::string line;
    while (std::getline(file, line)) {
        if (line.empty() || line[0] == '#') continue;
        size_t eq = line.find('=');
        if (eq == std::string::npos) continue;
        std::string key = line.substr(0, eq);
        std::string value = line.substr(eq + 1);
        // Trim whitespace
        auto trim = [](std::string &s) {
            while (!s.empty() && (s.back() == '\r' || s.back() == '\n' || isspace((unsigned char)s.back()))) s.pop_back();
            size_t start = 0; while (start < s.size() && isspace((unsigned char)s[start])) ++start; if (start) s.erase(0, start);
        };
        trim(key); trim(value);
        if(!key.empty()) setenv(key.c_str(), value.c_str(), 0);
    }
}
