"""Skip Ingo's races (rando_skip_races, asked 2026-11-21, bugs.md 92): the setting from the options file to the seed tool,
the launcher's row and the stamp; and the launcher's settings rows each a row of their own (the Infinite ammo row was
once written inside the Master Sword's). The flow edit itself (rando_seed.py ingo_races_skip) needs the game's file:
not read here."""
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
    seed = read("tools", "rando", "rando_seed.py")
    check('"rando_skip_races": 0' in seed and 'a.skip_races = a.skip_races or ini["rando_skip_races"] != 0' in seed,
          "the seed tool does not read rando_skip_races")
    check('stamp = stamp[:-1] + " races skipped\\n"' in seed, "the setting is not on the stamp's line of settings that move no item")
    check("gift_files[EPONA_FLOW] = ingo_races_skip(was)" in seed, "the seed does not write Ingo's flow with the setting on")
    check('X(SKIP_RACES, "Skip Ingo\'s races", "rando_skip_races",' in read("gpu", "vk", "oot_rando.h"), "the settings table has no row for it")
    launcher = read("launcher", "Launcher.cs")
    check('"rando_infinite_ammo", "rando_skip_races", "rando_epona_song" };' in launcher, "the launcher does not keep a seed when it changes (NoItemKeys)")
    check('new object[] { "rando_skip_races", "Skip Ingo\'s races",' in launcher, "the launcher has no row for it")
    # (every settings row ends its own array: no "new object[]" right after a row's help text without its closing brace)
    check(not re.search(r'"\s*,\s*\n\s*new object\[\] \{ "rando_', launcher), "a launcher settings row is written inside the one before it")
    print("FAIL" if failed else "PASS: skip Ingo's races")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
