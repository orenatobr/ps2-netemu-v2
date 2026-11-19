// Per-game CONFIG files for the ps2_netemu emulator (the file beside an ISO, "<iso name>.CONFIG", that webMAN passes to it).
//
// Radiata Stories (US, SLUS_212.62): the CONFIG webMAN copies beside the ISO on its first mount (its database entry CUSTOM) replaces
// busy-wait loops of the game's data unpack code, near the function that the same CONFIG hooks (0x125004, 0x1250A4, 0x14205C) with
// a branch that is never taken, so the results of the VU0 unpack are read before they are ready: the experience points the game
// computes after a battle come out random and the characters never level up. The CONFIG of the PS2 Classics package does not do that.
// This writes a CONFIG without those edits. Pure file logic, tested on the host.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace configs {

using Bytes = std::vector<std::uint8_t>;

/// The serial this CONFIG is for.
constexpr const char* kRadiataSerial = "SLUS_212.62";

/// The CONFIG written for Radiata Stories (US): revision, VU xgkick delay, the two EE hooks of the game and the smoothing switch.
const Bytes& radiataConfig();

/// True when `config` is a ps2_netemu CONFIG with the loop edit of address 0x125004 (the harmful webMAN database entry).
bool hasRadiataLoopEdits(const Bytes& config);

/// For every .iso of `isoDir` whose boot serial is Radiata Stories (US): writes `<iso>.CONFIG` when there is none, or replaces
/// it (keeping the old file as `<iso>.CONFIG.bak`) when it has the loop edits. Any other CONFIG is left alone. Returns the names
/// of the ISOs whose CONFIG was written.
std::vector<std::string> ensureConfigs(const std::string& isoDir);

}  // namespace configs
