"""An ocarina a character hands over is given as an item Link can hold up (tools/rando/rando_seed.py OCARINA_HELD,
host/hos_main.c oot_pot_as; bug 162, 2026-11-27). No game data.

A character's gift makes the item's actor and has Link hold it up. The ocarinas' own actors are the ones Link plays, not
made from the base every chest's item has, and the game fell as Link reached up for one (seen without a window at the
Potion Shop keeper's gift; a song there was fine). The seed tool gives an ocarina at such a gift as an item of its own,
whose name for the pouch is the ocarina's, and the game's side makes the add the ocarina's. Checked:
- a gift's flow names the held item for either ocarina, but not in the ocarinas' own scenes (Saria's, Zelda's: no
  hold-up there), and every other item as it is;
- the held item's pack: an actor of its own name from the base, naming the ocarina for the pouch, with the ocarina's
  model and pouch files and none of the song's it is made from; the ocarina's own actor file is not in it;
- its rows in the three lists: the ocarina's name and model in the list of actors, the ocarina's row in the pouch's;
- the main part uses it for the gifts and the lessons and makes the packs; seeds made before are written again;
- the game's side knows both held items by the names the seed tool gives them.

    python -I -B tests/test_rando_ocarina_held.py
"""
import collections
import importlib.util
import re
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


def node(value):
    if isinstance(value, dict):
        return ("dict", collections.OrderedDict(sorted((k, node(v)) for k, v in value.items())))
    if isinstance(value, list):
        return ("array", [node(v) for v in value])
    return ("string", value)


def plain(n):
    kind, value = n
    if kind == "dict":
        return {k: plain(v) for k, v in value.items()}
    if kind == "array":
        return [plain(v) for v in value]
    return value


def build(value):
    return S.byml_build(node(value), 7)


