"""Bug 128 (the owner's run 2026-11-23): Saria's Song to Darunia after Dodongo's Cavern gave a talk, not his gift.
Get_StoneOfFire's switch on Get_StoneOfFire_IsAfter_SariaMelodyPlay_Exp sends a Link past that step to the talk; with
Quest rewards the seed puts a switch on HavePlayedEvent.Dm_Goron_0030 (the gift's scene played) in front of the talk,
so a Link still owed the gift gets the scene (DARUNIA_LATE), and the scene's request of the quest's DodongoCavernOpne
step runs only while the quest is not past it (DARUNIA_ORDER), as QUEST_ORDER does for the Fire quest. darunia_late_flow
was tried on the game's two flows by hand (2026-11-23: each changed once, a second run refused, the scene also after
the gift's item swap and quiet_scene; the new switch is reached from Get_StoneOfFire_PlayOcarina). Here: by source. No
game files.

python -I -B tests/test_rando_darunia_late.py
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools", "rando"))
import rando_seed as seed  # noqa: E402

failed = False


def check(ok, what):
    global failed
    if not ok:
        failed = True
        print("FAIL: " + what)


def main():
    check(seed.DARUNIA_LATE[:4] == ("Get_StoneOfFire", "Get_StoneOfFire_IsAfter_SariaMelodyPlay_Exp", "Dm_Goron_0030", "HavePlayedEvent.Dm_Goron_0030"),
          "not the ocarina's flow, the step, the gift's scene and its done flag")
    check(seed.DARUNIA_ORDER[:3] == ("Dm_Goron_0030", "Get_StoneOfFire", "DodongoCavernOpne"), "not the scene's step request")
    check(next(g for g in seed.GIFTS if g.key == "darunia").flow == seed.DARUNIA_LATE[2], "Darunia's gift is not the scene's")
    src = open(seed.__file__, encoding="utf-8").read()
    body = src[src.index("def darunia_late_flow(raw, name):"):]
    body = body[:body.index("\n\n\n")]
    check('owed = ask(label, "EventQueryIsGameDataBool", done, sw.data.cases[0].v, sw.data.cases[1].v)' in body and
          "sw.data.cases[0].v = owed" in body, "the talk's way is not asked whether the gift is still owed")
    check('param(e.data.cases[1].v, "EventName") == scene' in body and "if len(hits) != 1:" in body,
          "the switch is not the one whose false way plays the gift's scene, found once")
    check('guard = ask(label, "EventQueryIsGameDataBoolExp", "%s_IsAfter_%s_Exp" % (quest, step), t.data.nxt.v, t)' in body and
          "for h in holders:" in body, "the scene's step request is not guarded by the quest's step")
    check('any(e.name.startswith("WillowDarunia") for e in fc.events)' in body, "a flow changed already is not refused")
    main_src = src[src.index("\ndef main():"):]
    quests = main_src[main_src.index("if a.quests:   # (gifts kept when their quest is moved on first"):]
    quests = quests[:quests.index("    for saver_on, rel, saver in")]
    check("gift_files[rel] = darunia_late_flow(was, n)" in quests, "the seed does not write Darunia's flows with Quest rewards")
    check(main_src.index("darunia_late_flow(was, n)") < main_src.index("    if a.skip_cutscenes:\n        folder, talks, kept"),
          "the scene is not changed before Skip cutscenes quiets it")
    check(seed.FIXES_VERSION >= 81, "FIXES_VERSION not past 80")
    print("FAIL" if failed else "PASS: Darunia's gift is had after Dodongo's Cavern too")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
