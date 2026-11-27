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

# ---- the setting, rando_boss_shuffle (2026-11-27 later): the shuffle and the rules ----
# Seen in trial seeds: 11 rules changed, the moved bosses' Heart Containers and the checks that wait for their temples or
# the Deku Tree, none asking for less; each with the keys of the dungeon the boss is fought from.
check(S.BOSS_CHILD == (DEKU, DC) and S.BOSS_ADULT == (FOREST, FIRE, WATER, SHADOW) and set(S.BOSS_CHILD + S.BOSS_ADULT) == set(S.BOSS_ROOMS), "the bosses' groups")
many = [S.boss_shuffle(s) for s in range(300)]
for f in many:
    check(set(f) == set(f.values()) == set(S.BOSS_ROOMS), "not a one-to-one change: %r" % f)
    check({f[d] for d in S.BOSS_CHILD} == set(S.BOSS_CHILD) and {f[d] for d in S.BOSS_ADULT} == set(S.BOSS_ADULT), "a boss fought from a room of the other group: %r" % f)
check({(a, b) for f in many for a, b in f.items()} == {(a, b) for g in (S.BOSS_CHILD, S.BOSS_ADULT) for a in g for b in g}, "over 300 seeds not every pair of a group came up")
check(S.boss_shuffle(7) == S.boss_shuffle(7) and any(S.boss_shuffle(s) != S.boss_shuffle(7) for s in range(8, 14)), "not by the seed alone")
kept = [S.boss_shuffle(s, child=False) for s in range(60)]
check(all(DEKU not in f and DC not in f and set(f) == set(S.BOSS_ADULT) for f in kept), "the child's two change rooms where they may not (the Door of Time shut, or the forest)")
waits = S.ENTRANCE_NOCTURNE_WAITS
quiet = [S.boss_shuffle(s, True, False) for s in range(300)]
check(all(f[SHADOW] not in waits for f in quiet) and {f[SHADOW] for f in quiet} == {SHADOW}, "without the Nocturne a waited temple's boss is fought from the Shadow Temple's boss's room")
moved = [S.boss_shuffle(s, True, False, {"ShadowTemple": "IceCavern", "IceCavern": SHADOW}) for s in range(100)]   # (the Ice Cavern behind the Shadow Temple's door: no boss)
check(all(f[SHADOW] not in waits for f in moved), "without the Nocturne, the Ice Cavern behind the Shadow Temple's door: a waited boss fought from the Shadow Temple's")
# (a temple behind the Shadow Temple's door without the Nocturne is a change the doors' shuffle never makes; asked for, no
#  change of the bosses fits two such rooms, and the search says so and ends: it ran without end, found by this check)
check(refused(S.boss_shuffle, 1, True, False, {"ShadowTemple": FIRE, FIRE: SHADOW}), "a search that cannot end is not refused")
check('sys.exit("Boss shuffle: %s. Nothing written." % e)' in src and "while True:" not in src[src.index("def boss_shuffle("):src.index("def boss_door_event(")]
      and "while True:" not in src[src.index("def entrance_shuffle("):src.index("def and_rules(")], "a shuffle's search without an end")
check(any(S.boss_shuffle(s)[SHADOW] in waits for s in range(40)), "with the Nocturne an item no waited boss is ever fought from the Shadow Temple's")

