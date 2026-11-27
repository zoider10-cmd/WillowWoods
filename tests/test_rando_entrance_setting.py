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
check('(" entrances %d%s" % (a.entrances, " ageless" if a.entrances >= 2 and (a.ageless or 0) & 2 else "") if a.entrances else "")' in main,
      "the setting is not on the stamp, or Either age's items is not with the child's group")
check("for group in ENTRANCE_POOLS.get(a.entrances, ()):" in main and
      "group = entrance_child_pool(bool(door_rules), bool(a.open_forest), bool((a.ageless or 0) & 2))" in main and
      'behind.update(entrance_shuffle(seed, group, NOCTURNE in PROGRESSION, "" if group is ENTRANCE_ADULT else "-child"))' in main, "the shuffle's calls")
block = main[main.index("    for group in ENTRANCE_POOLS.get(a.entrances, ()):"):main.index("    # (the tokens are placed by the logic when a rule counts them")]
for line in ("door_access = {door: entrance_access(needs, spots, door) for door in behind}",
             'door_access["ShadowTemple"] = and_rules(door_access["ShadowTemple"], *(door_access[door_of[t]] for t in ENTRANCE_NOCTURNE_WAITS if t in door_of))',
             "doors = {door_of[d] for d in (area, ending_of_gift.get(h)) + tuple(waits.get(h, ())) if d in door_of}",
             "return fit_rule(and_rules(rule, *(door_access[d] for d in sorted(doors)))) if doors and rule is not None else rule",
             "needs = {h: behind_door(h, spots[h][0] if h in spots else None, n) for h, n in needs.items()}",
             "skull_asks = lambda h, at=None: behind_door(h, at or skulls[h][0], skull_fixed(h, at))",
             "heart_asks = lambda h: behind_door(h, lying[h][0], heart_fixed(h))"):
    check(line in block, "the rules' step lacks: %s" % line)
check(main.index("    for group in ENTRANCE_POOLS.get(a.entrances, ()):") < main.index("kept_tokens = [(skull_asks(h, every_skull[h][0]), TOKEN)") < main.index("gives, stays, spheres = place("),
      "the rules' step is not before the tokens kept and the placement")
check("if cap is not None and d in door_of:" in main and "caps[t] = cap | min(through if isinstance(through, Either) else (through,)" in main, "a moved dungeon's Boss Key's cap")
check('if os.environ.get("RANDO_TEST_ENTRANCES") or door_of:' in main and "entrance_files(behind," in main, "the files are not moved for the setting")
check('f.write("".join("%s|%s\\n" % kv for kv in behind.items()))' in main and "written.append(ENTRANCES_FILE)" in main
      and "elif os.path.exists(doors_file):\n        os.remove(doors_file)" in main and 'spoiler = ["Dungeon entrances (a door -> the dungeon behind it)"]' in main,
      "ENTRANCES_FILE or the spoiler's lines")

header = (ROOT / "gpu" / "vk" / "oot_rando.h").read_text(encoding="utf-8")
launcher = (ROOT / "launcher" / "Launcher.cs").read_text(encoding="utf-8")
check('X(ENTRANCES, "Dungeon entrances", "rando_entrances",' in header and '"Off", "Adult dungeons", "Child dungeons", "Both")\n\nenum {' in header
      and header.index("X(ENTRANCES,") > header.index("X(KEYRINGS,"), "the menu's table: not there, or not last")
check('new object[] { "rando_entrances", "Dungeon entrances", new[] { "Off", "Adult dungeons", "Child dungeons", "Both" }, new[] { 0, 1, 2, 3 },' in launcher
      and launcher.index('new object[] { "rando_entrances"') > launcher.index('new object[] { "rando_keyrings"') and '"rando_dungeon_rewards", "rando_entrances" } },' in launcher,
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
print("ok: Dungeon entrances: the adult's and the child's dungeons")
