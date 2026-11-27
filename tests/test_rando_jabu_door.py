"""Jabu-Jabu among the doors (tools/rando/rando_seed.py JABU, placement 42; asked 2026-11-27). No game data.

His door is the one the game does not open by walking: a fish dropped before him has him swallow Link, a flow's step that
changes map to his belly by itself; after it his mouth is open and the door's actor leads in. The owner: "a possible fix
could have the cutscene skipped from the start, i think he behaves like a normal door then". Seen without a window: with
the flag JabJabOpenedMouth set and no fish, a child walks into his mouth; on a seed with the Deku Tree behind his door he
arrives in the Deku Tree, its first scene played, and by the Deku Tree's door in his belly, the belly's first scene
played; King Zora's seat is empty once the belly was entered so and his scene's flag is set (not with either alone).
Checked here:
- entrance_way_in: a door that leads to his belly plays the belly's first scene the first time (ENTRANCE_FIRST), a
  dungeon whose door has a first scene of its own keeps that one, and one with none gets none;
- jabu_swallow: the one map change to his belly leads to the dungeon behind his door: its map, start point, and its
  first scene (or its arrival, where it has no first scene); the flow's other steps as they were; a flow without that
  step, or with two, is refused;
- entrance_files with his dungeon moved: his door (the child's map alone) and his belly's way out are changed as any;
- the pool: his belly joins the child's when asked (a seed from JABU_DOOR_FROM), needs the Door of Time open as the
  others, and neither Open forest exit nor Either age's items; mixed, his belly is a child's to do (never behind an
  adult's door) and his door a child's alone (no Training Ground, the Fire and Water Temples with the tunics);
- the main part: a new game starts with his mouth open and King Zora's scene's flag set when another dungeon is behind
  his door, the swallow is led there, and seeds made before placement 42 keep their pool.

    python -I -B tests/test_rando_jabu_door.py
"""
import collections
import importlib.util
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "rando"))
spec = importlib.util.spec_from_file_location("rando_seed", ROOT / "tools" / "rando" / "rando_seed.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)
import evfl  # noqa: E402

OD = collections.OrderedDict
JABU, DEKU, DC, WELL = S.JABU, "InsideTheDekuTree", "DodongoCavern", "BottomOfTheWell"


def check(ok, why):
    if not ok:
        print("FAIL: %s" % why)
        sys.exit(1)


def refused(what, *args):
    try:
        what(*args)
    except ValueError:
        return True
    return False


def string(v):
    return ("string", v)


def door(name, **fields):
    return ("dict", OD([("Dynamic", ("dict", OD(sorted((k, string(v)) for k, v in fields.items())))), ("Gyaml", string(S.ENTRANCE_ACTOR)), ("Name", string(name))]))


def map_file(*actors):
    return S.byml_build(("dict", OD([("Actors", ("array", list(actors)))])), 7)


def all_fields(data, name):
    for a in S.byml_parse(data)[0][1]["Actors"][1]:
        if a[1]["Name"][1] == name:
            return {k: v[1] for k, v in a[1]["Dynamic"][1].items()}


game = {}
for d, (stems, name, out) in S.DUNGEON_DOORS.items():
    extra = {"InitEventName": d + "_First", "InitEventFlag": "HavePlayedEvent." + d} if d == DEKU else {}
    for stem in stems:
        game[S.entrance_file(stem)] = map_file(door(name, FirstEventName="Go_" + stem.split("/")[1], NextBancParamNameAdult=d, NextBancParamNameChild=d,
                                                    NextStartPosName=out, NextEventName="Arrive_" + d, **extra))
    area = stems[0].rsplit("_", 1)[0].split("/")[1]
    game[S.entrance_out_file(d)] = map_file(door(out, FirstEventName="Leave_" + d, NextBancParamNameAdult=area + "_Adult", NextBancParamNameChild=area + "_Child",
                                                 NextStartPosName=name, NextEventName="Arrive_" + area))
read = game.__getitem__

# entrance_way_in
way = {k: v[1] for k, v in S.entrance_way_in(JABU, read).items()}
check(way["InitEventName"] == "Get_StoneOfWater_ArriveJabuJabuBelly" and way["InitEventFlag"] == "HavePlayedEvent.Dm_InsideJabu_Jabu_0000"
      and way["NextBancParamNameChild"] == JABU and way["NextEventName"] == "Arrive_" + JABU, "the way into his belly: %r" % way)
way = {k: v[1] for k, v in S.entrance_way_in(DEKU, read).items()}
check(way["InitEventName"] == DEKU + "_First", "the Deku Tree's own first scene is not kept")
check("InitEventName" not in S.entrance_way_in(WELL, read), "a dungeon with no first scene is given one")
check(S.ENTRANCE_FIRST == {JABU: ("Get_StoneOfWater_ArriveJabuJabuBelly", "HavePlayedEvent.Dm_InsideJabu_Jabu_0000")}, "the first scenes played another way")


# jabu_swallow
def quest_flow(changes=1):
    flow = evfl.EventFlow()
    flow.name = "Get_StoneOfWater"
    fc = evfl.Flowchart()
    fc.name = "Get_StoneOfWater"
    system = evfl.Actor()
    system.identifier = evfl.ActorIdentifier("GameSystemActor")
    system.params = evfl.Container()
    change = evfl.common.StringHolder("EventReserveBancChange")
    system.actions.append(change)
    events = []
    for n, banc in enumerate([JABU] * changes + ["ZoraFountain_Child"]):
        e = evfl.Event()
        e.name = "Event%d" % n
        e.data = evfl.ActionEvent()
        e.data.actor.v, e.data.actor_action.v = system, change
        e.data.params = evfl.Container()
        e.data.params.data.update(NextBanc=banc, NextStartPos="Start_" + banc, BootEventName="Boot_" + banc, FadePattern=1)
        events.append(e)
    entry = evfl.EntryPoint("StoneOfWater_JabuJabuEat")
    entry.main_event.v = events[0]
    fc.actors, fc.events, fc.entry_points = [system], events, [entry]
    flow.flowchart = fc
    out = io.BytesIO()
    flow.write(out)
    return out.getvalue()


def changes(raw):
    f = evfl.EventFlow()
    f.read(raw)
    return [dict(e.data.params.data) for e in f.flowchart.events]


new = changes(S.jabu_swallow(quest_flow(), S.entrance_way_in(DEKU, read)))
check(new[0] == {"NextBanc": DEKU, "NextStartPos": "Entrance", "BootEventName": DEKU + "_First", "FadePattern": 1}, "the swallow led to the Deku Tree: %r" % new[0])
check(new[1] == {"NextBanc": "ZoraFountain_Child", "NextStartPos": "Start_ZoraFountain_Child", "BootEventName": "Boot_ZoraFountain_Child", "FadePattern": 1}, "another map change of the flow changed")
new = changes(S.jabu_swallow(quest_flow(), S.entrance_way_in(WELL, read)))
check(new[0]["NextBanc"] == WELL and new[0]["BootEventName"] == "Arrive_" + WELL and new[0]["NextStartPos"] == S.DUNGEON_DOORS[WELL][2], "the swallow led to the well: %r" % new[0])
check(refused(S.jabu_swallow, quest_flow(0), S.entrance_way_in(DEKU, read)) and refused(S.jabu_swallow, quest_flow(2), S.entrance_way_in(DEKU, read)),
      "a flow without the step, or with two, is taken")

# entrance_files
files = S.entrance_files({JABU: DEKU, DEKU: JABU}, read)
want = {S.entrance_file("ZoraFountain/ZoraFountain_Child"), S.entrance_out_file(JABU), S.entrance_out_file(DEKU)} | {S.entrance_file(s) for s in S.DUNGEON_DOORS[DEKU][0]}
check(set(files) == want, "the files with his dungeon moved: %r" % sorted(set(files) ^ want))
f = all_fields(files[S.entrance_file("ZoraFountain/ZoraFountain_Child")], "ZoraFountain_FromInsideJabuJabuBelly")
check(f["NextBancParamNameChild"] == DEKU and f["InitEventName"] == DEKU + "_First", "his door: %r" % f)
f = all_fields(files[S.entrance_file("KokiriForest/KokiriForest_Child")], "FrontDekuTree")
check(f["NextBancParamNameChild"] == JABU and f["InitEventName"] == "Get_StoneOfWater_ArriveJabuJabuBelly" and f["InitEventFlag"] == "HavePlayedEvent.Dm_InsideJabu_Jabu_0000",
      "the Deku Tree's door to his belly does not play the belly's first scene: %r" % f)
f = all_fields(files[S.entrance_out_file(JABU)], "InsideJabuJabuBelly_FromZoraFountain")
check(f["NextBancParamNameChild"] == "KokiriForest_Child" and f["NextStartPosName"] == "FrontDekuTree", "his belly's way out: %r" % f)

# the pool
pool = S.entrance_child_pool
check(pool(True, True, True, True) == (DEKU, DC, WELL, JABU) and pool(True, False, False, True) == (WELL, JABU) and pool(False, True, True, True) == (), "the child's pool with his belly")
check(pool(True, True, True) == S.ENTRANCE_CHILD == (DEKU, DC, WELL), "the pool of seeds made before (no Jabu-Jabu)")
fits = S.entrance_fits
check(all(not fits(door_, JABU, True) for door_ in S.ENTRANCE_ADULT) and all(fits(door_, JABU) for door_ in (DEKU, DC, WELL)), "his belly behind an adult's door, or not behind a child's")
check(not fits(JABU, "GerudoTrainingGround", True) and not fits(JABU, "FireTemple") and fits(JABU, "FireTemple", True) and fits(JABU, "ForestTemple") and fits(JABU, DC),
      "what may be behind his door")
many = [S.entrance_shuffle(s, pool(True, True, True, True), True, "-child") for s in range(300)]
check(len({(a, b) for m in many for a, b in m.items()}) == 16, "over 300 seeds not every pair of the four came up")

# the main part
src = (ROOT / "tools" / "rando" / "rando_seed.py").read_text(encoding="utf-8")
main = src[src.index("\ndef main():"):]
for line in ("with_jabu = placement >= JABU_DOOR_FROM",
             'if JABU in door_of.values() or JABU + "=" in os.environ.get("RANDO_TEST_ENTRANCES", "").replace(JABU + "=" + JABU, ""):',
             "more = flag_defaults(new if new is not None else was, JABU_MOUTH)",
             "if behind.get(JABU, JABU) != JABU:",
             "files[JABU_FLOW] = jabu_swallow(was, entrance_way_in(behind[JABU],"):
    check(line in main, "the main part lacks: %s" % line)
check(S.JABU_MOUTH == {"JabJabOpenedMouth": True, "HavePlayedEvent.Dm_Zora_0010": True}, "the flags a new game starts with")
check(S.PLACEMENT >= S.JABU_DOOR_FROM == 42 and "king_away" not in src.replace("(tried and taken out)", ""), "the placement, or the map change that did nothing is back")
print("ok: Jabu-Jabu among the doors")
