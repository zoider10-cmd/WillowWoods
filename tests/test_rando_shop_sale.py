"""Bug 115 (the owner's run 2026-11-23): two shelves of one item in a shop (two tokens), the one bought stayed and the
other vanished: the game's side marked the nearest unfinished check giving the item, and every shelf of a shop has its
shop's place, so the first in the list was taken. Then the adult rolling Goron's Heart Container marked the Goron
shop's Heart Container shelf, nearer to Link, which vanished. A shop's sale is told by the game's add (from 0x828d50ac
with x4 5, every shelf bought in that run and nothing else), and is a shelf's and only a shelf's; the shelf by the
price the game shows for the item picked (Shop_SelectItemPrice) against the price in the shelf's name. Checked by
source and the flag's hash. No game files.

python -I -B tests/test_rando_shop_sale.py
"""
import os
import struct
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
failed = False


def check(ok, what):
    global failed
    if not ok:
        failed = True
        print("FAIL: " + what)


def murmur3(data, seed=0):
    h, n = seed, len(data)
    for i in range(0, n - n % 4, 4):
        k = struct.unpack_from("<I", data, i)[0]
        k = (k * 0xcc9e2d51) & 0xffffffff
        k = ((k << 15) | (k >> 17)) & 0xffffffff
        k = (k * 0x1b873593) & 0xffffffff
        h ^= k
        h = ((h << 13) | (h >> 19)) & 0xffffffff
        h = (h * 5 + 0xe6546b64) & 0xffffffff
    k, tail = 0, data[n - n % 4:]
    for i, b in enumerate(tail):
        k ^= b << (8 * i)
    if tail:
        k = (k * 0xcc9e2d51) & 0xffffffff
        k = ((k << 15) | (k >> 17)) & 0xffffffff
        k = (k * 0x1b873593) & 0xffffffff
        h ^= k
    h ^= n
    h ^= h >> 16
    h = (h * 0x85ebca6b) & 0xffffffff
    h ^= h >> 13
    h = (h * 0xc2b2ae35) & 0xffffffff
    return h ^ (h >> 16)


def main():
    src = open(os.path.join(ROOT, "host", "hos_main.c"), encoding="utf-8").read()
    check(murmur3(b"Shop_SelectItemPrice") == 0x07a1b798 and "0x07a1b798u, &price, 0)" in src,
          "the price is not read by Shop_SelectItemPrice's hash")
    check("const int shop = c->x[30] == 0x828d50acULL && (uint32_t)c->x[4] == 5;" in src and
          "oot_tracker_item(name, shop, price);" in src, "a shop's sale is not told by the add's x4 5 from 0x828d50ac")
    body = src[src.index("static void oot_tracker_item(const char *name, int shop, int price) {"):]
    body = body[:body.index("\n}\n")]
    loop = body[body.index("for (int i = 0; i < oot_check_count; i++) {"):body.index("if (best >= 0 && nearest > OOT_CHECK_NEAR)")]
    check("(!oot_checks[i].shelf) != !shop) continue;" in loop, "a sale may mark a check that is no shelf, or another add a shelf")
    check("oot_checks[i].price != price) continue;" in loop, "a sale's price does not tell the shelves of one item apart")
    tail = body[body.index("if (best < 0) {"):]
    check("(shop || !oot_tracker_shop_on)" in tail and "oot_checks[i].price == price" in tail,
          "the shelves' name-tail match (bought by the pouch's name) is not kept to sales and their price")
    check('getenv("HOS_OOT_TRACK_SHOP")' in body, "no HOS_OOT_TRACK_SHOP=0 to go back to the old way")
    load = src[src.index("static void oot_tracker_load(const char *stamp) {"):]
    check('strstr(kind, " rupees")' in load and ".price =" in load, "a shelf's price is not read from its name")
    print("FAIL" if failed else "PASS: a shop's sale marks the shelf bought, and nothing else does")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
