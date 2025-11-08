#pragma once

#include <memory>
#include <unordered_map>
#include <typeinfo>
#include <functional>
#include <stdexcept>

class DependencyContainer {
private:
    std::unordered_map<std::string, std::shared_ptr<void>> instances_;
    std::unordered_map<std::string, std::function<std::shared_ptr<void>()>> factories_;
    
    template<typename T>
    std::string getTypeName() const {
        return typeid(T).name();
    }

public:
    // Register a singleton instance
    template<typename T>
    void registerSingleton(std::shared_ptr<T> instance) {
        instances_[getTypeName<T>()] = std::static_pointer_cast<void>(instance);
    }
    
    // Register a factory function for creating instances
    template<typename T>
    void registerFactory(std::function<std::shared_ptr<T>()> factory) {
        factories_[getTypeName<T>()] = [factory]() -> std::shared_ptr<void> {
            return std::static_pointer_cast<void>(factory());
        };
    }
    
    // Get an instance of type T
    template<typename T>
    std::shared_ptr<T> get() {
        std::string typeName = getTypeName<T>();
        
        // Check if we have a singleton instance
        auto instanceIt = instances_.find(typeName);
        if (instanceIt != instances_.end()) {
            return std::static_pointer_cast<T>(instanceIt->second);
        }
        
        // Check if we have a factory
        auto factoryIt = factories_.find(typeName);
        if (factoryIt != factories_.end()) {
            auto instance = factoryIt->second();
            return std::static_pointer_cast<T>(instance);
        }
        
        throw std::runtime_error("No registration found for type: " + typeName);
    }
    
    // Check if a type is registered
    template<typename T>
    bool isRegistered() const {
        std::string typeName = getTypeName<T>();
        return instances_.find(typeName) != instances_.end() || 
               factories_.find(typeName) != factories_.end();
    }
    
    // Clear all registrations
    void clear() {
        instances_.clear();
        factories_.clear();
    }
};