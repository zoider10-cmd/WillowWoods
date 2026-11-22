"""Castle guards let Link pass (rando_castle_guards, asked 2026-11-21): the setting read, on the stamp's line of the
settings that move no item, the game's table and the launcher's row. The flow edit (castle_guards_pass) needs the game's
file: not run here (seen without a window 2026-11-21: a guard's catch left Link where he was)."""
import os
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
    check('"rando_castle_guards": 0' in seed and 'a.castle_guards = a.castle_guards or ini["rando_castle_guards"] != 0' in seed,
          "the seed tool does not read rando_castle_guards")
    check('stamp = stamp[:-1] + " guards pass\\n"' in seed, "the setting is not on the stamp's line of settings that move no item")
    check("gift_files[GUARDS_FLOW] = castle_guards_pass(was)" in seed and 'GUARDS_ENTRIES = ("FoundBySecurity", "FoundBySecurity_Courtyard")' in seed,
          "the guards' flow is not written with the setting on")
    check('X(CASTLE_GUARDS, "Castle guards let Link pass", "rando_castle_guards",' in read("gpu", "vk", "oot_rando.h"), "the settings table has no row for it")
    launcher = read("launcher", "Launcher.cs")
    check('new object[] { "rando_castle_guards", "Castle guards let Link pass",' in launcher and '"rando_epona_song", "rando_castle_guards", "rando_free_scarecrow" };' in launcher,
          "the launcher has no row for it, or does not keep a seed when it changes")
    # (Free Scarecrow's Song, rando_free_scarecrow, asked 2026-11-21: whatever is played at a Pierre spot calls him)
    check('a.free_scarecrow = a.free_scarecrow or ini["rando_free_scarecrow"] != 0' in seed and 'stamp = stamp[:-1] + " scarecrow free\\n"' in seed
          and "FREE_SCARECROW_FILE = \"scarecrow_free.txt\"" in seed and "if (oot_check_count > 0) oot_scarecrow_free(c);" in read("host", "hos_main.c") and """X(FREE_SCARECROW, "Free Scarecrow's Song", "rando_free_scarecrow",""" in read("gpu", "vk", "oot_rando.h")
          and """new object[] { "rando_free_scarecrow", "Free Scarecrow's Song",""" in launcher, "Free Scarecrow's Song is not read, stamped, written, or offered")
    # (the song is kept twice, the recording and its notes: the first try wrote the recording alone, and the song list
    #  showed an empty staff. Both, and both copies of each)
    host = read("host", "hos_main.c")
    check("#define OOT_SCARECROW_NOTES 0xcc535536u" in host and "static const uint32_t notes[8] = {4, 7, 4, 7, 4, 0, 0, 0};" in host
          and "recomp_store32(c, list + 4 * k, notes[k]);" in host and "recomp_load32(c, notes_at) == 0" in host,
          "Free Scarecrow's Song does not write the song's notes (the Int array) beside its recording")
    print("FAIL" if failed else "PASS: castle guards let Link pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
