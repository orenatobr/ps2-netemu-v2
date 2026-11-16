#include "ps3.h"

#include <malloc.h>
#include <ppu-types.h>
#include <rsx/rsx.h>
#include <string.h>
#include <sysutil/sysutil.h>
#include <sysutil/video.h>
#include <unistd.h>

#include <io/pad.h>

#include "inter_bold_ttf.h"
#include "inter_regular_ttf.h"

namespace {

constexpr u32 kCommandBuffer = 0x100000;
constexpr u32 kHostSize = 32 * 1024 * 1024;
constexpr u32 kLabel = 255;

gcmContextData* g_context = nullptr;
u32 g_width = 0, g_height = 0, g_pitch = 0, g_offset[2] = {0, 0}, g_back = 0, g_label = 1;
u32* g_buffer[2] = {nullptr, nullptr};
bool g_firstFlip = true;
volatile bool g_quit = false;
bool g_circleConfirms = false;
bool g_padReady = false;
padData g_last[7];
bool g_valid[7] = {false, false, false, false, false, false, false};
bool g_prev[5] = {false, false, false, false, false};

void onSysutil(u64 status, u64, void*) {
    if (status == SYSUTIL_EXIT_GAME) g_quit = true;
}

void waitFinish() {
    rsxSetWriteBackendLabel(g_context, kLabel, g_label);
    rsxFlushBuffer(g_context);
    for (int i = 0; i < 100000 && *(vu32*)gcmGetLabelAddress(kLabel) != g_label; ++i) usleep(30);
    ++g_label;
}

void waitIdle() {
    rsxSetWriteBackendLabel(g_context, kLabel, g_label);
    rsxSetWaitLabel(g_context, kLabel, g_label);
    ++g_label;
    waitFinish();
}

void waitFlip() {
    for (int i = 0; i < 10000 && gcmGetFlipStatus() != 0; ++i) usleep(200);
    gcmResetFlipStatus();
}

bool edge(int slot, bool down) {  // fires once per press
    const bool fired = down && !g_prev[slot];
    g_prev[slot] = down;
    return fired;
}

}  // namespace

namespace ps3 {

bool videoInit(int& width, int& height) {
    void* host = memalign(1024 * 1024, kHostSize);
    if (!host || rsxInit(&g_context, kCommandBuffer, kHostSize, host) != 0) return false;
    videoState state;
    videoResolution res;
    if (videoGetState(0, 0, &state) != 0 || videoGetResolution(state.displayMode.resolution, &res) != 0) return false;
    if (res.width < 640 || res.height < 480) return false;
    videoConfiguration config;
    memset(&config, 0, sizeof config);
    config.resolution = state.displayMode.resolution;
    config.format = VIDEO_BUFFER_FORMAT_XRGB;
    config.pitch = res.width * sizeof(u32);
    waitIdle();
    if (videoConfigure(0, &config, nullptr, 0) != 0) return false;
    gcmSetFlipMode(GCM_FLIP_VSYNC);
    g_width = res.width;
    g_height = res.height;
    g_pitch = g_width * sizeof(u32);
    for (int i = 0; i < 2; ++i) {
        g_buffer[i] = static_cast<u32*>(rsxMemalign(64, g_height * g_pitch));
        if (!g_buffer[i]) return false;
        memset(g_buffer[i], 0, g_height * g_pitch);
        rsxAddressToOffset(g_buffer[i], &g_offset[i]);
        gcmSetDisplayBuffer(i, g_offset[i], g_pitch, g_width, g_height);
    }
    width = int(g_width);
    height = int(g_height);
    return true;
}

void videoPresent(const std::uint32_t* pixels) {
    if (!g_context) return;
    if (!g_firstFlip) waitFlip();
    else gcmResetFlipStatus();
    memcpy(g_buffer[g_back], pixels, std::size_t(g_height) * g_pitch);
    gcmSetFlip(g_context, g_back);
    rsxFlushBuffer(g_context);
    gcmSetWaitFlip(g_context);
    g_back ^= 1;
    g_firstFlip = false;
}

void videoShutdown() {
    if (!g_context) return;
    if (g_firstFlip) {
        waitFinish();
        return;
    }
    waitFlip();
    gcmSetWaitFlip(g_context);
    rsxFinish(g_context, 1);
}

bool inputInit() {
    s32 value = 0;
    if (sysUtilGetSystemParamInt(SYSUTIL_SYSTEMPARAM_ID_ENTER_BUTTON_ASSIGN, &value) == 0) g_circleConfirms = value == 0;
    sysUtilRegisterCallback(SYSUTIL_EVENT_SLOT0, onSysutil, nullptr);
    g_padReady = ioPadInit(7) == 0;
    return g_padReady;
}

Input poll() {
    bool up = false, down = false, cross = false, circle = false, tri = false;
    if (g_padReady) {
        padInfo info;
        ioPadGetInfo(&info);
        for (int i = 0; i < 7; ++i) {
            if (!info.status[i]) {
                g_valid[i] = false;
                continue;
            }
            padData fresh;
            memset(&fresh, 0, sizeof fresh);
            if (ioPadGetData(i, &fresh) == 0 && fresh.len > 0) {
                g_last[i] = fresh;
                g_valid[i] = true;
            }
            if (!g_valid[i]) continue;
            const padData& d = g_last[i];
            up |= d.BTN_UP;
            down |= d.BTN_DOWN;
            cross |= d.BTN_CROSS;
            circle |= d.BTN_CIRCLE;
            tri |= d.BTN_TRIANGLE;
        }
    }
    Input in;
    in.up = edge(0, up);
    in.down = edge(1, down);
    in.a = edge(2, g_circleConfirms ? circle : cross);
    in.b = edge(3, g_circleConfirms ? cross : circle);
    in.x = edge(4, tri);
    return in;
}

void pump() { sysUtilCheckCallback(); }
bool quitRequested() { return g_quit; }

bool portuguese() {
    s32 value = 0;
    return sysUtilGetSystemParamInt(SYSUTIL_SYSTEMPARAM_ID_LANG, &value) == 0 &&
           (value == SYSUTIL_LANG_PORTUGUESE_BR || value == SYSUTIL_LANG_PORTUGUESE_PT);
}

bool circleConfirms() { return g_circleConfirms; }

void sleepMs(int ms) {
    for (; ms > 0; ms -= 50) {
        sysUtilCheckCallback();
        usleep(static_cast<useconds_t>(ms < 50 ? ms : 50) * 1000);
    }
}

std::vector<std::uint8_t> fontBytes(bool bold) {
    if (bold) return std::vector<std::uint8_t>(inter_bold_ttf, inter_bold_ttf + inter_bold_ttf_size);
    return std::vector<std::uint8_t>(inter_regular_ttf, inter_regular_ttf + inter_regular_ttf_size);
}

}  // namespace ps3
