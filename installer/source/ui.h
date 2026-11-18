// The installer screen: strings and drawing, no console API (so it can be rendered on the host).
#pragma once

#include <string>

#include "gfx.h"
#include "installer.h"

namespace ui {

struct Text {
    const char *title, *subtitle, *file, *stock, *patched, *olderPatch, *unknown, *missing, *install, *restore, *exit;
    const char *installed, *installedNoBackup, *already, *restored, *notStock, *badPayload, *noBackup, *ioError, *noAccess, *patchedNoBackup;
    const char* cardsMade;  ///< followed by the number of memory cards the install created
    const char *installing, *restoring, *keepOn;
    const char* stage[7];  ///< One line per installer::Stage, in enum order.
};

extern const Text kEn;

std::string message(const Text& t, const installer::Outcome& o);

/// Draws the whole screen on the canvas.
void draw(gfx::Canvas& c, const Text& t, installer::State state, bool mounted, const std::string& note, bool noteOk,
          bool circleConfirms);

/// Draws the screen shown while install() or restore() runs: the stage, a progress bar and a percentage.
void drawProgress(gfx::Canvas& c, const Text& t, bool installing, installer::Stage stage, float fraction);

}  // namespace ui
