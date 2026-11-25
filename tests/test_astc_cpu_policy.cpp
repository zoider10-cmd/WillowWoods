// Copyright (C) 2026 Sacrappy (HeyListen 8f5ca506)
// astc_cpu_policy::by_default (gpu/vk/astc_cpu_policy.h): who decodes ASTC on the CPU when RX_VK_ASTC_CPU is unset.
// tests/test_astc_cpu_policy.py
#include "../gpu/vk/astc_cpu_policy.h"

#include <cstdio>

static int failures = 0;
static void expect(bool ok, const char* what) {
    if (!ok) {
        std::printf("FAIL: %s\n", what);
        failures++;
    }
}

int main() {
    using astc_cpu_policy::by_default;
    expect(by_default(true, 0x1002, 0x1900, true), "Windows, AMD Radeon 890M (an integrated GPU): issue 127");
    expect(by_default(true, 0x1002, 0x15BF, true), "Windows, AMD Radeon 780M");
    expect(by_default(true, 0x1002, 0x1681, true), "Windows, AMD Radeon 680M");
    expect(by_default(true, 0x1002, 0x164E, true), "Windows, Ryzen 7000 graphics (#489)");
    expect(by_default(true, 0x1002, 0x13C0, true), "Windows, Ryzen 9000 graphics (#489)");
    expect(by_default(true, 0x1002, 0x164E, false), "Windows, the Ryzen 7000 id whatever type the driver reports");
    expect(by_default(true, 0x1002, 0x13C0, false), "Windows, the Ryzen 9000 id whatever type the driver reports");
    expect(!by_default(true, 0x1002, 0x164C, true), "Windows, a Ryzen 7 5700U's Vega graphics: GPU path (CPU decode: 1.3 fps turning)");
    expect(!by_default(true, 0x1002, 0x1638, true), "Windows, a Ryzen 5000 Cezanne APU's Vega graphics: GPU path");
    expect(!by_default(true, 0x1002, 0x15D8, true), "Windows, a Ryzen 3000 Picasso APU's Vega graphics: GPU path");
    expect(!by_default(true, 0x1002, 0x747E, false), "Windows, an RX 7800 XT (discrete)");
    expect(!by_default(true, 0x1002, 0x744C, false), "Windows, an RX 7900 XTX (discrete)");
    expect(!by_default(true, 0x1002, 0x15BF, false), "Windows, AMD id of an APU reported as discrete or virtual: GPU path");
    expect(!by_default(true, 0x8086, 0x9A49, true), "Windows, Intel integrated");
    expect(!by_default(true, 0x10DE, 0x2684, false), "Windows, NVIDIA");
    expect(!by_default(true, 0x10DE, 0x164E, true), "Windows, another vendor with a Ryzen id");
    expect(!by_default(false, 0x1002, 0x1900, true), "Linux, AMD integrated (a Steam Deck): unchanged");
    expect(!by_default(false, 0x1002, 0x164E, true), "Linux, the Ryzen 7000 graphics: unchanged");
    if (failures) return 1;
    std::printf("astc_cpu_policy: ok\n");
    return 0;
}
