"""Shuffle Dampe's Hookshot (rando_dampe_hookshot): the race's Hookshot chest a place asked about by name, the Hookshot a
gating item, and the places the audit found it needed asking for it or the Longshot (tools/rando/rando_seed.py HOOK,
hook_need, hook_asks, race_words; share/hookshot-audit.md). Read from the sources and the seed tool's own functions:
no game files."""
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
    S = seed
    # ---- the rule: the Hookshot or the Longshot ----
    rule = S.ADULT | {S.BOW}
    made = S.each(S.hook_need, rule)
    check(isinstance(made, S.Either) and set(made) == {rule | {S.HOOK}, rule | {S.LONG}},
          "a place that needs the Hookshot does not take the Hookshot or the Longshot")
    check(S.each(S.hook_need, rule | {S.LONG}) == rule | {S.LONG}, "a place that asks for the Longshot asks for more")
    check(S.met(made, set(rule | {S.LONG})) and S.met(made, set(rule | {S.HOOK})) and not S.met(made, set(rule)),
          "the Longshot alone, or the Hookshot alone, does not meet the rule, or neither is needed")
    either = S.Either((rule, S.ADULT | {S.HAM}))
    check(set(S.each(S.hook_need, either)) == {rule | {S.HOOK}, rule | {S.LONG}, S.ADULT | {S.HAM, S.HOOK}, S.ADULT | {S.HAM, S.LONG}},
          "each way of a rule with ways is not given the Hookshot or the Longshot")
    # (with Progressive items the Longshot is the family's second: the way of the Longshot asks for both)
    check(S.progressive_need(frozenset((S.LONG,)), frozenset((S.HOOK, S.LONG))) == frozenset((S.HOOK, S.LONG)),
          "with Progressive items the Longshot's way does not ask for the Hookshot under it")

    # ---- where it is asked for (the audit) ----
    check(S.hook_asks("ForestTemple") and S.hook_asks("FireTemple") and S.hook_asks("Graveyard", S.DAMPE_EVENT) and
          S.hook_asks("DeathMountainCrater", key="song_bolero") and S.hook_asks("GoronCity", h=0xfbbc2d490276c68e),
          "a place the audit found needs the Hookshot does not ask for it")
    check(not any(S.hook_asks(a) for a in ("KakarikoVillage", "HyruleField", "WaterTemple", "IceCavern", "Graveyard", "GoronCity",
                                           "DeathMountainCrater", "DodongoCavern")),
          "a place the audit found does not need the Hookshot asks for it")
    check(S.DAMPE_EVENT == "MiniGame_DampeRace_OpenGoalTBox" and 0x4ccffbd5778b67e2 in S.DAMPE_RACE_CHESTS,
          "the race's chests are not known by their event (the Piece of Heart's asks for the Hookshot too: the tomb)")

    # ---- the chest takes part with the setting, and only then ----
    c = S.Chest(S.DAMPE_HOOK_CHEST, "Obj_TBox_A_02_NoBake", None, None, S.HOOK,
                ("GetEventName",), (-6.0, 82.5, 77.7), S.DAMPE_EVENT)
    try:
        S.HOOK_SHUFFLED = False
        off = S.stays_why(c, False)
        S.HOOK_SHUFFLED = True
        on = S.stays_why(c, False)
    finally:
        S.HOOK_SHUFFLED = False
    check(off is not None and on is None, "the race's Hookshot chest takes part without the setting, or not with it")

    # ---- what the race asks for: the chest's item, by its flags' name ----
    check(S.race_words(S.HOOK) == {}, "the race's flow is changed when its chest keeps the Hookshot")
    check(S.race_words("Item_Hammer") == {S.HOOK: "Item_Hammer", S.LONG: "Item_Hammer"},
          "the race's questions of both hookshots are not made to name the chest's item")
    check(S.race_words("Item_HeavyBoot") == {S.HOOK: "Armor_Adult_HeavyBoot", S.LONG: "Armor_Adult_HeavyBoot"},
          "the race's questions do not name an item by its flags' name (the pouch's)")

    # ---- the seed's steps ----
    script = read("tools", "rando", "rando_seed.py")
    check('a.dampe_hookshot = a.dampe_hookshot or ini["rando_dampe_hookshot"] == 1' in script and
          '(" dampe hookshot 1" if a.dampe_hookshot else "")' in script and '"rando_dampe_hookshot": 0}' in script,
          "the setting is not read, has no default, or is not in the seed's stamp")
    check("PROGRESSION = PROGRESSION | {HOOK}" in script and
          "lesson_only[DAMPE_HOOK_CHEST] = (lesson_safe," in script and
          "needs[h] = each(hook_need, needs[h])" in script,
          "the Hookshot is not a gating item, the race's chest may hold anything, or the rules do not ask for it")
    check("gift_items(unpack(open(os.path.join(romfs, *rel.split(\"/\")), \"rb\").read(), zs, dicts), words, kinds=(0, 1))" in script and
          'ainb_exp_swap(data, "IsGet." + HOOK, "IsGet." + lesson_flag(race_now))' in script,
          "the race's flow and the tomb's logic are not made to ask for the chest's item")
    check(S.DAMPE_FLOW == "Event/EventFlow/MiniGame_DampeRace.bfevfl.zs" and len(S.DAMPE_LOGIC) == 2,
          "the race's flow or the tomb's two logic files are not the ones read")

    # ---- the Tracker's code, in both lists ----
    check(S.CHECK_CODES.get(S.HOOK) == "HS", "the Tracker has no code for the Hookshot")
    menu = read("gpu", "vk", "vk_menu.cpp")
    check('{"HS", "Hookshot", {"Hookshot", "Longshot"}},' in menu, "the menu does not know HS, or the Longshot does not count for it")
    codes = list(S.CHECK_CODES.values())
    menu_codes = re.findall(r'^\s*\{"([A-Z]{2})", "', menu.split("constexpr LogicItem kLogicItems[] = {", 1)[1].split("};", 1)[0], re.M)
    check(codes == menu_codes, "the seed tool's codes and the menu's are not the same list in the same order")

    # ---- the setting's rows ----
    header = read("gpu", "vk", "oot_rando.h")
    launcher = read("launcher", "Launcher.cs")
    check('X(DAMPE_HOOKSHOT, "Shuffle Dampe\'s Hookshot", "rando_dampe_hookshot",' in header and
          '"rando_dampe_hookshot", "Shuffle Dampe\'s Hookshot", new[] { "Off", "On" }, new[] { 0, 1 },' in launcher and
          '"rando_master_sword", "rando_dampe_hookshot" } },' in launcher,
          "the setting has no row in the game's table or the launcher's, or the launcher does not show it")
    no_item = launcher.split("NoItemKeys = new HashSet<string> {", 1)[1].split("};", 1)[0]
    check('"rando_dampe_hookshot"' not in no_item, "the setting is counted as one that moves no item")
    print("FAIL" if failed else "PASS: Shuffle Dampe's Hookshot")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
