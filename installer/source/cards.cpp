#include "cards.h"

#include <cstdio>
#include <cstring>

#include "fsx.h"

namespace cards {

namespace {

constexpr int kSector = 2048;
constexpr std::size_t kMaxSerial = 16, kMinSerial = 4;

bool readAt(const std::string& path, std::uint64_t offset, void* out, std::size_t n) {
    std::FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) return false;
    const bool ok = fseeko(f, static_cast<off_t>(offset), SEEK_SET) == 0 && std::fread(out, 1, n, f) == n;
    std::fclose(f);
    return ok;
}

std::uint32_t le32(const std::uint8_t* p) { return p[0] | (p[1] << 8) | (p[2] << 16) | (static_cast<std::uint32_t>(p[3]) << 24); }

bool lowerExt(const std::string& name, const char* ext) {
    const std::size_t dot = name.rfind('.');
    if (dot == std::string::npos) return false;
    std::string e = name.substr(dot);
    for (char& c : e) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return e == ext;
}

}  // namespace

std::string serialFromCnf(const std::string& text) {
    std::size_t i = text.find("BOOT2");
    if (i == std::string::npos) return "";
    const std::size_t colon = text.find(':', i + 5);
    if (colon == std::string::npos) return "";
    std::size_t k = colon + 1;
    while (k < text.size() && (text[k] == '\\' || text[k] == '/')) ++k;
    std::string out;
    for (; k < text.size() && text[k] != ';' && static_cast<unsigned char>(text[k]) > 0x20 && out.size() < kMaxSerial; ++k) {
        const char c = text[k];
        if (c == '.') continue;
        out += c == '_' ? '-' : static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
    }
    return out.size() >= kMinSerial ? out : "";
}

std::string discOne(const std::string& isoPath) {
    for (const char* tag : {"(Disc ", "[Disc "}) {
        const std::size_t i = isoPath.find(tag);
        if (i == std::string::npos || i + 6 >= isoPath.size()) continue;
        const char d = isoPath[i + 6];
        if (d >= '2' && d <= '9') {
            std::string one = isoPath;
            one[i + 6] = '1';
            return one;
        }
    }
    return "";
}

std::string serialOfImage(const std::string& isoPath) {
    std::uint8_t pvd[0xB0];
    if (!readAt(isoPath, 16u * kSector, pvd, sizeof pvd) || pvd[0] != 1 || std::memcmp(pvd + 1, "CD001", 5) != 0) return "";
    std::vector<std::uint8_t> dir(kSector);
    if (!readAt(isoPath, static_cast<std::uint64_t>(le32(pvd + 158)) * kSector, dir.data(), dir.size())) return "";
    for (std::size_t pos = 0; pos + 34 <= dir.size() && dir[pos] != 0; pos += dir[pos]) {
        const std::size_t nameLen = dir[pos + 32];
        if (nameLen >= 10 && pos + 33 + 10 <= dir.size() && std::memcmp(&dir[pos + 33], "SYSTEM.CNF", 10) == 0) {
            std::vector<char> text(0x100);
            if (!readAt(isoPath, static_cast<std::uint64_t>(le32(&dir[pos + 2])) * kSector, text.data(), text.size())) return "";
            return serialFromCnf(std::string(text.data(), text.size()));
        }
    }
    return "";
}

std::string cardSerial(const std::string& isoPath) {
    const std::string one = discOne(isoPath);
    if (!one.empty()) {
        const std::string s = serialOfImage(one);
        if (!s.empty()) return s;
    }
    return serialOfImage(isoPath);
}

bool writeBlankCard(const std::string& path, const Bytes& head) {
    if (head.empty() || head.size() > kCardBytes) return false;
    const std::string tmp = path + ".new";
    std::FILE* f = std::fopen(tmp.c_str(), "wb");
    if (!f) return false;
    bool ok = std::fwrite(head.data(), 1, head.size(), f) == head.size();
    const Bytes erased(64 * 1024, 0xFF);
    for (std::size_t left = kCardBytes - head.size(); ok && left > 0;) {
        const std::size_t n = left < erased.size() ? left : erased.size();
        ok = std::fwrite(erased.data(), 1, n, f) == n;
        left -= n;
    }
    ok = (std::fclose(f) == 0) && ok;
    if (!ok || !fsx::renameFile(tmp, path)) {
        fsx::removeFile(tmp);
        return false;
    }
    return true;
}

std::vector<std::string> ensureCards(const std::string& isoDir, const std::string& vmcDir, const Bytes& head) {
    std::vector<std::string> made;
    fsx::makeDirs(vmcDir);
    for (const std::string& name : fsx::listDir(isoDir)) {
        if (!lowerExt(name, ".iso") && !lowerExt(name, ".bin")) continue;
        const std::string serial = cardSerial(isoDir + "/" + name);
        if (serial.empty()) continue;
        const std::string card = serial + ".VM2";
        const std::string path = vmcDir + "/" + card;
        if (fsx::exists(path)) continue;
        if (writeBlankCard(path, head)) made.push_back(card);
    }
    return made;
}

}  // namespace cards
