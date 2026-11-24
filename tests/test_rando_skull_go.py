"""Bug 117 (the owner's run 2026-11-23): Go there to three Gold Skulltulas put Link at the Skulltula's own place, on a wall
(Dodongo's Cavern's room 2, Zora's Fountain's night #2: stuck behind it; the grotto by Lon Lon Ranch: fallen out of the
world). tools/rando/rando_seed.py SKULL_GO gives each a floor spot, found without a window, and the checks file's line
carries it as its last field (where Go there puts Link), as a chest's front does. Game-free: check_lines on made-up
checks, and the seed tool's source."""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools", "rando"))
import rando_seed as S  # noqa: E402


def main():
    want = {0x0d53e429a1ef383d, 0x845ba51dc18c855e, 0xa6a4e87da18fa678}
    assert want <= set(S.SKULL_GO), "a Skulltula of bug 117 has no floor spot: %s" % sorted("%016x" % h for h in want - set(S.SKULL_GO))
    for h, (x, y, z) in S.SKULL_GO.items():
        assert all(isinstance(v, float) for v in (x, y, z)), "%016x's spot is not three numbers" % h
    h = 0x845ba51dc18c855e
    lines = [l for l in S.check_lines([], [("ZoraFountain", (80.0, 133.4, 12.9), "CA", frozenset(), "Gold Skulltula", h, "Item_Token_Gold",
                                            S.SKULL_GO[h]),
                                           ("ZoraFountain", (1.0, 2.0, 3.0), "CA", frozenset(), "Gold Skulltula", 0x1234, "Item_Token_Gold")])
             if not l.startswith("#")]
    skull = next(l.split("|") for l in lines if "%016x" % h in l)
    assert skull[4] == "80.0 133.4 12.9", "the Skulltula's own place (the Tracker's dot) was changed: %s" % skull[4]
    assert skull[8] == "%.1f %.1f %.1f" % S.SKULL_GO[h], "Go there does not take the floor spot: %r" % skull[8:]
    other = next(l.split("|") for l in lines if "0000000000001234" in l)
    assert len(other) == 8, "a Skulltula without a spot got one: %r" % other
    src = open(S.__file__, encoding="utf-8").read()
    assert "skull_drops.get(h) or drops.get(h) or TOKEN,\n                                        SKULL_GO.get(h))" in src, \
        "the seed's checks file is not given the Skulltulas' floor spots"
    print("PASS: Go there to a Gold Skulltula on a wall puts Link on the floor by it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
