"""A Piece of Heart lying in the world that gives another item shows that item (asked 2026-11-23, share/todo.md "Soon";
fixes 93, tools/rando/rando_seed.py PIECE_LOOK): an actor of its own for each item, the piece's pack with the item's
model (piece_variant_pack), the piece's rows of the three lists of actors with the item's model fields (piece_rows), and
the map files naming it (piece_named). The pouch's add is named by that actor (seen without a window 2026-11-24:
"pouch add Obj_Heart_Piece_R01"), so the game's side takes it for a piece (host/hos_main.c oot_is_piece) and gives the
seed's item. Game-free: made-up packs, tables and a map, and the sources.

python -I -B tests/test_rando_piece_looks.py
"""
import collections
import os
import struct
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools", "rando"))
import rando_seed as S  # noqa: E402

failed = False


def check(ok, what):
    global failed
    if not ok:
        failed = True
        print("FAIL: " + what)


def actor(comps):
    return S.byml_build(("dict", collections.OrderedDict(Components=("dict", collections.OrderedDict(
        (k, ("string", v)) for k, v in comps.items())))), 7)


def main():
    heart = S.sarc_write({S.ACTOR_FILE % S.HEART: actor({"ModelInfoRef": "?Component/ModelInfo/Obj_Heart_Piece.x", "ASRef": "?AS/Heart.asb",
                                                         "ActorNameRef": "?ActorSystem/ActorName/Obj_Heart_Piece.x", "AIInfoRef": "?AI/Heart.x"}),
                          "Component/ModelInfo/Obj_Heart_Piece.x": b"heart"})
    token = S.sarc_write({S.ACTOR_FILE % "Item_Token_Gold": actor({"ModelInfoRef": "?Component/ModelInfo/Item_Token_Gold.x",
                                                                   "ASRef": "?AS/Token.asb"}),
                          "Component/ModelInfo/Item_Token_Gold.x": b"token"})
    try:
        pack, own = S.piece_variant_pack("Item_Token_Gold", heart, token, "Obj_Heart_Piece_R00")
        parts = S.sarc_read(pack)
        comps = S.byml_parse(parts[S.ACTOR_FILE % "Obj_Heart_Piece_R00"])[0][1]["Components"][1]
        check(own == [S.ACTOR_FILE % "Obj_Heart_Piece_R00"] and comps["ModelInfoRef"][1] == "?Component/ModelInfo/Item_Token_Gold.x" and
              comps["ActorNameRef"][1] == "?ActorSystem/ActorName/Obj_Heart_Piece.x" and comps["AIInfoRef"][1] == "?AI/Heart.x" and
              "ASRef" not in comps and parts["Component/ModelInfo/Item_Token_Gold.x"] == b"token" and S.ACTOR_FILE % S.HEART in parts,
              "the piece's actor of its own is not the piece's (its name, its AI) with the item's model and no pose: %r" % {k: v[1] for k, v in comps.items()})
    except (ValueError, KeyError, struct.error) as e:
        check(False, "a made-up piece and token: %s" % e)
    n = lambda v: (0xD1, struct.pack("<I", v))
    rows = lambda *rs: S.byml_build(("array", [("dict", collections.OrderedDict(r)) for r in rs]), 7)
    table = rows([("__RowId", ("string", S.HEART)), ("FmdbName", ("string", "Heart")), ("InstanceHeapSize", n(100)), ("IsRespawn", ("string", "no"))],
                 [("__RowId", ("string", "Item_Token_Gold")), ("FmdbName", ("string", "Token")), ("InstanceHeapSize", n(500))])
    try:
        got = {r[1]["__RowId"][1]: r[1] for r in S.byml_parse(S.piece_rows(table, "ActorInfo", "Item_Token_Gold", "Obj_Heart_Piece_R00"))[0][1]}
        new = got.get("Obj_Heart_Piece_R00", {})
        check(new.get("FmdbName", ("", ""))[1] == "Token" and new.get("IsRespawn", ("", ""))[1] == "no" and
              struct.unpack("<I", new["InstanceHeapSize"][1])[0] == 500 + 32768 and got[S.HEART]["FmdbName"][1] == "Heart",
              "the actor's row is not the piece's (taken once) with the item's model and the larger heap")
        other = {r[1]["__RowId"][1]: r[1] for r in S.byml_parse(S.piece_rows(table, "GameActorInfo", "Item_Token_Gold", "Obj_Heart_Piece_R00"))[0][1]}
        check(other["Obj_Heart_Piece_R00"]["FmdbName"][1] == "Heart", "a list other than ActorInfo takes the item's model fields")
    except (ValueError, KeyError, struct.error) as e:
        check(False, "a made-up list of actors: %s" % e)
    host = open(os.path.join(ROOT, "host", "hos_main.c"), encoding="utf-8").read()
    check('return !strcmp(name, OOT_PIECE) || !strncmp(name, OOT_PIECE "_R", sizeof OOT_PIECE "_R" - 1);' in host and
          host.count("oot_is_piece(name) || !strcmp(name, OOT_PIECE_VALLEY)") == 2 and S.PIECE_LOOK == "Obj_Heart_Piece_R%02d",
          "the game's side does not take a piece's actor of its own for a piece")
    # (fixes 94: a boss's Heart Container the same way, from the container's actor)
    check('return !strcmp(name, OOT_CONTAINER) || !strncmp(name, OOT_CONTAINER "_R", sizeof OOT_CONTAINER "_R" - 1);' in host and
          host.count("oot_is_container(name)") == 3 and host.count("!strcmp(name, OOT_CONTAINER)") == 1 and
          S.CONTAINER_LOOK == "Obj_Heart_Container_R%02d",
          "the game's side does not take a container's actor of its own for a container")
    box = S.sarc_write({S.ACTOR_FILE % S.CONTAINER: actor({"ModelInfoRef": "?Component/ModelInfo/Obj_Heart_Container.x", "AIInfoRef": "?AI/Box.x"})})
    try:
        pack, own = S.piece_variant_pack("Item_Token_Gold", box, token, "Obj_Heart_Container_R00", S.CONTAINER)
        comps = S.byml_parse(S.sarc_read(pack)[S.ACTOR_FILE % "Obj_Heart_Container_R00"])[0][1]["Components"][1]
        check(comps["ModelInfoRef"][1] == "?Component/ModelInfo/Item_Token_Gold.x" and comps["AIInfoRef"][1] == "?AI/Box.x",
              "the container's actor of its own is not the container's with the item's model")
    except (ValueError, KeyError, struct.error) as e:
        check(False, "a made-up container and token: %s" % e)
    src = open(S.__file__, encoding="utf-8").read()
    main_src = src[src.index("\ndef main():"):]
    check("new, own_parts = piece_variant_pack(item, actor_pack(base), actor_pack(item), name, base)" in main_src and
          "piece_rows_many(table, kind, " in main_src and "new, k = piece_named(data, {h: renamed[h]}, base)" in main_src and
          "for base, look, of_boss in ((HEART, PIECE_LOOK, False), (CONTAINER, CONTAINER_LOOK, True)):" in main_src and
          main_src.index("piece_variant_pack(item") < main_src.index("    def shop_table(tbl):"),
          "the seed does not make the pieces' looks before the size table")
    print("FAIL" if failed else "PASS: a Piece of Heart shows the item it gives")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
