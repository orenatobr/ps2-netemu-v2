// Host tests for the install/restore logic (no console needed). Build and run: tests/run.sh
#include <cassert>
#include <cstdio>
#include <filesystem>
#include <string>

#include "fsx.h"
#include "installer.h"

namespace fs = std::filesystem;
using installer::Bytes;
using installer::State;

namespace {

Bytes bytes(const std::string& s) { return Bytes(s.begin(), s.end()); }

struct Fixture {
    fs::path dir = fs::temp_directory_path() / ("ps1inst_" + std::to_string(std::rand()));
    Bytes stock = bytes("stock ps1_netemu"), patched = bytes("patched ps1_netemu!");
    installer::Config cfg;

    Fixture() {
        fs::create_directories(dir / "flash");
        cfg.target = (dir / "flash/ps1_netemu.self").string();
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

}  // namespace

int main() {
    std::srand(static_cast<unsigned>(std::time(nullptr)));
    testSha256();
    testInstallBacksUpAndReplaces();
    testInstallTwiceIsHarmless();
    testRestore();
    testRefusesUnknownFile();
    testRefusesWrongPayload();
    testMissingTargetAndMissingBackup();
    testCorruptBackupIsRebuiltFromStockTarget();
    std::puts("all installer tests passed");
    return 0;
}