main = src[src.index("\ndef main():"):]
for line in ('a.boss_shuffle = ini["rando_boss_shuffle"] == 1',
             '(" bosses 1" if a.boss_shuffle else "")',
             "fights = boss_shuffle(seed, bool(door_rules) and bool(a.open_forest), NOCTURNE in PROGRESSION, behind) if a.boss_shuffle else {}",
             "boss_room = {boss: room for room, boss in fights.items() if room != boss}",
             "room_access = {room: heart_asks(heart_of[room]) for room in set(boss_room.values())}",
             "boss_rooms_of = lambda h: {boss_room[d] for d in (bosses.get(h), boss_gift.get(h)) + tuple(boss_waits.get(h, ())) if d in boss_room}",
             "return fit_rule(and_rules(rule, *(room_access[r] for r in sorted(rooms)))) if rooms and rule is not None else rule",
             "needs = {h: boss_moved(h, n) for h, n in needs.items()}",
             "heart_asks = lambda h: boss_moved(h, heart_unmoved(h))",
             "for room in sorted(boss_rooms_of(h)):",
             "needs[h] = each(lambda way, keys=key_sets[room]: frozenset(way) | keys, needs[h])",
             "tracked_own(h, n, d), frozenset(boss_key_tag(r) for r in boss_rooms_of(h) if r in moved_boss))",
             'if os.environ.get("RANDO_TEST_BOSSES") or boss_room:',
             "boss_flag = shelf_flags(len(shelves) + 2, a.shop_shelves, shield_shelf, placement)[-1]",
             "written.append(BOSSES_FILE)",
             'spoiler = ["Boss shuffle (a boss\'s room -> the boss fought from it)"]'):
    check(line in main, "the main part lacks: %s" % line)
check(main.index("    fights = boss_shuffle(") > main.index("        skull_asks = lambda h, at=None: behind_door(") and
      main.index("    fights = boss_shuffle(") < main.index("kept_tokens = [(skull_asks(h, every_skull[h][0]), TOKEN)"),
      "the bosses' rules are not after the doors' (a room's rule has its dungeon's door in) and before the placement")
check('"rando_boss_shuffle": 0' in src and "heart_before = heart_asks\n        heart_asks = lambda h: boss_moved" not in src, "the options' line, or a name of the main part's taken again")
header = (ROOT / "gpu" / "vk" / "oot_rando.h").read_text(encoding="utf-8")
launcher = (ROOT / "launcher" / "Launcher.cs").read_text(encoding="utf-8")
check('X(BOSS_SHUFFLE, "Boss shuffle", "rando_boss_shuffle",' in header and header.index("X(BOSS_SHUFFLE,") > header.index("X(ENTRANCES_MIX,")
      and header.rstrip().count("X(BOSS_SHUFFLE,") == 1 and '"Off", "On")\n\nenum {' in header[header.index("X(BOSS_SHUFFLE,"):], "the menu's table: not there, or not last")
check('new object[] { "rando_boss_shuffle", "Boss shuffle", new[] { "Off", "On" }, new[] { 0, 1 },' in launcher
      and launcher.index('new object[] { "rando_boss_shuffle"') > launcher.index('new object[] { "rando_entrances_mix"')
      and '"rando_entrances_mix", "rando_boss_shuffle" } },' in launcher, "the launcher's table or section")

# ---- the Tracker says the boss rooms, each only once Link has been through it (the owner's ask, 2026-11-27) ----
# Seen in the game without a window: a dungeon's page says "not found yet" and "not entered yet" before, and names the
# rooms after an adult went from the Forest Temple's boss's room to the Fire Temple's.
import os
import subprocess
import tempfile
sys.path.insert(0, str(ROOT / "tests"))
import srccut  # noqa: E402
menu = (ROOT / "gpu" / "vk" / "vk_menu.cpp").read_text(encoding="utf-8")
menu_parts = "\n".join(srccut.block(menu, start, "vk_menu.cpp") for start in (
    "void tracker_boss_words(const char* area, char* one, char* two, size_t size) {",
    "int tracker_pairs_load(const std::string& file, bool on, const std::string& seen_path, const std::string& stamp,",
    "void tracker_bosses_load(const std::string& folder, bool on, const std::string& seen_path, const std::string& stamp) {"))
check('tracker_bosses_load(path.substr(0, path.find_last_of("\\\\/") + 1), on, game_folder_path() + "rando\\\\boss_rooms_seen.txt", tracker_seed_stamp());' in menu,
      "the Tracker does not read the boss rooms with its lists")
panel = srccut.block(menu, "float tracker_panel(ui::Ctx& c, float x0, float x1, float y0, float y_max, int row, const char* hint) {", "vk_menu.cpp")
check("tracker_boss_words(tracker_name[row], boss_from, boss_leads, sizeof boss_from);" in panel and "for (const char* words : {way_in, leads, boss_from, boss_leads})" in panel
      and "(boss_from[0] ? 1 : 0) + (boss_leads[0] ? 1 : 0)) * 20 * s;" in panel, "a dungeon's panel does not say its boss rooms, or keeps no room for the lines")
