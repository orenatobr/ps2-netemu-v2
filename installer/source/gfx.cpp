#include "gfx.h"

#include <algorithm>
#include <cmath>

#include "mathx.h"

#include "stb_truetype.h"

namespace gfx {
namespace {

std::uint32_t pack(int r, int g, int b) { return 0xFF000000u | (std::uint32_t(r) << 16) | (std::uint32_t(g) << 8) | std::uint32_t(b); }

int mix(int src, int dst, int a) {  // a in 0..255
    const int t = src * a + dst * (255 - a) + 128;
    return (t + (t >> 8)) >> 8;
}

// Negative inside a rounded rectangle centred at (cx, cy) with half sizes (hx, hy) and corner radius r.
double roundBox(double px, double py, double cx, double cy, double hx, double hy, double r) {
    const double qx = std::fabs(px - cx) - (hx - r);
    const double qy = std::fabs(py - cy) - (hy - r);
    const double ox = std::max(qx, 0.0), oy = std::max(qy, 0.0);
    return std::sqrt(ox * ox + oy * oy) + std::min(std::max(qx, qy), 0.0) - r;
}

double capsule(double px, double py, double ax, double ay, double bx, double by) {
    const double dx = bx - ax, dy = by - ay;
    const double len2 = dx * dx + dy * dy;
    const double t = len2 > 0 ? std::clamp(((px - ax) * dx + (py - ay) * dy) / len2, 0.0, 1.0) : 0.0;
    const double ex = px - (ax + t * dx), ey = py - (ay + t * dy);
    return std::sqrt(ex * ex + ey * ey);
}

// Reads one UTF-8 code point; invalid bytes give U+FFFD.
std::uint32_t nextCodepoint(const std::string& s, std::size_t& i) {
    const unsigned char c = s[i++];
    if (c < 0x80) return c;
    int extra = 0;
    std::uint32_t cp = 0;
    if ((c & 0xE0) == 0xC0) {
        extra = 1;
        cp = c & 0x1F;
    } else if ((c & 0xF0) == 0xE0) {
        extra = 2;
        cp = c & 0x0F;
    } else if ((c & 0xF8) == 0xF0) {
        extra = 3;
        cp = c & 0x07;
    } else {
        return 0xFFFD;
    }
    for (int k = 0; k < extra; ++k) {
        if (i >= s.size() || (static_cast<unsigned char>(s[i]) & 0xC0) != 0x80) return 0xFFFD;
        cp = (cp << 6) | (static_cast<unsigned char>(s[i++]) & 0x3F);
    }
    return cp;
}

}  // namespace

Canvas::Canvas(int width, int height, std::vector<std::uint8_t> regular, std::vector<std::uint8_t> bold)
    : w_(width), h_(height), buf_(std::size_t(width) * height, pack(15, 23, 42)) {
    scale_ = std::min(w_ / double(kWidth), h_ / double(kHeight));
    ox_ = (w_ - kWidth * scale_) / 2;
    oy_ = (h_ - kHeight * scale_) / 2;
    fonts_[0].data = std::move(regular);
    fonts_[1].data = std::move(bold);
    for (Font& f : fonts_) {
        if (f.data.empty()) continue;
        f.info = std::make_unique<stbtt_fontinfo>();
        f.ok = stbtt_InitFont(f.info.get(), f.data.data(), stbtt_GetFontOffsetForIndex(f.data.data(), 0)) != 0;
    }
    if (!fonts_[1].ok) {  // no bold face: share the regular one
        fonts_[1].data.clear();
        fonts_[1].info.reset();
    }
}

Canvas::~Canvas() = default;

// ---------------------------------------------------------------- pixels --

void Canvas::blend(int x, int y, Color c, int alpha) {
    if (x < 0 || y < 0 || x >= w_ || y >= h_ || alpha <= 0) return;
    std::uint32_t& d = buf_[std::size_t(y) * w_ + x];
    if (alpha >= 255) {
        d = pack(c.r, c.g, c.b);
        return;
    }
    d = pack(mix(c.r, (d >> 16) & 0xFF, alpha), mix(c.g, (d >> 8) & 0xFF, alpha), mix(c.b, d & 0xFF, alpha));
}

void Canvas::clear(Color c) { std::fill(buf_.begin(), buf_.end(), pack(c.r, c.g, c.b)); }

template <class Sdf>
void Canvas::paint(double x0, double y0, double x1, double y1, Color c, Sdf sdf) {
    const int ix0 = std::max(0, int(std::floor(x0)) - 1), ix1 = std::min(w_, int(std::ceil(x1)) + 1);
    const int iy0 = std::max(0, int(std::floor(y0)) - 1), iy1 = std::min(h_, int(std::ceil(y1)) + 1);
    for (int y = iy0; y < iy1; ++y) {
        for (int x = ix0; x < ix1; ++x) {
            const double cov = std::clamp(0.5 - sdf(x + 0.5, y + 0.5), 0.0, 1.0);
            if (cov > 0) blend(x, y, c, int(cov * c.a + 0.5));
        }
    }
}

void Canvas::fillRound(double x0, double y0, double x1, double y1, double r, Color c) {
    if (x1 <= x0 || y1 <= y0) return;
    const double hx = (x1 - x0) / 2, hy = (y1 - y0) / 2, cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    r = std::clamp(r, 0.0, std::min(hx, hy));
    const int rowA = std::max(0, int(std::floor(y0))), rowB = std::min(h_, int(std::ceil(y1)));
    const int colA = std::max(0, int(std::floor(x0))), colB = std::min(w_, int(std::ceil(x1)));
    for (int y = rowA; y < rowB; ++y) {
        int fullA = colB, fullB = colB;  // fully covered columns [fullA, fullB)
        if (y >= y0 + 1 && y + 1 <= y1 - 1) {
            const double yc = y + 0.5;
            const double ty = std::max({0.0, (y0 + r) - yc, yc - (y1 - r)});
            const double dxc = std::sqrt(std::max(0.0, r * r - ty * ty));
            const double xl = ty == 0 ? x0 : x0 + r - dxc, xr = ty == 0 ? x1 : x1 - r + dxc;
            fullA = std::max(colA, int(std::ceil(xl)) + 2);
            fullB = std::min(colB, int(std::floor(xr)) - 1);
        }
        for (int x = colA; x < colB; ++x) {
            if (x >= fullA && x < fullB) {
                x = fullB - 1;  // skip to the end of the solid span, then fill it in one go below
                continue;
            }
            const double cov = std::clamp(0.5 - roundBox(x + 0.5, y + 0.5, cx, cy, hx, hy, r), 0.0, 1.0);
            if (cov > 0) blend(x, y, c, int(cov * c.a + 0.5));
        }
        for (int x = fullA; x < fullB; ++x) blend(x, y, c, c.a);
    }
}

void Canvas::fill(int x, int y, int w, int h, int radius, Color c) {
    fillRound(sx(x), sy(y), sx(x + w), sy(y + h), radius * scale_, c);
}

void Canvas::card(int x, int y, int w, int h, int radius, Color fillColor, int border, Color borderColor) {
    if (border > 0) fill(x, y, w, h, radius, borderColor);
    fill(x + border, y + border, w - 2 * border, h - 2 * border, std::max(0, radius - border), fillColor);
}

void Canvas::stroke(int x, int y, int w, int h, int radius, int thickness, Color c) {
    const double t = thickness * scale_;
    const double x0 = sx(x), y0 = sy(y), x1 = sx(x + w), y1 = sy(y + h);
    const double hx = (x1 - x0) / 2 - t / 2, hy = (y1 - y0) / 2 - t / 2, cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    const double r = std::max(0.0, std::min(radius * scale_ - t / 2, std::min(hx, hy)));
    paint(x0, y0, x1, y1, c, [=](double px, double py) { return std::fabs(roundBox(px, py, cx, cy, hx, hy, r)) - t / 2; });
}

void Canvas::circle(int cx, int cy, int radius, Color c) {
    const double X = sx(cx), Y = sy(cy), R = radius * scale_;
    paint(X - R, Y - R, X + R, Y + R, c, [=](double px, double py) { return mathx::hyp(px - X, py - Y) - R; });
}

void Canvas::ring(int cx, int cy, int radius, int thickness, Color c) {
    const double X = sx(cx), Y = sy(cy), R = radius * scale_, T = thickness * scale_;
    paint(X - R - T, Y - R - T, X + R + T, Y + R + T, c,
          [=](double px, double py) { return std::fabs(mathx::hyp(px - X, py - Y) - R) - T / 2; });
}

void Canvas::line(int x1, int y1, int x2, int y2, int width, Color c) {
    const double ax = sx(x1), ay = sy(y1), bx = sx(x2), by = sy(y2), half = width * scale_ / 2;
    paint(std::min(ax, bx) - half, std::min(ay, by) - half, std::max(ax, bx) + half, std::max(ay, by) + half, c,
          [=](double px, double py) { return capsule(px, py, ax, ay, bx, by) - half; });
}

void Canvas::checkBadge(int cx, int cy, int radius, Color disc, Color mark) {
    circle(cx, cy, radius, disc);
    const int w = std::max(2, radius / 4);
    const int x1 = int(cx - radius * 0.45), y1 = int(cy + radius * 0.02);
    const int x2 = int(cx - radius * 0.1), y2 = int(cy + radius * 0.4);
    const int x3 = int(cx + radius * 0.5), y3 = int(cy - radius * 0.38);
    line(x1, y1, x2, y2, w, mark);
    line(x2, y2, x3, y3, w, mark);
}

// ------------------------------------------------------------------ text --

int Canvas::fontIndex(Size size) const {
    const bool bold = size == Size::Large || size == Size::Title;
    return bold && fonts_[1].ok ? 1 : 0;
}

int Canvas::pixelSize(Size size) const { return std::max(6, int(mathx::iround(static_cast<int>(size) * scale_))); }

const Canvas::Glyph& Canvas::glyph(int font, int px, std::uint32_t cp) {
    const std::uint64_t key = (std::uint64_t(font) << 60) | (std::uint64_t(px) << 32) | cp;
    auto it = glyphs_.find(key);
    if (it != glyphs_.end()) return it->second;
    Glyph g;
    const stbtt_fontinfo* info = fonts_[font].info.get();
    if (info) {
        const float scale = stbtt_ScaleForMappingEmToPixels(info, float(px));
        if (stbtt_FindGlyphIndex(info, int(cp)) == 0 && cp != ' ') cp = '?';
        int adv = 0, lsb = 0;
        stbtt_GetCodepointHMetrics(info, int(cp), &adv, &lsb);
        g.advance = adv * scale;
        int w = 0, h = 0, xoff = 0, yoff = 0;
        unsigned char* bmp = stbtt_GetCodepointBitmap(info, scale, scale, int(cp), &w, &h, &xoff, &yoff);
        if (bmp) {
            g.w = w;
            g.h = h;
            g.xoff = xoff;
            g.yoff = yoff;
            g.alpha.assign(bmp, bmp + std::size_t(w) * h);
            stbtt_FreeBitmap(bmp, nullptr);
        }
    }
    if (glyphs_.size() > 6000) glyphs_.clear();  // keep memory bounded (a few MB at most)
    return glyphs_.emplace(key, std::move(g)).first->second;
}

float Canvas::kern(int font, int px, std::uint32_t a, std::uint32_t b) {
    const stbtt_fontinfo* info = fonts_[font].info.get();
    if (!info) return 0;
    return stbtt_GetCodepointKernAdvance(info, int(a), int(b)) * stbtt_ScaleForMappingEmToPixels(info, float(px));
}

float Canvas::widthPhys(const std::string& s, Size size) {
    const int font = fontIndex(size), px = pixelSize(size);
    if (!fonts_[font].ok) return 0;
    float w = 0;
    std::uint32_t prev = 0;
    for (std::size_t i = 0; i < s.size();) {
        const std::uint32_t cp = nextCodepoint(s, i);
        w += glyph(font, px, cp).advance;
        if (prev) w += kern(font, px, prev, cp);
        prev = cp;
    }
    return w;
}

int Canvas::textWidth(const std::string& s, Size size) { return int(mathx::iround(widthPhys(s, size) / scale_)); }

int Canvas::lineHeight(Size size) {
    const int font = fontIndex(size);
    if (!fonts_[font].ok) return static_cast<int>(size) + 6;
    int asc = 0, desc = 0, gap = 0;
    stbtt_GetFontVMetrics(fonts_[font].info.get(), &asc, &desc, &gap);
    const double em = stbtt_ScaleForMappingEmToPixels(fonts_[font].info.get(), float(static_cast<int>(size)));
    return int(mathx::iround((asc - desc + gap) * em));
}

std::string Canvas::fit(const std::string& s, Size size, int maxWidth) {
    if (maxWidth <= 0 || textWidth(s, size) <= maxWidth) return s;
    const std::string ell = "\xE2\x80\xA6";
    std::string out = s;
    while (!out.empty()) {
        do {
            out.pop_back();
        } while (!out.empty() && (static_cast<unsigned char>(out.back()) & 0xC0) == 0x80);
        while (!out.empty() && out.back() == ' ') out.pop_back();
        if (textWidth(out + ell, size) <= maxWidth) break;
    }
    return out + ell;
}

int Canvas::text(const std::string& s, Size size, Color c, int x, int y, Align align, int maxWidth) {
    const int font = fontIndex(size);
    if (!fonts_[font].ok || s.empty()) return 0;
    const std::string shown = fit(s, size, maxWidth);
    const int px = pixelSize(size);
    const double total = widthPhys(shown, size);
    double pen = sx(x);
    if (align == Align::Center) pen -= total / 2;
    if (align == Align::Right) pen -= total;
    const stbtt_fontinfo* info = fonts_[font].info.get();
    int asc = 0, desc = 0, gap = 0;
    stbtt_GetFontVMetrics(info, &asc, &desc, &gap);
    const double baseline = sy(y) + asc * stbtt_ScaleForMappingEmToPixels(info, float(px));

    std::uint32_t prev = 0;
    for (std::size_t i = 0; i < shown.size();) {
        const std::uint32_t cp = nextCodepoint(shown, i);
        if (prev) pen += kern(font, px, prev, cp);
        const Glyph& g = glyph(font, px, cp);
        const int gx = int(std::floor(pen + 0.5)) + g.xoff, gy = int(std::floor(baseline + 0.5)) + g.yoff;
        for (int yy = 0; yy < g.h; ++yy) {
            for (int xx = 0; xx < g.w; ++xx) {
                const int a = g.alpha[std::size_t(yy) * g.w + xx];
                if (a) blend(gx + xx, gy + yy, c, a * c.a / 255);
            }
        }
        pen += g.advance;
        prev = cp;
    }
    return int(mathx::iround(total / scale_));
}

std::vector<std::string> Canvas::wrap(const std::string& s, Size size, int maxWidth) {
    std::vector<std::string> lines;
    std::string line, word;
    auto flush = [&]() {
        if (word.empty()) return;
        const std::string trial = line.empty() ? word : line + " " + word;
        if (!line.empty() && textWidth(trial, size) > maxWidth) {
            lines.push_back(line);
            line = word;
        } else {
            line = trial;
        }
        word.clear();
    };
    for (char ch : s) {
        if (ch == ' ') flush();
        else word += ch;
    }
    flush();
    if (!line.empty()) lines.push_back(line);
    return lines;
}

// -------------------------------------------------------------- textures --

std::shared_ptr<Texture> Canvas::texture(const std::vector<std::uint8_t>& rgba, int w, int h) {
    if (w <= 0 || h <= 0 || rgba.size() < std::size_t(w) * h * 4) return nullptr;
    auto t = std::make_shared<Texture>();
    t->w = w;
    t->h = h;
    t->px.resize(std::size_t(w) * h);
    for (std::size_t i = 0; i < t->px.size(); ++i) {
        const int a = rgba[i * 4 + 3];
        t->px[i] = (std::uint32_t(a) << 24) | (std::uint32_t(rgba[i * 4] * a / 255) << 16) |
                   (std::uint32_t(rgba[i * 4 + 1] * a / 255) << 8) | std::uint32_t(rgba[i * 4 + 2] * a / 255);
    }
    return t;
}

int Canvas::pixels(int logical) const { return std::max(1, int(mathx::iround(logical * scale_))); }

std::shared_ptr<Texture> Canvas::thumbnail(const std::vector<std::uint8_t>& rgba, int w, int h, int tw, int th) {
    if (w <= 0 || h <= 0 || tw <= 0 || th <= 0 || rgba.size() < std::size_t(w) * h * 4) return nullptr;
    auto t = std::make_shared<Texture>();
    t->w = tw;
    t->h = th;
    t->px.resize(std::size_t(tw) * th);
    for (int ty = 0; ty < th; ++ty) {
        const int y0 = int(std::int64_t(ty) * h / th), y1 = std::max(y0 + 1, int(std::int64_t(ty + 1) * h / th));
        for (int tx = 0; tx < tw; ++tx) {
            const int x0 = int(std::int64_t(tx) * w / tw), x1 = std::max(x0 + 1, int(std::int64_t(tx + 1) * w / tw));
            std::uint32_t r = 0, g = 0, b = 0, a = 0;
            for (int yy = y0; yy < y1; ++yy) {
                const std::uint8_t* p = &rgba[(std::size_t(yy) * w + x0) * 4];
                for (int xx = x0; xx < x1; ++xx, p += 4) {
                    r += p[0] * p[3];
                    g += p[1] * p[3];
                    b += p[2] * p[3];
                    a += p[3];
                }
            }
            const std::uint32_t n = std::uint32_t(x1 - x0) * std::uint32_t(y1 - y0);
            t->px[std::size_t(ty) * tw + tx] = ((a / n) << 24) | ((r / (255 * n)) << 16) | ((g / (255 * n)) << 8) | (b / (255 * n));
        }
    }
    return t;
}

void Canvas::blit(const Texture& t, int x, int y, int w, int h, int radius) {
    if (t.w <= 0 || t.h <= 0 || w <= 0 || h <= 0) return;
    const double X0 = sx(x), Y0 = sy(y), X1 = sx(x + w), Y1 = sy(y + h);
    const double cx = (X0 + X1) / 2, cy = (Y0 + Y1) / 2, hx = (X1 - X0) / 2, hy = (Y1 - Y0) / 2;
    const double r = std::clamp(radius * scale_, 0.0, std::min(hx, hy));
    if (std::fabs((X1 - X0) - t.w) < 1 && std::fabs((Y1 - Y0) - t.h) < 1) {
        // 1:1 copy: no resampling, and the rounded-corner mask only matters near the corners.
        const int ox = int(mathx::iround(X0)), oy = int(mathx::iround(Y0)), band = int(std::ceil(r)) + 1;
        for (int ty = 0; ty < t.h; ++ty) {
            const int py = oy + ty;
            if (py < 0 || py >= h_) continue;
            const bool edgeRow = ty < band || ty >= t.h - band;
            for (int tx = 0; tx < t.w; ++tx) {
                const int px = ox + tx;
                if (px < 0 || px >= w_) continue;
                const std::uint32_t s = t.px[std::size_t(ty) * t.w + tx];
                double mask = 1;
                if (edgeRow && (tx < band || tx >= t.w - band)) {
                    mask = std::clamp(0.5 - roundBox(px + 0.5, py + 0.5, ox + t.w / 2.0, oy + t.h / 2.0, t.w / 2.0, t.h / 2.0, r), 0.0, 1.0);
                    if (mask <= 0) continue;
                }
                std::uint32_t& d = buf_[std::size_t(py) * w_ + px];
                if (mask >= 1 && (s >> 24) == 255) {
                    d = s | 0xFF000000u;
                    continue;
                }
                const double sa = (s >> 24) * mask, inv = 1 - sa / 255.0;
                const int rr = std::min(255, int(((s >> 16) & 0xFF) * mask + ((d >> 16) & 0xFF) * inv + 0.5));
                const int gg = std::min(255, int(((s >> 8) & 0xFF) * mask + ((d >> 8) & 0xFF) * inv + 0.5));
                const int bb = std::min(255, int((s & 0xFF) * mask + (d & 0xFF) * inv + 0.5));
                d = pack(rr, gg, bb);
            }
        }
        return;
    }
    const int ix0 = std::max(0, int(std::floor(X0))), ix1 = std::min(w_, int(std::ceil(X1)));
    const int iy0 = std::max(0, int(std::floor(Y0))), iy1 = std::min(h_, int(std::ceil(Y1)));
    auto texel = [&](int tx, int ty) { return t.px[std::size_t(std::clamp(ty, 0, t.h - 1)) * t.w + std::clamp(tx, 0, t.w - 1)]; };
    for (int py = iy0; py < iy1; ++py) {
        for (int px = ix0; px < ix1; ++px) {
            double mask = 1;
            if (r > 0 || px == ix0 || px == ix1 - 1 || py == iy0 || py == iy1 - 1) {
                mask = std::clamp(0.5 - roundBox(px + 0.5, py + 0.5, cx, cy, hx, hy, r), 0.0, 1.0);
                if (mask <= 0) continue;
            }
            const double u = (px + 0.5 - X0) / (X1 - X0) * t.w - 0.5, v = (py + 0.5 - Y0) / (Y1 - Y0) * t.h - 0.5;
            const int tx = int(std::floor(u)), ty = int(std::floor(v));
            const double fx = u - tx, fy = v - ty;
            const std::uint32_t p00 = texel(tx, ty), p10 = texel(tx + 1, ty), p01 = texel(tx, ty + 1), p11 = texel(tx + 1, ty + 1);
            double ch[4];
            for (int k = 0; k < 4; ++k) {
                const int sh = 24 - 8 * k;  // A, R, G, B
                const double top = ((p00 >> sh) & 0xFF) * (1 - fx) + ((p10 >> sh) & 0xFF) * fx;
                const double bot = ((p01 >> sh) & 0xFF) * (1 - fx) + ((p11 >> sh) & 0xFF) * fx;
                ch[k] = (top * (1 - fy) + bot * fy) * mask;
            }
            std::uint32_t& d = buf_[std::size_t(py) * w_ + px];
            const double inv = 1 - ch[0] / 255.0;
            const int rr = std::min(255, int(ch[1] + ((d >> 16) & 0xFF) * inv + 0.5));
            const int gg = std::min(255, int(ch[2] + ((d >> 8) & 0xFF) * inv + 0.5));
            const int bb = std::min(255, int(ch[3] + (d & 0xFF) * inv + 0.5));
            d = pack(rr, gg, bb);
        }
    }
}

}  // namespace gfx
