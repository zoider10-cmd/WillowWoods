"""Key rings (rando_keyrings, asked 2026-11-27): with Small keys: Anywhere, a dungeon's small keys are one item of the
shuffle, its ring, which gives every small key of its dungeon. No game data.

Checked:
- keyrings(): each dungeon's first key of the shuffle is its ring and stays a key; its other keys' chests hold the junk;
  the count of each dungeon's ring is the number of keys it had; a dungeon with one key is a ring of one;
- the ring's words say the ring and its count, in English; another dungeon's key (no ring) keeps the key's words;
- the main part: the setting counts only with Small keys: Anywhere, is on the stamp, makes the rings before the keys go
  into the rules, writes KEYRINGS_FILE (and takes an old one away), and gives the words the counts;
- the game's side: keyrings.txt is read with the tracker's lists; a small key of the shuffle raises its dungeon's count
  by its ring's keys (compiled and run: 1 without a ring, the ring's count with one); got in its own dungeon, where the
  game counts one itself, the rest is added (oot_keyring_rest: nothing for a ring of one or another item);
- the setting is in the launcher's and the menu's tables, last (a seed ID's order), and a seed ID has room for it.

    python -I -B tests/test_rando_keyrings.py
"""
import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import srccut  # noqa: E402

spec = importlib.util.spec_from_file_location("rando_seed", ROOT / "tools" / "rando" / "rando_seed.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)


def check(ok, why):
    if not ok:
        print("FAIL: %s" % why)
        sys.exit(1)


K = S.SMALL_KEY
spots = {10: ["WaterTemple", K + "@WaterTemple#2"], 11: ["WaterTemple", K + "@WaterTemple#1"], 12: ["WaterTemple", K + "@WaterTemple#3"],
         20: ["FireTemple", K + "@FireTemple#1"], 30: ["Market", "TBox_Rupee_Red"]}
tags = {h: s[1] for h, s in spots.items() if "@" in s[1]}
kept, counts = S.keyrings(spots, tags)
check(kept == {11: K + "@WaterTemple#1", 20: K + "@FireTemple#1"}, "the rings: %r" % kept)
check(counts == {"WaterTemple": 3, "FireTemple": 1}, "the counts: %r" % counts)
check(spots[10][1] == spots[12][1] == S.KEYRING_JUNK and spots[11][1] == K + "@WaterTemple#1" and spots[30][1] == "TBox_Rupee_Red", "the chests: %r" % spots)

# the words (dungeon_words' own part: the ring's lines)
check(S.KEYRING_WORDS[0].format("the Water Temple") == "You found the key ring of the Water Temple!", "the ring's message")
check(S.KEYRING_WORDS[1].format(4, "the Water Temple").startswith("It holds all 4 small keys of the Water Temple"), "the ring's caption")
src = (ROOT / "tools" / "rando" / "rando_seed.py").read_text(encoding="utf-8")
words = src[src.index("def dungeon_words(data, english, rings=None):"):src.index("def first_bag_words(")]
check("if item == SMALL_KEY and rings and folder in rings:" in words and "ring.format(rings[folder], DUNGEON_SAY[folder])" in words, "dungeon_words does not word a ring")

main = src[src.index("\ndef main():"):]
check('a.keyrings = ini["rando_keyrings"] == 1 and keys_mode == 2' in main, "the setting is not read, or counts without Small keys: Anywhere")
check('(" keyrings 1" if a.keyrings else "")' in main, "the setting is not on the stamp")
made, ruled = main.index("small_tags, ring_counts = keyrings(spots, small_tags)"), main.index("key_sets.setdefault(")
check(made < ruled, "the rings are made after the keys went into the rules")
check("dungeon_words(text, n.startswith(FIRST_BAG_ENGLISH), ring_counts)" in main, "the words are not given the rings")
check('f.write("".join("%s|%d\\n" % kv for kv in sorted(ring_counts.items())))' in main and "written.append(KEYRINGS_FILE)" in main
      and "elif os.path.exists(rings_file):\n        os.remove(rings_file)" in main, "KEYRINGS_FILE is not written, listed, or taken away")
check('"rando_keyrings": 0' in src, "the options' line is not known")

# the game's side
host = (ROOT / "host" / "hos_main.c").read_text(encoding="utf-8")
check('"mods/rando-seed/keyrings.txt"' in host and 'sscanf(line, "%23[A-Za-z]|%d", owner, &keys) != 2 || keys < 1 || keys > 99' in host, "keyrings.txt is not read")
item = srccut.block(host, "static int oot_dungeon_item(Ctx *c, const char *name) {", "hos_main.c")
check("n += oot_keyring(owner);" in item and "return oot_keyring_rest(c, name, owner), 0;" in item
      and "if (oot_dungeon_own[0]) oot_keyring_rest(c, name, oot_dungeon_own);" in item, "oot_dungeon_item does not count a ring")
check("snprintf(oot_dungeon_own, sizeof oot_dungeon_own, \"%s\", owner);" in srccut.block(host, "static int oot_dungeon_owner(", "hos_main.c"),
      "oot_dungeon_owner does not say whose dungeon Link is in")
ring = srccut.block(host, "static int oot_keyring(const char *folder) {", "hos_main.c")
rest = srccut.block(host, "static void oot_keyring_rest(Ctx *c, const char *name, const char *folder) {", "hos_main.c")
program = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef struct Ctx { int unused; } Ctx;
#define OOT_KEYRING_MAX 16
static struct { char folder[24]; int keys; } oot_keyrings[OOT_KEYRING_MAX];
static int oot_keyring_n;
static int32_t stored = 2, writes;
static char last[80];
static uint64_t oot_flag_hash(const char *flag) { snprintf(last, sizeof last, "%s", flag); return 7; }
static int oot_gamedata_int(Ctx *c, uint64_t h, int32_t *n, int write) { (void)c; (void)h; if (write) stored = *n, writes++; else *n = stored; return 1; }
static void hos_log(const char *f, ...) { (void)f; }
''' + ring + "\n" + rest + r'''
int main(void) {
    Ctx c = {0};
    if (oot_keyring("WaterTemple") != 1) return 1;                       /* no ring: a key is one */
    snprintf(oot_keyrings[0].folder, 24, "WaterTemple"), oot_keyrings[0].keys = 4;
    snprintf(oot_keyrings[1].folder, 24, "BottomOfTheWell"), oot_keyrings[1].keys = 1;
    oot_keyring_n = 2;
    if (oot_keyring("WaterTemple") != 4 || oot_keyring("BottomOfTheWell") != 1 || oot_keyring("FireTemple") != 1) return 2;
    oot_keyring_rest(&c, "Item_Dungeon_SmallKey", "WaterTemple");        /* in its own dungeon: three more */
    if (stored != 5 || writes != 1 || strcmp(last, "DungeonInfo.WaterTemple.SmallKeyNum")) return 3;
    oot_keyring_rest(&c, "Item_Dungeon_SmallKey", "BottomOfTheWell");    /* a ring of one: nothing more */
    oot_keyring_rest(&c, "Item_Dungeon_SmallKey", "FireTemple");         /* no ring */
    oot_keyring_rest(&c, "Item_Dungeon_BossKey", "WaterTemple");         /* another item */
    if (stored != 5 || writes != 1) return 4;
    puts("ok");
    return 0;
}
'''
cc = "clang"
for i, a in enumerate(sys.argv):
    if a == "--cc" and i + 1 < len(sys.argv):
        cc = sys.argv[i + 1]
with tempfile.TemporaryDirectory() as tmp:
    c_file, exe = os.path.join(tmp, "ring.c"), os.path.join(tmp, "ring.exe")
    Path(c_file).write_text(program, encoding="utf-8")
    built = subprocess.run([cc, "-O1", "-Wall", "-Werror", "-o", exe, c_file], capture_output=True, text=True)
    check(built.returncode == 0, "the ring's count does not compile:\n%s" % built.stderr)
    ran = subprocess.run([exe], capture_output=True, text=True)
    check(ran.returncode == 0, "the ring's count: case %d" % ran.returncode)

# the tables
header = (ROOT / "gpu" / "vk" / "oot_rando.h").read_text(encoding="utf-8")
launcher = (ROOT / "launcher" / "Launcher.cs").read_text(encoding="utf-8")
check('X(KEYRINGS, "Key rings", "rando_keyrings",' in header and header.index('X(KEYRINGS,') > header.index('X(POTS,'), "the menu's table: not there, or not last")
check('new object[] { "rando_keyrings", "Key rings", new[] { "Off", "On" }, new[] { 0, 1 },' in launcher
      and launcher.index('new object[] { "rando_keyrings"') > launcher.index('new object[] { "rando_pots"'), "the launcher's table: not there, or not last")
check('"rando_keys", "rando_keyrings", "rando_boss_keys"' in launcher, "the launcher's section does not list it beside Dungeon keys")
check("OOT_RANDO_ID_X3L_SLOTS = 66" in header and "X3lSlots = 66" in launcher and header.count("\n    X(") <= 66, "a seed ID has no room for the settings")
print("ok: Key rings")
