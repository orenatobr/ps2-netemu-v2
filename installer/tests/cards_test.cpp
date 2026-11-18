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

void write(const std::string& path, const std::vector<std::uint8_t>& data) { assert(fsx::writeBytes(path, data)); }

const cards::Bytes kHead(528 * 84, 0xAB);

std::string isoDir(const Dir& d) { return (d.root / "iso").string(); }

void testCardNameRule() {
    assert(cards::cardFileName("Grandia III (USA) (Disc 2).iso") == "PS2_Grandia_III__USA_.VM2");
    assert(cards::cardFileName("/x/Grandia III (USA) (Disc 1).iso") == "PS2_Grandia_III__USA_.VM2");
    assert(cards::cardFileName("Name (USA) [Disc 3 of 4].bin") == "PS2_Name__USA_.VM2");
    assert(cards::cardFileName("Final Fantasy X-2 (USA).iso") == "PS2_Final_Fantasy_X-2__USA_.VM2");
    assert(cards::cardFileName("Game (disc 2).ISO") == "PS2_Game.VM2");
    assert(cards::cardFileName("Naruto: Ultimate Ninja! (USA).iso") == "PS2_Naruto__Ultimate_Ninja___USA_.VM2");
    assert(cards::cardFileName("G\xC3\xB5.iso") == "PS2_G__.VM2");  // a byte at a time, like the patch
    assert(cards::cardFileName("(Disc 1).iso").empty());
    assert(cards::cardTitle(std::string(200, 'A') + ".iso") == std::string(cards::kMaxTitle, 'A'));
}

void testEnsureCardsReportsProgress() {
    Dir d;
    write(d.iso("A (USA) (Disc 1).iso"), {1});
    write(d.iso("A (USA) (Disc 2).iso"), {1});  // same card as disc 1: counted once
    write(d.iso("B.iso"), {1});
    std::vector<std::pair<std::size_t, std::size_t>> seen;
    const auto made = cards::ensureCards(isoDir(d), d.vmc(), kHead, [&](std::size_t done, std::size_t total) { seen.emplace_back(done, total); });
    assert(made.size() == 2);
    assert((seen == std::vector<std::pair<std::size_t, std::size_t>>{{0, 2}, {1, 2}, {2, 2}}));  // before each card, then the end
    seen.clear();
    cards::ensureCards(isoDir(d), d.vmc(), kHead, [&](std::size_t done, std::size_t total) { seen.emplace_back(done, total); });
    assert(seen.empty());  // nothing missing: no report
}

void testEnsureCardsCreatesOnlyMissingOnes() {
    Dir d;
    write(d.iso("Grandia III (USA) (Disc 1).iso"), {1});
    write(d.iso("Grandia III (USA) (Disc 2).iso"), {1});
    write(d.iso("B.ISO"), {1});
    write(d.iso("notes.txt"), {'h', 'i'});
    write(d.iso("(Disc 1).iso"), {1});  // no title: ignored
    fs::create_directories(d.root / "vmc");
    write(d.vmc() + "/PS2_B.VM2", {1, 2, 3});  // an existing card, with saves
    const auto made = cards::ensureCards(isoDir(d), d.vmc(), kHead);
    assert(made == std::vector<std::string>{"PS2_Grandia_III__USA_.VM2"});  // both discs share one card; B existed
    cards::Bytes card;
    assert(fsx::readBytes(d.vmc() + "/PS2_Grandia_III__USA_.VM2", card, cards::kCardBytes + 1) && card.size() == cards::kCardBytes);
    assert(std::equal(kHead.begin(), kHead.end(), card.begin()) && card.back() == 0xFF);
    cards::Bytes old;
    assert(fsx::readBytes(d.vmc() + "/PS2_B.VM2", old) && old == cards::Bytes({1, 2, 3}));  // never touched
    assert(!fs::exists(d.vmc() + "/PS2_Grandia_III__USA_.VM2.new"));
    assert(cards::ensureCards(isoDir(d), d.vmc(), kHead).empty());  // a second run does nothing
}

void testThereIsNoLimitOnTheNumberOfGames() {
    Dir d;
    for (int i = 0; i < 100; ++i) write(d.iso("Game" + std::to_string(100 + i) + ".iso"), {1});
    assert(cards::ensureCards(isoDir(d), d.vmc(), cards::Bytes(528, 0xAB)).size() == 100);
}

void testWriteBlankCardRefusesAnEmptyHead() {
    Dir d;
    assert(!cards::writeBlankCard((d.root / "x.VM2").string(), {}));
    assert(!fs::exists(d.root / "x.VM2"));
}

}  // namespace

int main() {
    std::srand(static_cast<unsigned>(std::time(nullptr)));
    testCardNameRule();
    testEnsureCardsCreatesOnlyMissingOnes();
    testEnsureCardsReportsProgress();
    testThereIsNoLimitOnTheNumberOfGames();
    testWriteBlankCardRefusesAnEmptyHead();
    std::puts("all card tests passed");
    return 0;
}
