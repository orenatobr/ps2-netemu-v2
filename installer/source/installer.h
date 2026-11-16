// Install / restore the patched ps1_netemu.self. Pure file logic: no console API, so it is tested on the host.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace installer {

using Bytes = std::vector<std::uint8_t>;

/// Lowercase hex SHA-256.
std::string sha256(const Bytes& data);

struct Config {
    std::string target;     ///< The emulator file on the console (/dev_blind/ps1emu/ps1_netemu.self).
    std::string backup;     ///< Where the stock file is kept.
    std::string stockSha;   ///< SHA-256 of the only stock build this patch fits.
    std::string patchedSha; ///< SHA-256 of the patched build we install.
};

enum class State { Missing, Stock, Patched, Unknown };

struct Outcome {
    bool ok = false;
    /// installed, already, restored (ok); missing, not_stock, bad_payload, no_backup, io_error (not ok).
    std::string code;
};

/// Reads the target and tells which build it is.
State detect(const Config& cfg);

/// Backs the stock file up, then replaces it with `payload`. Refuses any file that is not the known stock build.
Outcome install(const Config& cfg, const Bytes& payload);

/// Puts the backed-up stock file back.
Outcome restore(const Config& cfg);

}  // namespace installer
