"""Dungeon entrances (rando_entrances, asked 2026-11-27: 1 the adult's dungeons, 2 the child's, 3 both): the six dungeons only an adult enters change
places among their doors, and the rules ask for the door a dungeon is behind (tools/rando/rando_seed.py
entrance_shuffle, entrance_access, and_rules). No game data.

Seen in the game without a window, the setting on: an adult through the Shadow Temple's door into the Ice Cavern, its
arrival scene played, and back out to the Shadow Temple's door in the graveyard. In trial seeds: 224 rules changed, all of
moved dungeons' checks and of checks that wait for them, none asking for less. Checked here:
- entrance_shuffle: a one-to-one change of the pool, the same for the same seed, another for another; over many seeds
  every dungeon comes behind every door; without the Nocturne as an item the Forest, Fire and Water Temples are never
  behind the Shadow Temple's door, and with it they are;
- and_rules: every way of one with every way of the other, a way that holds another left out, a plain rule and nothing;
- entrance_access: the fewest-item ways of a door's own dungeon's chests, no more than ENTRANCE_WAYS, none of another
  dungeon's or of a spot that is no chest; no chest: refused;
- the pool is of dungeons with a door, an adult's alone (the Door of Time's adult places), no child's dungeon, not the
  Spirit Temple nor Ganon's Castle;
- the main part: the setting is read, is on the stamp, moves the files, writes ENTRANCES_FILE and the spoiler's lines; a
  moved check's rule is its own and its door's (chests, gifts, Gold Skulltulas, pieces and pots, an ending's gift, the
  checks that wait for temples), fitted for the tracker; a moved dungeon's Boss Key's cap has its door's way; the
  Shadow Temple's door waits for the three temples' doors without the Nocturne;
- the setting is in the launcher's and the menu's tables, last.

    python -I -B tests/test_rando_entrance_setting.py
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("rando_seed", ROOT / "tools" / "rando" / "rando_seed.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)


def check(ok, why):
    if not ok:
        print("FAIL: %s" % why)
        sys.exit(1)


def ways(rule):
    return {frozenset(w) for w in rule} if isinstance(rule, S.Either) else {frozenset(rule)}


POOL = S.ENTRANCE_ADULT
check(S.ENTRANCE_POOLS == {1: (S.ENTRANCE_ADULT,), 2: (S.ENTRANCE_CHILD,), 3: (S.ENTRANCE_ADULT, S.ENTRANCE_CHILD)}, "the setting's groups")
check(set(POOL) <= set(S.DUNGEON_DOORS) and set(POOL) == set(S.DOOR_ADULT_AREAS) and len(POOL) == 6, "the pool is not the adult's six dungeons with a door")
check(not set(POOL) & {"InsideTheDekuTree", "DodongoCavern", "InsideJabuJabuBelly", "BottomOfTheWell", "SpiritTemple", "InsideGanonCastle"}, "the pool has a dungeon it should not")

# entrance_shuffle
one = S.entrance_shuffle(303, POOL)
check(set(one) == set(one.values()) == set(POOL), "not a one-to-one change: %r" % one)
check(S.entrance_shuffle(303, POOL) == one and any(S.entrance_shuffle(s, POOL) != one for s in range(1, 6)), "not by the seed alone")
seen = {(door, dungeon) for s in range(400) for door, dungeon in S.entrance_shuffle(s, POOL).items()}
check(len(seen) == 36, "over 400 seeds %d of 36 door and dungeon pairs came up" % len(seen))
quiet = [S.entrance_shuffle(s, POOL, nocturne_item=False) for s in range(400)]
check(all(b["ShadowTemple"] not in S.ENTRANCE_NOCTURNE_WAITS for b in quiet), "a temple the Nocturne's lesson waits for is behind the Shadow Temple's door")
check({b["ShadowTemple"] for b in quiet} == {"ShadowTemple", "IceCavern", "GerudoTrainingGround"}, "the Shadow Temple's door without the Nocturne: %r" % {b["ShadowTemple"] for b in quiet})
check(all(set(b) == set(b.values()) == set(POOL) for b in quiet), "without the Nocturne: not a one-to-one change")
check(any(S.entrance_shuffle(s, POOL)["ShadowTemple"] in S.ENTRANCE_NOCTURNE_WAITS for s in range(60)), "with the Nocturne an item no temple is ever behind the Shadow Temple's door")
check(S.ENTRANCE_NOCTURNE_WAITS == S.STORY_GIFTS["song_nocturne"], "the temples the Nocturne's lesson waits for")

# and_rules
E = S.either
check(ways(S.and_rules(E([{"a"}, {"b", "c"}]), frozenset({"d"}))) == {frozenset("ad"), frozenset("bcd")}, "and_rules: a rule of two ways and a plain one")
check(ways(S.and_rules(E([{"a"}, {"a", "b"}]), E([{"a"}, {"c"}]))) == {frozenset("a")}, "and_rules keeps a way that holds another")
check(S.and_rules(frozenset({"a"})) == frozenset({"a"}) and S.and_rules(frozenset({"a"}), S.NONE) == frozenset({"a"}), "and_rules with nothing")
check(ways(S.and_rules(E([{"a"}, {"b"}]), E([{"c"}, {"d"}]), frozenset({"e"}))) == {frozenset(x) for x in ("ace", "ade", "bce", "bde")}, "and_rules of three")

# entrance_access
spots = {1: ["FireTemple", "x", True, "", "Obj_TBox_A_01"], 2: ["FireTemple", "x", True, "", "Obj_TBox_A_02"], 3: ["FireTemple", "x", True, "", "skulltula"],
         4: ["WaterTemple", "x", True, "", "Obj_TBox_A_01"], 5: ["FireTemple", "x", True, "", "Obj_TBox_A_01"], 6: ["FireTemple", "x", True, "", "Obj_TBox_A_01"],
         7: ["FireTemple", "x", True, "", "Obj_TBox_A_01"]}
needs = {1: E([{"a", "b"}, {"c"}]), 2: frozenset({"a", "b", "z"}), 3: S.NONE, 4: frozenset({"w"}), 5: frozenset({"d", "e", "f"}), 6: frozenset({"g", "h", "i", "j"}), 7: None}
got = S.entrance_access(needs, spots, "FireTemple")
check(ways(got) == {frozenset("c"), frozenset("ab"), frozenset("def")}, "entrance_access: %r" % (ways(got),))
check(S.ENTRANCE_WAYS == 3 and ways(S.entrance_access(needs, spots, "WaterTemple")) == {frozenset("w")}, "entrance_access of a dungeon with one chest")
try:
    S.entrance_access(needs, spots, "ShadowTemple")
    check(False, "a door with no chest's rule is given a way")
except ValueError:
    pass

# the main part
src = (ROOT / "tools" / "rando" / "rando_seed.py").read_text(encoding="utf-8")
main = src[src.index("\ndef main():"):]
check('a.entrances = ini["rando_entrances"] if ini["rando_entrances"] in ENTRANCE_POOLS else 0' in main and '"rando_entrances": 0' in src, "the setting is not read")
check('(" entrances %d%s%s" % (a.entrances, " ageless" if a.entrances >= 2 and (a.ageless or 0) & 2 else "", " mixed %d" % ((a.ageless or 0) & 6) if a.entrance_mix and (a.ageless or 0) & 2 else "") if a.entrances else "")' in main,
      "the setting is not on the stamp, or Either age's items is not with the child's group")
check("for group in () if mixed else ENTRANCE_POOLS.get(a.entrances, ()):" in main and
      "group = entrance_child_pool(bool(door_rules), bool(a.open_forest), bool((a.ageless or 0) & 2))" in main and
      'behind.update(entrance_shuffle(seed, group, NOCTURNE in PROGRESSION, "" if group is ENTRANCE_ADULT else "-child"))' in main, "the shuffle's calls")
block = main[main.index("    for group in () if mixed else ENTRANCE_POOLS.get(a.entrances, ()):"):main.index("    # (the tokens are placed by the logic when a rule counts them")]
for line in ("door_access = {door: entrance_access(needs, spots, door) for door in behind}",
             'door_access["ShadowTemple"] = and_rules(door_access["ShadowTemple"], *(door_access[door_of[t]] for t in ENTRANCE_NOCTURNE_WAITS if t in door_of))',
             "doors = {door_of[d] for d in (area, ending_of_gift.get(h)) + tuple(waits.get(h, ())) if d in door_of}",
             "return fit_rule(and_rules(rule, *(door_access[d] for d in sorted(doors)))) if doors and rule is not None else rule",
             "needs = {h: behind_door(h, spots[h][0] if h in spots else None, n) for h, n in needs.items()}",
             "skull_asks = lambda h, at=None: behind_door(h, at or skulls[h][0], skull_fixed(h, at))",
             "heart_asks = lambda h: behind_door(h, lying[h][0], heart_fixed(h))"):
    check(line in block, "the rules' step lacks: %s" % line)
check(main.index("    for group in () if mixed else ENTRANCE_POOLS.get(a.entrances, ()):") < main.index("kept_tokens = [(skull_asks(h, every_skull[h][0]), TOKEN)") < main.index("gives, stays, spheres = place("),
      "the rules' step is not before the tokens kept and the placement")
check("if cap is not None and d in door_of:" in main and "caps[t] = cap | min(through if isinstance(through, Either) else (through,)" in main, "a moved dungeon's Boss Key's cap")
check('if os.environ.get("RANDO_TEST_ENTRANCES") or door_of:' in main and "entrance_files(behind," in main, "the files are not moved for the setting")
check('f.write("".join("%s|%s|%s|%s\\n" % (door, dungeon, AREA_NAMES.get(door, door), AREA_NAMES.get(dungeon, dungeon)) for door, dungeon in behind.items()))' in main and "written.append(ENTRANCES_FILE)" in main
      and "elif os.path.exists(doors_file):\n        os.remove(doors_file)" in main and 'spoiler = ["Dungeon entrances (a door -> the dungeon behind it)"]' in main,
      "ENTRANCES_FILE or the spoiler's lines")

header = (ROOT / "gpu" / "vk" / "oot_rando.h").read_text(encoding="utf-8")
launcher = (ROOT / "launcher" / "Launcher.cs").read_text(encoding="utf-8")
check('X(ENTRANCES, "Dungeon entrances", "rando_entrances",' in header and '"Off", "Adult dungeons", "Child dungeons", "Both") \\\n    X(ENTRANCES_MIX,' in header
      and header.index("X(ENTRANCES,") > header.index("X(KEYRINGS,"), "the menu's table: not there, or not last")
check('new object[] { "rando_entrances", "Dungeon entrances", new[] { "Off", "Adult dungeons", "Child dungeons", "Both" }, new[] { 0, 1, 2, 3 },' in launcher
      and launcher.index('new object[] { "rando_entrances"') > launcher.index('new object[] { "rando_keyrings"') and '"rando_dungeon_rewards", "rando_entrances", "rando_entrances_mix", "rando_boss_shuffle" } },' in launcher,
      "the launcher's table or section")

# the child's dungeons (2026-11-27 later): the Deku Tree, Dodongo's Cavern and the well, each only where the rules stay true.
# Seen in the game without a window, the setting on: a child through the Deku Tree's door into the Bottom of the Well, its
# first visit's scene played, and out again at the Deku Tree's clearing; through the well's door into the Deku Tree.
CHILD = S.ENTRANCE_CHILD
check(CHILD == ("InsideTheDekuTree", "DodongoCavern", "BottomOfTheWell") and not set(CHILD) & set(POOL) and set(CHILD) <= set(S.DUNGEON_DOORS), "the child's group")
pool = S.entrance_child_pool
check(pool(False, True, True) == () and pool(False, False, False) == (), "the child's dungeons move with the Door of Time shut (an adult is the three stones in the rules)")
check(pool(True, True, True) == CHILD, "all three with every setting")
check(pool(True, False, True) == ("DodongoCavern", "BottomOfTheWell"), "the Deku Tree moves with the forest shut (its way out is the Deku Tree done)")
check(pool(True, True, False) == ("InsideTheDekuTree", "BottomOfTheWell"), "Dodongo's Cavern moves without Either age's items (an adult's ways behind a child's door)")
check(pool(True, False, False) == (), "one dungeon alone is a pool")
kids = [S.entrance_shuffle(s, CHILD, True, "-child") for s in range(200)]
check(all(set(b) == set(b.values()) == set(CHILD) for b in kids) and len({(d, x) for b in kids for d, x in b.items()}) == 9, "the child's shuffle: not one-to-one, or a pair never comes")
check(all(S.entrance_shuffle(s, POOL) == S.entrance_shuffle(s, POOL, True, "") for s in range(20))
      and any(S.entrance_shuffle(s, POOL, True, "-child") != S.entrance_shuffle(s, POOL) for s in range(20)), "a group's stream does not keep the adult's change as it was")
check(S.entrance_shuffle(303, POOL) == {"ForestTemple": "WaterTemple", "FireTemple": "ShadowTemple", "IceCavern": "IceCavern", "WaterTemple": "GerudoTrainingGround",
                                         "ShadowTemple": "FireTemple", "GerudoTrainingGround": "ForestTemple"}, "the adult's change of seed 303 moved (seeds made before)")
check("for h, g in gifts.items():   # (the checks the story holds back until the Deku Tree is done: DEKU_STORY)" in block
      and 'waits[h] = tuple(waits.get(h, ())) + ("InsideTheDekuTree",)' in block, "the checks that wait for the Deku Tree are not told its door")
check("InsideJabuJabuBelly" not in CHILD + POOL and "SpiritTemple" not in CHILD + POOL, "Jabu-Jabu or the Spirit Temple is in a pool")

# the two groups mixed (rando_entrances_mix, 2026-11-27 later still): a dungeon behind a door is one that whoever gets through
# that door can finish. Seen in trial seeds (the Deku Tree's door to the Forest Temple, the Training Ground's to Dodongo's
# Cavern, the well's to the Deku Tree).
fits, A, C = S.entrance_fits, S.ENTRANCE_ADULT, S.ENTRANCE_CHILD
DEKU, DC, WELL = C
check(S.ENTRANCE_CHILD_DOORS == (DEKU, WELL) and S.ENTRANCE_TUNICS == ("FireTemple", "WaterTemple") and S.ENTRANCE_NO_CHILD == ("GerudoTrainingGround",), "the mixed groups' lists")
for d in A + C:
    check(fits(d, d) and fits(d, d, True), "%s may not stay behind its own door" % d)
for kid in (DEKU, WELL):       # (a child's to do, crawlspaces: a child's door or Dodongo's Cavern's, never an adult's)
    check(all(not fits(door, kid, True) for door in A) and fits(DC, kid) and fits(DEKU, kid) and fits(WELL, kid), "%s behind a door a child does not pass, or not behind one he does" % kid)
for door in (DEKU, WELL):      # (only a child gets through: an adult's dungeon there is his to do)
    check(not fits(door, "GerudoTrainingGround") and not fits(door, "GerudoTrainingGround", True), "the Training Ground behind %s (the Silver Gauntlets)" % door)
    check(not fits(door, "FireTemple") and not fits(door, "WaterTemple") and fits(door, "FireTemple", True) and fits(door, "WaterTemple", True), "the Fire or Water Temple behind %s: the tunics" % door)
    check(all(fits(door, x) for x in ("ForestTemple", "IceCavern", "ShadowTemple", DC)), "a dungeon a child can do is kept from %s" % door)
check(all(fits(DC, x) and fits(x, DC) for x in A), "Dodongo's Cavern and its door take either age")
check(all(fits(x, y) for x in A for y in A), "an adult's dungeon behind an adult's door")
# (the table: only the Training Ground asks for the Silver Gauntlets on every way of a check)
table = __import__("json").loads((ROOT / "tools" / "rando" / S.DUNGEON_RULES2_FILE).read_text(encoding="utf-8"))["by_actor"]
needs_silver = {v["folder"] for v in table.values() if v["folder"] in A and v["ways"] and all(w.get("Progressive Strength Upgrade", 0) >= 2 for w in v["ways"])}
check(needs_silver == set(S.ENTRANCE_NO_CHILD), "the adult's dungeons with a check that takes the Silver Gauntlets every way: %r" % needs_silver)
ALL = A + C
for tunics in (False, True):
    many = [S.entrance_mixed(s, ALL, tunics) for s in range(250)]
    check(all(set(b) == set(b.values()) == set(ALL) and all(fits(x, y, tunics) for x, y in b.items()) for b in many), "a mixed change that does not fit, or is not one-to-one")
    seen = {(x, y) for b in many for x, y in b.items()}
    check(seen == {(x, y) for x in ALL for y in ALL if fits(x, y, tunics)}, "over 250 seeds not every fitting pair came up (tunics %s): %d" % (tunics, len(seen)))
check(S.entrance_mixed(3, ALL) == S.entrance_mixed(3, ALL) and any(S.entrance_mixed(s, ALL) != S.entrance_mixed(3, ALL) for s in range(4, 9)), "the mixed change is not by the seed alone")
check(all(S.entrance_mixed(s, ALL, True, False)["ShadowTemple"] not in S.ENTRANCE_NOCTURNE_WAITS for s in range(120)), "mixed, without the Nocturne: a waited temple behind the Shadow Temple's door")
check(set(S.entrance_mixed(5, A + (DC, WELL))) == set(A + (DC, WELL)), "a mixed pool without the Deku Tree")
for line in ('a.entrance_mix = ini["rando_entrances_mix"] == 1 and ini["rando_entrances"] == 3',
             "mixed = a.entrance_mix and bool((a.ageless or 0) & 2)",
             "doors = ENTRANCE_ADULT + entrance_child_pool(bool(door_rules), bool(a.open_forest), True)",
             "behind = entrance_mixed(seed, doors, bool(a.ageless & 4), NOCTURNE in PROGRESSION)"):
    check(line in main, "the main part lacks: %s" % line)
check('"rando_entrances_mix": 0' in src, "the options' line is not known")
check('X(ENTRANCES_MIX, "Mix child and adult dungeons", "rando_entrances_mix",' in header and header.index("X(ENTRANCES_MIX,") > header.index("X(ENTRANCES,")
      and 'new object[] { "rando_entrances_mix", "Mix child and adult dungeons", new[] { "Off", "On" }, new[] { 0, 1 },' in launcher
      and launcher.index('new object[] { "rando_entrances_mix"') > launcher.index('new object[] { "rando_entrances",')
      and '"rando_entrances", "rando_entrances_mix", "rando_boss_shuffle" } },' in launcher, "the mix setting in the tables")

# the Tracker says the doors (gpu/vk/vk_menu.cpp, asked 2026-11-27), and each only once it is found (the owner, the same day:
# "only show what dungeon it leads to after you've entered it once already in the seed"): the game's side notes the door
# of the dungeon Link is in (host/hos_main.c oot_doors_note) and keeps the found ones for the seed; both compiled and run
import os
import subprocess
import tempfile
sys.path.insert(0, str(ROOT / "tests"))
import srccut  # noqa: E402
menu = (ROOT / "gpu" / "vk" / "vk_menu.cpp").read_text(encoding="utf-8")
parts = "\n".join(srccut.block(menu, start, "vk_menu.cpp") for start in (
    "void tracker_door_words(const char* area, char* one, char* two, size_t size) {",
    "void tracker_doors_load(const std::string& folder, bool on, const std::string& seen_path, const std::string& stamp) {"))
check('tracker_doors_load(path.substr(0, path.find_last_of("\\\\/") + 1), on, game_folder_path() + "rando\\\\doors_seen.txt", tracker_seed_stamp());' in menu,
      "the Tracker does not read the doors and the found ones with its lists")
panel = srccut.block(menu, "float tracker_panel(ui::Ctx& c, float x0, float x1, float y0, float y_max, int row, const char* hint) {", "vk_menu.cpp")
check("tracker_door_words(tracker_name[row], way_in, leads, sizeof way_in);" in panel and "for (const char* words : {way_in, leads, boss_from, boss_leads})" in panel
      and "const float fixed = 22 * s + 32 * s + doors + 12 * s" in panel, "an area's panel does not say its doors, or keeps no room for them")
for a in S.ENTRANCE_ADULT + S.ENTRANCE_CHILD:
    check(a in S.AREA_NAMES and len(S.AREA_NAMES[a]) < 48, "%s has no name on the Tracker" % a)
program = r"""
#include <cstdio>
#include <cstring>
#include <string>
constexpr int kDoorRows = 16;
char tracker_door_key[kDoorRows][48], tracker_door_from[kDoorRows][48], tracker_door_to[kDoorRows][48];
bool tracker_door_seen[kDoorRows];
int tracker_door_count = 0;
""" + parts + r"""
static bool says(const char* area, const char* one, const char* two) {
    char a[112], b[112];
    tracker_door_words(area, a, b, sizeof a);
    if (strcmp(a, one) || strcmp(b, two)) printf("%s: \"%s\" / \"%s\"\n", area, a, b);
    return !strcmp(a, one) && !strcmp(b, two);
}
int main(int argc, char** argv) {
    if (argc < 2) return 9;
    const std::string folder = argv[1], seen = folder + "doors_seen.txt";
    tracker_doors_load(folder, true, folder + "none.txt", "the stamp");                      // (nothing found yet)
    if (tracker_door_count != 3) return 1;
    for (const char* area : {"Shadow Temple", "Ice Cavern", "Water Temple"})                 // (one behind its own door as the others)
        if (!says(area, "Way in: not found yet", "Its own door: not entered yet")) return 2;
    if (!says("Kokiri Forest", "", "") || !says("Market", "", "")) return 3;                  // (no dungeon of the file)
    tracker_doors_load(folder, true, seen, "the stamp");                                     // (the Shadow Temple's door found, and the Water Temple's)
    if (!says("Ice Cavern", "Way in: the door of Shadow Temple", "Its own door: not entered yet")) return 4;
    if (!says("Shadow Temple", "Way in: not found yet", "Its own door leads to: Ice Cavern")) return 5;
    if (!says("Water Temple", "Way in: its own door", "")) return 6;
    tracker_doors_load(folder, true, seen, "another seed's stamp");                          // (another seed's record: not taken)
    if (!says("Ice Cavern", "Way in: not found yet", "Its own door: not entered yet")) return 7;
    tracker_doors_load(folder, true, seen, "");                                              // (no stamp: not taken)
    if (!says("Water Temple", "Way in: not found yet", "Its own door: not entered yet")) return 8;
    tracker_doors_load(folder, true, seen, "the st");                                        // (this side's stamp cut short: the record's starts with it)
    if (!says("Water Temple", "Way in: its own door", "")) return 10;
    tracker_doors_load(folder, false, seen, "the stamp");                                    // (the randomizer off: none)
    if (tracker_door_count || !says("Ice Cavern", "", "")) return 11;
    tracker_doors_load(folder + "nowhere/", true, seen, "the stamp");                        // (no file: none)
    return tracker_door_count ? 12 : 0;
}
"""
host = (ROOT / "host" / "hos_main.c").read_text(encoding="utf-8")
host_parts = "\n".join(srccut.block(host, start, "hos_main.c") for start in (
    "static void oot_doors_save(void) {", "static int oot_doors_note(const char *map) {", "static void oot_doors_load(const char *stamp) {"))
check("oot_doors_load(stamp);" in srccut.block(host, "static void oot_tracker_load(const char *stamp) {", "hos_main.c"), "the doors are not read with the seed's lists")
check("oot_doors_note(oot_link_map);" in host and host.index("memcpy(oot_link_map, map, sizeof oot_link_map);") < host.index("oot_doors_note(oot_link_map);"),
      "the door of the dungeon Link is in is not noted as his map is read")
host_program = r"""
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#define MAX_PATH 260
#define OOT_DOORS_MAX 16
static char root[400], oot_checks_seed[1024];
static struct { char door[24], dungeon[24]; int seen; } oot_doors[OOT_DOORS_MAX];
static int oot_door_n;
static int oot_game_file(char *out, size_t size, const char *tail) { snprintf(out, size, "%s%s", root, strrchr(tail, '/') + 1); return 1; }
static int oot_banc_in_folder(const char *banc, const char *folder) {   /* (a map is its folder, or its folder and "_...") */
    const size_t n = strlen(folder);
    return !strncmp(banc, folder, n) && (!banc[n] || banc[n] == '_');
}
static void hos_log(const char *f, ...) { (void)f; }
""" + host_parts + r"""
int main(int argc, char **argv) {
    if (argc < 2) return 9;
    snprintf(root, sizeof root, "%s", argv[1]);
    snprintf(oot_checks_seed, sizeof oot_checks_seed, "the stamp");
    oot_doors_load("the stamp");
    if (oot_door_n != 4 || oot_doors[0].seen || oot_doors[1].seen || oot_doors[2].seen) return 1;   /* (the file's lines, one of two fields too) */
    if (oot_doors_note("") || oot_doors_note("HyruleField_Adult") || oot_doors_note("ShadowTempleX")) return 2;   /* (no dungeon of a door) */
    if (!oot_doors_note("IceCavern") || !oot_doors[0].seen || oot_doors[1].seen) return 3;   /* (in the Ice Cavern: the Shadow Temple's door) */
    if (oot_doors_note("IceCavern")) return 4;                                               /* (once) */
    if (!oot_doors_note("WaterTemple") || !oot_doors[2].seen) return 5;                      /* (a door to its own dungeon is found as any) */
    oot_door_n = 0;
    oot_doors_load("the stamp");                                                              /* (the record kept) */
    if (oot_door_n != 4 || !oot_doors[0].seen || oot_doors[1].seen || !oot_doors[2].seen) return 6;
    oot_doors_load("another seed's stamp");                                                   /* (another seed's: not taken) */
    if (oot_doors[0].seen || oot_doors[2].seen) return 7;
    return 0;
}
"""
cc, cxx = "clang", "clang++"
for i, arg in enumerate(sys.argv):
    if arg == "--cxx" and i + 1 < len(sys.argv):
        cxx = sys.argv[i + 1]
    if arg == "--cc" and i + 1 < len(sys.argv):
        cc = sys.argv[i + 1]
DOORS = "ShadowTemple|IceCavern|Shadow Temple|Ice Cavern\nIceCavern|ShadowTemple|Ice Cavern|Shadow Temple\nWaterTemple|WaterTemple|Water Temple|Water Temple\nOld|Line\n"
with tempfile.TemporaryDirectory() as tmp:
    Path(tmp, "entrances.txt").write_text(DOORS, encoding="utf-8")
    c_file, c_exe = os.path.join(tmp, "host.c"), os.path.join(tmp, "host.exe")
    Path(c_file).write_text(host_program, encoding="utf-8")
    built = subprocess.run([cc, "-O1", "-Wall", "-Werror", "-o", c_exe, c_file], capture_output=True, text=True)
    check(built.returncode == 0, "the game's side's doors do not compile:\n%s" % built.stderr)
    ran = subprocess.run([c_exe, tmp + "/"], capture_output=True, text=True)
    check(ran.returncode == 0, "the game's side's doors: case %d" % ran.returncode)
    record = Path(tmp, "doors_seen.txt").read_text(encoding="utf-8")
    check(record == "seed the stamp\nShadowTemple\nWaterTemple\n", "the record of the doors found: %r" % record)
    src_file, exe = os.path.join(tmp, "doors.cpp"), os.path.join(tmp, "doors.exe")
    Path(src_file).write_text(program, encoding="utf-8")
    built = subprocess.run([cxx, "-std=c++17", "-O1", "-Wall", "-Werror", "-o", exe, src_file], capture_output=True, text=True)
    check(built.returncode == 0, "the Tracker's doors do not compile:\n%s" % built.stderr)
    ran = subprocess.run([exe, tmp + os.sep], capture_output=True, text=True)   # (the record the game's side just wrote)
    check(ran.returncode == 0, "the Tracker's doors: case %d %s" % (ran.returncode, ran.stdout))
print("ok: Dungeon entrances: the adult's and the child's dungeons, and the Tracker's doors, each once found")
