// PS2 emulator patch installer: copies the patched ps2_netemu.self into the system folder (with a backup)
// or puts the original back. The patched file travels inside this package.
#include <sys/file.h>

#include <string>

#include "cards.h"
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
constexpr const char* kIsoDir = "/dev_hdd0/PS2ISO";
constexpr const char* kCardDir = "/dev_hdd0/savedata/vmc";

}  // namespace

int main() {
    int width = 0, height = 0;
    if (!ps3::videoInit(width, height)) return 1;
    ps3::inputInit();
    const ui::Text& t = ps3::portuguese() ? ui::kPt : ui::kEn;
    gfx::Canvas canvas(width, height, ps3::fontBytes(false), ps3::fontBytes(true));

    // webMAN (or an earlier run) may already have /dev_blind mounted: the mount then fails, but the files are there. Use them as
    // they are and leave the mount alone at the end, since it is not ours.
    const bool alreadyMounted = fsx::exists(kTarget);
    const bool ownMount = !alreadyMounted && sysLv2FsMount("CELL_FS_IOS:BUILTIN_FLSH1", "CELL_FS_FAT", "/dev_blind", 0) == 0;
    const bool mounted = alreadyMounted || ownMount;
    const installer::Config cfg{kTarget, kBackup, kStockSha, PATCHED_SHA256};
    const installer::Bytes payload(ps2_netemu_v2_bin, ps2_netemu_v2_bin + ps2_netemu_v2_bin_size);

    std::string note;
    bool noteOk = false;
    installer::State state = mounted ? installer::detect(cfg) : installer::State::Missing;
    if (!mounted) note = t.noAccess;
    else if (state == installer::State::Patched && !fsx::exists(kBackup)) note = t.patchedNoBackup;

    while (!ps3::quitRequested()) {
        ps3::pump();
        const ps3::Input in = ps3::poll();
        if (mounted && (in.a || in.x)) {
            const installer::Outcome o = in.a ? installer::install(cfg, payload) : installer::restore(cfg);
            note = ui::message(t, o);
            noteOk = o.ok;
            if (in.a && fsx::isDir(kIsoDir)) {  // the patch names the card after the game: make the ones that are missing
                const cards::Bytes head(ps2_card_head_bin, ps2_card_head_bin + ps2_card_head_bin_size);
                const auto made = cards::ensureCards(kIsoDir, kCardDir, head);
                if (!made.empty()) note += std::string(" ") + t.cardsMade + std::to_string(made.size());
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
