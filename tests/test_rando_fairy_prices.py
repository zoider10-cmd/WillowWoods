"""The Great Fairy prices setting (rando_fairy_prices, the owner's ask 2026-11-23: a setting of its own, with the shops'
choices). 0 as the shops (the way before, the default), 1 the game's own, 2 to 4 rolled as Low prices, Any price,
Affordable whatever Shops is; named on the stamp when set; the last row of the seed ID's table and the launcher's.
No game files.

python -I -B tests/test_rando_fairy_prices.py
"""
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


def main():
    m = seed.fairy_price_mode
    check(m(0, 2) == 2 and m(0, 0) == 0, "As the shops does not follow Shops")
    check(m(1, 2) == 0 and m(2, 0) == 1 and m(3, 0) == 3 and m(4, 0) == 0, "a choice is not shop_price's mode")
    check(seed.FAIRY_PRICE_OLD == {4: 3}, "an old Affordable (4, before Any price was taken out) is not read as Affordable")
    check(set(seed.fairy_prices(7, 3).values()) == {seed.SHOP_AFFORDABLE}, "Affordable is not every fairy's")
    src = open(seed.__file__, encoding="utf-8").read()
    check('"rando_fairy_prices": 0' in src and "fairy_cost = fairy_prices(seed, fairy_mode) if fairy_mode and placement >= FAIRY_PRICES_FROM else {}" in src,
          "the setting is not read, or the prices not rolled by it")
    check('(" fairies %d" % a.fairy_prices if a.fairy_prices else "")' in src, "the setting is not on the stamp (it moves items: the wallets)")
    header = open(os.path.join(ROOT, "gpu", "vk", "oot_rando.h"), encoding="utf-8").read()
    order = re.findall(r"^    X\(([A-Z_]+),", header, re.M)
    # (the last row when it was made: rows added since come after it, so a seed ID's settings keep their places)
    check("FAIRY_PRICES" in order and order.index("FAIRY_PRICES") == order.index("SKIP_TOWER") + 1 and '"rando_fairy_prices"' in header,
          "not the seed ID table's row after Skip the tower escape (its place when it was made)")
    launcher = open(os.path.join(ROOT, "launcher", "Launcher.cs"), encoding="utf-8").read()
    check('new object[] { "rando_fairy_prices", "Great Fairy prices"' in launcher and '"+shops", "rando_fairy_prices"' in launcher,
          "the launcher has no row for it beside Shops")
    print("FAIL" if failed else "PASS: the Great Fairy prices setting")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
