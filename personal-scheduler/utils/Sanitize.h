#pragma once
#include <string>
#include <algorithm>
#include "Logger.h"

inline std::string sanitize(const std::string &in, size_t maxLen = 256)
{
    Logger::debug("[sanitize] in.len=", in.size(), " max=", maxLen);

    std::string out;
    out.reserve(std::min(maxLen, in.size()));

    for (char c : in)
    {
        if (std::iscntrl(static_cast<unsigned char>(c)))
        {
            Logger::debug("[sanitize] skip ctrl char=", (int)static_cast<unsigned char>(c));
            continue;
        }
        out.push_back(c);
        if (out.size() >= maxLen)
        {
            Logger::debug("[sanitize] reached max, truncating at ", maxLen);
            break;
        }
    }

    Logger::debug("[sanitize] out.len=", out.size());
    return out;
}
