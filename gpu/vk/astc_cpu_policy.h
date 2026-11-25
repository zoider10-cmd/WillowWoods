// Copyright (C) 2026 Sacrappy
// (HeyListen d834350d + 8f5ca506, GPL-3.0-or-later)
// Which GPUs decode ASTC on the CPU by default, when RX_VK_ASTC_CPU is not set (vk_texture.cpp astc_on_cpu).
// tests/test_astc_cpu_policy.py
#pragma once
#include <cstdint>

namespace astc_cpu_policy {

// On Windows, AMD's integrated GPUs (vendor 0x1002, device type INTEGRATED_GPU): the Ryzen 7000/9000 desktop CPUs' 2-CU graphics
// (Longshot's #489) and the APUs' larger ones. Issue 127: on an Xbox Ally X (Radeon 890M, driver 26.10.1) the driver reset the GPU
// while a save loaded, in a burst of GPU ASTC decodes (491 ms of uploads in one frame); the CPU decode fixed it. The two Ryzen
// device ids stay named whatever type the driver reports. Not other vendors, not AMD's discrete cards, not off Windows.
// Not the Vega-generation APUs either (Ryzen 2000 to 5000 U/H/G series, vega_apu): on a Ryzen 7 5700U (driver 26.5.2, 15 GB) the GPU
// decode never reset the device in 6 runs, and the CPU decode, whose textures are RGBA8 (4 times the BC ones, with 486 MB of VRAM
// allowed), stalled 1.1-1.9 s 12 to 20 times a minute while the camera turned in Hyrule Field: 1.3 fps against 14.2.
inline bool vega_apu(uint32_t device_id) {
    switch (device_id) {
    case 0x15DD:   // Raven Ridge (Ryzen 2000 U/H/G)
    case 0x15D8:   // Picasso, Raven 2, Dali (Ryzen 3000 U/H/G, Athlon)
    case 0x1636:   // Renoir (Ryzen 4000 U/H/G)
    case 0x164C:   // Lucienne (Ryzen 5000 U, Zen 2: the 5700U)
    case 0x1638:   // Cezanne (Ryzen 5000 U/H/G, Zen 3)
    case 0x15E7:   // Barcelo (Ryzen 5000/7000 U refresh)
        return true;
    }
    return false;
}

inline bool by_default(bool windows, uint32_t vendor_id, uint32_t device_id, bool integrated) {
    if (!windows || vendor_id != 0x1002) return false;
    if (vega_apu(device_id)) return false;
    return integrated || device_id == 0x164E || device_id == 0x13C0;
}

} // namespace astc_cpu_policy
