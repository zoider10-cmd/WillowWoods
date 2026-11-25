"""The Tracker says which temples a check waits for (the owner's to-do, 2026-11-23: the Nocturne's lesson and Zelda's Light
Arrows showed "in logic" before the Water, Shadow and Spirit Temples were done). The rules count items only; the game
holds some checks back until temples are really done (their awakening scenes, HavePlayedEvent.Dm_Awake_<X>).

- the seed tool (tools/rando/rando_seed.py check_after) finds those checks in a checks file: the Nocturne's, the
  Prelude's and the Light Arrows' gifts, Lake Hylia's chests after the Water Temple, the Shadow Temple's own checks when
  the Nocturne is its lesson's alone, and the checks that need an item only a waiting check gives; main writes them to
  check_after.txt;
- the game's side (host/hos_main.c) tells the Tracker which temples' scenes have played, a bit each in the seed tool's
  STORY_TEMPLES order (OOT_TRACKER_TEMPLES);
- the Tracker (gpu/vk/vk_menu.cpp) reads the file, and its tracker_after_words, compiled here alone, names the temples
  not yet done; tracker_in_logic holds a check whose items are all held out of logic while it waits.

Game-free: made-up checks files, and the sources.

python -I -B tests/test_rando_story_waits.py [--cxx clang++]
"""
import argparse
import os
import subprocess
import sys
import tempfile

RUN_ALL_ARGS = ["--cxx", "{cxx}"]

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools", "rando"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # (tests/srccut.py: python -I leaves this folder off the path)
import rando_seed as S  # noqa: E402
from srccut import block  # noqa: E402


def fail(what):
    print("FAIL: " + what)
    sys.exit(1)


def line(area, name, folder, rule, hash_="-", gives=""):
    return "%s|%s|%s|A|0.0 0.0 0.0|%s|%s%s" % (area, name, folder, rule, hash_, "|" + gives if gives else "")


def gift_name(key):
    g = next(g for g in S.SONGS + S.GIFTS if g.key == key)
    return g.name[:1].upper() + g.name[1:]


FFW = ("ForestTemple", "FireTemple", "WaterTemple")


def check_seed():
    if S.STORY_TEMPLES != ("ForestTemple", "FireTemple", "WaterTemple", "ShadowTemple", "SpiritTemple"):
        fail("the story's temples are not the five medallions' in their order (the menu's bits)")
    noct, light, prelude = gift_name("song_nocturne"), gift_name("light_arrows"), gift_name("song_prelude")
    water = "%016x" % S.AFTER_WATER[0]
    # (the Nocturne its lesson's alone: no check gives it)
    lines = ["# header",
             line("Kakariko Village", noct, "KakarikoVillage", "KS,LS", "00000000000000a1", "Item_Hookshot"),
             line("Market", light, "Market", "BW,LT", "00000000000000a2", "Item_Arrow_Light"),
             line("Market", prelude, "Market", "BW", "00000000000000a5", "Obj_Rupee_Green"),
             line("Shadow Temple", "Chest", "ShadowTemple", "HB,LT", "00000000000000a3", "Item_Bombchu"),
             line("Lake Hylia", "Chest (red rupee) #1", "HyruleField", "IB", water, "Obj_Rupee_Red"),
             line("Kokiri Forest", "Chest", "KokiriForest", "-", "00000000000000a4", "Item_Boomerang"),
             line("Zora's River", "Chest", "ZoraRiver", "-", "00000000000000a6", "Obj_Rupee_Blue"),
             line("Market", "Shelf", "Market", "-")]
    got = dict(S.check_after(lines))
    want = {"00000000000000a1": FFW, "00000000000000a2": ("ShadowTemple", "SpiritTemple"), "00000000000000a5": ("ForestTemple",),
            "00000000000000a3": FFW, water: ("WaterTemple",)}
    if got != want:
        fail("the checks that wait, with the Nocturne its lesson's: %r, not %r" % (got, want))
    # (the Hookshot only at the Nocturne's lesson: the River's chest, whose only way asks for it, waits as that lesson does)
    got = dict(S.check_after(lines[:7] + [line("Zora's River", "Chest", "ZoraRiver", "HS,BW", "00000000000000a6")]))
    if got.get("00000000000000a6") != FFW:
        fail("a check whose every way needs an item that only a waiting check gives does not wait: %r" % got)
    got = dict(S.check_after(lines[:7] + [line("Zora's River", "Chest", "ZoraRiver", "HS/BM", "00000000000000a6")]))
    if "00000000000000a6" in got:
        fail("a check with a way that needs no waiting check's item waits")
    # (the Nocturne shuffled: the Shadow Temple waits only when the check that gives it does)
    nc = S.NOCTURNE
    shuffled = [line("Kakariko Village", noct, "KakarikoVillage", "KS", "00000000000000a1", nc),
                line("Shadow Temple", "Chest", "ShadowTemple", "NC,LT", "00000000000000a3"),
                line("Shadow Temple", "Chest #2", "ShadowTemple", "NC/HS", "00000000000000a7")]
    got = dict(S.check_after(shuffled))
    if got != {"00000000000000a1": FFW, "00000000000000a3": FFW}:
        fail("with the Nocturne at its own lesson, the Shadow Temple's checks that need it do not wait as the lesson: %r" % got)
    shuffled[0] = line("Kokiri Forest", "Chest", "KokiriForest", "-", "00000000000000a1", nc)
    if S.check_after(shuffled):
        fail("with the Nocturne in a chest that waits for nothing, a check waits: %r" % S.check_after(shuffled))
    src = open(S.__file__, encoding="utf-8").read()
    main_src = src[src.index("\ndef main():"):]
    if "after = check_after(f.read().splitlines())" not in main_src or "os.path.join(mod, CHECK_AFTER)" not in main_src:
        fail("main does not write check_after.txt from the checks file")


