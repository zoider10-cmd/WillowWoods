"""Gerudo guards don't jail Link (rando_gerudo_guards, asked 2026-11-23, share/todo.md): a Gerudo guard who catches adult
Link at the fortress goes back to her post and he stays where he is. gerudo_guards_pass makes SageOfSpirit's two
"caught" entries (GerudoFortress_GotoPrison_Alert and _Suprise) the guard's way home (Npc_EventStarter's
EventWarpToHomeMatrix, as the castle's guards have it) and the lifted alert, and nothing else: no talk, no cell. The flow
is built here in the game's shape with the flow library the seed tool uses (no game files). Then the wiring: the
setting read (off by default), on the stamp's line of settings that move no item, the in-game menu's row last, the
launcher's row in its Quality of life section.

python -I -B tests/test_rando_gerudo_guards.py
"""
import io
import os
import re
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
    """a small SageOfSpirit: the caught entries' start (talk, dark, the cell) and the lifted alert after it"""
    from evfl.common import ActorIdentifier, StringHolder
    flow = evfl.EventFlow()
    flow.name = "SageOfSpirit"
    fc = evfl.Flowchart()
    fc.name = "SageOfSpirit"
    flow.flowchart = fc

    def actor(name, *acts):
        a = evfl.Actor()
        a.identifier = ActorIdentifier(name)
        for n in acts:
            a.actions.append(StringHolder(n))
        fc.actors.append(a)
        return a
    starter = actor("Npc_EventStarter", "EventTalk")
    player = actor("Player_Event", "EventPlayerWarpToStarterLinkAnchor")
    system = actor("GameSystemActor", "EventAIScheduleNPCForceSecurityLifted")

    def action(name, who, act, nxt=None, **params):
        e = evfl.Event()
        e.name = name
        e.data = evfl.ActionEvent()
        e.data.actor.v = who
        e.data.actor_action.v = [h for h in who.actions if h.v == act][0]
        e.data.params = evfl.Container()
        e.data.params.data.update(params)
        e.data.nxt.v = nxt
        fc.events.append(e)
        return e
    lifted = action("Lifted", system, "EventAIScheduleNPCForceSecurityLifted")
    cell = action("Cell", player, "EventPlayerWarpToStarterLinkAnchor", lifted, ActorName="DestinationAnchor")
    talk = action("Talk", starter, "EventTalk", cell, MessageId="AlertTalkFirst")
    for name in ("GerudoFortress_GotoPrison_Alert", "GerudoFortress_GotoPrison_Suprise"):
        p = evfl.EntryPoint(name)
        p.main_event.v = talk
        fc.entry_points.append(p)
    out = io.BytesIO()
    flow.write(out)
    return out.getvalue()


def main():
    src = open(seed.__file__, encoding="utf-8").read()
    check(hasattr(seed, "gerudo_guards_pass") and getattr(seed, "GERUDO_GUARDS_FLOW", "") == "Event/EventFlow/SageOfSpirit.bfevfl.zs",
          "no gerudo_guards_pass")
    try:
        evfl = seed.evfl_module()
    except (SystemExit, ImportError) as e:
        evfl = None
        print("SKIP (the flow edit): no flow library (%s)" % e)
    if evfl is not None and not failed:
        out = seed.gerudo_guards_pass(build(evfl))
        flow = evfl.EventFlow()
        flow.read(out)
        fc = flow.flowchart
        for p in fc.entry_points:
            steps, e = [], p.main_event.v
            while e is not None and len(steps) < 10:
                steps.append("%s.%s" % (e.data.actor.v.identifier.name, e.data.actor_action.v.v))
                if e.data.actor_action.v.v == "EventWarpToHomeMatrix":
                    check(e.data.params.data.get("IsWaitEnd") is True, "the way home does not wait for its end, as the castle's does")
                e = e.data.nxt.v
            check(steps == ["Npc_EventStarter.EventWarpToHomeMatrix", "GameSystemActor.EventAIScheduleNPCForceSecurityLifted"],
                  "%s is not the guard's way home and the lifted alert alone: %s" % (p.name, steps))
        try:
            seed.gerudo_guards_pass(out)
            check(False, "a flow changed already is changed again")
        except ValueError:
            pass
    main_src = src[src.index("\ndef main():"):]
    check("gift_files[GERUDO_GUARDS_FLOW] = gerudo_guards_pass(was)" in main_src
          and main_src.index("gerudo_guards_pass(was)") < main_src.index("    # ---- the size table ----"),
          "the seed does not write the fortress's flow with the setting on, before the size table")
    check('"rando_gerudo_guards": 0' in src and 'a.gerudo_guards = ini["rando_gerudo_guards"] != 0' in src, "not read from the options, off by default")
    check('(a.gerudo_guards, " gerudo guards pass")' in src, "it is not on the stamp's second line (moves no item)")
    header = open(os.path.join(ROOT, "gpu", "vk", "oot_rando.h"), encoding="utf-8").read()
    order = re.findall(r"^    X\(([A-Z_]+),", header, re.M)
    check("GERUDO_GUARDS" in order and order.index("GERUDO_GUARDS") > order.index("SOIL_BOTTLE"), "the in-game menu's row is not after the ones before it")
    launcher = open(os.path.join(ROOT, "launcher", "Launcher.cs"), encoding="utf-8").read()
    check("""new object[] { "rando_gerudo_guards", "Gerudo guards don't jail Link", new[] { "Off", "On" }, new[] { 0, 1 },""" in launcher, "no launcher row")
    no_item = launcher[launcher.index("NoItemKeys = new HashSet<string>"):launcher.index("static bool MovesNoItem")]
    check('"rando_gerudo_guards"' in no_item, "the launcher does not count it as moving no item")
    qol = launcher[launcher.index('Title = "QUALITY OF LIFE"'):]
    check('"rando_gerudo_guards"' in qol[:qol.index("} },")], "it is not in the launcher's Quality of life section")
    print("FAIL" if failed else "PASS: a Gerudo guard who catches Link goes back to her post, no cell")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
