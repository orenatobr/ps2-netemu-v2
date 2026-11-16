#include "cards.h"

#include <algorithm>
#include <cstdio>

#include "fsx.h"

namespace cards {

namespace {

bool lowerExt(const std::string& name, const char* ext) {
    const std::size_t dot = name.rfind('.');
    if (dot == std::string::npos) return false;
    std::string e = name.substr(dot);
    for (char& c : e) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return e == ext;
}

bool isDiscTag(const std::string& s, std::size_t i) {
    return (s[i] == '(' || s[i] == '[') && (s.compare(i + 1, 4, "Disc") == 0 || s.compare(i + 1, 4, "disc") == 0);
}

}  // namespace

std::string gameTitle(const std::string& isoName) {
    std::string base = isoName.substr(isoName.rfind('/') == std::string::npos ? 0 : isoName.rfind('/') + 1);
    const std::size_t dot = base.rfind('.');
    if (dot != std::string::npos && dot > 0 && base.size() - dot <= 5) base.resize(dot);
    std::string out;
    for (std::size_t i = 0; i < base.size();) {
        if (isDiscTag(base, i)) {
            while (i < base.size() && base[i] != ')' && base[i] != ']') ++i;
            if (i < base.size()) ++i;
            if (!out.empty() && out.back() == ' ') out.pop_back();
            continue;
        }
        out += base[i++];
    }
    while (!out.empty() && out.back() == ' ') out.pop_back();
    return out;
}

std::string slotCardName(int slot) {
    char buf[24];
    std::snprintf(buf, sizeof buf, "PS2_C%02d.VM2", slot);
    return buf;
}

std::vector<Entry> readTable(const std::string& path) {
    std::vector<Entry> out;
    Bytes raw;
    if (!fsx::readBytes(path, raw)) return out;
    for (std::size_t at = 0; at + kRecord <= raw.size() && raw[at + 1] != 0; at += kRecord) {
        std::string name(reinterpret_cast<const char*>(&raw[at + 1]), kRecord - 1);
        name.resize(name.find('\0'));
        out.push_back({raw[at], name});
    }
    return out;
}

bool writeTable(const std::string& path, const std::vector<Entry>& entries) {
    Bytes raw;
    for (const Entry& e : entries) {
        if (e.slot < 0 || e.slot >= kSlots || e.name.empty() || e.name.size() > kRecord - 2) return false;
        Bytes rec(kRecord, 0);
        rec[0] = static_cast<std::uint8_t>(e.slot);
        std::copy(e.name.begin(), e.name.end(), rec.begin() + 1);
        raw.insert(raw.end(), rec.begin(), rec.end());
    }
    raw.insert(raw.end(), kRecord, 0);
    const std::string tmp = path + ".new";
    if (!fsx::writeBytes(tmp, raw) || !fsx::renameFile(tmp, path)) {
        fsx::removeFile(tmp);
        return false;
    }
    return true;
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
    const std::string tablePath = vmcDir + "/PS2_CARDS.TBL";
    std::vector<Entry> table = readTable(tablePath);
    const std::size_t before = table.size();
    std::vector<std::string> names = fsx::listDir(isoDir);
    std::sort(names.begin(), names.end());
    for (const std::string& name : names) {
        if (!lowerExt(name, ".iso") && !lowerExt(name, ".bin")) continue;
        const std::string title = gameTitle(name);
        if (title.empty() || name.size() > kRecord - 2) continue;
        if (std::any_of(table.begin(), table.end(), [&](const Entry& e) { return e.name == name; })) continue;
        int slot = -1;
        for (const Entry& e : table)
            if (gameTitle(e.name) == title) slot = e.slot;
        for (int s = 0; slot < 0 && s < kSlots; ++s)
            if (std::none_of(table.begin(), table.end(), [&](const Entry& e) { return e.slot == s; })) slot = s;
        if (slot >= 0) table.push_back({slot, name});
    }
    if (table.size() != before && !writeTable(tablePath, table)) return made;
    std::vector<bool> done(kSlots, false);
    for (const Entry& e : table) {
        if (done[e.slot]) continue;
        done[e.slot] = true;
        const std::string card = slotCardName(e.slot);
        if (!fsx::exists(vmcDir + "/" + card) && writeBlankCard(vmcDir + "/" + card, head)) made.push_back(card);
    }
    return made;
}

}  // namespace cards