menu_program = r"""
#include <cstdio>
#include <cstring>
#include <string>
constexpr int kDoorRows = 16;
""" + srccut.between(menu, "char tracker_boss_key[kDoorRows][48]", "void tracker_boss_words(", "vk_menu.cpp") + menu_parts + r"""
static bool says(const char* area, const char* one, const char* two) {
    char a[112], b[112];
    tracker_boss_words(area, a, b, sizeof a);
    if (strcmp(a, one) || strcmp(b, two)) printf("%s: \"%s\" / \"%s\"\n", area, a, b);
    return !strcmp(a, one) && !strcmp(b, two);
}
int main(int argc, char** argv) {
    if (argc < 2) return 9;
    const std::string folder = argv[1], seen = folder + "boss_rooms_seen.txt";
    tracker_bosses_load(folder, true, folder + "none.txt", "the stamp");
    if (tracker_boss_count != 3) return 1;
    for (const char* area : {"Forest Temple", "Fire Temple", "Water Temple"})
        if (!says(area, "Its boss: not found yet", "Its boss room: not entered yet")) return 2;
    if (!says("Kokiri Forest", "", "") || !says("Ice Cavern", "", "")) return 3;
    tracker_bosses_load(folder, true, seen, "the stamp");          // (the Forest Temple's room found, and the Water Temple's)
    if (!says("Fire Temple", "Its boss: in the boss room of Forest Temple", "Its boss room: not entered yet")) return 4;
    if (!says("Forest Temple", "Its boss: not found yet", "Its boss room has the boss of: Fire Temple")) return 5;
    if (!says("Water Temple", "Its boss: in its own room", "")) return 6;
    tracker_bosses_load(folder, true, seen, "another seed's stamp");
    if (!says("Fire Temple", "Its boss: not found yet", "Its boss room: not entered yet")) return 7;
    tracker_bosses_load(folder, false, seen, "the stamp");
    return tracker_boss_count ? 8 : 0;
}
"""
host_parts = "\n".join(srccut.block(host, start, "hos_main.c") for start in (
    "static void oot_boss_doors_save(void) {", "static int oot_boss_doors_note(const char *map, const char *left, int64_t since, int (*near)(const char *folder)) {",
    "static void oot_boss_doors_load(const char *stamp) {"))
