#include "Auth.h"

Auth::Auth(const std::string &key, const std::string &adminKey)
    : key_(key), adminKey_(adminKey) {}

bool Auth::authorize(const httplib::Request &req) const {
    auto header = req.get_header_value("Authorization");
    if (header.empty()) header = req.get_header_value("X-API-Key");
    if (header.empty()) return false;
    if (header == key_ || header == ("Bearer " + key_)) return true;
    if (!adminKey_.empty() && (header == adminKey_ || header == ("Bearer " + adminKey_))) return true;
    return false;
}

bool Auth::isAdmin(const httplib::Request &req) const {
    if (adminKey_.empty()) return false;
    auto header = req.get_header_value("Authorization");
    if (header.empty()) header = req.get_header_value("X-API-Key");
    if (header.empty()) return false;
    return header == adminKey_ || header == ("Bearer " + adminKey_);
}
