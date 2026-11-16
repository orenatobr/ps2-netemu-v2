// Small replacements for C99 math the PS3 newlib does not put in namespace std.
#pragma once

#include <cmath>

namespace mathx {

inline long iround(double x) { return static_cast<long>(std::floor(x + 0.5)); }

inline double hyp(double a, double b) { return std::sqrt(a * a + b * b); }

}  // namespace mathx
