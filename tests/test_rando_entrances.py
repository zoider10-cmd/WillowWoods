"""Dungeon entrances led elsewhere, the Dungeon Entrance Randomizer's first step (tools/rando/rando_seed.py
entrance_files, asked 2026-11-27; share/design-entrance-boss-shuffle-research.md). No game data: map files made here.

A door between the overworld and a dungeon is an actor of its map's _Static file whose Dynamic says where it leads.
"Dungeon B behind door A": A's doors (one in each age's map that has one) say what B's door said, and B's way out says
what A's way out said. Seen in the game without a window, 2026-11-27: the Deku Tree's door leading to Dodongo's Cavern
and to the Forest Temple, a child and an adult, in and back out to the Deku Tree's clearing. Checked here:
- entrance_dest reads a door's destination fields and no other; entrance_point gives a door another's, takes away the ones the
  other has not (a first visit's scene), keeps the door's own leaving event and the file's other actors, and the keys
  stay in order;
- entrance_files for a swap of two dungeons: every map file of each door is changed, each door leads to the other
  dungeon with that dungeon's arrival event and first scene, each dungeon's way out leads to the other's door in both
  ages' maps; a dungeon left where it is changes no file; doing it and undoing it gives the first files' fields back;
- a three-way change, and a door that is in one age's map only;
- refused: a change that is not one-to-one, a dungeon without a door in the table (Ganon's Castle), a door not found;
- the table: eleven dungeons, each of DUNGEON_FOLDERS but Ganon's Castle;
- the main part: a test's switch (RANDO_TEST_ENTRANCES) beside the setting (tests/test_rando_entrance_setting.py), its files in the size table.

    python -I -B tests/test_rando_entrances.py
"""
import collections
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("rando_seed", ROOT / "tools" / "rando" / "rando_seed.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)
OD = collections.OrderedDict


def check(ok, why):
    if not ok:
        print("FAIL: %s" % why)
        sys.exit(1)


def string(v):
    return ("string", v)


def door(name, **fields):
    dyn = OD(sorted((k, string(v)) for k, v in fields.items()))
    return ("dict", OD([("Dynamic", ("dict", dyn)), ("Gyaml", string(S.ENTRANCE_ACTOR)), ("Name", string(name))]))


def map_file(*actors):
    other = ("dict", OD([("Gyaml", string("Obj_Tree")), ("Name", string("Tree"))]))
    return S.byml_build(("dict", OD([("Actors", ("array", [other] + list(actors)))])), 7)


def fields(data, name):
    return {k: v[1] for k, v in S.entrance_dest(data, name).items()}


def all_fields(data, name):
    tree = S.byml_parse(data)[0]
    for a in tree[1]["Actors"][1]:
        if a[1]["Name"][1] == name:
            return [(k, v[1]) for k, v in a[1]["Dynamic"][1].items()]


def world():
    """the game's doors in small: every dungeon of the table, its door in each of its maps and its way out"""
    files = {}
    for d, (stems, name, out) in S.DUNGEON_DOORS.items():
        for stem in stems:
            extra = {"InitEventName": d + "_First", "InitEventFlag": "HavePlayedEvent." + d} if d in ("InsideTheDekuTree", "ForestTemple") else {}
            files[S.entrance_file(stem)] = map_file(door(name, FirstEventName="Go_" + stem.split("/")[1], NextBancParamNameAdult=d, NextBancParamNameChild=d,
                                                     NextStartPosName=out, NextEventName="Arrive_" + d, **extra),
                                                door("Elsewhere", FirstEventName="Go", NextBancParamNameAdult="LostWood_Adult", NextBancParamNameChild="LostWood_Child",
                                                     NextStartPosName="LostWood_Entrance", NextEventName="Arrive"))
        area = stems[0].rsplit("_", 1)[0].split("/")[1] if d != "BottomOfTheWell" else "KakarikoVillage"
        files[S.entrance_out_file(d)] = map_file(door(out, FirstEventName="Leave_" + d, NextBancParamNameAdult=area + "_Adult", NextBancParamNameChild=area + "_Child",
                                                  NextStartPosName=name, NextEventName="Arrive_" + area))
    return files


game = world()
read = lambda rel: game[rel]
DEKU, FOREST, ICE, JABU = "InsideTheDekuTree", "ForestTemple", "IceCavern", "InsideJabuJabuBelly"

# entrance_dest and entrance_point
one = game[S.entrance_file("KokiriForest/KokiriForest_Child")]
check(fields(one, "FrontDekuTree") == {"NextBancParamNameAdult": DEKU, "NextBancParamNameChild": DEKU, "NextStartPosName": "Entrance", "NextEventName": "Arrive_" + DEKU,
                                       "InitEventName": DEKU + "_First", "InitEventFlag": "HavePlayedEvent." + DEKU}, "entrance_dest: %r" % fields(one, "FrontDekuTree"))
dodongo = S.entrance_dest(game[S.entrance_file("DeathMountainTrail/DeathMountainTrail_Child")], "MountainTrail_DodongoCavernSide")
now = S.entrance_point(one, "FrontDekuTree", dodongo)
got = all_fields(now, "FrontDekuTree")
check(dict(got) == {"FirstEventName": "Go_KokiriForest_Child", "NextBancParamNameAdult": "DodongoCavern", "NextBancParamNameChild": "DodongoCavern",
                    "NextStartPosName": "DodongoCavern_MountainTrailSide", "NextEventName": "Arrive_DodongoCavern"}, "entrance_point: %r" % got)
check([k for k, _ in got] == sorted(k for k, _ in got), "entrance_point leaves the keys out of order")
check(fields(now, "Elsewhere") == fields(one, "Elsewhere") and len(S.byml_parse(now)[0][1]["Actors"][1]) == 3, "entrance_point touched another actor")
for bad in ("NoSuchDoor", "Tree"):
    try:
        S.entrance_dest(one, bad)
        check(False, "a door that is not there is read")
    except ValueError:
        pass

# a swap of two
files = S.entrance_files({DEKU: FOREST, FOREST: DEKU}, read)
want = {S.entrance_file(s) for d in (DEKU, FOREST) for s in S.DUNGEON_DOORS[d][0]} | {S.entrance_out_file(DEKU), S.entrance_out_file(FOREST)}
check(set(files) == want, "the files of a swap: %r" % sorted(set(files) ^ want))
for stem in S.DUNGEON_DOORS[DEKU][0]:
    f = dict(all_fields(files[S.entrance_file(stem)], "FrontDekuTree"))
    check(f["NextBancParamNameChild"] == f["NextBancParamNameAdult"] == FOREST and f["NextStartPosName"] == "ForestTemple" and f["NextEventName"] == "Arrive_" + FOREST
          and f["InitEventName"] == FOREST + "_First" and f["InitEventFlag"] == "HavePlayedEvent." + FOREST and f["FirstEventName"] == "Go_" + stem.split("/")[1],
          "the Deku Tree's door in %s: %r" % (stem, f))
f = dict(all_fields(files[S.entrance_out_file(FOREST)], "ForestTemple"))
check(f["NextBancParamNameAdult"] == "KokiriForest_Adult" and f["NextBancParamNameChild"] == "KokiriForest_Child" and f["NextStartPosName"] == "FrontDekuTree"
      and f["NextEventName"] == "Arrive_KokiriForest" and f["FirstEventName"] == "Leave_" + FOREST, "the Forest Temple's way out: %r" % f)
f = dict(all_fields(files[S.entrance_out_file(DEKU)], "Entrance"))
check(f["NextBancParamNameChild"] == "SacredForestMeadow_Child" and f["NextStartPosName"] == "OutsideOfForestTemple", "the Deku Tree's way out: %r" % f)
back = S.entrance_files({DEKU: FOREST, FOREST: DEKU}, lambda rel: files.get(rel, game[rel]))
for rel in want:
    for name in ("FrontDekuTree", "OutsideOfForestTemple", "Entrance", "ForestTemple"):
        try:
            check(all_fields(back[rel], name) == all_fields(game[rel], name), "a swap done twice is not the game's again: %s %s" % (rel, name))
        except ValueError:
            pass
check(S.entrance_files({DEKU: DEKU, FOREST: FOREST}, read) == {}, "a dungeon left where it is changes a file")

# three ways round, one of them a door in one age's map only
files = S.entrance_files({DEKU: ICE, ICE: JABU, JABU: DEKU}, read)
check(dict(all_fields(files[S.entrance_file("ZoraFountain/ZoraFountain_Adult")], "ZoraFountain_FromIceCavern"))["NextBancParamNameAdult"] == JABU, "the Ice Cavern's door")
check(dict(all_fields(files[S.entrance_file("ZoraFountain/ZoraFountain_Child")], "ZoraFountain_FromInsideJabuJabuBelly"))["NextBancParamNameChild"] == DEKU, "Jabu-Jabu's door")
check(dict(all_fields(files[S.entrance_out_file(JABU)], "InsideJabuJabuBelly_FromZoraFountain"))["NextStartPosName"] == "ZoraFountain_FromIceCavern", "Jabu-Jabu's way out")
check(dict(all_fields(files[S.entrance_out_file(ICE)], "IceCavern_FromZoraFountain"))["NextStartPosName"] == "FrontDekuTree", "the Ice Cavern's way out")

for bad in ({DEKU: FOREST}, {DEKU: FOREST, FOREST: FOREST}, {DEKU: "InsideGanonCastle", "InsideGanonCastle": DEKU}):
    try:
        S.entrance_files(bad, read)
        check(False, "a change that cannot be is made: %r" % bad)
    except ValueError:
        pass

check(set(S.DUNGEON_DOORS) == set(S.DUNGEON_FOLDERS) - {"InsideGanonCastle"} and len(S.DUNGEON_DOORS) == 11, "the doors' table")
src = (ROOT / "tools" / "rando" / "rando_seed.py").read_text(encoding="utf-8")
main = src[src.index("\ndef main():"):]
check('if os.environ.get("RANDO_TEST_ENTRANCES") or door_of:' in main and "behind = dict(pair.split(\"=\") for pair in os.environ[\"RANDO_TEST_ENTRANCES\"].split(\",\"))" in main
      and "sizes[rel[:-3]] = len(data)" in main and S.DOOR_ACTOR == "Obj_TimeTemple_Door_A_01",
      "the main part: no test's switch, its files are not in the size table, or the Door of Time's actor's name is taken")
print("ok: dungeon entrances led elsewhere (the files)")
