#include "installer.h"

#include <algorithm>
#include <cstring>

#include "fsx.h"

namespace installer {
namespace {

constexpr std::uint32_t kK[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01,
    0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
    0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
    0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08,
    0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};

inline std::uint32_t rotr(std::uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }

void block(std::uint32_t h[8], const std::uint8_t* p) {
    std::uint32_t w[64];
    for (int i = 0; i < 16; ++i) w[i] = (std::uint32_t(p[4 * i]) << 24) | (std::uint32_t(p[4 * i + 1]) << 16) |
                                        (std::uint32_t(p[4 * i + 2]) << 8) | p[4 * i + 3];
    for (int i = 16; i < 64; ++i) {
        const std::uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
        const std::uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
        w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    std::uint32_t a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], hh = h[7];
    for (int i = 0; i < 64; ++i) {
        const std::uint32_t t1 = hh + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + kK[i] + w[i];
        const std::uint32_t t2 = (rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
        hh = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
    }
    h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
}

bool readAll(const std::string& path, Bytes& out) { return fsx::readBytes(path, out); }

/// Turns the chunk reports of each step into one bar that only moves forward.
class Meter {
public:
    explicit Meter(const Progress& progress) : progress_(progress) {}

    void at(Stage stage, float fraction) {
        last_ = std::max(last_, std::min(fraction, 1.0f));
        if (progress_) progress_(stage, last_);
    }

    /// Chunk callback that maps the step's own 0..1 onto the slice [lo, hi] of the whole bar.
    fsx::Chunk slice(Stage stage, float lo, float hi) {
        return [=, this](std::size_t done, std::size_t total) { at(stage, lo + (hi - lo) * (total ? float(done) / float(total) : 1.0f)); };
    }

private:
    const Progress& progress_;
    float last_ = 0;
};

/// Reads a file and hashes it, the first half of [lo, hi] for the read and the second half for the hash.
bool readHashed(const std::string& path, Bytes& out, std::string& sha, Meter& m, Stage stage, float lo, float hi) {
    const float mid = (lo + hi) / 2;
    if (!fsx::readBytes(path, out, 64u * 1024 * 1024, m.slice(stage, lo, mid))) return false;
    sha = sha256(out, m.slice(stage, mid, hi));
    return true;
}

/// Writes `data` next to `path`, checks it by hash, then swaps it in. On failure `path` keeps its old content
/// unless the swap itself failed half way, in which case `fallback` is written back. The write, the check of the
/// new file and the final check share the part of the bar from `start` to the end (40%, 30% and 30%).
bool replaceFile(const std::string& path, const Bytes& data, const std::string& wantSha, const Bytes& fallback, Meter& m,
                 float start) {
    const float w = (1.0f - start) * 0.4f, v = (1.0f - start) * 0.3f;
    const std::string tmp = path + ".new";
    Bytes check;
    std::string sha;
    if (!fsx::writeBytes(tmp, data, m.slice(Stage::Write, start, start + w)) ||
        !readHashed(tmp, check, sha, m, Stage::Verify, start + w, start + w + v) || sha != wantSha) {
        fsx::removeFile(tmp);
        return false;
    }
    if (!fsx::removeFile(path) || !fsx::renameFile(tmp, path)) {
        fsx::writeBytes(path, fallback);  // never leave the console without an emulator
        fsx::removeFile(tmp);
        return false;
    }
    Bytes after;
    if (!readHashed(path, after, sha, m, Stage::Final, start + w + v, 1.0f) || sha != wantSha) return false;
    m.at(Stage::Final, 1.0f);
    return true;
}

}  // namespace

std::string sha256(const Bytes& data, const fsx::Chunk& onChunk) {
    std::uint32_t h[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
    std::size_t i = 0;
    for (; i + 64 <= data.size(); i += 64) {
        block(h, data.data() + i);
        if (onChunk && ((i + 64) % (64 * 1024) == 0)) onChunk(i + 64, data.size());
    }
    if (onChunk) onChunk(data.size(), data.size());
    std::uint8_t tail[128] = {0};
    const std::size_t rest = data.size() - i;
    if (rest) std::memcpy(tail, data.data() + i, rest);
    tail[rest] = 0x80;
    const std::size_t len = rest < 56 ? 64 : 128;
    const std::uint64_t bits = std::uint64_t(data.size()) * 8;
    for (int k = 0; k < 8; ++k) tail[len - 1 - k] = std::uint8_t(bits >> (8 * k));
    for (std::size_t o = 0; o < len; o += 64) block(h, tail + o);
    static const char* hex = "0123456789abcdef";
    std::string out;
    for (int k = 0; k < 8; ++k)
        for (int s = 28; s >= 0; s -= 4) out += hex[(h[k] >> s) & 0xf];
    return out;
}

static bool isOlder(const Config& cfg, const std::string& sha) {
    return std::find(cfg.olderPatched.begin(), cfg.olderPatched.end(), sha) != cfg.olderPatched.end();
}

State detect(const Config& cfg) {
    Bytes cur;
    if (!readAll(cfg.target, cur)) return State::Missing;
    const std::string sha = sha256(cur);
    if (sha == cfg.patchedSha) return State::Patched;
    if (sha == cfg.stockSha) return State::Stock;
    if (isOlder(cfg, sha)) return State::OlderPatch;
    return State::Unknown;
}

Outcome install(const Config& cfg, const Bytes& payload, const Progress& progress) {
    Meter m(progress);
    m.at(Stage::Package, 0);
    if (sha256(payload, m.slice(Stage::Package, 0.0f, 0.10f)) != cfg.patchedSha) return {false, "bad_payload"};
    Bytes cur;
    std::string sha;
    if (!readHashed(cfg.target, cur, sha, m, Stage::Read, 0.10f, 0.16f)) return {false, "missing"};
    if (sha == cfg.patchedSha) {
        m.at(Stage::Final, 1.0f);
        return {true, "already"};
    }

    Bytes saved;
    std::string savedSha;
    const bool backupOk = readHashed(cfg.backup, saved, savedSha, m, Stage::Backup, 0.16f, 0.22f) && savedSha == cfg.stockSha;
    // A patched build is replaced when the original is safe in the backup (any unknown file then comes from a patch, an
    // older release or another tool), or when it is one of the builds this project shipped (a full copy of the stock
    // file with our edits: replacing it cannot make things worse, but there is then no original to restore). Any other
    // file without a valid backup is refused.
    const bool known = sha == cfg.stockSha || isOlder(cfg, sha);
    if (!known && !backupOk) return {false, "not_stock"};
    if (sha != cfg.stockSha && !backupOk) {
        if (!replaceFile(cfg.target, payload, cfg.patchedSha, cur, m, 0.30f)) return {false, "io_error"};
        return {true, "installed_nobackup"};
    }
    if (!backupOk) {  // missing or damaged: rebuild it from the live file (which is the stock one here)
        if (!fsx::writeBytes(cfg.backup, cur, m.slice(Stage::Backup, 0.22f, 0.27f)) ||
            !readHashed(cfg.backup, saved, savedSha, m, Stage::Backup, 0.27f, 0.30f) || savedSha != cfg.stockSha)
            return {false, "io_error"};
    }
    if (!replaceFile(cfg.target, payload, cfg.patchedSha, cur, m, 0.30f)) return {false, "io_error"};
    return {true, "installed"};
}

Outcome restore(const Config& cfg, const Progress& progress) {
    Meter m(progress);
    m.at(Stage::Backup, 0);
    Bytes saved;
    std::string savedSha;
    if (!readHashed(cfg.backup, saved, savedSha, m, Stage::Backup, 0.0f, 0.15f) || savedSha != cfg.stockSha)
        return {false, "no_backup"};
    Bytes cur;
    std::string sha;
    if (readHashed(cfg.target, cur, sha, m, Stage::Read, 0.15f, 0.20f) && sha == cfg.stockSha) {
        m.at(Stage::Final, 1.0f);
        return {true, "already"};
    }
    if (!replaceFile(cfg.target, saved, cfg.stockSha, cur, m, 0.20f)) return {false, "io_error"};
    return {true, "restored"};
}

}  // namespace installer
