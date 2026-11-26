"""The seed tool's batched steps give what the one-by-one steps gave (2026-11-26, share/better-ways-2026-11-26.md I: a seed
took 1 min 49 s to make, 25 s after; tools/rando/rando_seed.py size_table_add_each, shop_rows_many, piece_rows_many,
model_rows): no game data.

- the size table: many paths added in one pass, each with its own size, are the bytes of adding them one by one with the
  code as it was (kept here), the first of two alike winning and a path the table has left as it is;
- a list of actors: many shelves' rows, and many pieces' rows, written in one pass are the bytes of one at a time;
- a model's box is read from the list of actors once while the same list is asked about, and again for another list.

    python -I -B tests/test_rando_seed_speed.py
"""
import collections
import importlib.util
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("rando_seed", ROOT / "tools" / "rando" / "rando_seed.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)


def check(ok, why):
    if not ok:
        print("FAIL: %s" % why)
        sys.exit(1)


def add_as_it_was(tbl, paths, size):
    """size_table_add before 2026-11-26, word for word"""
    count = struct.unpack_from("<I", tbl, 14)[0]
    end = 22 + count * 8
    have = {struct.unpack_from("<I", tbl, 22 + k * 8)[0] for k in range(count)}
    new = sorted({zlib.crc32(path.encode()) & 0xffffffff for path in paths} - have)
    if not new:
        return tbl
    rows = [bytes(tbl[22 + k * 8:30 + k * 8]) for k in range(count)] + [struct.pack("<II", crc, size) for crc in new]
    rows.sort(key=lambda r: struct.unpack_from("<I", r)[0])
    return bytes(tbl[:14]) + struct.pack("<I", len(rows)) + bytes(tbl[18:22]) + b"".join(rows) + bytes(tbl[end:])


def main():
    crc = lambda p: zlib.crc32(p.encode()) & 0xffffffff
    game = ["Pack/Actor/G%d.pack" % k for k in range(40)]
    rows = sorted((crc(p), 1000 + k) for k, p in enumerate(game))
    tbl = b"RESTBL" + bytes(8) + struct.pack("<I", len(rows)) + b"\x01\x02\x03\x04" + b"".join(struct.pack("<II", *r) for r in rows) + b"the names' part"
    entries = [("Pack/Actor/New%d.pack" % k, 5000 + 32 * k) for k in range(25)] + [(game[3], 7), ("Pack/Actor/New4.pack", 9)]
    one_by_one = tbl
    for path, size in entries:
        one_by_one = add_as_it_was(one_by_one, [path], size)
    check(S.size_table_add_each(tbl, entries) == one_by_one, "many paths added to the size table in one pass are not the one-by-one bytes")
    check(S.size_table_add(tbl, [p for p, _ in entries], 4321) == add_as_it_was(tbl, [p for p, _ in entries], 4321) and
          S.size_table_add(tbl, game[:5], 1) is tbl, "size_table_add is not what it was")
    index = S.size_table_index(one_by_one)
    check(index[crc(game[3])] == 1003 and index[crc("Pack/Actor/New4.pack")] == 5000 + 32 * 4 and len(index) == 65,
          "the size table's index does not give each path's entry, the game's own and the first added kept")

    def row(name, **more):
        fields = [("__RowId", ("string", name))] + [(k, ("string", v)) for k, v in sorted(more.items())]
        return ("dict", collections.OrderedDict(fields))
    table = S.byml_build(("array", [row(n, Look=n + "'s") for n in ("Item_A", "Item_B", S.HEART, S.SHOP_ROW)]), 7)
    sales = [("Item_A", 10, "Shelf_2"), ("Item_B", 20, "Shelf_1"), ("Item_A", 30, "Shelf_2")]
    step = table
    for item, price, name in sales:
        step = S.shop_rows(step, "GameActorInfo", item, price, name)
    check(S.shop_rows_many(table, "GameActorInfo", sales) == step, "many shelves' rows written in one pass are not the one-by-one bytes")
    made = [("Item_A", "Piece_Look_1"), ("Item_B", "Piece_Look_0")]
    step = table
    for item, name in made:
        step = S.piece_rows(step, "GameActorInfo", item, name)
    check(S.piece_rows_many(table, "GameActorInfo", made) == step and step != table,
          "many pieces' rows written in one pass are not the one-by-one bytes")

    def box_row(name, low, high):
        ends = lambda v: ("dict", collections.OrderedDict((a, (0xD2, struct.pack("<f", x))) for a, x in zip("XYZ", v)))
        return ("dict", collections.OrderedDict((("ModelAabbMax", ends(high)), ("ModelAabbMin", ends(low)), ("__RowId", ("string", name)))))
    first = S.byml_build(("array", [box_row("Item_A", (0, 1, 2), (3, 4, 5)), box_row("Item_B", (9, 9, 9), (10, 10, 10))]), 7)
    other = S.byml_build(("array", [box_row("Item_A", (6, 7, 8), (9, 10, 11))]), 7)
    check(S.model_box(first, "Item_A") == ((0.0, 1.0, 2.0), (3.0, 4.0, 5.0)) and S.model_floor(first, "Item_B") == 9.0 and
          S.model_box(first, "Item_C") is None, "a model's box is not read from the list of actors")
    check(S.model_box(other, "Item_A") == ((6.0, 7.0, 8.0), (9.0, 10.0, 11.0)) and S.model_box(other, "Item_B") is None and
          S.model_floor(first, "Item_A") == 1.0, "another list of actors is answered from the one read before")
    print("PASS: the seed tool's batched steps give what the one-by-one steps gave")


if __name__ == "__main__":
    main()
