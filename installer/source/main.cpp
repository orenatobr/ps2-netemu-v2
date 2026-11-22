// PS2 emulator patch installer: copies the patched ps2_netemu.self into the system folder (with a backup)
// or puts the original back. The patched file travels inside this package.
#include <sys/file.h>

#include <iterator>
#include <string>

#include "cards.h"
#include "configs.h"
#include "gfx.h"
#include "fsx.h"
#include "installer.h"
#include "ps3.h"
#include "ui.h"
#include "ps2_card_head_bin.h"
#include "ps2_netemu_v2_bin.h"

#ifndef PATCHED_SHA256
#error "PATCHED_SHA256 must be set by the Makefile (sha256 of payload/ps2_netemu_v2.bin)"
#endif

namespace {

// The one stock build this patch was made for (ps2_netemu.self, LV2 type).
constexpr const char* kStockSha = "bad3e45c9a81f25726e414b146ea5a112f28216ab4bdd2fd9f5c81b33d04c80a";
constexpr const char* kTarget = "/dev_blind/ps2emu/ps2_netemu.self";
constexpr const char* kBackup = "/dev_hdd0/ps2_netemu_stock.self";
// Every other build this project put on a console (releases and test builds): a full copy of the stock file with our edits.
constexpr const char* kOlderPatched[] = {
    "30d6c72f9ced4d1685a1574127a8d21b28fb157252881e7974e9dd659703aba5", "1bc79d941650368004bddff1c13dfd39f747b165ae0f41307ab4465e026c5747",
    "8c6900c100a2c07f00443ababbc1a4895fee668bc43097d8be7934fe09da964e", "a9fabddf62d92228af214335e9c26e8cfbe6f8a74fd03d0efa5510a738232649",
    "727d6e9b6141b2f230539e836bedbb728bffb1d2e9672305acdc207195c4160e", "45f4a2997fa2a66b7d3c11fc4a42e77787fdebd5b66f4653ee455c1fc3493342",
    "b1a72264de4007090e49e4bc1b8892c4a33080508e11201bdce3fd39e254739c", "ce2ba5b9d037690cd7641aaf56d2a39176ea3cb4a7a4e50b6fcf21815530ee22",
    "dbdaf3ec69c882c7bef7c1e0ec6ef68563b06f0328fe9da36bb2212023fce70d", "7b19e46c924052df16240e1839d506354a45d8330cddb29fbb1163373c3fbf9e",
    "0df73a5d95687056702fc846a1c6eb02b73b87ddc594ebf2afcf6c198c90d41d", "23f0e17b6561c0db6cf7f90d191b87f1b671de621e16c565773e08abf8be6a11",
    "ee82dfedf62fb0f98636efa6df0a212525b9809998e8b01b42f7e7e6de8f0596", "aac7a8cf480f1d4a767751966e753f321d56fcc7c87476411d59d219ea5dcf06",
};
constexpr const char* kIsoDir = "/dev_hdd0/PS2ISO";
constexpr const char* kCardDir = "/dev_hdd0/savedata/vmc";

}  // namespace

int main() {
    int width = 0, height = 0;
    if (!ps3::videoInit(width, height)) return 1;
    ps3::inputInit();
    const ui::Text& t = ui::kEn;
    gfx::Canvas canvas(width, height, ps3::fontBytes(false), ps3::fontBytes(true));

    // webMAN (or an earlier run) may already have /dev_blind mounted: the mount then fails, but the files are there. Use them as
    // they are and leave the mount alone at the end, since it is not ours.
    const bool alreadyMounted = fsx::exists(kTarget);
    const bool ownMount = !alreadyMounted && sysLv2FsMount("CELL_FS_IOS:BUILTIN_FLSH1", "CELL_FS_FAT", "/dev_blind", 0) == 0;
    const bool mounted = alreadyMounted || ownMount;
    const installer::Config cfg{kTarget, kBackup, kStockSha, PATCHED_SHA256, {std::begin(kOlderPatched), std::end(kOlderPatched)}};
    const installer::Bytes payload(ps2_netemu_v2_bin, ps2_netemu_v2_bin + ps2_netemu_v2_bin_size);

    std::string note;
    bool noteOk = false;
    installer::State state = mounted ? installer::detect(cfg) : installer::State::Missing;
    if (!mounted) note = t.noAccess;
    else if (state == installer::State::Patched && !fsx::exists(kBackup)) note = t.patchedNoBackup;

    // Redraws the progress screen whenever the percentage or the stage changes (install, restore and the creation of the
    // memory cards take a while: the flash is slow, the hashing runs on the CPU and each card is 8 MB, so without this the
    // screen looked frozen).
    bool installing = true;
    int lastPct = -1;
    installer::Stage lastStage = installer::Stage::Package;
    const installer::Progress show = [&](installer::Stage stage, float fraction) {
        const int pct = static_cast<int>(fraction * 100);
        if (pct == lastPct && stage == lastStage) return;
        lastPct = pct;
        lastStage = stage;
        ps3::pump();
        ui::drawProgress(canvas, t, installing, stage, fraction);
        ps3::videoPresent(canvas.pixels());
    };

    while (!ps3::quitRequested()) {
        ps3::pump();
        const ps3::Input in = ps3::poll();
        if (mounted && (in.a || in.x)) {
            installing = in.a;
            lastPct = -1;
            const installer::Outcome o = in.a ? installer::install(cfg, payload, show) : installer::restore(cfg, show);
            note = ui::message(t, o);
            noteOk = o.ok;
            if (in.a && fsx::isDir(kIsoDir)) {  // the patch names the card after the game: make the ones that are missing
                const cards::Bytes head(ps2_card_head_bin, ps2_card_head_bin + ps2_card_head_bin_size);
                lastPct = -1;
                const auto made = cards::ensureCards(kIsoDir, kCardDir, head, [&](std::size_t done, std::size_t total) {
                    show(installer::Stage::Cards, total ? float(done) / float(total) : 1.0f);
                });
                if (!made.empty()) note += std::string(" ") + t.cardsMade + std::to_string(made.size());
            }
            if (in.a && fsx::isDir(kIsoDir)) {  // webMAN copies a CONFIG beside Radiata Stories that breaks its experience points
                const auto fixed = configs::ensureConfigs(kIsoDir);
                if (!fixed.empty()) note += std::string(" ") + t.configsFixed + std::to_string(fixed.size());
            }
            state = installer::detect(cfg);
        }
        if (in.b) break;
        ui::draw(canvas, t, state, mounted, note, noteOk, ps3::circleConfirms());
        ps3::videoPresent(canvas.pixels());
        ps3::sleepMs(33);
    }
    if (ownMount) sysLv2FsUnmount("/dev_blind");
    ps3::videoShutdown();
    return 0;
}
