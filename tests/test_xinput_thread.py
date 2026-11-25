"""(ProjectReLink 550bde6) XInput's slots asked on a thread of their own (host/nn_hid.c; no game, no pad).

An empty XInput slot is slow to ask (a millisecond or more on PCs with Bluetooth or a virtual pad's driver), and the four
empty slots were asked together once a second on the game's thread. A thread asks them now and the game's read takes the
last answers. Read from the source, and the parts we keep that ReLink's version lacks:
- XInput is still loaded from System32 only (LOAD_LIBRARY_SEARCH_SYSTEM32), never beside the game or on PATH;
- pads_read still asks XInput only when SDL has no pads or HOS_XINPUT=1, and the thread asks only within 1 s of such a read;
- the menu's dead zone and stick inversion (rx_option 11, 16, 17) still apply to XInput's sticks, and xinput_pads_now is kept;
- an empty slot is asked again after 1 s, a connected one at every pass; HOS_XINPUT_INLINE=1 asks on the game's thread.

    python -I -B tests/test_xinput_thread.py
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from srccut import block  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main():
    hid = (ROOT / "host/nn_hid.c").read_text(encoding="utf-8")
    fails = []

    def check(ok, why):
        if not ok:
            fails.append(why)

    load = block(hid, "static void xinput_load(int64_t now) {")
    check(load.count("LOAD_LIBRARY_SEARCH_SYSTEM32") == 2, "XInput is not loaded from System32 only")
    poll = block(hid, "static void xinput_poll(int64_t now) {")
    check("if (now < xin_retry[p]) continue;" in poll and "if (!on) xin_retry[p] = now + 1000000000LL;" in poll,
          "an empty slot is not left for a second, or a connected one is not asked at every pass")
    check("AcquireSRWLockExclusive(&xin_lock);" in poll, "the slots' answers are written without their lock")
    main_ = block(hid, "static DWORD WINAPI xinput_main(LPVOID unused) {")
    check("xin_wanted_at" in main_ and "< 1000000000LL" in main_, "the thread asks XInput while the game does not want it")
    take = block(hid, "static void xinput_take(int64_t now, XinSlot out[XUSER_MAX_COUNT]) {")
    check('env_on("HOS_XINPUT_INLINE")' in take and "if (mode != 1) xinput_poll(now);" in take,
          "HOS_XINPUT_INLINE=1 (or a thread that could not start) does not ask on the game's thread")
    check(take.find("xin_wanted_at") < take.find("CreateThread("), "the read does not say it wants XInput before the thread starts")
    pads = block(hid, "static void pads_read(")
    check(pads.find("if (!sdl_pads || poll_xinput_env) {") < pads.find("xinput_take(now, slots);"),
          "XInput is asked even while SDL has pads (the double reads of #1480, #1583)")
    check("xinput_get(" not in pads and "LoadLibrary" not in pads, "the game's read still asks XInput or loads it itself")
    for want in ("rx_option(11, 0)", "rx_option(16, 0)", "rx_option(17, 0)", "xinput_pads_now = any;", "if (!slots[p].on) continue;"):
        check(want in pads, "pads_read lost: " + want)
    if fails:
        for f in fails:
            print("FAIL: " + f)
        raise SystemExit(1)
    print("XInput on its own thread: ok (System32, the SDL gate, the dead zone and inversion kept)")


if __name__ == "__main__":
    main()
