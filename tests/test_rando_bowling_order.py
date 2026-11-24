"""Bombchu Bowling: the first two wins give the two checks (asked 2026-11-23, share/todo.md). The game's prizes come by
three questions in a row (won once before? twice? three times?): 10 Bombchus, the bag, the Piece of Heart, then a red
rupee. bowling_order_flow sends the 1st win to the bag's prize, the 2nd to the Piece of Heart's and the 3rd to the
Bombchus, on every seed whose gifts put the bowling's flow in (from fixes 88). The flow is built here from the game's
own shape with the flow library the seed tool uses (no game files): the three questions, the bag's question and the
hand-overs.

python -I -B tests/test_rando_bowling_order.py
"""
import io
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


def build(evfl):
    """a small MiniGame_BombchuBowling: GetPrise's questions and prizes as the game has them"""
    from evfl.common import ActorIdentifier, StringHolder
    flow = evfl.EventFlow()
    flow.name = "MiniGame_BombchuBowling"
    fc = evfl.Flowchart()
    fc.name = "MiniGame_BombchuBowling"
    flow.flowchart = fc

    def actor(name):
        a = evfl.Actor()
        a.identifier = ActorIdentifier(name)
        fc.actors.append(a)
        return a
    data, pouch, common = actor("GameDataActor"), actor("PouchSystemActor"), actor("EventSystemActor")
    query = StringHolder("EventQueryIsGameDataBool")
    data.queries.append(query)
    pq = StringHolder("EventQueryIsExistInPouch")
    pouch.queries.append(pq)

    def event(name, d):
        e = evfl.Event()
        e.name, e.data = name, d
        fc.events.append(e)
        return e

    def handover(name, item):
        d = evfl.SubFlowEvent()
        d.res_flowchart_name, d.entry_point_name = "NpcCommon", "NpcCommon_HandOver_NpcToPlayer_NoDisplay"
        d.params = evfl.Container()
        d.params.data["ReveiveItem"] = item
        return event(name, d)

    def ask(name, actor_, q, params, yes, no):
        d = evfl.SwitchEvent()
        d.actor.v, d.actor_query.v = actor_, q
        d.params = evfl.Container()
        d.params.data.update(params)
        e = event(name, d)
        for k, to in ((0, yes), (1, no)):
            d.cases[k] = evfl.util.RequiredIndex()
            d.cases[k].v = to
        return e
    rupee, heart = handover("Rupee", "Obj_Rupee_Red"), handover("Heart", "Obj_Heart_Piece")
    medium, large = handover("BagMedium", "Item_BombBag_Medium"), handover("BagLarge", "Item_BombBag_Large")
    chus = handover("Chus", "Item_BombchuBundle_Medium")
    bag = ask("Bag", pouch, pq, {"Actor": "Item_BombBag_Medium", "Num": 1}, large, medium)
    third = ask("Third", data, query, {"GameDataName": "MiniGame_BombchuBowling_ClearThirdTime", "Index": -1}, rupee, heart)
    second = ask("Second", data, query, {"GameDataName": "MiniGame_BombchuBowling_ClearSecondTime", "Index": -1}, third, bag)
    first = ask("First", data, query, {"GameDataName": "MiniGame_BombchuBowling_ClearFirstTime", "Index": -1}, second, chus)
    p = evfl.EntryPoint("MiniGame_BombchuBowling_GetPrise")
    p.main_event.v = first
    fc.entry_points.append(p)
    out = io.BytesIO()
    flow.write(out)
    return out.getvalue()


def main():
    try:
        evfl = seed.evfl_module()
    except (SystemExit, ImportError) as e:
        print("SKIP: no flow library (%s)" % e)
        return 0
    src = open(seed.__file__, encoding="utf-8").read()
    check(hasattr(seed, "bowling_order_flow") and getattr(seed, "BOWLING_FLOW", "").endswith("/MiniGame_BombchuBowling.bfevfl.zs"),
          "no bowling_order_flow")
    if failed:
        print("FAIL")
        return 1
    out = seed.bowling_order_flow(build(evfl))
    flow = evfl.EventFlow()
    flow.read(out)
    ev = {e.name: e for e in flow.flowchart.events}
    gets = lambda n, k: ev[n].data.cases[k].v.name
    check(gets("First", 1) == "Bag", "the 1st win does not go to the bag's prize (%s)" % gets("First", 1))
    check(gets("Second", 1) == "Heart", "the 2nd win does not go to the Piece of Heart (%s)" % gets("Second", 1))
    check(gets("Third", 1) == "Chus", "the 3rd win does not go to the 10 Bombchus (%s)" % gets("Third", 1))
    check(gets("First", 0) == "Second" and gets("Second", 0) == "Third" and gets("Third", 0) == "Rupee",
          "the questions' 'won before' ways changed, or later wins no longer give the red rupee")
    try:
        seed.bowling_order_flow(out)
        check(False, "a flow changed already is changed again (its prizes swapped back)")
    except ValueError:
        pass
    check("if BOWLING_FLOW in gift_files:" in src and src.index("if BOWLING_FLOW in gift_files:") < src.index("    # ---- the size table ----"),
          "the seed does not change the bowling's flow with its gifts, before the size table")
    check(seed.FIXES_VERSION >= 88, "no fixes version for it: a seed being played would not get it")
    print("FAIL" if failed else "PASS: Bombchu Bowling's first two wins give the bag's and the Piece of Heart's checks")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
