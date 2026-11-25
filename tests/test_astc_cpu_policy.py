# Copyright (C) 2026 Sacrappy
"""(HeyListen d834350d + 8f5ca506) Compile and run the rule for who decodes ASTC on the CPU by default
(gpu/vk/astc_cpu_policy.h; no game/GPU). Their issue 127: AMD integrated GPUs (Radeon 890M) on Windows; Vega APUs keep the GPU
decode; AMD's discrete cards, other vendors and Linux are unchanged."""
import argparse
import subprocess
import tempfile
from pathlib import Path

RUN_ALL_ARGS = ["--cxx", "{cxx}"]
ROOT = Path(__file__).resolve().parents[1]


def check_source():
    """The texture setup still asks the rule, with the device type, lets RX_VK_ASTC_CPU win, and logs when it applies"""
    src = (ROOT / "gpu/vk/vk_texture.cpp").read_text(encoding="utf-8")
    for needle in ('#include "astc_cpu_policy.h"', "astc_cpu_policy::by_default(windows, dev.props.vendorID, dev.props.deviceID,",
                   "dev.props.deviceType == VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU);",
                   'if (const char* e = getenv("RX_VK_ASTC_CPU")) v = !env_value_off(e);', 'logf("vk: ASTC decoded on the CPU'):
        if needle not in src:
            raise SystemExit("vk_texture.cpp no longer has: " + needle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()
    check_source()
    with tempfile.TemporaryDirectory(prefix="astc-cpu-policy-") as tmp:
        exe = Path(tmp) / "astc-cpu-policy.exe"
        subprocess.run([args.cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror",
                        str(ROOT / "tests/test_astc_cpu_policy.cpp"), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
