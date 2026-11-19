#include "configs.h"

#include <algorithm>
#include <cctype>

#include "fsx.h"
#include "isoinfo.h"

namespace configs {

namespace {

bool hasExtension(const std::string& name, const char* ext) {
    const std::size_t dot = name.rfind('.');
    if (dot == std::string::npos) return false;
    std::string e = name.substr(dot);
    for (char& c : e) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return e == ext;
}

// Commands are little endian 32 bit words: id, then its parameters.
Bytes makeRadiataConfig() {
    Bytes out;
    auto word = [&out](std::uint32_t v) {
        for (int s = 0; s < 32; s += 8) out.push_back(static_cast<std::uint8_t>(v >> s));
    };
    word(0x3D), word(0x4457);                  // config revision 17495 (ps2_netemu 4.78 and newer)
    word(0x07), word(8);                       // delay VU xgkick by 8 cycles
    word(0x01), word(0x124D94), word(0x0A);    // EE hook: TriAce unpack function, add 1 to the unpacked data
    word(0x01), word(0x1AF618), word(0x0B);    // EE hook: set $at to 0
    word(0x44);                                // disable smoothing
    word(0x00);                                // title id, always last; the file ends right after it, like the shipped ones
    for (const char* c = "SLUS-21262"; *c; ++c) out.push_back(static_cast<std::uint8_t>(*c));
    return out;
}

}  // namespace

const Bytes& radiataConfig() {
    static const Bytes config = makeRadiataConfig();
    return config;
}

bool hasRadiataLoopEdits(const Bytes& config) {
    // EE_INSN_REPLACE32 entry: offset 0x125004, original 0x1000FFFA (b -6, a loop), replacement 0x1400FFFA (bne zero, zero)
    static const Bytes signature = {0x04, 0x50, 0x12, 0x00, 0xFA, 0xFF, 0x00, 0x10, 0xFA, 0xFF, 0x00, 0x14};
    return std::search(config.begin(), config.end(), signature.begin(), signature.end()) != config.end();
}

std::vector<std::string> ensureConfigs(const std::string& isoDir) {
    std::vector<std::string> written;
    for (const std::string& name : fsx::listDir(isoDir)) {
        if (!hasExtension(name, ".iso")) continue;
        const std::string iso = isoDir + "/" + name;
        if (isoinfo::bootSerial(iso) != kRadiataSerial) continue;
        const std::string path = iso + ".CONFIG";
        Bytes current;
        if (fsx::exists(path)) {
            if (!fsx::readBytes(path, current, 1u << 20)) continue;
            if (current == radiataConfig() || !hasRadiataLoopEdits(current)) continue;  // already ours, or the owner's own file
            if (!fsx::exists(path + ".bak")) fsx::writeBytes(path + ".bak", current);
        }
        const std::string tmp = path + ".new";
        if (fsx::writeBytes(tmp, radiataConfig()) && fsx::renameFile(tmp, path)) written.push_back(name);
        else fsx::removeFile(tmp);
    }
    return written;
}

}  // namespace configs
