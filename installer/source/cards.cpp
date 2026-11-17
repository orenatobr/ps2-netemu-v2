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

bool keep(unsigned char c) {
    return (c >= '0' && c <= '9') || (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || c == '-' || c == '_';
}

}  // namespace

std::string cardTitle(const std::string& isoName) {
    std::string base = isoName.substr(isoName.rfind('/') == std::string::npos ? 0 : isoName.rfind('/') + 1);
    const std::size_t dot = base.rfind('.');
    if (dot != std::string::npos && dot > 0 && base.size() - dot <= 5) base.resize(dot);
    std::string out;
    for (std::size_t i = 0; i < base.size();) {
        if (isDiscTag(base, i)) {
            while (i < base.size()) {
                const char c = base[i++];
                if (c == ')' || c == ']') break;
            }
            if (!out.empty() && out.back() == ' ') out.pop_back();
            continue;
        }
        if (out.size() >= kMaxTitle) break;
        out += base[i++];
    }
    while (!out.empty() && out.back() == ' ') out.pop_back();
    for (char& c : out)
        if (!keep(static_cast<unsigned char>(c))) c = '_';
    return out;
}

std::string cardFileName(const std::string& isoName) {
    const std::string title = cardTitle(isoName);
    return title.empty() ? "" : "PS2_" + title + ".VM2";
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
    std::vector<std::string> names = fsx::listDir(isoDir);
    std::sort(names.begin(), names.end());
    for (const std::string& name : names) {
        if (!lowerExt(name, ".iso") && !lowerExt(name, ".bin")) continue;
        const std::string card = cardFileName(name);
        if (card.empty() || fsx::exists(vmcDir + "/" + card)) continue;
        if (writeBlankCard(vmcDir + "/" + card, head)) made.push_back(card);
    }
    return made;
}

}  // namespace cards
