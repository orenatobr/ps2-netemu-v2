// Host tests for the ISO serial reader and the Radiata Stories CONFIG. Build and run: tests/run.sh
#include <cassert>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <string>
#include <vector>

#include "configs.h"
#include "fsx.h"
#include "isoinfo.h"

namespace fs = std::filesystem;

namespace {

using Bytes = std::vector<std::uint8_t>;

struct Dir {
    fs::path root = fs::temp_directory_path() / ("ps2cfg_" + std::to_string(std::rand()));
    Dir() { fs::create_directories(root); }
    ~Dir() { fs::remove_all(root); }
    std::string path(const std::string& name) const { return (root / name).string(); }
};

void put32(Bytes& b, std::size_t at, std::uint32_t v) {
    for (int i = 0; i < 4; ++i) b[at + i] = static_cast<std::uint8_t>(v >> (8 * i));
}

/// A tiny ISO9660 image: PVD at sector 16, the root directory at sector 17 with a decoy file and SYSTEM.CNF at sector 20.
Bytes makeIso(const std::string& cnf, bool withCnf = true) {
    Bytes iso(24 * 2048, 0);
    const std::size_t pvd = 16 * 2048;
    iso[pvd] = 1;
    std::memcpy(&iso[pvd + 1], "CD001", 5);
    iso[pvd + 156] = 34;
    put32(iso, pvd + 156 + 2, 17);
    put32(iso, pvd + 156 + 10, 2048);
    std::size_t at = 17 * 2048;
    auto record = [&](const std::string& name, std::uint32_t lba, std::uint32_t size) {
        iso[at] = static_cast<std::uint8_t>(33 + name.size() + (name.size() % 2 == 0 ? 1 : 0));
        put32(iso, at + 2, lba);
        put32(iso, at + 10, size);
        iso[at + 32] = static_cast<std::uint8_t>(name.size());
        std::memcpy(&iso[at + 33], name.data(), name.size());
        at += iso[at];
    };
    record("IOPRP300.IMG;1", 22, 100);
    if (withCnf) record("SYSTEM.CNF;1", 20, static_cast<std::uint32_t>(cnf.size()));
    std::memcpy(&iso[20 * 2048], cnf.data(), cnf.size());
    return iso;
}

const std::string kRadiataCnf = "BOOT2 = cdrom0:\\SLUS_212.62;1\r\nVER = 1.00\r\nVMODE = NTSC\r\n";

void testSerialIsRead() {
    Dir d;
    assert(fsx::writeBytes(d.path("a.iso"), makeIso(kRadiataCnf)));
    assert(isoinfo::bootSerial(d.path("a.iso")) == "SLUS_212.62");
    assert(fsx::writeBytes(d.path("b.iso"), makeIso("BOOT2=cdrom0:/slus_213.45;1\nVER=1.00\n")));
    assert(isoinfo::bootSerial(d.path("b.iso")) == "SLUS_213.45");  // no spaces, a slash, lower case
}

void testNotAnIsoGivesNothing() {
    Dir d;
    assert(isoinfo::bootSerial(d.path("missing.iso")).empty());
    assert(fsx::writeBytes(d.path("junk.iso"), Bytes(40 * 2048, 7)));
    assert(isoinfo::bootSerial(d.path("junk.iso")).empty());
    assert(fsx::writeBytes(d.path("nocnf.iso"), makeIso("", false)));
    assert(isoinfo::bootSerial(d.path("nocnf.iso")).empty());
    assert(fsx::writeBytes(d.path("noboot.iso"), makeIso("VER = 1.00\n")));
    assert(isoinfo::bootSerial(d.path("noboot.iso")).empty());
    assert(fsx::writeBytes(d.path("short.iso"), Bytes(100, 1)));
    assert(isoinfo::bootSerial(d.path("short.iso")).empty());
}

// The CUSTOM entry of the webMAN database for SLUS_212.62 (112 bytes), the one that is copied beside the ISO on its first mount.
const Bytes kWebmanCustom = {
    0x3d, 0x00, 0x00, 0x00, 0x57, 0x44, 0x00, 0x00, 0x07, 0x00, 0x00, 0x00, 0x08, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x94, 0x4d,
    0x12, 0x00, 0x0a, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x18, 0xf6, 0x1a, 0x00, 0x0b, 0x00, 0x00, 0x00, 0x44, 0x00, 0x00, 0x00,
    0x0a, 0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00, 0x04, 0x50, 0x12, 0x00, 0xfa, 0xff, 0x00, 0x10, 0xfa, 0xff, 0x00, 0x14, 0xa4, 0x50,
    0x12, 0x00, 0xfa, 0xff, 0x00, 0x10, 0xfa, 0xff, 0x00, 0x14, 0x5c, 0x20, 0x14, 0x00, 0xfa, 0xff, 0x00, 0x10, 0xfa, 0xff, 0x00, 0x14,
    0x54, 0xf7, 0x22, 0x00, 0x01, 0x00, 0x03, 0x24, 0x2d, 0x18, 0x00, 0x00, 0x21, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00};

void testTheWebmanEntryIsRecognisedAndOursIsNot() {
    assert(kWebmanCustom.size() == 112);
    assert(configs::hasRadiataLoopEdits(kWebmanCustom));
    assert(!configs::hasRadiataLoopEdits(configs::radiataConfig()));
    const Bytes& c = configs::radiataConfig();  // header, hooks 0x124D94 / 0x1AF618, smoothing, title at the end
    assert(c.size() == 54 + 4 && c[0] == 0x3D && c[4] == 0x57 && c[5] == 0x44);
    assert(std::string(c.end() - 10, c.end()) == "SLUS-21262");
}

void testEnsureWritesWhenMissing() {
    Dir d;
    assert(fsx::writeBytes(d.path("Radiata Stories (USA).iso"), makeIso(kRadiataCnf)));
    assert(fsx::writeBytes(d.path("Other (USA).iso"), makeIso("BOOT2 = cdrom0:\\SLUS_213.45;1\r\n")));
    const auto done = configs::ensureConfigs(d.root.string());
    assert(done == std::vector<std::string>{"Radiata Stories (USA).iso"});
    Bytes got;
    assert(fsx::readBytes(d.path("Radiata Stories (USA).iso.CONFIG"), got) && got == configs::radiataConfig());
    assert(!fs::exists(d.path("Other (USA).iso.CONFIG")));  // other games are not touched
    assert(configs::ensureConfigs(d.root.string()).empty());  // a second run does nothing
}

void testEnsureReplacesTheWebmanEntryAndKeepsABackup() {
    Dir d;
    assert(fsx::writeBytes(d.path("R.iso"), makeIso(kRadiataCnf)));
    assert(fsx::writeBytes(d.path("R.iso.CONFIG"), kWebmanCustom));
    assert(configs::ensureConfigs(d.root.string()).size() == 1);
    Bytes got, bak;
    assert(fsx::readBytes(d.path("R.iso.CONFIG"), got) && got == configs::radiataConfig());
    assert(fsx::readBytes(d.path("R.iso.CONFIG.bak"), bak) && bak == kWebmanCustom);
    assert(!fs::exists(d.path("R.iso.CONFIG.new")));
}

void testEnsureLeavesTheOwnersOwnConfig() {
    Dir d;
    assert(fsx::writeBytes(d.path("R.iso"), makeIso(kRadiataCnf)));
    const Bytes mine = {0x3d, 0, 0, 0, 1, 2, 3, 4, 0x44, 0, 0, 0};
    assert(fsx::writeBytes(d.path("R.iso.CONFIG"), mine));
    assert(configs::ensureConfigs(d.root.string()).empty());
    Bytes got;
    assert(fsx::readBytes(d.path("R.iso.CONFIG"), got) && got == mine);
    assert(!fs::exists(d.path("R.iso.CONFIG.bak")));
}

}  // namespace

int main() {
    testSerialIsRead();
    testNotAnIsoGivesNothing();
    testTheWebmanEntryIsRecognisedAndOursIsNot();
    testEnsureWritesWhenMissing();
    testEnsureReplacesTheWebmanEntryAndKeepsABackup();
    testEnsureLeavesTheOwnersOwnConfig();
    std::puts("all config tests passed");
    return 0;
}
