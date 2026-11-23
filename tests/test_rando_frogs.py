"""The frogs' two prizes are two checks (placement 27, bug 132, the owner's run 2026-11-23: the Song of Storms gave the
check's item, and their ocarina game gave it again). MiniGame_FrogTenors gives a Piece of Heart from its
PlayOcarinaForFrogMiniGame_Melody entry (the Song of Storms) and from FrogMiniGame_Insectrepellent and
FrogMiniGame_RetryFlow (the game, first try and retry): "frogs" is the first's alone from FROGS_SPLIT_FROM, "frogs_game"
the others', each swapped by its own entries (gift_items' (entry, name) keys). Game-free: read from the seed tool (the swap was
tried on the game's flow by hand, 2026-11-23: each entry's call alone changed)."""
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


def main():
    seed = open(os.path.join(ROOT, "tools", "rando", "rando_seed.py"), encoding="utf-8").read()
    frogs = next(g for g in S.GIFTS if g.key == "frogs")
    game = next((g for g in S.GIFTS if g.key == "frogs_game"), None)
    check(game is not None, "the frogs' game is not a gift of its own")
    check(S.PLACEMENT >= S.FROGS_SPLIT_FROM == 27 and S.GIFTS_FROM.get("frogs_game") == 27,
          "the frogs' split is not placement 27's (seeds made before keep one gift)")
    if game:
        check(game.flow == frogs.flow == "MiniGame_FrogTenors" and game.when == frogs.when == "frogs",
              "the frogs' game is not the frogs' flow, or not of the same setting")
        check(game.entry == ("FrogMiniGame_Insectrepellent", "FrogMiniGame_RetryFlow"), "the frogs' game is not its two entries' (first try, retry)")
        check(S.GIFT_PLACES.get("frogs_game") == S.GIFT_PLACES["frogs"], "Go there has no place for the frogs' game")
    check(frogs.entry is None and S.FROG_STORMS_ENTRY == "PlayOcarinaForFrogMiniGame_Melody", "the Song of Storms' entry is not the Melody's")
    check('if g.key == "frogs" and placement >= FROGS_SPLIT_FROM:' in seed and
          "g = g._replace(entry=FROG_STORMS_ENTRY, name=FROG_STORMS_NAME)" in seed,
          "from placement 27 the frogs' gift is not the Song of Storms' alone")
    check("(SONGS_HARD_SPLIT if placement >= FROGS_SPLIT_FROM else SONGS_HARD)" in seed and S.SONGS_HARD_SPLIT == ("frogs_game",),
          "with the songs shuffled the frogs' Song of Storms still asks for everything, or their game not")
    check("entries = g.entry if isinstance(g.entry, tuple) else (g.entry,) if g.entry else (None,)" in seed and
          "((e, old) if e else old, gives[h]) for e in entries for old in g.olds" in seed,
          "a gift of several entries is not swapped at each")
    print("FAIL" if failed else "PASS: the frogs' two prizes are two checks")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
