"""RX_VK_THREAD_PRIO (HeyListen c81f500c, PRIO1): the background compile threads kept off the replay's core (gpu/vk/thread_prio.h)
and its call sites. No game, no GPU.

thread_prio.h is built on its own (tests/test_thread_prio.cpp) and run at RX_VK_THREAD_PRIO=0 and 1: the mask, the hook, the
mark a pinned thread leaves for the workers it starts, the start line. The source is checked function by function
(tests/srccut.py): the in-play compile threads carry the pin (the update's shaders behind the game, prepare_background and
prepare_run's workers when background; the predicted pipelines, predict_background and predict_run's workers when
background; the state list's and the libraries' workers when their caller was pinned), the start's precompile and the jobs
workers do not, no time-critical level, the start line and the affinity call in vk_main.cpp.

python -I -B tests/test_thread_prio.py [--cxx clang++]
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))   # (python -I leaves the check's own folder off the path)
from srccut import block  # noqa: E402

RUN_ALL_ARGS = ["--cxx", "{cxx}"]

ROOT = Path(__file__).resolve().parents[1]
PIN = "MKWVK_PIN_BACKGROUND();"


def check_source():
    vk = ROOT / "gpu" / "vk"
    draw = (vk / "vk_draw.cpp").read_text(encoding="utf-8")
    main = (vk / "vk_main.cpp").read_text(encoding="utf-8")
    for name in ("vk_draw.cpp", "vk_jobs.cpp", "vk_replay.cpp", "vk_main.cpp", "vk_memory.cpp"):
        if "THREAD_PRIORITY_TIME_CRITICAL" in (vk / name).read_text(encoding="utf-8"):
            raise SystemExit("a renderer thread is time-critical: " + name)
    jobs = (vk / "vk_jobs.cpp").read_text(encoding="utf-8")
    if "MKWVK_PIN_BACKGROUND" in jobs or "thread_prio" in jobs:
        raise SystemExit("the jobs workers run work a frame waits for: they are not pinned off the replay's core (HeyListen: -1% warm)")
    want = {   # (function: the pins it holds, as written)
        "void state_list_prepare(": ["if (pin) " + PIN] * 2,
        "bool warm_libraries(": ["if (pin) " + PIN],
        "bool prepare_run(": ["if (background) " + PIN],
        "void prepare_background() {": [PIN],
        "void predict_run(": ["if (background) " + PIN],
        "void predict_background() {": [PIN],
        "void precompile_run(": [],
    }
    for marker, pins in want.items():
        body = block(draw, marker, where="gpu/vk/vk_draw.cpp")
        if body.count(PIN) != len(pins) or any(body.count(p) < pins.count(p) for p in pins):
            raise SystemExit("%s: the background compile pins are not as thread_prio.h says (want %s)" % (marker, pins))
    for marker in ("void state_list_prepare(", "bool warm_libraries("):
        if "const bool pin = ::mkwvk::prio::pinned_here();" not in block(draw, marker, where="gpu/vk/vk_draw.cpp"):
            raise SystemExit(marker + " no longer asks whether its caller is a pinned background thread")
    init = block(main, "static void thread_prio_init() {", where="gpu/vk/vk_main.cpp")
    if 'logf("vk: thread priorities: %s"' not in init or "thread_prio_init();" not in main:
        raise SystemExit("the start line for the thread priorities is gone")
    if "SetThreadAffinityMask(GetCurrentThread(), (DWORD_PTR)mask)" not in init or "host->reserved_cpus" not in init:
        raise SystemExit("the compile threads are no longer kept off the replay's core")
    if "RX_VK_THREAD_PRIO" not in (vk / "thread_prio.h").read_text(encoding="utf-8"):
        raise SystemExit("the switch is not named in its header")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="clang++")
    args = parser.parse_args()
    check_source()
    print("PASS: the in-play compile threads carry the pin, the start's and the jobs workers do not; the start line")
    with tempfile.TemporaryDirectory(prefix="thread-prio-") as tmp:
        exe = Path(tmp) / ("thread-prio.exe" if os.name == "nt" else "thread-prio")
        subprocess.run([args.cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT / "gpu" / "vk"),
                        str(ROOT / "tests" / "test_thread_prio.cpp"), "-o", str(exe)], check=True, timeout=120)
        for mode in ("0", "1"):
            r = subprocess.run([str(exe), mode], capture_output=True, text=True, timeout=60,
                               env={**os.environ, "RX_VK_THREAD_PRIO": mode})
            print(r.stdout, end="")
            if r.returncode or "ok" not in r.stdout:
                raise SystemExit("thread_prio.h at RX_VK_THREAD_PRIO=%s" % mode)


if __name__ == "__main__":
    main()
