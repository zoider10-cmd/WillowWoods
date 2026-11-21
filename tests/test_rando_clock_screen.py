"""The In-game clock row (asked 2026-11-21): the game side sends the time of day (OOT_CLOCK_ID), the renderer keeps it and
draws it as hours and minutes while the row is on. Read from the sources: no game files."""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
failed = []


def check(ok, what):
    if not ok:
        failed.append(what)
        print("FAIL: " + what)


def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


def main():
    ids = read("gpu", "vk", "oot_cheat_items.h")
    m = re.search(r"#define OOT_CLOCK_ID (\d+)", ids)
    taken = {int(v) for k, v in re.findall(r"#define (OOT_\w+_ID|OOT_TRACKER_\w+) (\d+)", ids) if k != "OOT_CLOCK_ID"}
    check(m and int(m.group(1)) not in taken, "OOT_CLOCK_ID is missing or shares a number with another ID")
    host = read("host", "hos_main.c")
    check("rx_option_set(OOT_CLOCK_ID, loaded && clock ? (int)recomp_load32(c, clock + 0x28) : -1);" in host,
          "the game side does not send the clock's seconds in the day (-1 with no save loaded)")
    menu = read("gpu", "vk", "vk_menu.cpp")
    check('{TAB_GAMEPLAY, "In-game clock", &opts.show_clock, 0, 1, 1, tx_onoff,' in menu, "the Gameplay tab has no In-game clock row")
    check("if (id == OOT_CLOCK_ID) {" in menu and "game_clock.store(value" in menu, "the renderer does not keep the time it is sent")
    check(menu.count("if (clock) draw_clock(c);") == 2, "the clock is not drawn both on screen and on a test run's pictures")
    check('"%02d:%02d", secs / 3600 % 24, secs / 60 % 60' in menu, "the clock is not drawn as hours and minutes")
    print("FAIL" if failed else "PASS: the in-game clock")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
