#pragma once
#include <string>
#include <sstream>
#include <iostream>
#include <atomic>
#include <mutex>

enum class LogLevel { DEBUG = 0, INFO = 1, WARN = 2, ERROR = 3, NONE = 4 };

class Logger {
public:
    static LogLevel getLevel() {
        static std::once_flag initFlag;
        std::call_once(initFlag, [](){
            const char* env = std::getenv("LOG_LEVEL");
            if (!env) { level_.store(static_cast<int>(LogLevel::INFO)); return; }
            std::string val = env;
            for (auto &c : val) c = static_cast<char>(::toupper(c));
            if (val == "DEBUG") level_.store(static_cast<int>(LogLevel::DEBUG));
            else if (val == "INFO") level_.store(static_cast<int>(LogLevel::INFO));
            else if (val == "WARN" || val == "WARNING") level_.store(static_cast<int>(LogLevel::WARN));
            else if (val == "ERROR") level_.store(static_cast<int>(LogLevel::ERROR));
            else level_.store(static_cast<int>(LogLevel::INFO));
        });
        return static_cast<LogLevel>(level_.load());
    }

    static void setLevel(LogLevel lvl) { level_.store(static_cast<int>(lvl)); }

    template<typename... Args>
    static void debug(Args&&... args) { write(LogLevel::DEBUG, std::forward<Args>(args)...); }
    template<typename... Args>
    static void info(Args&&... args)  { write(LogLevel::INFO,  std::forward<Args>(args)...); }
    template<typename... Args>
    static void warn(Args&&... args)  { write(LogLevel::WARN,  std::forward<Args>(args)...); }
    template<typename... Args>
    static void error(Args&&... args) { write(LogLevel::ERROR, std::forward<Args>(args)...); }

private:
    template<typename... Args>
    static void write(LogLevel lvl, Args&&... args) {
        if (static_cast<int>(lvl) < static_cast<int>(getLevel())) return;
        std::ostringstream oss;
        (oss << ... << args);
        std::cerr << oss.str() << std::endl;
    }
    static std::atomic<int> level_;
};

