"""Gifts kept when their quest is moved on first, and the Fire quest never moved back (OOTRR 92dbffd, 2026-11-22).

tools/rando/rando_seed.py quest_order_flow puts, in front of the rolling Goron's and thawed King Zora's later talks, a
branch that gives an adult the gift part while the gift's done flag is false (QUEST_LATE); guards SageOfFire's three
step requests so each runs only while the quest is not past it (QUEST_ORDER); and makes the Crater's exit to Goron City
set the Goron's creation flag for an adult (QUEST_MAKE). The edit itself is checked on the game's flows by the seed
tool's write (it stops with nothing written if a flow is not as expected); here, by source and constants.

python -I -B tests/test_rando_quest_order.py
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "rando"))
import rando_seed as seed  # noqa: E402

failed = False


def check(ok, what):
    global failed
    if not ok:
        failed = True
        print("FAIL: " + what)


def main():
    late = {l[0]: l for l in getattr(seed, "QUEST_LATE", ())}
    goron, zora = late.get("Npc_Goron_DaruniaJr_Adult"), late.get("Npc_Zora_KingZora_adult")
    check(goron is not None and set(goron[1]) == {"Talk", "Npc_Goron_DaruniaJr_Step3_on", "SageOfFire_IsCompleted_Exp_Talk"} and
          goron[2] is None and goron[3] == "SageOfFire_Step02_DoorOpen" and
          goron[4] == ("SageOfFire", "Step02_Npc_Goron_DaruniaJr_Adult_Talk"),
          "the rolling Goron's later talks do not give his gift part while it is owed")
    check(zora is not None and zora[1] == ("Talk",) and zora[2] == "SageOfWater_IsCompleted_Exp" and
          zora[3] == "SageOfWater_KingZora_adult_Talk_Event198" and zora[4] == ("SageOfWater", "Safety_Entry"),
          "King Zora's thawed talk does not give his gift part while it is owed (after the Water Temple only)")
    check(getattr(seed, "QUEST_ORDER", None) == ("SageOfFire", "SageOfFire", ("StopDaruniaJr", "TalkDaruniaJr", "MoveStatue"), "WillowOrder"),
          "the Fire quest's three step requests are not guarded (a gift part could move the quest back)")
    check(getattr(seed, "QUEST_MAKE", None) == ("Dm_SY_BancChangeGo", "DeathMountainCrater_ToGoronCity", "SageOfFire_GenerateDaruniaJr",
                                                "WillowLateGoronMake"),
          "the Crater's exit to Goron City does not make the rolling Goron for an adult")
    src = (ROOT / "tools" / "rando" / "rando_seed.py").read_text(encoding="utf-8")
    check("def quest_order_flow(raw, name):" in src and "gift_files[rel] = quest_order_flow(was, n)" in src and
          "gift_sizes[rel[:-3]] = len(gift_files[rel])" in src and
          src.index("gift_files[rel] = quest_order_flow(was, n)") < src.index("    # ---- the size table ----"),
          "the flows are not changed before the size table is made, or their new sizes are not given to it")
    check('"Sequence_IsChildhood", old, then)' in src and "p._sub_flow_event_indices.append(at)" in src,
          "the branch is not for an adult only, or the entry does not list its new sub-call")
    print("FAIL" if failed else "PASS: the Goron's and King Zora's gifts kept when their quest is moved on first")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
