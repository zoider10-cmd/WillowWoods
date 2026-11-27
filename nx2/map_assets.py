"""(Willow Woods, asked 2026-11-26) The Tracker's map pictures, made from the player's own RomFS at the end of a build
(nx2/make_game.py) into <game folder>/maps/: the game's own map pictures (UI/CustomTex/Map: a picture an outdoor area and
age, a picture a dungeon floor) and where each lies in the world, for the Tracker tab to draw behind its checks
(gpu/vk/vk_map_pictures.cpp). Nothing of the game is in this repository, and what this makes stays in the game folder: it is
made from the game, never sent. With only the Python the builder ships (zstandard): a picture keeps the game's own ASTC
blocks, decoded by the renderer (suyu's ASTC decoder), as the item wheel's icons (nx2/wheel_assets.py).

    python -I nx2/map_assets.py --romfs <dir> --out <game folder>/maps

Where a picture lies is the game's own word (seen 2026-11-26, the checks of a seed drawn on every picture: the Market's
guard house pots in the guard house, 45 of the Forest Temple's 45 checks on its rooms): Game/MapMenuInfo's n-th map has
Game/MapCaptureInfo's n-th capture, a camera looking down from CameraPos; the picture's middle is the camera's X and Z, its
WIDTH is the capture's Height in metres (so a metre is width / Height pixels both ways), x to the right and z down.

index.txt: a first line "# map pictures <VERSION>", then a line a picture:
    <folder>|<ages>|<floor>|<name>|<camera x>|<camera z>|<height>|<width px>|<height px>
folder: the map's Banc folder, as the Tracker's checks name it (HyruleField, ShadowTemple; Lake Hylia's
picture is HyruleField's too, where its checks are, before the field's own: drawn under it); ages: C, A or CA; floor: "" an outdoor area's, "All" a dungeon's
every room as one shape, else the floor's name (B2, 1F).
<name>.hmap: "HWMP", u32 version 1, u32 format (the BNTX's), u32 width, u32 height, u32 block width, u32 block height,
u32 bytes of blocks, then the blocks in rows, top down, as one zstd frame (no dictionary).
"""
import argparse
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wheel_assets as pa   # noqa: E402 (zs_dictionary, read_zs, bntx_textures, gob_offset)

VERSION = 1
BLOCK = {0x2D: (4, 4), 0x2E: (5, 4), 0x2F: (5, 5), 0x30: (6, 5), 0x31: (6, 6), 0x32: (8, 5), 0x33: (8, 6), 0x34: (8, 8)}   # (the BNTX's ASTC formats)
# (a map whose checks are another folder's in the Tracker, drawn under that folder's own picture)
FOLDER_OF = {"LakeHylia": "HyruleField"}   # (Lon Lon Ranch is drawn on the field's own picture; the lake lies south of it)
FLOOR = re.compile(r"^(B\d|\dF)(?:_.*)?_Main$")


def floor_order(floor):
    """a floor's place from the bottom: B2 < B1 < 1F < 2F"""
    return -int(floor[1]) if floor[0] == "B" else int(floor[0])


def pictures(menu, captures, field_names, dungeon_names):
    """[(folder, ages, floor, texture name, camera x, camera z, height)] of the game's map list (MapMenuInfo's
    MapMenuParamArray), its captures (MapCaptureInfo's MapCaptureParamArray, the same order) and the pictures there are
    (the names in UI/CustomTex/Map/Field and /Dungeon). A later map of the same folder and age takes over (Ganon's
    Castle's own, after Hyrule Castle's adult picture)."""
    fields, dungeons = {}, {}
    for i, entry in enumerate(menu):
        if i >= len(captures):
            break
        pos = captures[i].get("CameraPos") or {}
        height = captures[i].get("Height")
        if not height:
            continue
        place = (float(pos.get("X", 0.0)), float(pos.get("Z", 0.0)), float(height))
        bancs, textures = entry.get("BancName") or [], entry.get("TextureName") or []
        for age in (0, 1):
            if age >= len(bancs) or age >= len(textures) or not textures[age]:
                continue
            base = re.sub(r"_(Child|Adult)(_Alternative)?$", "", bancs[age])
            folder = FOLDER_OF.get(base, base)
            if textures[age] in field_names:
                fields[(folder, base, "CA"[age])] = (textures[age],) + place
            elif not age:
                floors = {}
                for name in sorted(dungeon_names):
                    if not name.startswith(textures[age] + "_"):
                        continue
                    rest = name[len(textures[age]) + 1:]
                    m = FLOOR.match(rest)
                    if m:
                        floors.setdefault(m.group(1), name)   # (a floor's first picture: its State00, its Lv1)
                    elif rest.endswith("All") and "All" not in floors:
                        floors["All"] = name
                if floors:
                    dungeons[folder] = (floors, place)
    out = []
    for (folder, base, age), (name, x, z, height) in sorted(fields.items(), key=lambda kv: (kv[0][0], kv[0][1] == kv[0][0], kv[0][1], kv[0][2])):
        out.append((folder, age, "", name, x, z, height))
    for folder, (floors, (x, z, height)) in sorted(dungeons.items()):
        for floor in sorted(floors, key=lambda f: (f != "All", floor_order(f) if f != "All" else 0)):
            out.append((folder, "CA", floor, floors[floor], x, z, height))
    return out


