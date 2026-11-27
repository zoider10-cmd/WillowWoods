"""A grotto's checks say their way in, the hole in the field (tools/rando/rando_seed.py way_in; bugs 149 and 153). No game data.

A grotto lies under its area's ground, its checks some 15 m to the side of the hole: the Tracker's maps and the minimap drew
them away from the hole. The game names each grotto with anchors (HidingHole_HoleEntrance where Link lands, HidingHole_
FieldEntranceGo the hole above it). Checked, with the places of the owner's seed:
- a landing is paired with the hole straight above it, each place once, a landing with no hole left out;
- a check is its nearest landing's when it is near and at the landing's height (Kakariko's grotto chest, the Graveyard's two
  graves each to its own, Hyrule Castle's Skulltula a metre over the landing); not Mido's house's chests, 5 m over Kokiri
  Forest's grotto, nor a check far off or in a folder without grottos;
- the list's line has the hole after where Link is put, its own place staying the line's place (the game's side finds a
  Gold Skulltula's and a pot's check by it), and a check in no grotto has no such field; the menu reads it into the place
  its maps draw; a seed being played gets it (FIXES_VERSION).

    python -I -B tests/test_rando_grotto_ways.py
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


def main():
    L, F = S.HOLE_LANDING, S.HOLE_FIELD
    yard = [(L + "01", (21.5, 91.2, 11.2)), (F + "01", (21.5, 103.0, 11.2)), (L + "02", (21.4, 90.7, 23.2)), (F + "02", (21.4, 103.1, 23.2)),
            (L + "01", (21.5, 91.2, 11.2)), (F + "01", (21.5, 103.0, 11.2)),          # (the adult's map has them too)
            (L + "03", (60.0, 80.0, 60.0)),                                          # (a landing with no hole over it)
            (F + "04", (-4.0, 103.0, -10.9)), ("HidingHole_HoleExit01", (21.5, 91.0, 12.0)), ("PlayerPos", (21.5, 120.0, 11.2))]
    holes = S.grottos(yard)
    check(holes == [((21.4, 90.7, 23.2), (21.4, 103.1, 23.2)), ((21.5, 91.2, 11.2), (21.5, 103.0, 11.2))], "the Graveyard's grottos: %r" % (holes,))
    check(S.way_in((38.3, 86.3, 11.2), holes) == (21.5, 103.0, 11.2), "the Hylian Shield's grave is not its own")
    check(S.way_in((21.4, 85.8, 39.3), holes) == (21.4, 103.1, 23.2), "the Piece of Heart's grave is not its own")
    check(S.way_in((-16.6, 108.0, -8.9), holes) is None and S.way_in((-6.0, 82.5, 77.7), holes) is None, "a check above the ground, or far off, is in a grotto")
    kak = S.grottos([(L, (-26.8, 82.9, 12.4)), (F, (-26.8, 101.2, 12.4))])
    check(S.way_in((-41.7, 79.7, 11.4), kak) == (-26.8, 101.2, 12.4), "Kakariko's grotto chest has no way in")
    castle = S.grottos([(L, (35.9, 100.1, -106.2)), (F, (35.9, 117.3, -106.2))])
    check(S.way_in((39.0, 101.1, -116.1), castle) == (35.9, 117.3, -106.2) and S.way_in((23.7, 108.2, -63.2), castle) is None,
          "Hyrule Castle's storms grotto: its Skulltula is not in it, or the pots by the bridge are")
    forest = S.grottos([(L, (-51.9, 107.5, -62.8)), (F, (-51.9, 121.6, -62.8))])
    check(S.way_in((-70.0, 112.3, -72.0), forest) is None, "Mido's house's chests are in the grotto under them")
    check(S.way_in((1.0, 2.0, 3.0), None) is None and S.way_in((1.0, 2.0, 3.0), []) is None, "a folder without grottos")
    # ---- the list's lines ----
    lines = S.check_lines([("KakarikoVillage", (-41.7, 79.7, 11.4), "CA", frozenset(), "Chest (blue rupee)", 0xb30e25a1c5e03c1e, "TBox_Rupee_Blue", (-41.7, 79.7, 12.7)),
                           ("KakarikoVillage", (5.6, 130.2, 41.4), "A", frozenset(), "Chest (purple rupee)", 0xb588e3f93990af69, "TBox_Rupee_Purple")],
                          [("HyruleCastle", (39.0, 101.1, -116.1), "CA", frozenset(), "Gold Skulltula", 0x7f28485fa5d3688f, "Item_Token_Gold")],
                          [("HyruleField", (25.0, 129.9, 22.1), "A", frozenset(), "A scrub", None, "Obj_Heart_Piece")],
                          holes={"KakarikoVillage": kak, "HyruleCastle": castle, "HyruleField": S.grottos([(L, (39.9, 134.2, 26.6)), (F, (39.9, 148.3, 26.6))])})
    by = {l.split("|")[1]: l.split("|") for l in lines[1:]}
    chest, plain, skull, scrub = by["Chest (blue rupee)"], by["Chest (purple rupee)"], by["Gold Skulltula"], by["A scrub"]
    check(chest[4] == "-41.7 79.7 11.4" and chest[8] == "-41.7 79.7 12.7" and chest[9] == "-26.8 101.2 12.4", "a grotto chest's line: %r" % (chest,))
    check(len(plain) == 8, "a check in no grotto has a way in: %r" % (plain,))
    check(skull[4] == "39.0 101.1 -116.1" and skull[8] == "39.0 101.1 -116.1" and skull[9] == "35.9 117.3 -106.2", "a grotto Skulltula's line: %r" % (skull,))
    check(scrub[6] == "-" and scrub[8] == "25.0 129.9 22.1" and scrub[9] == "39.9 148.3 26.6", "a grotto gift's line: %r" % (scrub,))
    same = S.check_lines([("KakarikoVillage", (-41.7, 79.7, 11.4), "CA", frozenset(), "Chest (blue rupee)", 0xb30e25a1c5e03c1e, "TBox_Rupee_Blue")], [])
    check(len(same[1].split("|")) == 8, "without the grottos a line has a way in")
    check(S.FIXES_VERSION >= 106, "no fixes version for it: a seed being played would not get it")
    src = (ROOT / "tools" / "rando" / "rando_seed.py").read_text(encoding="utf-8")
    check("hole_marks[folder] += hole_anchors(data)" in src and "holes={folder: grottos(marks_) for folder, marks_ in hole_marks.items()}" in src,
          "the map files' grotto anchors do not reach the list")
    menu = (ROOT / "gpu" / "vk" / "vk_menu.cpp").read_text(encoding="utf-8")
    check("%f %f %f|%f %f %f\", k.area, k.kind," in menu and "&k.stand[2], &k.at[0], &k.at[1], &k.at[2]);" in menu and
          "if (got < 16) memcpy(k.at, k.pos, sizeof k.at);" in menu, "the menu does not read a check's way in")
    host = (ROOT / "host" / "hos_main.c").read_text(encoding="utf-8")
    check("&oot_checks[oot_check_count].place[0]," in host, "the game's side no longer reads a check's own place")
    print("PASS: a grotto's checks' way in")


if __name__ == "__main__":
    main()
