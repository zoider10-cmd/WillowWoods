#!/usr/bin/env python3
"""The Deku Tree's and the Bottom of the Well's doors, for an adult (the owner, 2026-11-28: "look into a way to make bottom
of the well and deku tree accessable as an adult", with three saves and screenshots).

The doors' actors are in the adult's maps with the child's fields; what stops him is the way to their trigger: vines and
rocks before the Deku Tree's mouth, the hole under the well's door that only a child crawls through. The trigger is baked
with the map (the actor moved in a test seed changed nothing). So the game's side (host/hos_main.c oot_adult_door) sends
an adult who walks up to where he is stopped through the door, as the door's own request would (the dungeon behind it by
the seed's entrances.txt, its entrance, its first scene the first time), and puts an adult whom a dungeon's way out left
past the obstacle on the open side. Seen without a window on the owner's saves: into the Deku Tree (before and after the
Forest Temple) and the well, each first scene played; out again by the dungeon's own way, and put on the open side.

This check reads the game's side's source against the seed tool's doors.
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
    inside = host[host.index("} oot_door_inside[] = {"):]
    inside = inside[:inside.index("};")]
    rows = re.findall(r'\{"(\w+)", "(\w+)", "(\w+)", "(\w+)", "(\w*)", (0x[0-9a-f]+u|0)\}', inside)
    check(sorted(r[0] for r in rows) == sorted(S.DUNGEON_DOORS), "the doors' insides are not those of the seed tool's dungeons with a door")
    for dungeon, banc, start, nxt, init, flag in rows:
        check(banc == dungeon and start and nxt, "%s's inside is not its own map, or has no start point or arrival" % dungeon)
        check((init == "") == (flag == "0"), "%s: a first scene without its played flag, or a flag without a scene" % dungeon)
    by = {r[0]: r for r in rows}
    # (the first scenes the seed tool itself knows: Jabu-Jabu's by ENTRANCE_FIRST, with its played flag's hash)
    scene, flag = S.ENTRANCE_FIRST["InsideJabuJabuBelly"]
    check(by["InsideJabuJabuBelly"][4] == scene and int(by["InsideJabuJabuBelly"][5][:-1], 16) == S.murmur3(flag.encode()),
          "Jabu-Jabu's belly's first scene is not the seed tool's")
    check(int(by["InsideTheDekuTree"][5][:-1], 16) == S.murmur3(b"HavePlayedEvent.Dm_Deku_0000") and
          int(by["BottomOfTheWell"][5][:-1], 16) == S.murmur3(b"HavePlayedEvent.Goto_KakarikoWells"),
          "the Deku Tree's or the well's first scene's flag is another")
    doors = host[host.index("} oot_adult_doors[] = {"):]
    doors = doors[:doors.index("};")]
    names = re.findall(r'\{"(\w+)", "(\w+)", ', doors)
    check(names == [("InsideTheDekuTree", "KokiriForest"), ("BottomOfTheWell", "KakarikoVillage")],
          "the adult's doors are not the Deku Tree's in the forest and the well's in Kakariko: %r" % names)
    for door, folder in names:
        check(any(stem.startswith(folder + "/") for stem in S.DUNGEON_DOORS[door][0]), "%s's door is not in %s's maps" % (door, folder))
    body = host[host.index("static void oot_adult_door(Ctx *c, uint64_t actor, const char *map) {"):]
    body = body[:body.index("\n}\n") + 3]
    check('if (!map[0] || oot_link_child != 0 || !strstr(map, "_Adult")) return;' in body, "a child, or a child's map, is sent through too")
    check("if (!strcmp(oot_doors[k].door, oot_adult_doors[i].door)) dungeon = oot_doors[k].dungeon;" in body,
          "the door does not lead to the dungeon the seed put behind it (Dungeon entrances)")
    check("oot_gamedata_bool(c, oot_door_inside[k].init_flag, &played) && !played) boot = oot_door_inside[k].init;" in body,
          "the dungeon's first scene is not played the first time")
    check("if (away > OOT_ADULT_DOOR_ARM) armed[i] = 1;" in body and "if (!armed[i] || away > OOT_ADULT_DOOR_NEAR) continue;" in body and
          "memset(armed, 0, sizeof armed);" in body, "the door is not armed only once he has stood away from it in this map")
    check("memcpy(oot_put_place, oot_adult_doors[i].outside, sizeof oot_put_place);" in body and "oot_put_asked = 1, armed[i] = 0;" in body and
          "if (oot_put_asked) {" in host and "&& !go && !oot_put_asked && now >= hold_until) return;" in host,
          "an adult left past the obstacle by a dungeon's way out is not put on the open side")
    check("oot_adult_door(c, actor, oot_link_map);" in host, "the look is not made")
    print("PASS: an adult is sent through the Deku Tree's and the well's doors, and put on the open side coming out")


if __name__ == "__main__":
    main()
