// Host tests for the per-game card creation (no console needed). Build and run: tests/run.sh
#include <cassert>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <string>
#include <vector>

#include "cards.h"
#include "fsx.h"

namespace fs = std::filesystem;

namespace {

struct Dir {
    fs::path root = fs::temp_directory_path() / ("ps2cards_" + std::to_string(std::rand()));
    Dir() { fs::create_directories(root / "iso"); }
    ~Dir() { fs::remove_all(root); }
    std::string iso(const std::string& name) const { return (root / "iso" / name).string(); }
    std::string vmc() const { return (root / "vmc").string(); }
};

void put32le(std::vector<std::uint8_t>& v, std::size_t at, std::uint32_t x) {
    for (int i = 0; i < 4; ++i) v[at + i] = static_cast<std::uint8_t>(x >> (8 * i));
}
void put32be(std::vector<std::uint8_t>& v, std::size_t at, std::uint32_t x) {
    for (int i = 0; i < 4; ++i) v[at + i] = static_cast<std::uint8_t>(x >> (24 - 8 * i));
}

// A 2048 byte sector image: volume descriptor at 16, root directory at 20, SYSTEM.CNF at 30.
std::vector<std::uint8_t> image(const std::string& cnf, const char* magic = "CD001", bool withCnf = true) {
    std::vector<std::uint8_t> img(40 * 2048, 0);
    const std::size_t pvd = 16 * 2048;
    img[pvd] = 1;
    std::memcpy(&img[pvd + 1], magic, 5);
    img[pvd + 156] = 34;
    put32le(img, pvd + 158, 20);
    put32be(img, pvd + 162, 20);
    put32le(img, pvd + 166, 2048);
    put32be(img, pvd + 170, 2048);
    std::size_t pos = 20 * 2048;
    auto record = [&](const std::string& name, std::uint32_t lba, std::uint32_t size) {
        std::size_t len = 33 + name.size();
        if (len % 2) ++len;
        img[pos] = static_cast<std::uint8_t>(len);
        put32le(img, pos + 2, lba);
        put32be(img, pos + 6, lba);
        put32le(img, pos + 10, size);
        put32be(img, pos + 14, size);
        img[pos + 32] = static_cast<std::uint8_t>(name.size());
        std::memcpy(&img[pos + 33], name.data(), name.size());
        pos += len;
    };
    record(std::string(1, '\0'), 20, 2048);
    record(std::string(1, '\1'), 20, 2048);
    record("FILE0.DAT;1", 31, 100);
    if (withCnf) {
        record("SYSTEM.CNF;1", 30, static_cast<std::uint32_t>(cnf.size()));
        std::memcpy(&img[30 * 2048], cnf.data(), cnf.size());
    }
    return img;
}

std::string boot(const std::string& exe) { return "BOOT2 = cdrom0:\\" + exe + ";1\r\nVER = 1.00\r\nVMODE = NTSC\r\n"; }

void write(const std::string& path, const std::vector<std::uint8_t>& data) { assert(fsx::writeBytes(path, data)); }

const cards::Bytes kHead(528 * 84, 0xAB);

void testSerialFormats() {
    assert(cards::serialFromCnf(boot("SLUS_213.45")) == "SLUS-21345");
    assert(cards::serialFromCnf("BOOT2 = cdrom0:SCES_503.42;1\r\n") == "SCES-50342");
    assert(cards::serialFromCnf("BOOT2 = cdrom0:/slps_250.01;1\r\n") == "SLPS-25001");
    assert(cards::serialFromCnf("BOOT2 = cdrom0:\\SLUS_213.45\r\n") == "SLUS-21345");
    assert(cards::serialFromCnf("BOOT = cdrom:\\SLUS_006.62;1\r\n").empty());  // a PS1 disc has no BOOT2
    assert(cards::serialFromCnf(boot("AB")).empty());                          // too short
    assert(cards::serialFromCnf("").empty());
}

void testDiscOne() {
    assert(cards::discOne("/x/Game (Disc 2).iso") == "/x/Game (Disc 1).iso");
    assert(cards::discOne("/x/Game [Disc 9].iso") == "/x/Game [Disc 1].iso");
    assert(cards::discOne("/x/Game (Disc 2 of 3) (USA).iso") == "/x/Game (Disc 1 of 3) (USA).iso");
    for (const char* p : {"/x/Game.iso", "/x/Game (Disc 1).iso", "/x/Game (Disc 0).iso", "/x/Game (Disc).iso"})
        assert(cards::discOne(p).empty());
}

void testSerialOfImage() {
    Dir d;
    write(d.iso("G.iso"), image(boot("SLUS_213.45")));
    assert(cards::serialOfImage(d.iso("G.iso")) == "SLUS-21345");
    write(d.iso("P.iso"), image("BOOT = cdrom:\\SLUS_006.62;1\r\n"));
    assert(cards::serialOfImage(d.iso("P.iso")).empty());
    write(d.iso("N.iso"), image(boot("SLUS_213.45"), "XXXXX"));
    assert(cards::serialOfImage(d.iso("N.iso")).empty());
    write(d.iso("C.iso"), image("", "CD001", false));
    assert(cards::serialOfImage(d.iso("C.iso")).empty());
    assert(cards::serialOfImage(d.iso("missing.iso")).empty());
}

void testDiscTwoUsesDiscOneWhenItExists() {
    Dir d;
    write(d.iso("Grandia III (USA) (Disc 2).iso"), image(boot("SLUS_213.45")));
    assert(cards::cardSerial(d.iso("Grandia III (USA) (Disc 2).iso")) == "SLUS-21345");  // no disc 1 image
    write(d.iso("Grandia III (USA) (Disc 1).iso"), image(boot("SLUS_213.34")));
    assert(cards::cardSerial(d.iso("Grandia III (USA) (Disc 2).iso")) == "SLUS-21334");
    assert(cards::cardSerial(d.iso("Grandia III (USA) (Disc 1).iso")) == "SLUS-21334");
}

void testEnsureCardsCreatesOnlyMissingOnes() {
    Dir d;
    write(d.iso("A (Disc 1).iso"), image(boot("SLUS_213.34")));
    write(d.iso("A (Disc 2).iso"), image(boot("SLUS_213.45")));
    write(d.iso("B.ISO"), image(boot("SCUS_974.08")));
    write(d.iso("ps1.bin"), image("BOOT = cdrom:\\SLUS_006.62;1\r\n"));
    write(d.iso("notes.txt"), {'h', 'i'});
    fs::create_directories(d.root / "vmc");
    write(d.vmc() + "/SCUS-97408.VM2", {1, 2, 3});  // an existing card, with saves
    const auto made = cards::ensureCards(d.iso("").substr(0, d.iso("").size() - 1), d.vmc(), kHead);
    assert(made == std::vector<std::string>{"SLUS-21334.VM2"});  // both discs of A share one card; B existed
    cards::Bytes card;
    assert(fsx::readBytes(d.vmc() + "/SLUS-21334.VM2", card, cards::kCardBytes + 1));
    assert(card.size() == cards::kCardBytes);
    assert(std::equal(kHead.begin(), kHead.end(), card.begin()));
    assert(card[kHead.size()] == 0xFF && card.back() == 0xFF);
    cards::Bytes old;
    assert(fsx::readBytes(d.vmc() + "/SCUS-97408.VM2", old) && old == cards::Bytes({1, 2, 3}));  // never touched
    assert(!fs::exists(d.vmc() + "/SLUS-21334.VM2.new"));
    assert(cards::ensureCards(d.iso("").substr(0, d.iso("").size() - 1), d.vmc(), kHead).empty());  // a second run does nothing
}

void testWriteBlankCardRefusesAnEmptyHead() {
    Dir d;
    assert(!cards::writeBlankCard((d.root / "x.VM2").string(), {}));
    assert(!fs::exists(d.root / "x.VM2"));
}

}  // namespace

int main() {
    std::srand(static_cast<unsigned>(std::time(nullptr)));
    testSerialFormats();
    testDiscOne();
    testSerialOfImage();
    testDiscTwoUsesDiscOneWhenItExists();
    testEnsureCardsCreatesOnlyMissingOnes();
    testWriteBlankCardRefusesAnEmptyHead();
    std::puts("all card tests passed");
    return 0;
}
