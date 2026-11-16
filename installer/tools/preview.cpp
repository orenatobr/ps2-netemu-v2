// Renders the installer screens to PNG files on the host, with the same ui::draw the console uses.
// Usage: tools/preview.sh OUTDIR
#include <cstdio>
#include <fstream>
#include <vector>

#define STB_IMAGE_WRITE_IMPLEMENTATION
#define STBI_WRITE_NO_STDIO
#include "stb_image_write.h"
#include "ui.h"

namespace {

std::vector<std::uint8_t> load(const char* path) {
    std::ifstream f(path, std::ios::binary);
    return {std::istreambuf_iterator<char>(f), {}};
}

void save(const std::string& path, const gfx::Canvas& c) {
    std::vector<std::uint8_t> rgb(std::size_t(c.width()) * c.height() * 3);
    for (int i = 0; i < c.width() * c.height(); ++i) {
        const std::uint32_t p = c.pixels()[i];
        rgb[3 * i] = (p >> 16) & 255;
        rgb[3 * i + 1] = (p >> 8) & 255;
        rgb[3 * i + 2] = p & 255;
    }
    std::vector<std::uint8_t> png;
    stbi_write_png_to_func([](void* ctx, void* d, int n) { auto* v = static_cast<std::vector<std::uint8_t>*>(ctx);
                               v->insert(v->end(), static_cast<std::uint8_t*>(d), static_cast<std::uint8_t*>(d) + n); },
                           &png, c.width(), c.height(), 3, rgb.data(), c.width() * 3);
    std::ofstream(path, std::ios::binary).write(reinterpret_cast<const char*>(png.data()), std::streamsize(png.size()));
}

}  // namespace

int main(int argc, char** argv) {
    const std::string out = argc > 1 ? argv[1] : ".";
    gfx::Canvas c(1280, 720, load("data/inter_regular.ttf"), load("data/inter_bold.ttf"));
    using installer::State;
    struct Shot { const char* name; const ui::Text* t; State s; bool mounted; std::string note; bool ok; };
    const Shot shots[] = {
        {"en_stock", &ui::kEn, State::Stock, true, "", false},
        {"en_installed", &ui::kEn, State::Patched, true, ui::kEn.installed, true},
        {"pt_unknown", &ui::kPt, State::Unknown, true, ui::kPt.notStock, false},
        {"pt_noflash", &ui::kPt, State::Missing, false, ui::kPt.noAccess, false},
    };
    for (const Shot& s : shots) {
        ui::draw(c, *s.t, s.s, s.mounted, s.note, s.ok, false);
        save(out + "/" + s.name + ".png", c);
    }
    return 0;
}
