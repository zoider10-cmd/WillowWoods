"""Which dungeon checks need none of their dungeon's small keys (Small keys: Anywhere, share/dungeon-items-plan.md stage
3, asked 2026-11-23). The dungeon rules (dungeon_logic.py) are worked out with the keys lying where the game has them, so
they never ask for a key. With the keys anywhere a check behind a locked door needs them: here each dungeon is reached
with every item held and its small keys taken out of the world; a check still reached needs none, every other check of
the dungeon asks for all of the dungeon's keys that the shuffle moves (rando_seed.py key_need: too much, never too
little).

    py -I tools/rando/dungeon_keyless.py [--write tools/rando/dungeon_keyless.json]

The written table: {"keyed": [an actor's hash in decimal, ...], "keyless": [...]}, by ootrr's pins as dungeon_logic.py's
by_actor (an actor pinned to several locations is keyless only when every one of them is).
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dungeon_logic as D  # noqa: E402


def keyless(calc):
    """({dungeon: the locations reached with every item and no small key}, {dungeon: those reached with them})"""
    full = {name: top for name, top in D.TRIED}
    with_keys = {d: calc.reached(d, full) for d in D.DUNGEONS}
    kept = calc.fixed
    calc.fixed = {loc: item for loc, item in kept.items() if "Small Key" not in item}
    try:
        without = {d: calc.reached(d, full) for d in D.DUNGEONS}
    finally:
        calc.fixed = kept
    return without, with_keys


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--write")
    a = p.parse_args()
    calc = D.Calc()
    without, with_keys = keyless(calc)
    for d in D.DUNGEONS:
        print("%-24s %3d checks reached, %3d of them without a small key" % (d, len(with_keys[d]), len(without[d] & with_keys[d])))
    rules = {d: {loc: ([{}] if loc in without[d] else []) for loc in with_keys[d]} for d in D.DUNGEONS}
    reached = D.by_actor({d: {loc: [{}] for loc in with_keys[d]} for d in D.DUNGEONS}, calc.pins)
    free = D.by_actor(rules, calc.pins)
    out = {"source": "tools/rando/dungeon_keyless.py", "keyless": sorted(int(h) for h in free),
           "keyed": sorted(int(h) for h in reached if h not in free)}
    print("actors: %d keyless, %d keyed" % (len(out["keyless"]), len(out["keyed"])))
    if a.write:
        with open(a.write, "w", encoding="utf-8", newline="\n") as f:
            json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
