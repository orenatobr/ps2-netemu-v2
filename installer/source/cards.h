// One PS2 memory card per game: finds the serial of each ISO and creates the formatted card that is missing.
// Pure file logic (no console API), so it is tested on the host. Same rule as the patched emulator:
// a disc named "(Disc N)" or "[Disc N]" with N from 2 to 9 uses the card of the image with the same name and "1".
#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace cards {

using Bytes = std::vector<std::uint8_t>;

constexpr std::size_t kCardBytes = 8650752;  ///< 16384 pages of 512 data bytes and 16 ECC bytes

/// The serial ("SLUS-21345") of the BOOT2 line of a SYSTEM.CNF text, or "" when there is no usable one.
std::string serialFromCnf(const std::string& text);

/// The path of disc 1 for a disc 2..9 image, or "" when the name is not of that kind.
std::string discOne(const std::string& isoPath);

/// The serial of the image itself (ISO9660, 2048 byte sectors), or "".
std::string serialOfImage(const std::string& isoPath);

/// The serial the card of this image is named after: disc 1's when the name says so and that image gives one.
std::string cardSerial(const std::string& isoPath);

/// Writes a blank formatted card: `head` (the written pages) then erased pages up to kCardBytes. The file appears
/// complete or not at all. Returns false on any failure.
bool writeBlankCard(const std::string& path, const Bytes& head);

/// Creates `<vmcDir>/<serial>.VM2` for every image of `isoDir` whose card does not exist. Cards that exist are never
/// touched. Returns the names of the cards created.
std::vector<std::string> ensureCards(const std::string& isoDir, const std::string& vmcDir, const Bytes& head);

}  // namespace cards
