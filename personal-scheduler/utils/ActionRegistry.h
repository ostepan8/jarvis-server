#pragma once
#include "CallbackRegistry.h"

namespace ActionRegistry {
    using Action = std::function<void()>;
    using Impl = CallbackRegistry<Action>;

    inline void registerAction(const std::string& name, Action action) {
        Impl::registerItem(name, std::move(action));
    }

    inline Action getAction(const std::string& name) {
        return Impl::getItem(name);
    }

    inline std::vector<std::string> availableActions() {
        return Impl::availableItems();
    }
}
