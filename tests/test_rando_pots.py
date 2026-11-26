"""Pots (rando_pots, "Potsanity", asked 2026-11-23): the pots the logic's tables rule (pot_actors: kind "pot") take part as
Gold Skulltulas do: a spot holding its own item (POT_OWN) in the pool, dropping what a Skulltula may (skull_may), by
the rule its table gives it (heart_asks over lying, the pieces and the pots), its map's pot given that drop (add_drop),
and a "Pot" check on the Tracker; the game's side gives a pot's item once (host/hos_main.c oot_pot_again). Game-free: the
tables and the sources.

python -I -B tests/test_rando_pots.py
"""
import collections
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools", "rando"))
import rando_seed as S  # noqa: E402


def main():
    pots = S.pot_actors()
    assert 60 <= len(pots) <= 120, len(pots)
    assert all(isinstance(h, int) and f for h, f in pots.items())
    assert S.skulltula_holds(S.POT_OWN, S.PROGRESSION), "a pot's own item is not one a Skulltula may drop"
    src = open(S.__file__, encoding="utf-8").read()
    main_src = src[src.index("\ndef main():"):]
    assert 'a.pots = ini["rando_pots"] == 1' in main_src and '(" pots 1" if a.pots else "")' in main_src
    assert 'joined.update((h, [pots[h][0], pot_own(h, placement), None, None, "pot", pots[h][1], ""]) for h in pots)' in main_src
    assert 'holds[h] = skull_may if s[4] in ("skulltula", "pot") else' in main_src
    assert "lying = collections.ChainMap(pieces, pots)" in main_src and "own_rule(h, lying[h][0], lambda:" in main_src, \
        "a pot's rule is not read as a piece's"
    assert main_src.index("drops.setdefault(h, item)\n        if a.progressive:") < main_src.index("    # ---- the map files ----"), \
        "the pots' drops are not given before the map files are written"
    assert '"Pot", h, pot_drops.get(h, POT_OWN))' in main_src, "no Pot check on the Tracker"
    host = open(os.path.join(ROOT, "host", "hos_main.c"), encoding="utf-8").read()
    assert 'oot_checks[oot_check_count].pot = !strncmp(kind, "Pot", 3) && (!kind[3] || kind[3] == \' \');' in host
    again = host.index("if (c->x[30] != 0x828d50acULL && oot_pot_again(c, name)) return 1;")
    assert again < host.index("oot_tracker_item(name, shop, price);"), "a pot back after a day is recorded before it is refused"
    # (2026-11-25, from play: the pot is known by the game's "broken" truth value by its hash, not by distance: the Market's
    #  guard house has 22 pots in 8 m, and a second token from the pot beside a collected one was refused)
    body = host[host.index("static int oot_pot_open(Ctx *c, const char *name, int *broken) {"):]
    body = body[:body.index("\n}\n")]
    again = host[host.index("static int oot_pot_again(Ctx *c, const char *name) {"):]
    again = again[:again.index("\n}\n")]
    assert "oot_gamedata_keyed_bool(c, oot_checks[i].broken, &now)" in body and "OOT_POT_NEAR" not in host, \
        "a pot is still found by distance"
    assert "if (oot_checks[i].done != 1) {" in body and "open = i;" in body and "if (open < 0) open = alike;" in body and "return broken > 0;" in again, \
        "an item is refused while a broken pot giving it is not collected"
    assert "oot_checks[oot_check_count].broken = oot_checks[oot_check_count].pot ? oot_checks[oot_check_count].key : 0;" in host
    track = host[host.index("static void oot_tracker_item(const char *name, int shop, int price) {"):]
    assert "best = oot_pot_chosen;" in track[:track.index("\n}\n")], "the record does not mark the pot just broken"
    # (FIXES 96, POT_ACTOR: a pot taking part is an actor of its own, coloured, its drop by its own table; its
    #  model and texture copies under names of the same length)
    assert S.pot_look_name("Obj_Pot_A_05_Respawn") == "Obj_Pot_R_05_Respawn" and S.pot_look_name("Obj_Pot_A_01") == "Obj_Pot_R_01"
    assert S.pot_look_name("Obj_Pot_Big") is None and len(S.POT_FROM) == len(S.POT_TO) and len(S.POT_TEX_FROM) == len(S.POT_TEX_TO)
    import colorsys
    for rgb in ((180, 70, 40), (120, 118, 115), (20, 20, 20)):   # (red clay, grey stone, near black: the hue, a colour, the brightness kept)
        h, s, v = colorsys.rgb_to_hsv(*(c / 255.0 for c in S.pot_colour(rgb)))
        assert abs(h * 360 - S.POT_HUE) < 1 and s >= S.POT_SATURATION - 1e-6 and abs(v - max(rgb) / 255.0) < 1e-6, (rgb, h, s, v)
    tree = ("dict", S.collections.OrderedDict([("Actors", ("array", [
        ("dict", S.collections.OrderedDict([("Dynamic", ("dict", S.collections.OrderedDict([("Drop__DropActor", ("string", "Obj_Rupee_Green"))]))),
                                            ("Gyaml", ("string", g)), ("Hash", (0xD5, S.struct.pack("<Q", h)))]))
        for g, h in (("Obj_Pot_A_01", 11), ("Obj_Pot_A_01", 12), ("Obj_Pot_A_05_Respawn", 13), ("Obj_TBox", 14))]))]))
    data = S.byml_build(tree, 7)
    assert S.pot_kinds(data, {11, 13, 14}) == {11: "Obj_Pot_A_01", 13: "Obj_Pot_A_05_Respawn"}
    out, n, was = S.pot_placed(data, {11: "Obj_PotR000", 13: "Obj_PotR001", 14: "Obj_PotR002"})
    actors = S.byml_parse(out)[0][1]["Actors"][1]
    names = [a[1]["Gyaml"][1] for a in actors]
    assert n == 2 and names == ["Obj_PotR000", "Obj_Pot_A_01", "Obj_PotR001", "Obj_TBox"], names
    assert dict(actors[0][1]["Dynamic"][1]) == {"Drop__DropTable": ("string", "None")}, "a pot of its own does not drop by its own table"
    assert actors[1][1]["Dynamic"][1]["Drop__DropActor"][1] == "Obj_Rupee_Green", "a pot not taking part was changed"
    # (placement 30: every pot takes part, one the tables don't rule by the nearest ruled actor's rule, its room's first)
    placed = {"f": [(1, (0, 0, 0), 3), (2, (1, 0, 0), 4), (3, (5, 0, 0), 3), (9, (0, 0, 0), 5)]}
    got = S.rule_sources({1: ["A", (0, 0, 0), "f"], 9: ["A", (0, 0, 0), "f"], 7: ["A", (0, 0, 0), "g"]}, placed, {2, 3, 9})
    assert got == {1: 3}, got   # (1: room 3's ruled actor, though another is nearer; 9 ruled; 7 none in its file)
    assert S.pot_own(5, 30) in S.POT_OWNS and S.pot_own(5, 29) == S.POT_OWN and all(S.skulltula_holds(i, S.PROGRESSION) for i in S.POT_OWNS)
    assert "found = dungeon_table().get(RULE_AS.get(h, h))" in src and "h = RULE_AS.get(h, h)" in main_src, "a pot's borrowed rule is not read"
    pack_src = src[src.index("\ndef pot_pack("):src.index("\ndef pot_rows(")]
    design_src = src[src.index("\ndef pot_design("):src.index("\ndef pot_fall_pack(")]
    assert "LiftableRef" not in pack_src + design_src, "a pot taking part is not lifted as the game's are"
    assert 'comps["DropRef"] = ("string", "?" + POT_DROP_PARAM % name)' in pack_src, \
        "the pot does not drop by its own table"
    assert all(p_.startswith(("Drop/", "Component/")) and "Rando" in p_ for p_ in (S.POT_DROP_PARAM, S.POT_DROP_TABLE, S.POT_DROP_SUB)), \
        "a pot's drop files are under the game's own paths (the game keeps the first copy of a path)"
    # (FIXES 97: a pot's junk is the game's own pick-up, no "You got" scene; the game's side knows the same pairs)
    import re
    pairs = dict((b, a) for a, b in re.findall(r'\{"(Obj_\w+)", "(\w+)"\}', host[host.index("static const char *const oot_pot_world[][2] = {"):
                                                                                   host.index("static const char *oot_pot_world_item(")]))
    assert pairs == S.POT_WORLD, (pairs, S.POT_WORLD)
    assert "IsReplace" not in pack_src.split("# (IsReplace kept")[0], "a pot's drop is not the game's supply rule"
    flags = host[host.index("static int oot_shelf_flags(Ctx *c) {"):]
    assert "oot_checks[i].pot && oot_checks[i].broken && oot_checks[i].done != 1 && oot_pot_junk(oot_checks[i].item)" in flags[:flags.index("\n}\n")], \
        "a junk pot is not collected when it breaks (it may drop a green rupee or nothing)"
    assert 'dropped = POT_WORLD.get(item, item) if world else item' in pack_src and all(i in S.POT_WORLD for i in S.POT_OWNS), "a pot's own junk has a scene"
    assert "if (open >= 0 || oot_pot_world_item(name) || oot_pot_junk(name)) return 0;" in host, "a world pick-up (grass's too) can be refused"
    assert S.POT_BAGGED <= set(S.POT_WORLD) and "pot_pack(kind[h], designs[kind[h]], bagged, pot_drops[h], world=False, fall=fall_of(pot_drops[h]))" in main_src,         "a pot's Deku Nuts or Sticks have no actor dropping their bag-giving bundle"
    assert "if (open >= 0 || oot_pot_world_item(name) || oot_pot_junk(name)) return 0;" in host, "a junk pot's bundle is refused after its pot is collected"
    assert "? -2 : -1;" in host and "if (oot_pot_chosen == -2) {" in track[:track.index("\n}\n")], \
        "a junk pot's item got after its pot was collected marks another check"
    # (reported 2026-11-25: a new game of a seed showed the last game's pots collected) a pot is collected in a save by the
    #  save's progress it was collected at, not the folder's record alone
    prog = host[host.index("static int oot_pot_progress(Ctx *c) {"):]
    prog = prog[:prog.index("\n}\n")]
    assert "if (oot_checks[i].pot_at < 0 || oot_checks[i].pot_at > progress) {" in prog and \
        "oot_checks[i].pot_kept = 0, oot_checks[i].pot_at = -1, oot_checks[i].done = 0, changed++;" in prog, \
        "a pot's mark is not the save's (a new game keeps the last one's pots)"
    assert "steady = read && oot_link_map[0] && progress == last ? steady + 1 : 0;" in prog and "steady < 5" in prog, \
        "pots are dropped on the title's defaults (progress 0), not in a game being played"
    assert 'fprintf(f, "%d:%d\\n", i, oot_checks[i].pot_at);' in host and "marks += oot_pot_progress(c);" in host, \
        "the record keeps no pot's progress, or it is never read against the save"
    # (FIXES 103: a new game of the seed is known by a flag of its own, true in a new game; its pots start afresh)
    assert "new_game_flag = shelf_flags(len(shelves) + 1, a.shop_shelves, shield_shelf, placement)[-1]" in main_src and \
        "flag_defaults(new if new is not None else was, {new_game_flag: True})" in main_src, "no flag of a new game's own"
    assert "a new game of the seed: %d pots of another game dropped from the record" in prog and \
        "oot_gamedata_set_bool(c, fresh, 0)" in prog, "a new game keeps another game's pots, or its flag is never put out"
    look = host[host.index("static uint64_t oot_pot_look_answer(Ctx *c, uint64_t name_at) {"):]
    look = look[:look.index("\n}\n")]
    assert "if (oot_checks[i].pot && oot_checks[i].broken == oot_pot_looks[k].hash)" in look and "if (done && !answer) {" in look and "oot_pot_looks[k].bagged[0] && oot_bundle_holder(item, &sizes) == 1" in look and "mods/rando-seed/pot_looks.txt" in look, \
        "a collected pot is not read as the game's pot"
    assert host.index("const uint64_t pot = oot_pot_look_answer(c, name_at);") < host.index("if (!name_at || !__atomic_load_n(&oot_tier_shelf_count"), \
        "the pots are answered only where shelves of a family are"
    assert "size_table_entry(tbl, was)" in main_src, "a pot's model and texture copies have no size table entry"
    # (FIXES 102: a pot's unique item is an actor of its own that falls, the item's pick-up with the rupee's body)
    def actor(name, parent=None, **parts):
        d = collections.OrderedDict()
        if parent:
            d["$parent"] = ("string", S.ACTOR_REF % parent)
        d["Components"] = ("dict", collections.OrderedDict((k, ("string", v)) for k, v in parts.items()))
        return S.byml_build(("dict", d), 7)
    token_set, token_physics = S.POT_FALL_SET_FROM % S.PICKUP_BASE, S.POT_FALL_PHYSICS_FROM % S.PICKUP_BASE
    pickup = S.sarc_write(collections.OrderedDict((
        (S.ACTOR_FILE % "Item_X", actor("Item_X", S.PICKUP_BASE, ModelInfoRef="?m")),
        (token_set, S.byml_build(("dict", collections.OrderedDict((("RigidBodyEntityNamePathAry", ("array", [("dict", collections.OrderedDict((
            ("FilePath", ("string", "Work/Phive/RigidBodyEntityParam/Token_Gold_0.phive__RigidBodyEntityParam.gyml")), ("Name", ("string", "Body")))))])),))), 7)),
        (token_physics, S.byml_build(("dict", collections.OrderedDict((("ControllerSetPath", ("string", S.ref_of(token_set))),))), 7)))))
    body = S.sarc_write(collections.OrderedDict(((S.POT_FALL_BODY_FROM, b"the body that falls"),)))
    fall, own = S.pot_fall_pack("Item_X", pickup, body, S.POT_FALL_AS % "Item_X")
    parts = S.sarc_read(fall)
    mine = S.byml_parse(parts[S.ACTOR_FILE % "Item_X_Fall"])[0][1]
    assert mine["$parent"][1] == S.ACTOR_REF % "Item_X" and dict(mine["Components"][1]) == {"PhysicsRef": ("string", "?" + S.POT_FALL_PHYSICS)}, mine
    assert S.byml_parse(parts[S.POT_FALL_PHYSICS])[0][1]["ControllerSetPath"][1] == S.ref_of(S.POT_FALL_SET)
    assert S.byml_parse(parts[S.POT_FALL_SET])[0][1]["RigidBodyEntityNamePathAry"][1][0][1]["FilePath"][1] == S.ref_of(S.POT_FALL_BODY)
    assert parts[S.POT_FALL_BODY] == b"the body that falls" and parts[token_set] == S.sarc_read(pickup)[token_set], "the token's own set was changed"
    assert sorted(own) == sorted([S.ACTOR_FILE % "Item_X_Fall", S.POT_FALL_BODY, S.POT_FALL_SET, S.POT_FALL_PHYSICS])
    assert all("Rando_Fall" in p_ for p_ in (S.POT_FALL_BODY, S.POT_FALL_SET, S.POT_FALL_PHYSICS)), "a falling pick-up's files are under the game's own names"
    rows = S.byml_parse(S.pot_fall_rows(S.byml_build(("array", [("dict", collections.OrderedDict((("__RowId", ("string", n)), ("K", ("string", n + "'s")))))
                                                                  for n in ("Item_A", "Item_X")]), 7), {"Item_X_Fall": "Item_X", "Item_Q_Fall": "Item_Q"}))[0][1]
    assert [(r[1]["__RowId"][1], r[1]["K"][1]) for r in rows] == [("Item_A", "Item_A's"), ("Item_X", "Item_X's"), ("Item_X_Fall", "Item_X's")], rows
    assert "fall if fall and dropped == item else dropped" in pack_src, "a pot's unique item is not dropped as its falling pick-up"
    assert "drop = POT_AS.get(pot_drops[h], pot_drops[h])" in main_src and "fall=None if drop in POT_WORLD else fall_of(drop, owners.get(h) if drop in DUNGEON_ITEMS else None)" in main_src,         "a pot's unique item hangs where the pot broke, or the Master Sword is not dropped as its own pick-up (POT_AS)"
    assert "size_table_add(tbl, pot_fall_parts, POT_FALL_PART)" in main_src and S.POT_FALL_PART > 8976 + 4096,         "a falling pick-up's files have no size table entry, or one its set of bodies does not fit (the game stops as the area loads)"
    assert "pot_fall_rows(pot_rows(table, table_kind, made)" in main_src, "a falling pick-up has no rows in the lists of actors"
    add = host[host.index("int hos_oot_pouch_add(Ctx *c) {"):]
    room = host[host.index("int hos_oot_pickup_room(Ctx *c) {"):host.index("int hos_oot_pouch_add(Ctx *c) {")]
    assert '#define OOT_POT_FALL "%s"' % (S.POT_FALL_AS % "") in host, "the game's side does not know a falling pick-up's name"
    assert add.index("if (oot_pot_fall(name)) {") < add.index('hos_log("rando: pouch add %s x%d') and "view = oot_pouch_name(c, view, name);" in add[:add.index('hos_log("rando: pouch add %s x%d')],         "a falling pick-up's add is not its item's"
    assert room.index("oot_pot_fall(name);") < room.index("oot_bundle_holder(name, &sizes)"), "a falling pick-up is not asked for as its item"
    header = open(os.path.join(ROOT, "gpu", "vk", "oot_rando.h"), encoding="utf-8").read()
    assert 'X(POTS, "Pots", "rando_pots",' in header
    print("PASS: Pots: every pot takes part")
    return 0


if __name__ == "__main__":
    sys.exit(main())
