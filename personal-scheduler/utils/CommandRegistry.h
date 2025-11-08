#pragma once
#include <string>
#include <unordered_map>
#include <functional>
#include <vector>

// Simple registry for CLI commands with descriptions.
// Usage:
//   CommandRegistry::registerCommand("list", []{ ... }, "List events");
//   auto cmd = CommandRegistry::getCommand("list"); if (cmd) cmd->fn();

struct CliCommand {
    std::function<void()> fn;
    std::string description;
};

class CommandRegistry {
public:
    static std::unordered_map<std::string, CliCommand> &registry() {
        static std::unordered_map<std::string, CliCommand> impl;
        return impl;
    }

    static void clear() { registry().clear(); }

    static void registerCommand(const std::string &name, std::function<void()> fn,
                                const std::string &description = std::string()) {
        registry()[name] = CliCommand{std::move(fn), description};
    }

    static const CliCommand *getCommand(const std::string &name) {
        auto &m = registry();
        auto it = m.find(name);
        if (it == m.end()) return nullptr;
        return &it->second;
    }

    static std::vector<std::pair<std::string, std::string>> available() {
        std::vector<std::pair<std::string, std::string>> out;
        out.reserve(registry().size());
        for (const auto &kv : registry()) out.emplace_back(kv.first, kv.second.description);
        std::sort(out.begin(), out.end(), [](auto &a, auto &b){ return a.first < b.first; });
        return out;
    }
};

