"""The bean-soil Gold Skulltulas without bugs (asked 2026-11-24): each of the ten stands in its child map only while its
soil's flag (Gimmick_MagicBeanSoil_<area>, set by bugs let out on it) is set; tools/rando/rando_seed.py soil_by_bottle
makes it wait for IsGet.Item_Bottle instead, in every seed (SOIL_FILES), and the seed stops if it finds other than ten.
Game-free: a made-up map file, and the seed tool's source."""
import collections
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools", "rando"))
import rando_seed as S  # noqa: E402


def actor(gyaml, flag=None, soil=None):
    d = collections.OrderedDict(Gyaml=("string", gyaml))
    if soil is not None:
        d["Dynamic"] = ("dict", collections.OrderedDict(Enemy_Skulltula_Gold_IsMagicBeanSoil=(0xD0, (1 if soil else 0).to_bytes(4, "little"))))
    if flag:
        d["Presence"] = ("dict", collections.OrderedDict(FlagName=("string", flag)))
    return ("dict", d)


def main():
    tree = ("dict", collections.OrderedDict(Actors=("array", [
        actor("Enemy_Skulltula_Gold", "Gimmick_MagicBeanSoil_KokiriForest", True),   # (the soil's: changed)
        actor("Enemy_Skulltula_Gold", "SomeOtherFlag", True),                       # (another flag: kept)
        actor("Enemy_Skulltula_Gold", None, False),                                 # (a plain one: kept)
        actor("Obj_MagicBeanSoil", "Gimmick_MagicBeanSoil_KokiriForest")])))        # (not a Skulltula: kept)
    data, n = S.soil_by_bottle(S.byml_build(tree, 7))
    got, _ = S.byml_parse(data)
    flags = [a[1]["Presence"][1]["FlagName"][1] if "Presence" in a[1] else None for a in got[1]["Actors"][1]]
    assert n == 1 and flags == ["IsGet.Item_Bottle", "SomeOtherFlag", None, "Gimmick_MagicBeanSoil_KokiriForest"], (n, flags)
    assert S.SOIL_COUNT == 10 and len(S.SOIL_FILES) == 9 and all(f.endswith("_Child_Static.bcett.byml.zs") for f in S.SOIL_FILES)
    assert S.SOIL_BOTTLE == "IsGet." + S.BOTTLE
    src = open(S.__file__, encoding="utf-8").read()
    main_src = src[src.index("\ndef main():"):]
    assert ("for rel in SOIL_FILES if a.soil_bottle else ():" in main_src and "changed[rel], k = soil_by_bottle(data)" in main_src and
            "if a.soil_bottle and soils != SOIL_COUNT:" in main_src and
            main_src.index("soil_by_bottle(data)") < main_src.index("    # ---- the size table ----")), "the soil Skulltulas do not wait for a bottle with the setting on"
    # (a Quality of life setting, 2026-11-24: Soil Skulltulas without bugs, off by default, moves no item)
    assert '"rando_soil_bottle": 0' in src and 'a.soil_bottle = ini["rando_soil_bottle"] != 0' in src, "not read from the options, off by default"
    assert '(a.soil_bottle, " soil bottle")' in src, "it is not on the stamp's second line (moves no item)"
    header = open(os.path.join(ROOT, "gpu", "vk", "oot_rando.h"), encoding="utf-8").read()
    order = re.findall(r"^    X\(([A-Z_]+),", header, re.M)
    assert order[-1] == "SOIL_BOTTLE" and order.index("SOIL_BOTTLE") > order.index("FAST_PUSH"), "the in-game menu's row is not after the ones before it"
    launcher = open(os.path.join(ROOT, "launcher", "Launcher.cs"), encoding="utf-8").read()
    assert 'new object[] { "rando_soil_bottle", "Soil Skulltulas without bugs", new[] { "Off", "On" }, new[] { 0, 1 },' in launcher, "no launcher row"
    no_item = launcher[launcher.index("NoItemKeys = new HashSet<string>"):launcher.index("static bool MovesNoItem")]
    assert '"rando_soil_bottle"' in no_item, "the launcher does not count it as moving no item"
    qol = launcher[launcher.index('Title = "QUALITY OF LIFE"'):]
    assert '"rando_soil_bottle"' in qol[:qol.index("} },")], "it is not in the launcher's Quality of life section"
    print("PASS: the bean-soil Gold Skulltulas are there for a bottle, no bugs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