def main():
    fairy, time = S.OCARINA, S.OCARINA_TIME
    check(set(S.OCARINA_HELD) == {fairy, time} and len(set(S.OCARINA_HELD.values())) == 2, "not both ocarinas have a held item of their own")
    # a gift's flow
    check(S.held_gift("Npc_Hylia_020_Shop_Child", fairy) == S.OCARINA_HELD[fairy] and S.held_gift("Dm_FairyFountain_Din", time) == S.OCARINA_HELD[time],
          "an ocarina at a character's gift is still the ocarina Link plays")
    for flow in S.OCARINA_KINDS:
        check(S.held_gift(flow, fairy) == fairy and S.held_gift(flow, time) == time, "%s: the ocarinas' own scene names a held item" % flow)
    check(S.held_gift("Npc_Hylia_020_Shop_Child", "Item_Bottle") == "Item_Bottle", "another item is changed")
    # the pack
    song = S.OCARINA_HELD_FROM
    from_pack = S.sarc_write(collections.OrderedDict((
        (S.ACTOR_FILE % S.OCARINA_HELD_PARENT, build({"Components": {"PhysicsRef": "?Component/Physics/Dummy.engine__component__PhysicsParam.bgyml"}})),
        (S.ACTOR_FILE % song, build({"$parent": S.ACTOR_REF % S.OCARINA_HELD_PARENT, "Components": {}})),
        ("Component/EventPerformerParam/PouchContent.engine__component__EventPerformerParam.bgyml", build({"a": "b"})),
        (S.MODEL_INFO_FILE % song, build({"FmdbName": "Obj_Rupee"})),
        ("Component/PouchContentParam/KeyItemMelody.game__component__PouchContentParam.bgyml", build({"a": "b"})),
        ("Component/Physics/Dummy.engine__component__PhysicsParam.bgyml", build({"a": "b"})))))
    own_pack = S.sarc_write(collections.OrderedDict((
        (S.ACTOR_FILE % fairy, build({"Components": {"AccessoryRef": "x"}})),
        (S.MODEL_INFO_FILE % fairy, build({"FmdbName": fairy})),
        (S.OCARINA_HELD_POUCH % fairy, build({"SpecialDeal": "Ocarina"})),
        ("Game/OcarinaParam/%s.game__ocarina__OcarinaParam.bgyml" % fairy, build({"a": "b"})))))
    data, parts = S.held_ocarina_pack(fairy, own_pack, from_pack)
    files = S.sarc_read(data)
    name = S.OCARINA_HELD[fairy]
    check(parts == [S.ACTOR_FILE % name] and S.ACTOR_FILE % name in files, "the held item's pack has no actor of its own name")
    actor = plain(S.byml_parse(files[S.ACTOR_FILE % name])[0])
    check(actor["$parent"] == S.ACTOR_REF % S.OCARINA_HELD_PARENT, "the held item is not made from the base every chest's item has")
    comps = actor["Components"]
    check(comps.get("ActorNameRef") == S.OCARINA_HELD_NAME % fairy and "/ActorName/%s." % fairy in comps["ActorNameRef"],
          "the held item's name for the pouch is not the ocarina's")
    check(comps.get("ModelInfoRef") == "?" + S.MODEL_INFO_FILE % fairy and comps.get("PouchContentRef") == "?" + S.OCARINA_HELD_POUCH % fairy,
          "the held item does not show the ocarina, or has not its pouch file")
    check(files.get(S.MODEL_INFO_FILE % fairy) == S.sarc_read(own_pack)[S.MODEL_INFO_FILE % fairy] and S.OCARINA_HELD_POUCH % fairy in files,
          "the ocarina's model or pouch file is not in the held item's pack")
    check(S.ACTOR_FILE % fairy not in files and not any("OcarinaParam" in f for f in files), "the ocarina Link plays is in the held item's pack")
    check(S.ACTOR_FILE % S.OCARINA_HELD_PARENT in files and S.ACTOR_FILE % song not in files and S.MODEL_INFO_FILE % song not in files and
          not any("KeyItemMelody" in f for f in files) and any("EventPerformerParam" in f for f in files) and any("/Physics/" in f for f in files),
          "the base's parts are not all there, or the song's own files came with them")
    try:
        S.held_ocarina_pack(fairy, from_pack, from_pack)
        check(False, "a pack that is not the ocarina's is taken for it")
    except ValueError:
        pass
    # the rows
    actors = build([{"__RowId": fairy, "ActorName": fairy, "FmdbName": fairy, "ModelProjectName": fairy, "ELinkUserName": fairy, "CalcPriority": "After"},
                    {"__RowId": song, "ActorName": song, "FmdbName": "Obj_Rupee", "ModelProjectName": "Obj_Rupee", "ClassName": "GameActor"}])
    rows = {r["__RowId"]: r for r in plain(S.byml_parse(S.held_ocarina_rows(actors, "ActorInfo", fairy))[0])}
    check(name in rows and len(rows) == 3, "the list of actors has no row of the held item")
    check(rows[name]["ActorName"] == fairy and rows[name]["FmdbName"] == fairy and rows[name]["ModelProjectName"] == fairy,
          "the held item's row has not the ocarina's name for the pouch, or not its model")
    check("ELinkUserName" not in rows[name] and "CalcPriority" not in rows[name] and rows[name].get("ClassName") == "GameActor",
          "the held item's row is the played ocarina's, not an item's")
    pouch = build([{"__RowId": fairy, "PouchSpecialDeal": "Ocarina", "OcarinaTypeValue": "1"}, {"__RowId": song, "PouchSpecialDeal": "Melody"}])
    rows = {r["__RowId"]: r for r in plain(S.byml_parse(S.held_ocarina_rows(pouch, "PouchActorInfo", fairy))[0])}
    check(rows[name].get("PouchSpecialDeal") == "Ocarina" and rows[name].get("OcarinaTypeValue") == "1", "the held item's pouch row is not the ocarina's")
    game = build([{"__RowId": fairy}, {"__RowId": song}])
    check(name in {r["__RowId"] for r in plain(S.byml_parse(S.held_ocarina_rows(game, "GameActorInfo", fairy))[0])}, "the third list has no row of the held item")
    # the main part
    script = (ROOT / "tools" / "rando" / "rando_seed.py").read_text(encoding="utf-8")
    check("{old: held_gift(flow, new) for old, new in change.items()}, kinds=OCARINA_KINDS.get(flow, (4,)))" in script and
          "held_used |= {new for new in change.values() if held_gift(flow, new) != new}" in script,
          "the gifts' flows are not written with the held item")
    check("gift_items(was, {own[flow]: held_gift(flow, now_gives[own[flow]])}, kinds=(4,))" in script and
          "held_used |= {now_gives[own[flow]]} & set(OCARINA_HELD)" in script, "a lesson's own gift is not written with the held item")
    check("new, parts = held_ocarina_pack(ocarina, read_pack(ocarina), read_pack(OCARINA_HELD_FROM))" in script and
          'shop_packs["Pack/Actor/%s.pack" % OCARINA_HELD[ocarina]] = len(new)' in script and
          "table = held_ocarina_rows(table, kind, ocarina)" in script, "the held items' packs and rows are not made")
    check(S.FIXES_VERSION >= 107, "FIXES_VERSION not raised: a seed made before, an ocarina at a gift, would keep the crash")
    # the game's side
    host = (ROOT / "host" / "hos_main.c").read_text(encoding="utf-8")
    line = re.search(r"^static const char \*const oot_pot_as\[\]\[2\] = .*$", host, re.M)
    check(line is not None, "host/hos_main.c: oot_pot_as was not found: bring the check up to date")
    for ocarina, held in S.OCARINA_HELD.items():
        check('{"%s", "%s"}' % (held, ocarina) in line.group(0), "the game's side does not make %s's add %s's" % (held, ocarina))
        check(len(held) < 96, "a held item's name is too long for the add's buffer")
    print("PASS: an ocarina a character hands over is an item Link can hold up, and the pouch gets the ocarina")


if __name__ == "__main__":
    main()
