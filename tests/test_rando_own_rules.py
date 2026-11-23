"""Bug 118 (the owner's run 2026-11-23): Hyrule Field's tree Gold Skulltulas and the remake's own chests were out of
logic when easy: the other logic doesn't have them, so they took a pool's hardest rule or the old whole-area one.
tools/rando/overworld_own.json gives each a rule of its own, worked out by overworld_logic.py into each variant's
"own" of overworld_rules.json, read by the seed tool from OWN_FROM only. Checked on the files and the source; no game
files.

python -I -B tests/test_rando_own_rules.py
"""
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RANDO = os.path.join(ROOT, "tools", "rando")
sys.path.insert(0, RANDO)
import rando_seed as seed  # noqa: E402

failed = False


def check(ok, what):
    global failed
    if not ok:
        failed = True
        print("FAIL: " + what)


# (the owner's own words from play, 2026-11-23: these rules are theirs)
OWNER = {"1e38e8d23596eecf": "can_bonk", "04be4a8ff29f2099": "can_bonk", "f21b7ae43e7ff515": "can_use(Hookshot)",
         "10266fe15a73cb29": "is_adult", "25e6072d4df023b3": "can_use(Boomerang)"}


def main():
    own = json.load(open(os.path.join(RANDO, "overworld_own.json"), encoding="utf-8"))["rules"]
    check(len(own) >= 40, "only %d rules of our own" % len(own))
    for h, words in OWNER.items():
        check(h in own and words in own[h]["rule"], "%s: not the owner's rule (%s)" % (h, own.get(h, {}).get("rule")))
    table = json.load(open(os.path.join(RANDO, "overworld_rules.json"), encoding="utf-8"))["variants"]
    for key, v in table.items():
        got = v.get("own", {})
        missing = [h for h in own if str(int(h, 16)) not in got]
        check(not missing, "variant %s has no ways for %d of our rules (overworld_logic.py --write not run?)" % (key, len(missing)))
        check(all(not k.startswith("OWN ") for k in v.get("named", {})), "variant %s names an OWN location" % key)
    check(seed.PLACEMENT >= seed.OWN_FROM == 26, "new seeds are not made from OWN_FROM")
    src = open(seed.__file__, encoding="utf-8").read()
    check("over_own.get(h) if placement >= OWN_FROM and h in over_own else over.get(h)" in src,
          "our own ways are not read in place of the table's, from OWN_FROM only")
    print("FAIL" if failed else "PASS: the remake's own checks by rules of their own")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
