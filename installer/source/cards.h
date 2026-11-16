// One PS2 memory card per game. The patched emulator has 32 fixed card paths (/savedata/vmc/PS2_C00.VM2 ...) and reads a
// table file (/savedata/vmc/PS2_CARDS.TBL) that says which slot an ISO file name uses. This code keeps that table and
// creates the formatted cards that are missing. Pure file logic (no console API), so it is tested on the host.
// All the discs of a game (names that differ only by a "(Disc N)" or "[Disc N]" tag) share one slot.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace cards {

using Bytes = std::vector<std::uint8_t>;

constexpr std::size_t kCardBytes = 8650752;  ///< 16384 pages of 512 data bytes and 16 ECC bytes
constexpr std::size_t kRecord = 128;         ///< a table record: slot byte, ISO name (up to 126 bytes), NUL padding
constexpr int kSlots = 32;

struct Entry {
    int slot;
    std::string name;  ///< ISO file name, no folder
};

/// The game an ISO file name belongs to: no folder, no short extension, no "(Disc N)" / "[Disc N]" tag (nor the space
/// before it), no trailing space. "" when nothing is left.
std::string gameTitle(const std::string& isoName);

/// "PS2_C07.VM2" for slot 7.
std::string slotCardName(int slot);

/// The entries of a table file (stops at the empty record or the end). A missing or unreadable file gives none.
std::vector<Entry> readTable(const std::string& path);

/// Writes the table (one record per entry, then the empty record). Atomic: the file appears complete or not at all.
bool writeTable(const std::string& path, const std::vector<Entry>& entries);

/// Writes a blank formatted card: `head` (the written pages) then erased pages up to kCardBytes. The file appears
/// complete or not at all. Returns false on any failure.
bool writeBlankCard(const std::string& path, const Bytes& head);

/// Gives every ISO of `isoDir` a slot (kept when the table already has the name or another disc of the same game,
/// otherwise the lowest free one), rewrites `<vmcDir>/PS2_CARDS.TBL` when it changed and creates the cards of the used
/// slots that do not exist. Cards that exist are never touched. Returns the names of the cards created.
std::vector<std::string> ensureCards(const std::string& isoDir, const std::string& vmcDir, const Bytes& head);

}  // namespace cards