check("oot_boss_doors_load(stamp);" in srccut.block(host, "static void oot_tracker_load(const char *stamp) {", "hos_main.c"), "the boss rooms are not read with the seed's lists")
check("oot_boss_doors_note(oot_link_map, oot_left_map, now - oot_left_at, oot_boss_room_near);" in host, "the boss room Link was sent from is not noted as his map is read")
near = srccut.block(host, "static int oot_boss_room_near(const char *folder) {", "hos_main.c")
check("oot_boss_rooms[i].place" in near and "< 30.0f * 30.0f" in near, "a boss's room is not told by the game's side's own places")
host_program = r"""
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define MAX_PATH 260
#define OOT_DOORS_MAX 16
static char root[400], oot_checks_seed[1024], in_room[24];
static int oot_game_file(char *out, size_t size, const char *tail) { snprintf(out, size, "%s%s", root, strrchr(tail, '/') + 1); return 1; }
static int oot_banc_in_folder(const char *banc, const char *folder) {
    const size_t n = strlen(folder);
    return !strncmp(banc, folder, n) && (!banc[n] || banc[n] == '_');
}
static void hos_log(const char *f, ...) { (void)f; }
static int near(const char *folder) { return !strcmp(folder, in_room); }
static struct { char room[24], boss[24]; int seen; } oot_boss_doors[OOT_DOORS_MAX];
static int oot_boss_door_n;
""" + host_parts + r"""
#define S 1000000000LL
int main(int argc, char **argv) {
    if (argc < 2) return 9;
    snprintf(root, sizeof root, "%s", argv[1]);
    snprintf(oot_checks_seed, sizeof oot_checks_seed, "the stamp");
    oot_boss_doors_load("the stamp");
    if (oot_boss_door_n != 3) return 1;
    /* (0: the Forest Temple's room -> the Fire Temple's boss; 1: the Fire Temple's -> the Forest Temple's; 2: the Water Temple's own) */
    snprintf(in_room, sizeof in_room, "FireTemple");
    if (oot_boss_doors_note("FireTemple", "DeathMountainCrater_Adult", 2 * S, near)) return 2;   /* (walked in by its own door: nothing) */
    if (oot_boss_doors_note("FireTemple", "ForestTemple", 40 * S, near)) return 3;                /* (left the Forest Temple long ago) */
    in_room[0] = 0;
    if (oot_boss_doors_note("FireTemple", "ForestTemple", 2 * S, near)) return 4;                 /* (in the temple, not in the boss's room) */
    snprintf(in_room, sizeof in_room, "FireTemple");
    if (!oot_boss_doors_note("FireTemple", "ForestTemple", 2 * S, near) || !oot_boss_doors[0].seen || oot_boss_doors[1].seen) return 5;
    if (oot_boss_doors_note("FireTemple", "ForestTemple", 3 * S, near)) return 6;                 /* (once) */
    snprintf(in_room, sizeof in_room, "WaterTemple");
    if (!oot_boss_doors_note("WaterTemple", "HyruleField_Adult", 500 * S, near) || !oot_boss_doors[2].seen) return 7;   /* (a room with its own boss: standing in it) */
    oot_boss_door_n = 0;
    oot_boss_doors_load("the stamp");
    if (oot_boss_door_n != 3 || !oot_boss_doors[0].seen || oot_boss_doors[1].seen || !oot_boss_doors[2].seen) return 8;
    oot_boss_doors_load("another seed's stamp");
    return oot_boss_doors[0].seen || oot_boss_doors[2].seen ? 10 : 0;
}
"""
cc, cxx = "clang", "clang++"
for i, arg in enumerate(sys.argv):
    if arg == "--cxx" and i + 1 < len(sys.argv):
        cxx = sys.argv[i + 1]
    if arg == "--cc" and i + 1 < len(sys.argv):
        cc = sys.argv[i + 1]
with tempfile.TemporaryDirectory() as tmp:
    Path(tmp, "boss_doors.txt").write_text("ForestTemple|FireTemple|Forest Temple|Fire Temple\nFireTemple|ForestTemple|Fire Temple|Forest Temple\n"
                                            "WaterTemple|WaterTemple|Water Temple|Water Temple\n", encoding="utf-8")
    c_file, c_exe = os.path.join(tmp, "host.c"), os.path.join(tmp, "host.exe")
    Path(c_file).write_text(host_program, encoding="utf-8")
    built = subprocess.run([cc, "-O1", "-Wall", "-Werror", "-o", c_exe, c_file], capture_output=True, text=True)
    check(built.returncode == 0, "the game's side's boss rooms do not compile:\n%s" % built.stderr)
    ran = subprocess.run([c_exe, tmp + "/"], capture_output=True, text=True)
    check(ran.returncode == 0, "the game's side's boss rooms: case %d" % ran.returncode)
    record = Path(tmp, "boss_rooms_seen.txt").read_text(encoding="utf-8")
    check(record == "seed the stamp\nForestTemple\nWaterTemple\n", "the record of the boss rooms found: %r" % record)
    cpp, exe = os.path.join(tmp, "menu.cpp"), os.path.join(tmp, "menu.exe")
    Path(cpp).write_text(menu_program, encoding="utf-8")
    built = subprocess.run([cxx, "-std=c++17", "-O1", "-Wall", "-Werror", "-o", exe, cpp], capture_output=True, text=True)
    check(built.returncode == 0, "the Tracker's boss rooms do not compile:\n%s" % built.stderr)
    ran = subprocess.run([exe, tmp + os.sep], capture_output=True, text=True)
    check(ran.returncode == 0, "the Tracker's boss rooms: case %d %s" % (ran.returncode, ran.stdout))
print("ok: Boss shuffle: the files, the shuffle, the rules and the Tracker's boss rooms")
