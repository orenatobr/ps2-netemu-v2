// Software 2D canvas: colours, anti-aliased shapes, text (stb_truetype) and RGBA textures.
//
// Everything is drawn in logical 1280x720 coordinates; the canvas scales them to the real output
// size (720p, 1080p or SD, letterboxed) so the screens are laid out once. Pixels are 0xAARRGGBB
// words with alpha 255, which is what the RSX frame buffer (X8R8G8B8, big endian) expects.
#pragma once

#include <cstdint>
#include <map>
#include <memory>
#include <string>
#include <vector>

struct stbtt_fontinfo;

namespace gfx {

struct Color {
    std::uint8_t r, g, b, a = 255;
};

/// Theme tokens (dark UI; text and focus colours checked against the card and background colours).
namespace theme {
constexpr Color bg{15, 23, 42};          // #0F172A
constexpr Color card{25, 33, 52};        // #192134
constexpr Color raised{34, 48, 74};      // #22304A
constexpr Color line{44, 56, 82};        // border on dark
constexpr Color text{248, 250, 252};     // #F8FAFC
constexpr Color muted{148, 163, 184};    // #94A3B8
constexpr Color green{34, 197, 94};      // #22C55E accent and focus ring
constexpr Color greenDark{21, 128, 61};  // #15803D fill behind white text
constexpr Color amber{245, 158, 11};     // #F59E0B changed rows, warnings
constexpr Color red{239, 68, 68};        // #EF4444 errors
}  // namespace theme

/// Text sizes in pixels at 1280x720. Large and Title use the bold face.
enum class Size { Small = 22, Body = 26, Large = 34, Title = 52 };

enum class Align { Left, Center, Right };

/// Straight-alpha RGBA image prepared for blitting (premultiplied inside).
class Texture {
public:
    int w = 0, h = 0;
    std::vector<std::uint32_t> px;  ///< Premultiplied 0xAARRGGBB.
};

class Canvas {
public:
    static constexpr int kWidth = 1280;
    static constexpr int kHeight = 720;

    /// Args:
    ///     width: Output width in pixels.
    ///     height: Output height in pixels.
    ///     regular: TrueType bytes of the regular face (copied).
    ///     bold: TrueType bytes of the bold face (copied); the regular face is used when empty.
    Canvas(int width, int height, std::vector<std::uint8_t> regular, std::vector<std::uint8_t> bold);
    ~Canvas();
    Canvas(const Canvas&) = delete;
    Canvas& operator=(const Canvas&) = delete;

    int width() const { return w_; }
    int height() const { return h_; }
    const std::uint32_t* pixels() const { return buf_.data(); }
    bool hasFont() const { return fonts_[0].ok; }

    void clear(Color c);
    /// Rounded rectangle; radius 0 gives a plain rectangle. Colour alpha blends over what is there.
    void fill(int x, int y, int w, int h, int radius, Color c);
    /// Rounded rectangle with a border of `border` pixels.
    void card(int x, int y, int w, int h, int radius, Color fillColor, int border, Color borderColor);
    /// Outline of a rounded rectangle (the inside stays untouched).
    void stroke(int x, int y, int w, int h, int radius, int thickness, Color c);
    void circle(int cx, int cy, int radius, Color c);
    void ring(int cx, int cy, int radius, int thickness, Color c);
    void line(int x1, int y1, int x2, int y2, int width, Color c);
    /// Round badge with a check, used as logo and as status mark.
    void checkBadge(int cx, int cy, int radius, Color disc, Color mark);

    /// Draws text; returns the drawn width. `maxWidth` > 0 shortens the text with an ellipsis.
    int text(const std::string& s, Size size, Color c, int x, int y, Align align = Align::Left, int maxWidth = 0);
    int textWidth(const std::string& s, Size size);
    int lineHeight(Size size);
    /// Splits text into lines no wider than maxWidth.
    std::vector<std::string> wrap(const std::string& s, Size size, int maxWidth);

    /// Creates a texture from top-down straight RGBA pixels.
    static std::shared_ptr<Texture> texture(const std::vector<std::uint8_t>& rgba, int w, int h);
    /// Like texture(), but box-filtered down to tw x th pixels so blit() can copy it 1:1.
    static std::shared_ptr<Texture> thumbnail(const std::vector<std::uint8_t>& rgba, int w, int h, int tw, int th);
    /// Size in pixels of a logical length at the current scale.
    int pixels(int logical) const;
    /// Draws the texture scaled to the logical rectangle with rounded corners (radius 0 = square).
    /// A texture already sized to the rectangle in pixels is copied without resampling.
    void blit(const Texture& t, int x, int y, int w, int h, int radius = 0);

private:
    struct Font {
        std::vector<std::uint8_t> data;
        std::unique_ptr<stbtt_fontinfo> info;
        bool ok = false;
    };
    struct Glyph {
        int w = 0, h = 0, xoff = 0, yoff = 0;
        float advance = 0;
        std::vector<std::uint8_t> alpha;
    };

    double sx(double x) const { return ox_ + x * scale_; }
    double sy(double y) const { return oy_ + y * scale_; }
    void blend(int x, int y, Color c, int alpha);
    template <class Sdf>
    void paint(double x0, double y0, double x1, double y1, Color c, Sdf sdf);
    void fillRound(double x0, double y0, double x1, double y1, double r, Color c);
    int fontIndex(Size size) const;
    int pixelSize(Size size) const;
    const Glyph& glyph(int font, int px, std::uint32_t cp);
    float kern(int font, int px, std::uint32_t a, std::uint32_t b);
    float widthPhys(const std::string& s, Size size);
    std::string fit(const std::string& s, Size size, int maxWidth);

    int w_, h_;
    double scale_ = 1, ox_ = 0, oy_ = 0;
    std::vector<std::uint32_t> buf_;
    Font fonts_[2];
    std::map<std::uint64_t, Glyph> glyphs_;
};

}  // namespace gfx
