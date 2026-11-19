#include "ui.h"

#include <algorithm>
#include <string>

#ifndef APP_VERSION
#error "APP_VERSION must be set by the Makefile (the release version, read from the VERSION file)"
#endif

namespace ui {

const Text kEn = {"PS2 emulator patch v" APP_VERSION,
                  "ps2_netemu.self: picture fills the 4:3 frame, one memory card per game.",
                  "File on the console", "Original (not patched)", "Patched (v" APP_VERSION ")", "Patched (an older release)", "Unknown build", "Not found",
                  "Install the patch", "Restore the original", "Exit",
                  "Installed. The original is saved in /dev_hdd0/ps2_netemu_stock.self. Start a PS2 game.",
                  "Installed over an older patched build. There is no backup of the original on this console, so Triangle cannot restore it.",
                  "Already installed.", "Original restored.",
                  "This file is not the build the patch was made for. Nothing was changed.",
                  "The package is damaged. Nothing was changed.", "No backup found. Nothing to restore.",
                  "Write failed. The original was kept; try again.", "Could not open the system files. This needs custom firmware.",
                  "The patch is installed but there is no backup of the original, so Triangle cannot restore it. Copy the original to /dev_hdd0/ps2_netemu_stock.self.",
                  "Memory cards created for your PS2 games: ", "Game CONFIG fixed (Radiata Stories experience points): ",
                  "Installing the patch...", "Restoring the original...", "Do not turn off the console.",
                  {"Checking the package", "Reading the emulator file", "Checking the backup", "Writing the file",
                   "Verifying the new file", "Final check", "Creating the memory cards"}};

std::string message(const Text& t, const installer::Outcome& o) {
    if (o.code == "installed") return t.installed;
    if (o.code == "installed_nobackup") return t.installedNoBackup;
    if (o.code == "already") return t.already;
    if (o.code == "restored") return t.restored;
    if (o.code == "missing") return t.missing;
    if (o.code == "not_stock") return t.notStock;
    if (o.code == "bad_payload") return t.badPayload;
    if (o.code == "no_backup") return t.noBackup;
    return t.ioError;
}

namespace {

void header(gfx::Canvas& c, const Text& t) {
    using namespace gfx;
    c.clear(theme::bg);
    c.checkBadge(112, 112, 34, theme::greenDark, theme::text);
    c.text(t.title, Size::Title, theme::text, 170, 82);
    int sy = 170;
    for (const auto& line : c.wrap(t.subtitle, Size::Body, 1120)) {
        c.text(line, Size::Body, theme::muted, 80, sy);
        sy += c.lineHeight(Size::Body) + 2;
    }
}

enum class Button { Cross, Circle, Triangle };

/// A controller face button (dark disc, coloured ring, symbol) centred at cx, cy.
void buttonIcon(gfx::Canvas& c, Button b, int cx, int cy) {
    using gfx::Color;
    const Color tone = b == Button::Cross ? Color{124, 160, 214} : b == Button::Circle ? Color{232, 96, 107} : Color{63, 191, 155};
    c.circle(cx, cy, 20, gfx::theme::bg);
    c.ring(cx, cy, 20, 3, tone);
    switch (b) {
        case Button::Cross:
            c.line(cx - 8, cy - 8, cx + 8, cy + 8, 3, tone);
            c.line(cx - 8, cy + 8, cx + 8, cy - 8, 3, tone);
            break;
        case Button::Circle: c.ring(cx, cy, 9, 3, tone); break;
        case Button::Triangle:
            c.line(cx, cy - 9, cx - 9, cy + 7, 3, tone);
            c.line(cx - 9, cy + 7, cx + 9, cy + 7, 3, tone);
            c.line(cx + 9, cy + 7, cx, cy - 9, 3, tone);
            break;
    }
}

/// Icon followed by its action, with the label's top at y = 668 like the rest of the bar.
void action(gfx::Canvas& c, Button b, const char* label, int x) {
    buttonIcon(c, b, x + 20, 681);
    c.text(label, gfx::Size::Body, gfx::theme::text, x + 56, 668);
}

}  // namespace

void draw(gfx::Canvas& c, const Text& t, installer::State state, bool mounted, const std::string& note, bool noteOk,
          bool circleConfirms) {
    using namespace gfx;
    header(c, t);
    c.card(80, 250, 1120, 130, 18, theme::card, 2, theme::line);
    c.text(t.file, Size::Small, theme::muted, 120, 276);
    const char* label = !mounted ? "-"
                        : state == installer::State::Patched ? t.patched
                        : state == installer::State::OlderPatch ? t.olderPatch
                        : state == installer::State::Stock   ? t.stock
                        : state == installer::State::Unknown ? t.unknown
                                                             : t.missing;
    const Color tone = state == installer::State::Patched ? theme::green
                       : state == installer::State::Stock ? theme::text
                                                          : theme::amber;
    c.text(label, Size::Large, mounted ? tone : theme::red, 120, 312, Align::Left, 1040);
    if (!note.empty()) {
        int y = 420;
        for (const auto& line : c.wrap(note, Size::Body, 1120)) {
            c.text(line, Size::Body, noteOk ? theme::green : theme::amber, 80, y);
            y += c.lineHeight(Size::Body) + 4;
        }
    }
    const Button confirm = circleConfirms ? Button::Circle : Button::Cross;
    const Button back = circleConfirms ? Button::Cross : Button::Circle;
    c.fill(0, 640, 1280, 80, 0, theme::card);
    action(c, confirm, t.install, 80);
    action(c, Button::Triangle, t.restore, 470);
    action(c, back, t.exit, 1000);
}

void drawProgress(gfx::Canvas& c, const Text& t, bool installing, installer::Stage stage, float fraction) {
    using namespace gfx;
    header(c, t);
    const float f = fraction < 0 ? 0 : fraction > 1 ? 1 : fraction;
    const int barX = 120, barY = 346, barW = 1040, barH = 24;
    c.card(80, 250, 1120, 130, 18, theme::card, 2, theme::line);
    c.text(installing ? t.installing : t.restoring, Size::Small, theme::muted, 120, 276);
    c.text(t.stage[static_cast<int>(stage)], Size::Body, theme::text, 120, 304);
    c.fill(barX, barY, barW, barH, barH / 2, theme::raised);
    if (f > 0) c.fill(barX, barY, std::max(barH, static_cast<int>(barW * f)), barH, barH / 2, theme::green);
    c.text(std::to_string(static_cast<int>(f * 100)) + "%", Size::Large, theme::text, 1160, 276, Align::Right);
    c.text(t.keepOn, Size::Body, theme::amber, 80, 420);
}

}  // namespace ui
