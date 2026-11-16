// The installer screen: strings and drawing, no console API (so it can be rendered on the host).
#pragma once

#include <string>

#include "gfx.h"
#include "installer.h"

namespace ui {

struct Text {
    const char *title, *subtitle, *file, *stock, *patched, *unknown, *missing, *install, *restore, *exit, *triangle;
    const char *installed, *already, *restored, *notStock, *badPayload, *noBackup, *ioError, *noAccess, *patchedNoBackup;
};

extern const Text kEn;
extern const Text kPt;

std::string message(const Text& t, const installer::Outcome& o);

/// Draws the whole screen on the canvas.
void draw(gfx::Canvas& c, const Text& t, installer::State state, bool mounted, const std::string& note, bool noteOk,
          bool circleConfirms);

}  // namespace ui
