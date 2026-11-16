// PS1 emulator patch installer: copies the patched ps1_netemu.self into the system folder (with a backup)
// or puts the original back. The patched file travels inside this package.
#include <sys/file.h>

#include <string>

#include "gfx.h"
#include "fsx.h"
#include "installer.h"
#include "ps3.h"
#include "ui.h"
#include "ps1_netemu_v2_bin.h"

#ifndef PATCHED_SHA256
#error "PATCHED_SHA256 must be set by the Makefile (sha256 of payload/ps1_netemu_v2.bin)"
#endif

namespace {

// The one stock build this patch was made for (ps1_netemu.self, key revision 0x1C).
constexpr const char* kStockSha = "27d4121ecf8dddf83fa7f0117a454254bd6626c6f17e3412cdd9e24aa7ebdd5d";
constexpr const char* kTarget = "/dev_blind/ps1emu/ps1_netemu.self";
constexpr const char* kBackup = "/dev_hdd0/ps1_netemu_stock.self";

}  // namespace

int main() {
    int width = 0, height = 0;
    if (!ps3::videoInit(width, height)) return 1;
    ps3::inputInit();
    const ui::Text& t = ps3::portuguese() ? ui::kPt : ui::kEn;
    gfx::Canvas canvas(width, height, ps3::fontBytes(false), ps3::fontBytes(true));

    const bool mounted = sysLv2FsMount("CELL_FS_IOS:BUILTIN_FLSH1", "CELL_FS_FAT", "/dev_blind", 0) == 0;
    const installer::Config cfg{kTarget, kBackup, kStockSha, PATCHED_SHA256};
    const installer::Bytes payload(ps1_netemu_v2_bin, ps1_netemu_v2_bin + ps1_netemu_v2_bin_size);

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
            state = installer::detect(cfg);
        }
        if (in.b) break;
        ui::draw(canvas, t, state, mounted, note, noteOk, ps3::circleConfirms());
        ps3::videoPresent(canvas.pixels());
        ps3::sleepMs(33);
    }
    if (mounted) sysLv2FsUnmount("/dev_blind");
    ps3::videoShutdown();
    return 0;
}