def linear_blocks(b, t):
    """the texture's first level as its ASTC blocks in rows, top down (16 bytes a block), with the block's size"""
    _, fmt, w, h, gobs, data = t
    if fmt >> 8 not in BLOCK:
        raise ValueError("format %#x is not ASTC" % fmt)
    bx, by = BLOCK[fmt >> 8]
    bw, bh = (w + bx - 1) // bx, (h + by - 1) // by
    pitch = (bw * 16 + 63) // 64
    return bx, by, b"".join(b[data + o:data + o + 16] for o in (pa.gob_offset(x * 16, y, gobs, pitch) for y in range(bh) for x in range(bw)))


def game_tables(romfs, dictionary):
    """the game's map list and captures, as Python values (tools/rando/rando_seed.py's BYML reader)"""
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools", "rando"))
    import rando_seed as R

    def plain(node):
        kind, value = node
        if kind == "dict":
            return {k: plain(v) for k, v in value.items()}
        if kind == "array":
            return [plain(v) for v in value]
        if kind == 0xD2:
            return struct.unpack("<f", value)[0]
        if kind == 0xD1:
            return struct.unpack("<i", value)[0]
        return value

    def table(rel, key):
        path = os.path.join(romfs, *rel.split("/"))
        with open(path, "rb") as f:
            data = f.read()
        if data[:4] == b"\x28\xb5\x2f\xfd":
            data = pa.read_zs(romfs, os.path.join(*rel.split("/")), dictionary)
        return plain(R.byml_parse(data)[0])[key]

    return (table("Game/MapMenuInfo/MapMenuInfo.game__ui__MapMenuInfo.bgyml", "MapMenuParamArray"),
            table("Game/MapCaptureInfo/MapCaptureInfo.game__MapCaptureInfo.bgyml", "MapCaptureParamArray"))


def names_in(romfs, kind):
    folder = os.path.join(romfs, "UI", "CustomTex", "Map", kind)
    return {f[:-len(".bntx.zs")] for f in os.listdir(folder) if f.endswith(".bntx.zs")} if os.path.isdir(folder) else set()


def up_to_date(out, rows):
    """whether <out> already holds these pictures, made by this version (a build makes them once: half a minute)"""
    try:
        with open(os.path.join(out, "index.txt"), encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return False
    if not lines or lines[0] != "# map pictures %d" % VERSION:
        return False
    have = {tuple(l.split("|")[:7]) for l in lines[1:] if l.count("|") >= 8}
    want = {(folder, ages, floor, name, "%g" % x, "%g" % z, "%g" % height) for folder, ages, floor, name, x, z, height in rows}
    return have == want and all(os.path.isfile(os.path.join(out, r[3] + ".hmap")) for r in rows)


def write_maps(romfs, out):
    import zstandard
    dictionary = pa.zs_dictionary(romfs)
    menu, captures = game_tables(romfs, dictionary)
    fields, dungeons = names_in(romfs, "Field"), names_in(romfs, "Dungeon")
    rows = pictures(menu, captures, fields, dungeons)
    if not rows:
        raise ValueError("no map pictures found")
    if up_to_date(out, rows):
        print("map pictures: %d already in %s" % (len(rows), out), file=sys.stderr)
        return len(rows)
    os.makedirs(out, exist_ok=True)
    index = os.path.join(out, "index.txt")
    if os.path.exists(index):
        os.remove(index)   # (no index while the pictures are half made)
    lines, done, packer = [], set(), zstandard.ZstdCompressor(level=9)
    for folder, ages, floor, name, x, z, height in rows:
        kind = "Field" if name in fields else "Dungeon"
        b = pa.read_zs(romfs, os.path.join("UI", "CustomTex", "Map", kind, name + ".bntx.zs"), dictionary)
        tex = pa.bntx_textures(b)
        if not tex:
            continue
        t = next(iter(tex.values()))
        try:
            bx, by, blocks = linear_blocks(b, t)
        except ValueError as e:
            print("map pictures: %s left out (%s)" % (name, e), file=sys.stderr)
            continue
        if name not in done:
            with open(os.path.join(out, name + ".hmap"), "wb") as f:
                f.write(b"HWMP" + struct.pack("<IIIIIII", 1, t[1], t[2], t[3], bx, by, len(blocks)) + packer.compress(blocks))
            done.add(name)
        lines.append("%s|%s|%s|%s|%g|%g|%g|%d|%d" % (folder, ages, floor, name, x, z, height, t[2], t[3]))
    for f in os.listdir(out):   # (pictures of another version's list)
        if f.endswith(".hmap") and f[:-5] not in done:
            os.remove(os.path.join(out, f))
    with open(index, "w", encoding="utf-8", newline="\n") as f:
        f.write("# map pictures %d\n" % VERSION + "\n".join(lines) + "\n")
    print("map pictures: %d pictures in %s" % (len(done), out), file=sys.stderr)
    return len(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--romfs", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    try:
        write_maps(a.romfs, a.out)
    except Exception as e:   # (a game whose maps are not the ones known: the Tracker's maps are its marks alone)
        print("map pictures: not made (%s): the Tracker's maps show the checks without a picture" % e, file=sys.stderr)
        index = os.path.join(a.out, "index.txt")
        if os.path.exists(index):
            os.remove(index)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
