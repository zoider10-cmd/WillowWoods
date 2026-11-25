"""Pots (rando_pots, "Potsanity", asked 2026-11-23): the pots the logic's tables rule (pot_actors: kind "pot") take part as
Gold Skulltulas do: a spot holding its own item (POT_OWN) in the pool, dropping what a Skulltula may (skull_may), by
the rule its table gives it (heart_asks over lying, the pieces and the pots), its map's pot given that drop (add_drop),
and a "Pot" check on the Tracker; the game's side gives a pot's item once (host/hos_main.c oot_pot_again). Game-free: the
tables and the sources.

python -I -B tests/test_rando_pots.py
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools", "rando"))
import rando_seed as S  # noqa: E402


def main():
    pots = S.pot_actors()
    assert 60 <= len(pots) <= 120, len(pots)
    assert all(isinstance(h, int) and f for h, f in pots.items())
    assert S.skulltula_holds(S.POT_OWN, S.PROGRESSION), "a pot's own item is not one a Skulltula may drop"
    src = open(S.__file__, encoding="utf-8").read()
    main_src = src[src.index("\ndef main():"):]
    assert 'a.pots = ini["rando_pots"] == 1' in main_src and '(" pots 1" if a.pots else "")' in main_src
    assert 'joined.update((h, [pots[h][0], POT_OWN, None, None, "pot", pots[h][1], ""]) for h in pots)' in main_src
    assert 'holds[h] = skull_may if s[4] in ("skulltula", "pot") else' in main_src
    assert "lying = collections.ChainMap(pieces, pots)" in main_src and "own_rule(h, lying[h][0], lambda:" in main_src, \
        "a pot's rule is not read as a piece's"
    assert main_src.index("drops.setdefault(h, item)\n        if a.progressive:") < main_src.index("    # ---- the map files ----"), \
        "the pots' drops are not given before the map files are written"
    assert '"Pot", h, pot_drops.get(h, POT_OWN))' in main_src, "no Pot check on the Tracker"
    host = open(os.path.join(ROOT, "host", "hos_main.c"), encoding="utf-8").read()
    assert 'oot_checks[oot_check_count].pot = !strncmp(kind, "Pot", 3) && (!kind[3] || kind[3] == \' \');' in host
    again = host.index("if (c->x[30] != 0x828d50acULL && oot_pot_again(c, name)) return 1;")
    assert again < host.index("oot_tracker_item(name, shop, price);"), "a pot back after a day is recorded before it is refused"
    # (2026-11-25, from play: the pot is known by the game's "broken" truth value by its hash, not by distance: the Market's
    #  guard house has 22 pots in 8 m, and a second token from the pot beside a collected one was refused)
    body = host[host.index("static int oot_pot_open(Ctx *c, const char *name, int *broken) {"):]
    body = body[:body.index("\n}\n")]
    again = host[host.index("static int oot_pot_again(Ctx *c, const char *name) {"):]
    again = again[:again.index("\n}\n")]
    assert "oot_gamedata_keyed_bool(c, oot_checks[i].broken, &now)" in body and "OOT_POT_NEAR" not in host, \
        "a pot is still found by distance"
    assert "if (oot_checks[i].done != 1) open = i;" in body and "return broken > 0;" in again, \
        "an item is refused while a broken pot giving it is not collected"
    assert "oot_checks[oot_check_count].broken = oot_checks[oot_check_count].pot ? oot_checks[oot_check_count].key : 0;" in host
    track = host[host.index("static void oot_tracker_item(const char *name, int shop, int price) {"):]
    assert "best = oot_pot_chosen;" in track[:track.index("\n}\n")], "the record does not mark the pot just broken"
    header = open(os.path.join(ROOT, "gpu", "vk", "oot_rando.h"), encoding="utf-8").read()
    assert 'X(POTS, "Pots", "rando_pots",' in header
    print("PASS: Pots: the tables' pots take part")
    return 0


if __name__ == "__main__":
    sys.exit(main())
