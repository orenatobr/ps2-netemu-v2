// Install / restore the patched ps2_netemu.self. Pure file logic: no console API, so it is tested on the host.
#pragma once

#include <cstdint>
#include <functional>
#include <string>
#include <vector>

#include "fsx.h"

namespace installer {

using Bytes = std::vector<std::uint8_t>;

/// Lowercase hex SHA-256. `onChunk` is called about every 64 KB so a caller can draw a progress bar.
std::string sha256(const Bytes& data, const fsx::Chunk& onChunk = nullptr);

struct Config {
    std::string target;     ///< The emulator file on the console (/dev_blind/ps2emu/ps2_netemu.self).
    std::string backup;     ///< Where the stock file is kept.
    std::string stockSha;   ///< SHA-256 of the only stock build this patch fits.
    std::string patchedSha; ///< SHA-256 of the patched build we install.
    std::vector<std::string> olderPatched;  ///< SHA-256 of the builds this project shipped before: safe to replace even without a backup.
};

enum class State { Missing, Stock, Patched, OlderPatch, Unknown };

struct Outcome {
    bool ok = false;
    /// installed, installed_nobackup, already, restored (ok); missing, not_stock, bad_payload, no_backup, io_error (not ok).
    std::string code;
};

/// What install() and restore() are doing, in the order they happen (the screen shows one line per stage).
enum class Stage { Package, Read, Backup, Write, Verify, Final, Cards };

/// Called while install() or restore() runs with the stage and the overall fraction done (0 to 1, never going back).
using Progress = std::function<void(Stage stage, float fraction)>;

/// Reads the target and tells which build it is.
State detect(const Config& cfg);

/// Backs the stock file up, then replaces it with `payload`. Refuses any file that is not the known stock build.
Outcome install(const Config& cfg, const Bytes& payload, const Progress& progress = nullptr);

/// Puts the backed-up stock file back.
Outcome restore(const Config& cfg, const Progress& progress = nullptr);

}  // namespace installer
