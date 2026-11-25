"""Lake Hylia's Fire Arrows a check (asked 2026-11-23, share/todo.md; placement 28, tools/rando/rando_seed.py SUN_ARROWS):
the Fire Arrows lying on the lake's island after the sun's shot take part as a lying Piece of Heart does, whatever the
Heart Pieces setting: their Fire Arrows in the pool, their rule the other logic's "LH Sun" asking for more (the Water
Temple's boss beaten and the Bow), and the game's side giving the seed's item at their pick-up (host/hos_main.c
oot_is_sun, by the check's name). Game-free: the sources.

python -I -B tests/test_rando_sun_arrows.py
"""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools", "rando"))
import rando_seed as S  # noqa: E402


def main():
    assert S.SUN_ARROWS == 0x3fd1b7093f47892e and S.SUN_ACTOR == "Obj_Arrow_Fire" and S.SUN_ITEM == "Item_Arrow_Fire"
    assert S.SUN_FROM == 28 and S.PLACEMENT >= S.SUN_FROM, "the placement that adds the check is not the seed tool's"
    src = open(S.__file__, encoding="utf-8").read()
    main_src = src[src.index("\ndef main():"):]
    assert "if placement >= SUN_FROM and folder == SUN_FOLDER:" in main_src and "suns.add(h)" in main_src, "the arrows are not read from the map"
    assert "for h in pieces if a.heart_pieces or h in suns)" in main_src, "the arrows take part only with the Heart Pieces setting"
    assert '(boss_need("WaterTemple") | {BOW}) if h in suns else' in main_src, "the arrows' rule is not the Water Temple's and the Bow"
    assert "SUN_ITEM if h in suns else HEART" in main_src, "the arrows' spot does not hold its Fire Arrows of its own"
    assert main_src.count("h not in suns") == 2, "the arrows are given a Piece of Heart's look (the scene binds the actor by name)"
    assert "SUN_NAME if h in suns else" in main_src, "the arrows' check is not named for the game's side"
    host = open(os.path.join(ROOT, "host", "hos_main.c"), encoding="utf-8").read()
    want = re.search(r'#define OOT_SUN_CHECK "([^"]+)"', host)
    assert want and S.SUN_NAME.startswith(want.group(1)), "the game's side does not know the arrows' check by its name"
    assert 'return !strcmp(name, "Obj_Arrow_Fire") || !strcmp(name, "Item_Arrow_Fire");' in host
    assert "} else if (oot_is_sun(name) && c->x[30] != 0x828d50acULL && oot_piece_gives(gives, sizeof gives, 0) && strcmp(gives, name)) {" in host, \
        "the arrows' pick-up does not give the seed's item"
    print("PASS: Lake Hylia's Fire Arrows are a check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
