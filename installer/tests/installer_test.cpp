// Host tests for the install/restore logic (no console needed). Build and run: tests/run.sh
#include <cassert>
#include <cstdio>
#include <filesystem>
#include <string>
#include <vector>

#include "fsx.h"
#include "installer.h"

namespace fs = std::filesystem;
using installer::Bytes;
using installer::State;

namespace {

Bytes bytes(const std::string& s) { return Bytes(s.begin(), s.end()); }

struct Fixture {
    fs::path dir = fs::temp_directory_path() / ("ps2inst_" + std::to_string(std::rand()));
    Bytes stock = bytes("stock ps2_netemu"), patched = bytes("patched ps2_netemu!");
    installer::Config cfg;

    Fixture() {
        fs::create_directories(dir / "flash");
        cfg.target = (dir / "flash/ps2_netemu.self").string();
        cfg.backup = (dir / "backup.self").string();
        cfg.stockSha = installer::sha256(stock);
        cfg.patchedSha = installer::sha256(patched);
    }
    ~Fixture() { fs::remove_all(dir); }
    void put(const std::string& path, const Bytes& b) { assert(fsx::writeBytes(path, b)); }
    Bytes get(const std::string& path) {
        Bytes b;
        assert(fsx::readBytes(path, b));
        return b;
    }
};

void testSha256() {
    // FIPS 180-4 test vectors
    assert(installer::sha256(bytes("abc")) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    assert(installer::sha256({}) == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
    assert(installer::sha256(bytes("abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq")) ==
           "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1");
    assert(installer::sha256(Bytes(1000000, 'a')) == "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0");
}

void testInstallBacksUpAndReplaces() {
    Fixture f;
    f.put(f.cfg.target, f.stock);
    assert(installer::detect(f.cfg) == State::Stock);
    const auto r = installer::install(f.cfg, f.patched);
    assert(r.ok && r.code == "installed");
    assert(f.get(f.cfg.target) == f.patched);
    assert(f.get(f.cfg.backup) == f.stock);
    assert(installer::detect(f.cfg) == State::Patched);
    assert(!fs::exists(f.cfg.target + ".new"));
}

void testInstallTwiceIsHarmless() {
    Fixture f;
    f.put(f.cfg.target, f.stock);
    assert(installer::install(f.cfg, f.patched).ok);
    const auto r = installer::install(f.cfg, f.patched);
    assert(r.ok && r.code == "already");
    assert(f.get(f.cfg.backup) == f.stock);  // the backup is never overwritten by the patched file
}

void testRestore() {
    Fixture f;
    f.put(f.cfg.target, f.stock);
    assert(installer::install(f.cfg, f.patched).ok);
    const auto r = installer::restore(f.cfg);
    assert(r.ok && r.code == "restored");
    assert(f.get(f.cfg.target) == f.stock);
    assert(installer::restore(f.cfg).code == "already");
}

void testRefusesUnknownFile() {
    Fixture f;
    const Bytes other = bytes("some other firmware build");
    f.put(f.cfg.target, other);
    assert(installer::detect(f.cfg) == State::Unknown);
    const auto r = installer::install(f.cfg, f.patched);
    assert(!r.ok && r.code == "not_stock");
    assert(f.get(f.cfg.target) == other);  // untouched
    assert(!fs::exists(f.cfg.backup));
}

void testUpdatesAnOlderPatchWhenTheBackupOfTheOriginalExists() {
    Fixture f;
    const Bytes older = bytes("an older patched build");
    f.put(f.cfg.target, older);
    f.put(f.cfg.backup, f.stock);
    assert(installer::detect(f.cfg) == State::Unknown);
    const auto r = installer::install(f.cfg, f.patched);
    assert(r.ok && r.code == "installed");
    assert(f.get(f.cfg.target) == f.patched);
    assert(f.get(f.cfg.backup) == f.stock);
}

void testAnOlderReleaseIsReplacedEvenWithoutABackup() {
    Fixture f;
    const Bytes older = bytes("a build this project shipped before");
    f.cfg.olderPatched = {installer::sha256(older)};
    f.put(f.cfg.target, older);
    assert(installer::detect(f.cfg) == State::OlderPatch);
    const auto r = installer::install(f.cfg, f.patched);
    assert(r.ok && r.code == "installed_nobackup");
    assert(f.get(f.cfg.target) == f.patched);
    assert(!fs::exists(f.cfg.backup));  // there is no original to keep, and none is invented
}

void testAnOlderReleaseWithTheBackupKeepsTheOriginal() {
    Fixture f;
    const Bytes older = bytes("a build this project shipped before");
    f.cfg.olderPatched = {installer::sha256(older)};
    f.put(f.cfg.target, older);
    f.put(f.cfg.backup, f.stock);
    const auto r = installer::install(f.cfg, f.patched);
    assert(r.ok && r.code == "installed");
    assert(f.get(f.cfg.backup) == f.stock);
}

void testAnUnknownFileWithADamagedBackupIsStillRefused() {
    Fixture f;
    const Bytes other = bytes("some other firmware build");
    f.put(f.cfg.target, other);
    f.put(f.cfg.backup, bytes("not the original"));
    const auto r = installer::install(f.cfg, f.patched);
    assert(!r.ok && r.code == "not_stock");
    assert(f.get(f.cfg.target) == other);
}

void testRefusesWrongPayload() {
    Fixture f;
    f.put(f.cfg.target, f.stock);
    const auto r = installer::install(f.cfg, bytes("not the patched build"));
    assert(!r.ok && r.code == "bad_payload");
    assert(f.get(f.cfg.target) == f.stock);
}

void testMissingTargetAndMissingBackup() {
    Fixture f;
    assert(installer::detect(f.cfg) == State::Missing);
    assert(installer::install(f.cfg, f.patched).code == "missing");
    f.put(f.cfg.target, f.patched);  // patched but no backup: nothing to restore from
    assert(installer::restore(f.cfg).code == "no_backup");
    assert(f.get(f.cfg.target) == f.patched);
}

void testCorruptBackupIsRebuiltFromStockTarget() {
    Fixture f;
    f.put(f.cfg.target, f.stock);
    f.put(f.cfg.backup, bytes("garbage"));
    assert(installer::install(f.cfg, f.patched).ok);
    assert(f.get(f.cfg.backup) == f.stock);
}

/// Records every progress report so the tests can check the bar only moves forward and ends full.
struct Recorder {
    std::vector<std::pair<installer::Stage, float>> seen;
    installer::Progress fn() {
        return [this](installer::Stage s, float f) { seen.emplace_back(s, f); };
    }
    void expectSmoothAndComplete(std::size_t minReports) const {
        assert(seen.size() >= minReports);
        float last = 0;
        for (const auto& [stage, f] : seen) {
            (void)stage;
            assert(f >= last && f >= 0.0f && f <= 1.0f);
            last = f;
        }
        assert(seen.back().second == 1.0f);
    }
};

void testSha256ReportsChunks() {
    const Bytes big(300000, 'a');
    std::size_t calls = 0, lastDone = 0;
    const std::string sha = installer::sha256(big, [&](std::size_t done, std::size_t total) {
        assert(total == big.size() && done >= lastDone && done <= total);
        lastDone = done;
        ++calls;
    });
    assert(sha == installer::sha256(big));
    assert(calls >= 4 && lastDone == big.size());  // several reports, not one jump
}

void testInstallReportsProgress() {
    Fixture f;
    f.put(f.cfg.target, Bytes(300000, 's'));
    Bytes stock(300000, 's'), patched(400000, 'p');
    f.cfg.stockSha = installer::sha256(stock);
    f.cfg.patchedSha = installer::sha256(patched);
    Recorder r;
    assert(installer::install(f.cfg, patched, r.fn()).ok);
    r.expectSmoothAndComplete(20);
    assert(r.seen.front().second == 0.0f);
}

void testRestoreReportsProgress() {
    Fixture f;
    Bytes stock(300000, 's'), patched(400000, 'p');
    f.cfg.stockSha = installer::sha256(stock);
    f.cfg.patchedSha = installer::sha256(patched);
    f.put(f.cfg.target, stock);
    assert(installer::install(f.cfg, patched).ok);
    Recorder r;
    assert(installer::restore(f.cfg, r.fn()).ok);
    r.expectSmoothAndComplete(20);
}

void testRefusalKeepsTheBarInRange() {
    Fixture f;
    f.put(f.cfg.target, bytes("some other firmware build"));
    Recorder r;
    assert(!installer::install(f.cfg, f.patched, r.fn()).ok);
    assert(r.seen.empty() || r.seen.back().second <= 1.0f);
}

}  // namespace

int main() {
    std::srand(static_cast<unsigned>(std::time(nullptr)));
    testSha256();
    testInstallBacksUpAndReplaces();
    testInstallTwiceIsHarmless();
    testRestore();
    testRefusesUnknownFile();
    testUpdatesAnOlderPatchWhenTheBackupOfTheOriginalExists();
    testAnOlderReleaseIsReplacedEvenWithoutABackup();
    testAnOlderReleaseWithTheBackupKeepsTheOriginal();
    testAnUnknownFileWithADamagedBackupIsStillRefused();
    testRefusesWrongPayload();
    testMissingTargetAndMissingBackup();
    testCorruptBackupIsRebuiltFromStockTarget();
    testSha256ReportsChunks();
    testInstallReportsProgress();
    testRestoreReportsProgress();
    testRefusalKeepsTheBarInRange();
    std::puts("all installer tests passed");
    return 0;
}
