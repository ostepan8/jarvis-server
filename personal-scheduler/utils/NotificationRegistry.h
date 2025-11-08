#pragma once
#include "CallbackRegistry.h"

namespace NotificationRegistry {
    using Notifier = std::function<void(const std::string&, const std::string&)>;
    using Impl = CallbackRegistry<Notifier>;

    inline void registerNotifier(const std::string& name, Notifier notifier) {
        Impl::registerItem(name, std::move(notifier));
    }

    inline Notifier getNotifier(const std::string& name) {
        return Impl::getItem(name);
    }

    inline std::vector<std::string> availableNotifiers() {
        return Impl::availableItems();
    }
}
