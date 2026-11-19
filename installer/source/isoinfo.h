// Reads the boot serial of a PS2 disc image (ISO9660, 2048 byte sectors) from its SYSTEM.CNF. Pure file logic, tested on the host.
#pragma once

#include <string>

namespace isoinfo {

/// The serial in the BOOT2 line of SYSTEM.CNF in the root of the image, upper case, as the disc writes it
/// ("SLUS_212.62"). Returns "" when the file is not an ISO9660 image, has no SYSTEM.CNF or no BOOT2 line.
std::string bootSerial(const std::string& isoPath);

}  // namespace isoinfo
