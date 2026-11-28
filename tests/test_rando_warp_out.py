#!/usr/bin/env python3
"""A boss's blue warp, with Dungeon entrances or Boss shuffle: out by the door Link came in by (the owner, 2026-11-28).

The owner's test: Volvagia fought from the Forest Temple's boss's room, her scenes and medallion, and the warp put Link
in front of the Fire Temple "like it would in a normal game"; asked for: "have it send to the actual dungeon you
entered". The scenes stay the boss's own (they give its reward); once they are over the game's side (host/hos_main.c
oot_warp_out) takes Link to the outside of the door he came in by: the boss's room's dungeon by the seed's boss_doors.txt,
the door that dungeon is behind by its entrances.txt, and that door's own dungeon's way out as the game's maps have it.
Seen without a window, 2026-11-28, on a seed with the Deku Tree behind the Bottom of the Well's door: Gohma's warp, the
Deku Tree's scenes in the forest, then Link at Kakariko's well.

This check reads the game's side's source: the doors' outsides for every dungeon with a door, how the door is found, and
what tells a warp from another way out.
"""
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(ok, what):
    if not ok:
        raise SystemExit("FAIL: " + what)


def main():
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("rando_seed", ROOT / "tools" / "rando" / "rando_seed.py")
    S = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(S)
    host = (ROOT / "host" / "hos_main.c").read_text(encoding="utf-8")
    table = host[host.index("} oot_door_outside[] = {"):]
    table = table[:table.index("};")]
    rows = re.findall(r'\{"(\w+)", "(\w+)", "(\w+)", "(\w+)", "(\w+)"\}', table)
    # (a row for every dungeon the seed gives a door, and its way out's name as the seed tool has it from the door's side)
    check(sorted(r[0] for r in rows) == sorted(S.DUNGEON_DOORS), "the doors' outsides are not those of the seed tool's dungeons with a door: %r" %
          sorted(set(S.DUNGEON_DOORS) ^ {r[0] for r in rows}))
    for door, adult, child, start, boot in rows:
        maps = [stem.split("/")[1] for stem in S.DUNGEON_DOORS[door][0]]
        check(adult in maps or child in maps, "%s's outside is not a map its door is in: %s, %s (the door's: %s)" % (door, adult, child, maps))
        check(adult.endswith("_Adult") and (child.endswith("_Child") or child == adult) and boot, "%s's outside has not a map an age, or no arrival" % door)
    body = lambda head: host[host.index(head):host.index("\n}\n", host.index(head)) + 3]
    door = body("static const char *oot_warp_out_door(const char *boss) {")
    check("if (!strcmp(oot_boss_doors[i].boss, boss)) room = oot_boss_doors[i].room;" in door and
          "if (!strcmp(oot_doors[i].dungeon, room)) door = oot_doors[i].door;" in door and "door = room;" in door,
          "the door Link came in by is not the boss's room's dungeon's door (Boss shuffle, then Dungeon entrances)")
    out = body("static void oot_warp_out(Ctx *c, uint64_t actor, const char *map, int64_t now) {")
    # (the owner's run, 2026-11-28: an adult sent into the Deku Tree beat Gohma, and the warp's scenes, the child's forest's,
    #  made him a child. The age he rode the warp at is put back with the move, his own door's outside too then; so the look
    #  is made in every randomizer game, not only with the doors or the bosses moved)
    check("if (!oot_door_n && !oot_boss_door_n) {" not in out and "if (oot_link_child >= 0) rode_child = oot_link_child;" in out and
          "pending_child = rode_child;" in out and
          "const int aged = pending_child >= 0 && oot_link_child >= 0 && oot_link_child != pending_child;" in out and
          "if (aged && !oot_gamedata_set_bool(c, 0xcea220d3u, pending_child)) {" in out and "if (aged) oot_teleport_child = pending_child;" in out and
          "if (aged) oot_gamedata_set_bool(c, 0xcea220d3u, !pending_child);" in out,
          "Link is not made the age he rode the warp at again once its scenes are over")
    check('rode = at_boss >= 0 && oot_event_playing(c) && strcmp(oot_warp_event, "DmF_SY_GameOver");' in out and
          "at_boss = oot_boss_room_near(oot_boss_rooms[dungeon].folder) ? dungeon : -1;" in out and
          "if (at_boss >= 0 && rode) pending = at_boss, pending_since = now, settled = 0, pending_child = rode_child;" in out,
          "a warp is not told from a death in the boss's room, or from leaving the dungeon another way")
    check("if (oot_event_playing(c) || (oot_gamedata_bool(c, 0xef2b60c2u, &loading) && loading)) {" in out and "if (++settled < 3) return;" in out and
          "if (now - pending_since > 300000000000LL) {" in out, "Link is moved while the warp's scenes play, or waited for without end")
    check("if (!strcmp(door, boss) && !aged) {" in out and "const int sent = oot_teleport(c, actor, OOT_OWN_DESTINATION);" in out and "settled = 0;" in out,
          "the boss's own door is not left as the game has it, or a move not taken is not tried again")
    check("oot_warp_out(c, actor, oot_link_map, now);" in host and "if (is_new && hos_rando_on()) oot_warp_out_event(name);" in host and
          "const OotDestination *d = index == OOT_OWN_DESTINATION ? &oot_own_destination : &oot_destinations[index];" in host,
          "the look is not made each second, the events' names are not kept, or the teleport has no destination of its own")
    print("PASS: a boss's blue warp leads out by the door Link came in by")


if __name__ == "__main__":
    main()
