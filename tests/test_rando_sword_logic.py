"""With Shuffle the Master Sword, adult checks asked for the sword everywhere (door_need's blanket rule), where bombs,
the Bow or the Hammer do (the owner's ask, 2026-11-23). From SWORD_FROM a check with a rule of its own (the dungeons'
and overworld's tables, worked out with the engine's shuffle_master_sword, our own rules), a gift or a shelf is not
given the sword by door_need; the bosses keep it. No game files.

python -I -B tests/test_rando_sword_logic.py
"""
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RANDO = os.path.join(ROOT, "tools", "rando")
sys.path.insert(0, RANDO)
import rando_seed as S  # noqa: E402

failed = False


def check(ok, what):
    global failed
    if not ok:
        failed = True
        print("FAIL: " + what)


def main():
    check(S.PLACEMENT >= S.SWORD_FROM == 26, "new seeds are not made from SWORD_FROM")
    was = S.MASTER_SHUFFLED
    try:
        S.MASTER_SHUFFLED = True
        need = frozenset((S.BB,))
        check(S.MASTER in S.door_need(need, True), "an adult's place without its own rule lost the sword")
        check(S.MASTER not in S.door_need(need, True, sword_asked=False), "an adult's place with its own rule still asks for the sword")
    finally:
        S.MASTER_SHUFFLED = was
    src = open(S.__file__, encoding="utf-8").read()
    main_src = src[src.index("\ndef main():"):]
    check("no_sword = lambda h: placement >= SWORD_FROM and h not in bosses and (" in main_src and
          "h in ruled or h in shelves or h in gifts and gifts[h].key not in reward_keys)" in main_src,
          "the sword is not dropped for the checks with their own rules, the gifts and the shelves, or kept for the bosses")
    check(main_src.count("sword_asked=not no_sword(h)") == 3, "not every door_need of the seed passes the sword's word")
    dungeon = json.load(open(os.path.join(RANDO, S.DUNGEON_RULES2_FILE), encoding="utf-8"))
    check(len(dungeon.get("ms_by_actor", {})) == len(dungeon["by_actor"]), "the dungeons' table has no sword-shuffled ways")
    over = json.load(open(os.path.join(RANDO, S.OVERWORLD_RULES_FILE), encoding="utf-8"))["variants"]
    check(all(S.overworld_variant(f == "open", f != "closed", g == "open", True, True) in over
              for f in ("open", "closed_deku", "closed") for g in ("open", "zelda")),
          "the overworld's table has no sword-shuffled variant for some settings")
    print("FAIL" if failed else "PASS: adult checks ask for the Master Sword only where a fight needs it")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