FIXTURE = r'''#include <cstdio>
#include <cstdlib>
#include <string>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL:%d %s\n", __LINE__, #x); exit(1); } } while (0)
@WORDS@
int main() {
    CHECK(tracker_after_words(0, 0) == "");
    CHECK(tracker_after_words(7, 7) == "");
    CHECK(tracker_after_words(7, -1) == "");   // (no save read yet: nothing said)
    CHECK(tracker_after_words(7, 0) == "the Forest, Fire and Water Temples");
    CHECK(tracker_after_words(7, 1) == "the Fire and Water Temples");
    CHECK(tracker_after_words(7, 3) == "the Water Temple");
    CHECK(tracker_after_words(24, 8) == "the Spirit Temple");
    CHECK(tracker_after_words(24, 0) == "the Shadow and Spirit Temples");
    printf("PASS: the Tracker names the temples a check waits for\n");
    return 0;
}
'''


def check_menu(cxx):
    menu = open(os.path.join(ROOT, "gpu", "vk", "vk_menu.cpp"), encoding="utf-8").read()
    start = menu.index("constexpr const char* kStoryTemples[] = {")
    names = menu[start:menu.index("};", start)]
    if [n for n in S.STORY_TEMPLES if '"%s"' % n in names] != list(S.STORY_TEMPLES) or names.count('"') != 2 * len(S.STORY_TEMPLES):
        fail("the Tracker's temples are not the seed tool's STORY_TEMPLES, in its order")
    if '"check_after.txt"' not in menu or S.CHECK_AFTER != "check_after.txt":
        fail("the Tracker does not read the seed's check_after.txt")
    logic = block(menu, "int tracker_in_logic(const TrackerCheck& k, std::string* missing) {")
    if "if (held) return tracker_after(k).empty() ? 1 : 0;" not in logic:
        fail("tracker_in_logic does not hold a waiting check out of logic")
    if "OOT_TRACKER_TEMPLES" not in menu:
        fail("the Tracker does not take the game's word on the temples done")
    header = open(os.path.join(ROOT, "gpu", "vk", "oot_cheat_items.h"), encoding="utf-8").read()
    if "#define OOT_TRACKER_TEMPLES " not in header:
        fail("oot_cheat_items.h has no OOT_TRACKER_TEMPLES")
    host = open(os.path.join(ROOT, "host", "hos_main.c"), encoding="utf-8").read()
    start = host.index("static const char *const oot_story_scenes[] = {")
    scenes = host[start:host.index("};", start)]
    want = ['"HavePlayedEvent.Dm_Awake_%s"' % t.replace("Temple", "") for t in S.STORY_TEMPLES]
    if [w for w in want if w in scenes] != want or scenes.count('"') != 2 * len(want):
        fail("the game's side does not read the five awakening scenes in STORY_TEMPLES' order")
    if "rx_option_set(OOT_TRACKER_TEMPLES," not in host:
        fail("the game's side does not tell the Tracker the temples done")
    words = block(menu, "std::string tracker_after_words(int wait, int done) {")
    with tempfile.TemporaryDirectory(prefix="story-waits-") as tmp:
        src, exe = os.path.join(tmp, "t.cpp"), os.path.join(tmp, "t.exe")
        open(src, "w", encoding="utf-8").write(FIXTURE.replace("@WORDS@", words))
        r = subprocess.run([cxx, "-std=c++17", src, "-o", exe], capture_output=True, text=True)
        if r.returncode:
            fail("tracker_after_words does not compile alone:\n" + r.stdout + r.stderr)
        r = subprocess.run([exe], capture_output=True, text=True)
        print(r.stdout.strip())
        if r.returncode:
            fail(r.stderr.strip())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cxx", default="clang++")
    a = p.parse_args()
    check_seed()
    check_menu(a.cxx)
    print("PASS: checks that wait for temples are told apart")
    return 0


if __name__ == "__main__":
    sys.exit(main())
