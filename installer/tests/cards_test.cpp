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

void testGameTitle() {
    assert(cards::gameTitle("Grandia III (USA) (Disc 2).iso") == "Grandia III (USA)");
    assert(cards::gameTitle("/x/Grandia III (USA) (Disc 1).iso") == "Grandia III (USA)");
    assert(cards::gameTitle("Name [Disc 3 of 4].bin") == "Name");
    assert(cards::gameTitle("Final Fantasy X-2 (USA).iso") == "Final Fantasy X-2 (USA)");
    assert(cards::gameTitle("Game (disc 2).ISO") == "Game");
    assert(cards::gameTitle("(Disc 1).iso").empty());
}

void testSlotCardName() {
    assert(cards::slotCardName(0) == "PS2_C00.VM2");
    assert(cards::slotCardName(31) == "PS2_C31.VM2");
}

void testTableRoundTripAndFormat() {
    Dir d;
    const std::string p = (d.root / "t.TBL").string();
    assert(cards::readTable(p).empty());  // missing
    assert(cards::writeTable(p, {{3, "A (Disc 1).iso"}, {3, "A (Disc 2).iso"}, {0, "B.iso"}}));
    cards::Bytes raw;
    assert(fsx::readBytes(p, raw) && raw.size() == 4 * cards::kRecord);  // three records and the empty one
    assert(raw[0] == 3 && std::string(reinterpret_cast<char*>(&raw[1])) == "A (Disc 1).iso");
    assert(raw[3 * cards::kRecord] == 0 && raw[3 * cards::kRecord + 1] == 0);
    const auto back = cards::readTable(p);
    assert(back.size() == 3 && back[2].slot == 0 && back[2].name == "B.iso" && back[1].name == "A (Disc 2).iso");
    assert(!cards::writeTable(p, {{cards::kSlots, "x.iso"}}) && !cards::writeTable(p, {{1, std::string(127, 'x')}}));
    assert(cards::readTable(p).size() == 3);  // a refused write leaves the old file
    assert(!fs::exists(p + ".new"));
}

void testEnsureCardsAssignsSlotsAndCreatesOnlyMissingCards() {
    Dir d;
    write(d.iso("Grandia III (USA) (Disc 1).iso"), {1});
    write(d.iso("Grandia III (USA) (Disc 2).iso"), {1});
    write(d.iso("B.ISO"), {1});
    write(d.iso("notes.txt"), {'h', 'i'});
    write(d.iso("(Disc 1).iso"), {1});  // no title: ignored
    fs::create_directories(d.root / "vmc");
    write(d.vmc() + "/PS2_C00.VM2", {1, 2, 3});  // an existing card, with saves
    const auto made = cards::ensureCards(isoDir(d), d.vmc(), kHead);
    const auto table = cards::readTable(d.vmc() + "/PS2_CARDS.TBL");
    assert(table.size() == 3);  // both discs and B
    assert(table[0].name == "B.ISO" && table[0].slot == 0 && table[1].slot == 1 && table[2].slot == 1);  // discs share slot 1
    assert(made == std::vector<std::string>{"PS2_C01.VM2"});  // slot 0 existed
    cards::Bytes card;
    assert(fsx::readBytes(d.vmc() + "/PS2_C01.VM2", card, cards::kCardBytes + 1) && card.size() == cards::kCardBytes);
    assert(std::equal(kHead.begin(), kHead.end(), card.begin()) && card.back() == 0xFF);
    cards::Bytes old;
    assert(fsx::readBytes(d.vmc() + "/PS2_C00.VM2", old) && old == cards::Bytes({1, 2, 3}));  // never touched
    assert(!fs::exists(d.vmc() + "/PS2_C01.VM2.new") && !fs::exists(d.vmc() + "/PS2_CARDS.TBL.new"));
    assert(cards::ensureCards(isoDir(d), d.vmc(), kHead).empty());  // a second run does nothing
}

void testSlotsAreStableWhenGamesAreAdded() {
    Dir d;
    write(d.iso("M.iso"), {1});
    cards::ensureCards(isoDir(d), d.vmc(), kHead);
    write(d.iso("A.iso"), {1});  // sorts before M, but M keeps slot 0
    write(d.iso("M (Disc 2).iso"), {1});
    cards::ensureCards(isoDir(d), d.vmc(), kHead);
    const auto t = cards::readTable(d.vmc() + "/PS2_CARDS.TBL");
    assert(t.size() == 3 && t[0].name == "M.iso" && t[0].slot == 0);
    for (const auto& e : t) assert(e.name != "A.iso" || e.slot == 1);
    for (const auto& e : t) assert(e.name != "M (Disc 2).iso" || e.slot == 0);  // another disc of M joins slot 0
}

void testMoreGamesThanSlotsAreLeftOnTheSharedCard() {
    Dir d;
    for (int i = 0; i < cards::kSlots + 3; ++i) write(d.iso("Game" + std::to_string(100 + i) + ".iso"), {1});
    cards::ensureCards(isoDir(d), d.vmc(), kHead);
    assert(cards::readTable(d.vmc() + "/PS2_CARDS.TBL").size() == static_cast<std::size_t>(cards::kSlots));
}

void testNamesThatDoNotFitAreIgnored() {
    Dir d;
    write(d.iso(std::string(130, 'x') + ".iso"), {1});
    assert(cards::ensureCards(isoDir(d), d.vmc(), kHead).empty());
}

void testWriteBlankCardRefusesAnEmptyHead() {
    Dir d;
    assert(!cards::writeBlankCard((d.root / "x.VM2").string(), {}));
    assert(!fs::exists(d.root / "x.VM2"));
}

}  // namespace

int main() {
    std::srand(static_cast<unsigned>(std::time(nullptr)));
    testGameTitle();
    testSlotCardName();
    testTableRoundTripAndFormat();
    testEnsureCardsAssignsSlotsAndCreatesOnlyMissingCards();
    testSlotsAreStableWhenGamesAreAdded();
    testMoreGamesThanSlotsAreLeftOnTheSharedCard();
    testNamesThatDoNotFitAreIgnored();
    testWriteBlankCardRefusesAnEmptyHead();
    std::puts("all card tests passed");
    return 0;
}
