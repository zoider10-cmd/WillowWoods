"""The Tracker's marks from the hints heard and the run's stats (asked 2026-11-21): the game's side counting the time
played, the deaths and Ganon's end into rando/run_stats.txt, and the menu reading it for the whole game's row; the hints'
three kinds of words making an area's row say Foolish or Hinted. Read from the source; the game is needed to see them."""
import os
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


def main():
    host, menu = read("host", "hos_main.c"), read("gpu", "vk", "vk_menu.cpp")
    check('!strcmp(name, "DmF_SY_GameOver"), ganon = !strcmp(name, "Defeat_Ganon")' in host and "oot_stats_second();" in host
          and '"rando/run_stats.txt"' in host and "if (is_new && hos_rando_on()) oot_stats_event(name);" in host,
          "the game's side does not count the time played, the deaths and Ganon's end")
    check("if (!skipping) return;" in host, "the events' names are read only with Skip cutscenes on (the stats need them too)")
    check("tracker_stats_load(path.substr(" in menu and 'game_folder_path() + "rando/run_stats.txt"' in menu and
          "selr.tracker == 0 && tracker_check_count ? stats_help.c_str() : selr.help;" in menu, "the whole game's row does not show the run's stats")
    # (the hints' words, as choose_hints writes them, give the menu's three kinds)
    words = S.choose_hints.__code__.co_consts
    said = " ".join(c for c in words if isinstance(c, str))
    for kind in ("They say that it is foolish to look in ", " is on the way of the hero.", " can be found in "):
        check(kind.strip(" .") in said and ('"%s"' % kind) in menu, "the menu does not read the hints' words %r" % kind)
    check('if (hinted) words = (hinted == 1 ? "Foolish: " : "Hinted: ") + words;' in menu, "an area's row does not say what a hint heard said of it")
    print("FAIL" if failed else "PASS: the run's stats and the hints' marks")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
