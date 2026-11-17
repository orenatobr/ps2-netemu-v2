// One PS2 memory card per game. The patched emulator names the card of an ISO after its file name ("PS2_<title>.VM2": no folder,
// no short extension, no "(Disc N)" / "[Disc N]" tag, cut at 52 bytes, every byte that is not a letter, a digit, '_' or '-'
// turned into '_'), so all the discs of a game share one card and there is no limit on the number of games. The emulator does
// not create a missing card, so this code creates the formatted cards that are missing. Pure file logic (no console API),
// so it is tested on the host. The rule must stay identical to cave_wrap.py (card_name) and the code in the patch.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace cards {

using Bytes = std::vector<std::uint8_t>;

constexpr std::size_t kCardBytes = 8650752;  ///< 16384 pages of 512 data bytes and 16 ECC bytes
constexpr std::size_t kMaxTitle = 52;

/// The title part of the card name for an ISO file name or path: "" when nothing is left.
std::string cardTitle(const std::string& isoName);

/// "PS2_<title>.VM2", or "" when the ISO gives no title.
std::string cardFileName(const std::string& isoName);

/// Writes a blank formatted card: `head` (the written pages) then erased pages up to kCardBytes. The file appears
/// complete or not at all. Returns false on any failure.
bool writeBlankCard(const std::string& path, const Bytes& head);

/// Creates `<vmcDir>/<cardFileName>` for every .iso / .bin of `isoDir` whose card does not exist. Cards that exist are
/// never touched. Returns the names of the cards created.
std::vector<std::string> ensureCards(const std::string& isoDir, const std::string& vmcDir, const Bytes& head);

}  // namespace cards
