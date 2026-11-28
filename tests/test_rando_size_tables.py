#!/usr/bin/env python3
"""A game folder with an older version's size table beside the one the game reads (a player's report, 2026-11-27, v0.1.9).

Their launcher said: "the size table ResourceSizeTable.Product.100.Nin_Ounce_NVN2.rsizetable.zs could not be updated
(GameData/GameDataList.Product.110.byml is not in the size table). Nothing written." Their dump of the game had the base
game's table left beside the update's (Product.111, which the build asks for and the game reads); the seed tool updated
every table it found and stopped at the first that lacked a file the update brought. tools/rando/rando_seed.py
size_tables_made: the newest table must be made, an older one that cannot be is left as it is and said.
"""
import importlib.util
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(ok, what):
    if not ok:
        raise SystemExit("FAIL: " + what)


def table(paths):
    rows = sorted((zlib.crc32(p.encode()) & 0xffffffff, 1000) for p in paths)
    return b"RESTBL" + bytes(8) + struct.pack("<I", len(rows)) + bytes(4) + b"".join(struct.pack("<II", *r) for r in rows)


def main():
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("rando_seed", ROOT / "tools" / "rando" / "rando_seed.py")
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    old, new = "ResourceSizeTable.Product.100.Nin_Ounce_NVN2.rsizetable.zs", "ResourceSizeTable.Product.111.Nin_Ounce_NVN2.rsizetable.zs"
    flags, banc = "GameData/GameDataList.Product.110.byml", "Banc/Market/Market_Child.bcett.byml"
    files = {old: table([banc]), new: table([banc, flags])}   # (the base game's table has no file the update brought)
    make = lambda n: seed.size_table_update(files[n], {flags: 5000, banc: 3000})
    # (the report itself: the old table alone cannot be updated)
    try:
        make(old)
        check(False, "the old table takes a file it does not have")
    except ValueError as e:
        check(str(e) == "GameData/GameDataList.Product.110.byml is not in the size table", "the old table's error is another: %s" % e)
    made, left = seed.size_tables_made([new, old], make)
    check(list(made) == [new] and [n for n, _ in left] == [old] and "is not in the size table" in str(left[0][1]),
          "the old version's table is not left as it is, or the game's own is not made")
    check(seed.size_table_entry(made[new], flags) == seed.size_entry(5000) and seed.size_table_entry(made[new], banc) == seed.size_entry(3000),
          "the game's own table is not raised to fit")
    # (the table the game reads must be made: its error is the seed's, as before)
    try:
        seed.size_tables_made([old], make)
        check(False, "a folder whose only table cannot be updated makes a seed")
    except ValueError:
        pass
    files[new] = table([banc])
    try:
        seed.size_tables_made([old, new], make)
        check(False, "the newest table failing is passed over")
    except ValueError:
        pass
    # (both good: both made, none left)
    files[old] = files[new] = table([banc, flags])
    made, left = seed.size_tables_made([old, new], make)
    check(sorted(made) == [old, new] and not left, "two good tables are not both made")
    script = (ROOT / "tools" / "rando" / "rando_seed.py").read_text(encoding="utf-8")
    check("made, left = size_tables_made(tables, table_made)" in script and
          'sys.exit("the size table %s could not be updated (%s). Nothing written." % (tables[-1], e))' in script and
          'print("the size table %s is an older version\'s and is left as it is (%s): the game reads %s" % (n, why, tables[-1]))' in script,
          "the seed's tables are not made through size_tables_made, or a table left is not said")
    print("PASS: an older version's size table beside the game's does not stop a seed")


if __name__ == "__main__":
    main()
