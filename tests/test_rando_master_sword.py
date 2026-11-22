"""Shuffle the Master Sword (rando_master_sword): the sword an item of the shuffle, the pedestal's first trip through
time a place, and an adult's places asking for the sword (tools/rando/rando_seed.py MASTER, MASTER_GIFT, pedestal_holds,
door_need; host/hos_main.c oot_pedestal_give). Read from the sources and the seed tool's own functions: no game files."""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "tools", "rando"))
import rando_seed as seed  # noqa: E402

failed = []


def check(ok, what):
    if not ok:
        failed.append(what)
        print("FAIL: " + what)


def read(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


def main():
    # ---- the rules: an adult's place asks for the sword with the setting, and only then ----
    adult_rule = seed.ADULT | {seed.BOW}
    try:
        seed.MASTER_SHUFFLED = False
        off = seed.door_need(adult_rule, True)
        child_off = seed.door_need(seed.CHILD, False)
        seed.MASTER_SHUFFLED = True
        on = seed.door_need(adult_rule, True)
        partial = seed.door_need(frozenset((seed.BOW,)), True)
        child_on = seed.door_need(seed.CHILD, False)
    finally:
        seed.MASTER_SHUFFLED = False
    check(seed.MASTER not in off and seed.MASTER in on and on - {seed.MASTER} == off,
          "an adult's place does not ask for the Master Sword with the setting, or asks for more than it")
    check(seed.MASTER in partial, "an adult's place whose rule is not the whole of ADULT does not ask for the sword")
    check(seed.MASTER not in child_on and child_on == child_off, "a child's place asks for the Master Sword")

    # ---- what the pedestal may hold: what the pouch takes by name ----
    yes = ("Item_Longshot", "Item_Boomerang", "Weapon_Sword_Master", "Item_DekuStickBundle_Small", "Item_Bottle")
    no = ("TBox_Rupee_Red", "Item_Melody_ZeldaLullaby", "Item_Dungeon_SmallKey", seed.TOKEN, "Item_FairyBless_MPDouble",
          "Obj_Heart_Container", "Obj_Armor_Zora")
    check(all(seed.pedestal_holds(i) for i in yes) and not any(seed.pedestal_holds(i) for i in no),
          "the pedestal may hold what the pouch does not take by name, or not what it does")

    # ---- the gift, its place and its code ----
    g = seed.MASTER_GIFT
    check(g.item == seed.MASTER == "Weapon_Sword_Master" and g.flow == "" and g.area == "Market" and g.need == seed.CHILD,
          "the pedestal is not a child's place in the Market without a scene, holding the Master Sword")
    ages, at = seed.GIFT_PLACES["master_sword"]
    check(ages == "C" and abs(at[0] - 137.6) < 0.5 and abs(at[2] + 34.0) < 0.5,
          "the pedestal's place is not the sword's (the game's side finds the check by it)")
    check(seed.CHECK_CODES.get(seed.MASTER) == "MW", "the Tracker has no code for the Master Sword")
    menu = read("gpu", "vk", "vk_menu.cpp")
    check('{"MW", "Master Sword", {"Master Sword"}},' in menu, "the menu does not know the Tracker's code MW")
    codes = list(seed.CHECK_CODES.values())
    menu_codes = re.findall(r'^\s*\{"([A-Z]{2})", "', menu.split("constexpr LogicItem kLogicItems[] = {", 1)[1].split("};", 1)[0], re.M)
    check(codes == menu_codes, "the seed tool's codes and the menu's are not the same list in the same order")

    # ---- the seed's steps ----
    script = read("tools", "rando", "rando_seed.py")
    check('a.master_sword = a.master_sword or ini["rando_master_sword"] == 1' in script and
          "if a.master_sword and not (a.open_door or a.door_song):" in script and '(" master sword 2" if a.master_sword else "")' in script,
          "the setting is not read, not left off without Open Door of Time, or not in the seed's stamp")
    check("spots[gift_hash(MASTER_GIFT.key)] = [MASTER_GIFT.area, MASTER_GIFT.item, None, None, \"gift\", MASTER_GIFT.name, \"\"]" in script and
          "PROGRESSION = PROGRESSION | {MASTER}" in script and
          "holds[gift_hash(MASTER_GIFT.key)] = frozenset(i for i in every if pedestal_holds(i))" in script and
          'if s[4] in ("shop", "scrub"):' in script,
          "the pedestal is not a place of the shuffle, the sword not a gating item, or it may be put on a shelf")
    check("if MASTER_SHUFFLED:   # (the pedestal's few kinds before the shelves'" in script,
          "the spots with few kinds are not filled first with the setting (the pedestal found nothing it may hold)")

    # ---- the game's side ----
    host = read("host", "hos_main.c")
    check("static int oot_pedestal_give(Ctx *c) {" in host and
          "const int shuffled = child ? oot_pedestal_give(c) : 0;" in host and
          "if (child && shuffled == 0 && oot_pouch_count(c, \"Weapon_Sword_Master\") == 0)" in host and
          "const int status = oot_pouch_change(c, item, 1);" in host and "oot_gamedata_keyed_set_bool(c, key, 1);" in host and
          "if (given) return 1;" in host,
          "the first trip through time does not give the pedestal's item once, or still gives the sword with the setting")

    # ---- the setting's rows ----
    header = read("gpu", "vk", "oot_rando.h")
    launcher = read("launcher", "Launcher.cs")
    check('X(MASTER_SWORD, "Shuffle the Master Sword", "rando_master_sword",' in header and
          '"rando_master_sword", "Shuffle the Master Sword", new[] { "Off", "On" }, new[] { 0, 1 },' in launcher and
          '"rando_chest_size", "rando_master_sword"' in launcher,
          "the setting has no row in the game's table or the launcher's, or the launcher does not show it")
    no_item = launcher.split("NoItemKeys = new HashSet<string> {", 1)[1].split("};", 1)[0]
    check('"rando_master_sword"' not in no_item, "the setting is counted as one that moves no item")
    print("FAIL" if failed else "PASS: Shuffle the Master Sword")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
