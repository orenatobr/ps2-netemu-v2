#include "fsx.h"

#include <dirent.h>
#include <sys/stat.h>

#include <algorithm>
#include <cstdio>

namespace fsx {

bool readBytes(const std::string& path, std::vector<std::uint8_t>& out, std::size_t maxBytes) {
    out.clear();
    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) return false;
    bool ok = std::fseek(f, 0, SEEK_END) == 0;
    const long size = ok ? std::ftell(f) : -1;
    ok = ok && size >= 0 && static_cast<std::size_t>(size) <= maxBytes && std::fseek(f, 0, SEEK_SET) == 0;
    if (ok) {
        out.resize(static_cast<std::size_t>(size));
        ok = size == 0 || std::fread(out.data(), 1, out.size(), f) == out.size();
    }
    std::fclose(f);
    if (!ok) out.clear();
    return ok;
}

bool readFile(const std::string& path, std::string& out) {
    std::vector<std::uint8_t> b;
    if (!readBytes(path, b)) return false;
    out.assign(b.begin(), b.end());
    return true;
}

bool writeBytes(const std::string& path, const std::vector<std::uint8_t>& data) {
    FILE* f = std::fopen(path.c_str(), "wb");
    if (!f) return false;
    const bool ok = data.empty() || std::fwrite(data.data(), 1, data.size(), f) == data.size();
    return (std::fclose(f) == 0) && ok;
}

bool copyFile(const std::string& from, const std::string& to) {
    std::vector<std::uint8_t> bytes;
    return readBytes(from, bytes) && writeBytes(to, bytes);
}

bool isDir(const std::string& path) {
    DIR* d = opendir(path.c_str());
    if (!d) return false;
    closedir(d);
    return true;
}

bool exists(const std::string& path) {
    FILE* f = std::fopen(path.c_str(), "rb");
    if (f) {
        std::fclose(f);
        return true;
    }
    return isDir(path);
}

bool makeDirs(const std::string& path) {
    for (std::size_t i = 1; i <= path.size(); ++i) {
        if (i == path.size() || path[i] == '/') {
            const std::string part = path.substr(0, i);
            if (part.back() == ':' || part.back() == '/') continue;
            mkdir(part.c_str(), 0777);  // existing directories simply fail with EEXIST
        }
    }
    return isDir(path);
}

std::vector<std::string> listDir(const std::string& path) {
    std::vector<std::string> names;
    DIR* d = opendir(path.c_str());
    if (!d) return names;
    while (dirent* e = readdir(d)) {
        const std::string n = e->d_name;
        if (n != "." && n != "..") names.push_back(n);
    }
    closedir(d);
    std::sort(names.begin(), names.end());
    return names;
}

bool renameFile(const std::string& from, const std::string& to) {
    if (std::rename(from.c_str(), to.c_str()) == 0) return true;
    // Some file systems refuse to replace an existing target: retry only when the source is readable.
    FILE* src = std::fopen(from.c_str(), "rb");
    if (!src) return false;
    std::fclose(src);
    std::remove(to.c_str());
    return std::rename(from.c_str(), to.c_str()) == 0;
}

bool removeFile(const std::string& path) {
    std::remove(path.c_str());
    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) return true;
    std::fclose(f);
    return false;
}

std::uint32_t fnv1a(const std::vector<std::uint8_t>& data) {
    std::uint32_t h = 2166136261u;
    for (std::uint8_t b : data) {
        h ^= b;
        h *= 16777619u;
    }
    return h;
}

std::uint32_t fnv1a(const std::string& text) {
    std::uint32_t h = 2166136261u;
    for (unsigned char c : text) {
        h ^= c;
        h *= 16777619u;
    }
    return h;
}

}  // namespace fsx
