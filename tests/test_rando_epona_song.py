"""Epona by Epona's Song (rando_epona_song, asked 2026-11-21, bugs.md 98; it replaced Skip Ingo's races): the setting from the options file to the seed
tool, the launcher and the stamp; evfl kept beside the seed tool with its licence; and the event table rows written
from a small made-up table (epona_event_rows). The flows themselves need the game's files: not read here."""
import collections
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools", "rando"))
import rando_seed as S  # noqa: E402

failed = []


def check(ok, what):
    if not ok:
        failed.append(what)
        print("FAIL: " + what)


def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


def row(name, **fields):
    d = collections.OrderedDict([("__RowId", ("string", name))])
    d.update(fields)
    return ("dict", d)


def main():
    seed = read("tools", "rando", "rando_seed.py")
    check('"rando_epona_song": 0' in seed and 'a.epona_song = a.epona_song or ini["rando_epona_song"] != 0' in seed,
          "the seed tool does not read rando_epona_song")
    check('stamp = stamp[:-1] + " epona by song\\n"' in seed, "the setting is not on the stamp's line of settings that move no item")
    check("gift_new.add(EPONA_OWN_FLOW[:-3])" in seed and "pack_new | gift_new" in seed,
          "the new event's flow file gets no size table entry")
    # (the quest is finished whatever the lesson, and at every call: a save that had her before the lesson (the owner's
    #  run, 2026-11-21) kept Ingo and Talon as before the races)
    check("EPONA_LESSON" not in seed, "the new event still waits on Malon's lesson to finish the quest")
    check('"WillowEpona2", quest, "EventExecuteProgressChallengeStep"' in seed and "IsIgnoreCompletedChallenge=True" in seed
          and "ask.data.cases[0].v = finish" in seed, "calling an owned Epona does not finish the quest")
    check('X(EPONA_SONG, "Epona by Epona\'s Song", "rando_epona_song",' in read("gpu", "vk", "oot_rando.h"), "the settings table has no row for it")
    launcher = read("launcher", "Launcher.cs")
    no_item = launcher[launcher.index('"rando_skulltulas_day", "rando_hints"'):]
    check('"rando_epona_song"' in no_item[:no_item.index("};")] and 'new object[] { "rando_epona_song",' in launcher,
          "the launcher has no row for it, or does not keep a seed when it changes")
    # (Skip Ingo's races, which this replaced, is gone; and every launcher settings row ends its own array: the Infinite
    #  ammo row was once written inside the Master Sword's)
    check("rando_skip_races" not in launcher and "rando_skip_races" not in seed, "Skip Ingo's races is still offered")
    check(not re.search(r'"\s*,\s*\n\s*new object\[\] \{ "rando_', launcher), "a launcher settings row is written inside the one before it")
    here = os.path.join(ROOT, "tools", "rando", "evfl")
    check(os.path.isfile(os.path.join(here, "LICENSE")) and os.path.isfile(os.path.join(here, "evfl.py")), "evfl is not beside the seed tool with its licence")
    check(S.evfl_module().EventFlow is not None, "evfl does not load from beside the seed tool")
    # ---- the event tables: a row copied from Pierre's, the ocarina's child events ----
    tmpl = row(S.EPONA_TEMPLATE, FlowchartFileName=("string", "Work/Event/EventFlow/x.evfc"), EntryPointName=("string", "x"),
               EventBaseSetting=("string", "Starter"))
    oc = row("Dm_SY_Ocarina", EventBaseSetting=("string", "PlayerPos"), ChildEventList=("array", [("string", S.EPONA_TEMPLATE)]))
    setting = S.byml_parse(S.epona_event_rows(S.byml_build(("array", [tmpl, oc]), 7), False))[0]
    by = {r[1]["__RowId"][1]: r[1] for r in setting[1]}
    mine = by.get(S.EPONA_OWN, {})
    check(mine.get("FlowchartFileName") == ("string", "Work/Event/EventFlow/%s.evfc" % S.EPONA_OWN) and mine.get("EntryPointName") == ("string", S.EPONA_OWN)
          and mine.get("EventBaseSetting") == ("string", "PlayerPos"), "the settings row does not name the new event's flow and entry at Link: %r" % (mine,))
    check([r[1]["__RowId"][1] for r in setting[1]] == sorted(r[1]["__RowId"][1] for r in setting[1]), "the rows are not in order")
    tmpl = row(S.EPONA_TEMPLATE, SubFlowList=("array", [("string", "Dm_SY_Ocarina")]))
    analyzed = S.byml_parse(S.epona_event_rows(S.byml_build(("array", [tmpl, oc]), 7), True))[0]
    by = {r[1]["__RowId"][1]: r[1] for r in analyzed[1]}
    check(by.get(S.EPONA_OWN, {}).get("SubFlowList") == ("array", []), "the analyzed row keeps Pierre's sub-flows")
    check(("string", S.EPONA_OWN) in by["Dm_SY_Ocarina"]["ChildEventList"][1], "the new event is not one of the ocarina event's child events")
    try:
        S.epona_event_rows(S.byml_build(("array", [tmpl, oc, row(S.EPONA_OWN)]), 7), True)
        check(False, "a table that has the new event already is changed again")
    except ValueError:
        pass
    print("FAIL" if failed else "PASS: Epona by Epona's Song")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
