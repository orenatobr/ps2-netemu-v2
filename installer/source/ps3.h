// Console layer (PSL1GHT): RSX frame buffer, controller and system events.
#pragma once

#include <cstdint>
#include <vector>

namespace ps3 {

struct Input {
    bool up = false, down = false;
    bool a = false;  ///< confirm (cross, or circle with the Japanese layout)
    bool b = false;  ///< back (the other one)
    bool x = false;  ///< triangle
};

/// Opens the frame buffer; width/height get the real output size.
bool videoInit(int& width, int& height);
void videoPresent(const std::uint32_t* pixels);
void videoShutdown();

/// Controllers and system events (PS button, quit). Call once per frame.
bool inputInit();
Input poll();
void pump();
bool quitRequested();
bool circleConfirms();  ///< true when circle is the confirm button
void sleepMs(int ms);

std::vector<std::uint8_t> fontBytes(bool bold);

}  // namespace ps3
