#pragma once
#include <string>
#include <unordered_map>
#include <functional>
#include <vector>
#include <algorithm>

// Generic registry for mapping string names to callback functions.
// Template parameter F is the callback type (e.g. std::function<void()>).

template<typename F>
class CallbackRegistry {
public:
    using Callback = F;

    static std::unordered_map<std::string, Callback>& registry() {
        static std::unordered_map<std::string, Callback> impl;
        return impl;
    }

    static void registerItem(const std::string& name, Callback cb) {
        registry()[name] = std::move(cb);
    }

    static Callback getItem(const std::string& name) {
        auto it = registry().find(name);
        if (it == registry().end()) return Callback{};
        return it->second;
    }

    static std::vector<std::string> availableItems() {
        std::vector<std::string> names;
        for (const auto& kv : registry()) names.push_back(kv.first);
        std::sort(names.begin(), names.end());
        return names;
    }
};
