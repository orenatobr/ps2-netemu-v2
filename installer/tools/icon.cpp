// Renders the package icon (ICON0.PNG, 320x176) with the version from the VERSION file, using the same canvas as the app.
// It is drawn at 4x and box-filtered down so the edges and the small text stay smooth.
// Usage: tools/icon.sh OUT.png
#include <fstream>
#include <string>
#include <vector>

#define STB_IMAGE_WRITE_IMPLEMENTATION
#define STBI_WRITE_NO_STDIO
#include "stb_image_write.h"
#include "gfx.h"

#ifndef APP_VERSION
#error "APP_VERSION must be set (the release version, read from the VERSION file)"
#endif

namespace {

constexpr int kScale = 4, kOutW = 320, kOutH = 176;
// Canvas draws on a 1280 x 720 logical grid; this one is 1280 x 704 pixels, so the logical size equals the pixel size.
constexpr gfx::Size kHeadline = static_cast<gfx::Size>(50 * kScale), kSub = static_cast<gfx::Size>(23 * kScale),
                    kLine = static_cast<gfx::Size>(20 * kScale);

std::vector<std::uint8_t> load(const char* path) {
    std::ifstream f(path, std::ios::binary);
    return {std::istreambuf_iterator<char>(f), {}};
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) return 2;
    gfx::Canvas c(kOutW * kScale, kOutH * kScale, load("data/inter_regular.ttf"), load("data/inter_bold.ttf"));
    using namespace gfx;
    c.clear(theme::bg);
    c.checkBadge(45 * kScale, 70 * kScale, 24 * kScale, theme::greenDark, theme::text);
    c.text("PS2", kHeadline, theme::text, 108 * kScale, 34 * kScale);
    c.text("emulator patch", kSub, theme::muted, 108 * kScale, 86 * kScale);
    c.text("v" APP_VERSION " for ps2_netemu", kLine, theme::green, 26 * kScale, 117 * kScale);

    std::vector<std::uint8_t> rgb(std::size_t(kOutW) * kOutH * 3);
    for (int y = 0; y < kOutH; ++y)
        for (int x = 0; x < kOutW; ++x) {
            int sum[3] = {0, 0, 0};
            for (int dy = 0; dy < kScale; ++dy)
                for (int dx = 0; dx < kScale; ++dx) {
                    const std::uint32_t p = c.pixels()[(y * kScale + dy) * c.width() + x * kScale + dx];
                    sum[0] += (p >> 16) & 255, sum[1] += (p >> 8) & 255, sum[2] += p & 255;
                }
            for (int k = 0; k < 3; ++k) rgb[(std::size_t(y) * kOutW + x) * 3 + k] = std::uint8_t(sum[k] / (kScale * kScale));
        }
    std::vector<std::uint8_t> png;
    stbi_write_png_to_func([](void* ctx, void* d, int n) { auto* v = static_cast<std::vector<std::uint8_t>*>(ctx);
                               v->insert(v->end(), static_cast<std::uint8_t*>(d), static_cast<std::uint8_t*>(d) + n); },
                           &png, kOutW, kOutH, 3, rgb.data(), kOutW * 3);
    std::ofstream(argv[1], std::ios::binary).write(reinterpret_cast<const char*>(png.data()), std::streamsize(png.size()));
    return 0;
}
