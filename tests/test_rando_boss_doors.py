"""Boss Shuffle's files: a boss's room led to another boss's fight (tools/rando/rando_seed.py boss_files, asked
2026-11-27; share/design-entrance-boss-shuffle-research.md B). No game data: a flow, tables and map files made here.

A boss's fight is started by one request of its dungeon's map. "Boss X behind boss Y's door": Y's request asks for an
event of our own, whose flow asks a flag: put out (Link walked in), the flag is set and the map changed to X's dungeon at
the start point in X's room, booting X's fight; set (he was just sent here), it is put out and nothing more. Seen in the
game without a window: a child put in Gohma's room is in King Dodongo's, his scene played and the fight on, and stays;
without the flag the room he arrived in sent him on again. Checked here:
- boss_room_request: the one request of a dungeon's fight asks for our event, the map's other actors and requests as they
  were; a map without it, or with two, is refused;
- boss_door_flow: an entry for each door, named as the request asks; it asks the flag, the case of a flag put out sets it
  and changes map to the boss's dungeon, its start point and its fight's event, the case of a flag set puts it out and
  ends; the Fire and Water Temples' entry scenes' flags are set on the way to their bosses, and no other's; the flow has
  our name and no entry of the rematches';
- boss_event_rows: a row for each door in both tables, copied from a rematch's, the settings' naming our flow and entry,
  the analyzed one's with no sub flows; the game's rows kept, in order; done twice: refused;
- boss_files: a door that keeps its boss is left out of every file; nothing moved: no files; a change that is not
  one-to-one, or names a dungeon without a room to lead to (Jabu-Jabu, the Spirit Temple), is refused;
- the table of rooms agrees with the game's side's (host/hos_main.c oot_boss_rooms: the same events, and the flags of the
  two entry scenes by their hashes).

    python -I -B tests/test_rando_boss_doors.py
"""
import collections
import importlib.util
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "rando"))
spec = importlib.util.spec_from_file_location("rando_seed", ROOT / "tools" / "rando" / "rando_seed.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)
import evfl  # noqa: E402

OD = collections.OrderedDict


def check(ok, why):
    if not ok:
        print("FAIL: %s" % why)
        sys.exit(1)


def string(v):
    return ("string", v)


def refused(what, *args):
    try:
        what(*args)
    except ValueError:
        return True
    return False


# ---- a map file with a boss's request, another request and another actor ----
def map_file(*requests):
    actors = [("dict", OD([("Gyaml", string("Obj_WarpPoint_A_01")), ("Name", string("Warp"))]))]
    for event in requests:
        actors.append(("dict", OD([("Dynamic", ("dict", OD([("RequestEventName", string(event))]))), ("Gyaml", string(S.BOSS_REQUEST))])))
    return S.byml_build(("dict", OD([("Actors", ("array", actors))])), 7)


def requests(data):
    return [a[1]["Dynamic"][1]["RequestEventName"][1] for a in S.byml_parse(data)[0][1]["Actors"][1] if "Dynamic" in a[1]]


DEKU, DC, FOREST, FIRE, WATER, SHADOW = "InsideTheDekuTree", "DodongoCavern", "ForestTemple", "FireTemple", "WaterTemple", "ShadowTemple"
check(list(S.BOSS_ROOMS) == [DEKU, DC, FOREST, FIRE, WATER, SHADOW], "the bosses with a room to lead to: %r" % list(S.BOSS_ROOMS))
one = map_file(S.BOSS_ROOMS[DC][0], "Get_StoneOfFire_EscapeDungeon")
now = S.boss_room_request(one, DC)
check(requests(now) == [S.boss_door_event(DC), "Get_StoneOfFire_EscapeDungeon"] and len(S.byml_parse(now)[0][1]["Actors"][1]) == 3, "boss_room_request: %r" % requests(now))
check(S.boss_door_event(DC) == "WillowBossDoor_DodongoCavern", "our event's name")
check(refused(S.boss_room_request, map_file("Another"), DC) and refused(S.boss_room_request, map_file(S.BOSS_ROOMS[DC][0], S.BOSS_ROOMS[DC][0]), DC)
      and refused(S.boss_room_request, now, DC), "a map without the request, with two, or done already is taken")


# ---- the rematches' flow in small: a map change of the GameSystemActor, a GameDataActor that asks a flag ----
def rematch_flow():
    flow = evfl.EventFlow()
    flow.name = "DreamBossStage"
    fc = evfl.Flowchart()
    fc.name = "DreamBossStage"
    system, data = evfl.Actor(), evfl.Actor()
    system.identifier, data.identifier = evfl.ActorIdentifier("GameSystemActor"), evfl.ActorIdentifier("GameDataActor")
    for a in (system, data):
        a.params = evfl.Container()
        a.params.data.update(EventMemberCreateMethod=0)
    change, ask = evfl.common.StringHolder("EventReserveBancChange"), evfl.common.StringHolder("EventQueryIsGameDataBool")
    system.actions.append(change)
    data.queries.append(ask)
    go = evfl.Event()
    go.name = "Event444"
    go.data = evfl.ActionEvent()
    go.data.actor.v, go.data.actor_action.v = system, change
    go.data.params = evfl.Container()
    go.data.params.data.update(IsWaitEnd=True, IsStartOnEvent=False, EventStarterName="", FadePattern=1, NextBanc="GohmaStage", NextStartPos="GohmaStage",
                               BootEventName="DreamBossStage_Rematch_Gohma_Start", IsItemWarp=False)
    entry = evfl.EntryPoint("Rematch_Gohma")
    entry.main_event.v = go
    fc.actors, fc.events, fc.entry_points = [system, data], [go], [entry]
    flow.flowchart = fc
    out = io.BytesIO()
    flow.write(out)
    return out.getvalue()


FLAG = "IsGet.Some_Actor_Never_Got"
fights = {DEKU: DC, DC: FIRE, FIRE: WATER, WATER: DEKU}
raw = S.boss_door_flow(rematch_flow(), fights, FLAG)
made = evfl.EventFlow()
made.read(raw)
fc = made.flowchart
check(made.name == fc.name == S.BOSS_DOOR_NAME == "WillowBossDoor", "the flow's name")
check(sorted(e.name for e in fc.entry_points) == sorted(S.boss_door_event(d) for d in fights), "the flow's entries: %r" % [e.name for e in fc.entry_points])
check(S.BOSS_FLAG_OUT == 1 and S.BOSS_FLAG_SET == 0, "the flag query's cases, as seen in the game")


def chain(event):
    out = []
    while event is not None:
        d = event.data
        out.append((str(d.actor_action.v), dict(d.params.data)))
        event = d.nxt.v
    return out


for entry in fc.entry_points:
    door = entry.name[len(S.BOSS_DOOR_NAME) + 1:]
    boss = fights[door]
    fight, start, seen = S.BOSS_ROOMS[boss]
    ask = entry.main_event.v.data
    check(isinstance(ask, evfl.SwitchEvent) and str(ask.actor_query.v) == "EventQueryIsGameDataBool" and ask.actor.v.identifier.name == "GameDataActor"
          and dict(ask.params.data) == {"GameDataName": FLAG, "Index": -1} and set(ask.cases) == {0, 1}, "%s does not ask the flag first" % entry.name)
    sent, here = chain(ask.cases[S.BOSS_FLAG_OUT].v), chain(ask.cases[S.BOSS_FLAG_SET].v)
    check(here == [("EventTriggerSetGameDataBool", {"Value": False, "Index": -1, "GameDataName": FLAG})], "%s: just sent here, the flag is not put out and no more: %r" % (entry.name, here))
    check(sent[0] == ("EventTriggerSetGameDataBool", {"Value": True, "Index": -1, "GameDataName": FLAG}), "%s: walked in, the flag is not set first: %r" % (entry.name, sent))
    change = sent[-1]
    check(change[0] == "EventReserveBancChange" and change[1]["NextBanc"] == boss and change[1]["NextStartPos"] == start and change[1]["BootEventName"] == fight
          and change[1]["FadePattern"] == 1 and change[1]["IsItemWarp"] is False, "%s: the map change: %r" % (entry.name, change))
    between = sent[1:-1]
    want = [("EventTriggerSetGameDataBool", {"Value": True, "Index": -1, "GameDataName": seen})] if seen else []
    check(between == want, "%s: the entry scene's flag on the way to %s: %r" % (entry.name, boss, between))
check({boss for boss, room in S.BOSS_ROOMS.items() if room[2]} == {FIRE, WATER}, "the dungeons whose entry scene's flag is set")
bare = evfl.EventFlow()
bare.read(raw)
bare.flowchart.events = [e for e in bare.flowchart.events if not isinstance(e.data, evfl.ActionEvent) or str(e.data.actor_action.v) != "EventReserveBancChange"]
for e in bare.flowchart.events:
    if isinstance(e.data, evfl.ActionEvent):
        e.data.nxt.v = None
plain = io.BytesIO()
bare.write(plain)
check(refused(S.boss_door_flow, plain.getvalue(), fights, FLAG), "a flow with no map change to copy is taken")


# ---- the event tables ----
def table(analyzed):
    def row(name, flow, entry):
        if analyzed:
            return ("dict", OD([("SubFlowList", ("array", [string("Npc_Dream")])), ("__RowId", string(name))]))
        return ("dict", OD([("EntryPointName", string(entry)), ("EventBaseSetting", string("StarterPos")), ("FlowchartFileName", string("Work/Event/EventFlow/%s.evfc" % flow)),
                            ("__RowId", string(name))]))
    return S.byml_build(("array", [row("Aaa_First", "Aaa", "First"), row(S.BOSS_DOOR_TEMPLATE, "DreamBossStage", "Rematch_Gohma"), row("Zzz_Last", "Zzz", "Last")]), 7)


for analyzed in (False, True):
    new = S.boss_event_rows(table(analyzed), analyzed, fights)
    rows = [r[1] for r in S.byml_parse(new)[0][1]]
    names = [r["__RowId"][1] for r in rows]
    check(names == sorted(names) and len(names) == 3 + len(fights) and {"Aaa_First", S.BOSS_DOOR_TEMPLATE, "Zzz_Last"} <= set(names), "the table's rows: %r" % names)
    for door in fights:
        r = next(r for r in rows if r["__RowId"][1] == S.boss_door_event(door))
        if analyzed:
            check(r["SubFlowList"] == ("array", []), "the analyzed row of %s keeps the rematch's sub flows" % door)
        else:
            check(r["FlowchartFileName"][1] == "Work/Event/EventFlow/WillowBossDoor.evfc" and r["EntryPointName"][1] == S.boss_door_event(door)
                  and r["EventBaseSetting"][1] == "StarterPos", "the settings' row of %s: %r" % (door, r))
    check(refused(S.boss_event_rows, new, analyzed, fights), "rows added twice")
    check(refused(S.boss_event_rows, S.byml_build(("array", []), 7), analyzed, fights), "a table without the rematch's row is taken")

# ---- boss_files ----
game = {S.entrance_out_file(d): map_file(S.BOSS_ROOMS[d][0], "Other_" + d) for d in S.BOSS_ROOMS}
game[S.BOSS_DOOR_FROM] = rematch_flow()
game.update(zip(S.EVENT_TABLES, (table(False), table(True))))
maps, flow, tables = S.boss_files({DEKU: DC, DC: DEKU, FOREST: FOREST, FIRE: FIRE, WATER: WATER, SHADOW: SHADOW}, game.__getitem__, FLAG)
check(set(maps) == {S.entrance_out_file(DEKU), S.entrance_out_file(DC)} and set(tables) == set(S.EVENT_TABLES), "the files of a swap of two: %r" % sorted(maps))
check(requests(maps[S.entrance_out_file(DEKU)])[0] == S.boss_door_event(DEKU), "the Deku Tree's boss's request")
got = evfl.EventFlow()
got.read(flow)
check(sorted(e.name for e in got.flowchart.entry_points) == sorted(S.boss_door_event(d) for d in (DEKU, DC)), "a door that keeps its boss has an event")
check(S.boss_files({d: d for d in S.BOSS_ROOMS}, game.__getitem__, FLAG) == ({}, None, {}), "nothing moved, and files")
for bad in ({DEKU: DC}, {DEKU: DC, DC: DC}, {DEKU: "InsideJabuJabuBelly", "InsideJabuJabuBelly": DEKU}, {DEKU: "SpiritTemple", "SpiritTemple": DEKU}):
    check(refused(S.boss_files, bad, game.__getitem__, FLAG), "a change that cannot be is made: %r" % bad)

# ---- the game's side's table says the same ----
host = (ROOT / "host" / "hos_main.c").read_text(encoding="utf-8")
rows = dict((m.group(1), (m.group(2), m.group(3))) for m in re.finditer(r'\{"(\w+)", "CA", \{[^}]*\}, "(\w+)"(?:, (0x[0-9a-f]+)u)?\},', host))
for dungeon, (fight, start, seen) in S.BOSS_ROOMS.items():
    check(dungeon in rows and rows[dungeon][0] == fight, "%s's fight's event is not the game's side's: %r" % (dungeon, rows.get(dungeon)))
    check((int(rows[dungeon][1], 16) if rows[dungeon][1] else None) == (S.murmur3(seen.encode()) if seen else None), "%s's entry scene's flag is not the game's side's" % dungeon)
src = (ROOT / "tools" / "rando" / "rando_seed.py").read_text(encoding="utf-8")
check("RANDO_TEST_BOSS_MODE" not in src and "RANDO_TEST_BOSS_FLAG" not in src and "TRIAL" not in src[src.index("def boss_door_flow"):src.index("def boss_event_rows")], "a trial's code is left in")
print("ok: a boss's room led to another boss's fight (the files)")
