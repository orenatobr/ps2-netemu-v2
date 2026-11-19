#include "isoinfo.h"

#include <sys/types.h>

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <cstdio>
#include <vector>

namespace isoinfo {

namespace {

constexpr long kSector = 2048;
constexpr std::uint32_t kMaxDir = 1u << 20;  // a root directory bigger than 1 MB is not a PS2 disc
constexpr std::uint32_t kMaxCnf = 4096;

std::uint32_t le32(const std::vector<unsigned char>& b, std::size_t at) {
    return std::uint32_t(b[at]) | std::uint32_t(b[at + 1]) << 8 | std::uint32_t(b[at + 2]) << 16 | std::uint32_t(b[at + 3]) << 24;
}

bool readAt(std::FILE* f, std::uint64_t lba, std::uint32_t size, std::vector<unsigned char>& out) {
    out.assign(size, 0);
    return fseeko(f, static_cast<off_t>(lba) * kSector, SEEK_SET) == 0 && std::fread(out.data(), 1, size, f) == size;
}

/// The BOOT2 value of a SYSTEM.CNF text: "BOOT2 = cdrom0:\SLUS_212.62;1" gives "SLUS_212.62".
std::string parseBoot2(const std::string& text) {
    const std::size_t at = text.find("BOOT2");
    if (at == std::string::npos) return "";
    std::size_t i = text.find("cdrom0:", at);
    if (i == std::string::npos) return "";
    i += 7;
    while (i < text.size() && (text[i] == '\\' || text[i] == '/' || text[i] == ' ')) ++i;
    std::string serial;
    while (i < text.size() && text[i] != ';' && text[i] != '\r' && text[i] != '\n' && text[i] != ' ')
        serial += static_cast<char>(std::toupper(static_cast<unsigned char>(text[i++])));
    return serial;
}

}  // namespace

std::string bootSerial(const std::string& isoPath) {
    std::FILE* f = std::fopen(isoPath.c_str(), "rb");
    if (!f) return "";
    std::string serial;
    std::vector<unsigned char> pvd, dir, cnf;
    if (readAt(f, 16, kSector, pvd) && pvd[0] == 1 && std::equal(pvd.begin() + 1, pvd.begin() + 6, "CD001")) {
        const std::uint32_t rootLba = le32(pvd, 156 + 2), rootSize = le32(pvd, 156 + 10);
        if (rootSize > 0 && rootSize <= kMaxDir && readAt(f, rootLba, rootSize, dir)) {
            for (std::size_t i = 0; i + 34 <= dir.size();) {
                const std::size_t len = dir[i];
                if (len == 0) {  // records never cross a sector: the rest of this one is padding
                    i = (i / kSector + 1) * kSector;
                    continue;
                }
                const std::size_t nameLen = dir[i + 32];
                if (i + 33 + nameLen > dir.size()) break;
                const std::string name(dir.begin() + i + 33, dir.begin() + i + 33 + nameLen);
                if (name == "SYSTEM.CNF;1" || name == "SYSTEM.CNF") {
                    const std::uint32_t lba = le32(dir, i + 2), size = std::min(le32(dir, i + 10), kMaxCnf);
                    if (readAt(f, lba, size, cnf)) serial = parseBoot2(std::string(cnf.begin(), cnf.end()));
                    break;
                }
                i += len;
            }
        }
    }
    std::fclose(f);
    return serial;
}

}  // namespace isoinfo
