"""The Tracker's map pictures (asked 2026-11-26): the game's own map pictures behind the Tracker's checks. No game data.

The pictures are the game's, so none is in the repository or a release: a build makes them on the player's PC from their
own RomFS (nx2/map_assets.py, run by nx2/make_game.py) into <game folder>/maps, and the renderer reads them there
(gpu/vk/vk_map_pictures.cpp) for the Tracker's maps (gpu/vk/vk_menu.cpp tracker_area_map). Checked:
- which pictures a game's map list gives (map_assets.pictures: an outdoor map's two ages, Lake Hylia's under Hyrule
  Field's, a later map of a folder taking over, a dungeon's shape and its floors from the bottom up, a floor's first
  picture of several states), and that a made folder is left alone only when it holds exactly those;
- the index's lines as the renderer reads them, where a picture lies in the world (its WIDTH is the capture's height in
  metres: seen on a seed's checks 2026-11-26), and which pictures a map, an age and a floor draw: compiled and run;
- a dungeon's checks' floors from the floors' pictures (vk_menu.cpp tracker_floors_assign): compiled and run;
- the build makes them, the Tracker draws them under its marks, and nothing of them is in the repository.

    python -I -B tests/test_map_pictures.py [--cxx g++]
"""
import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from srccut import block   # noqa: E402

RUN_ALL_ARGS = ["--cxx", "{cxx}"]
FIXTURE = r"""
#include <algorithm>
#include <cfloat>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
constexpr int kMapFloors = 8;
// FUNCTIONS
int failed = 0;
void check(bool ok, const char* what) { if (!ok) printf("FAIL: %s\n", what), failed = 1; }
int main() {
    // ---- the index's lines ----
    MapRow r;
    check(!map_row_parse("# map pictures 1\n", &r) && !map_row_parse("\n", &r) && !map_row_parse("a|b|c\n", &r), "a line that is no picture's");
    check(map_row_parse("Market|C||Market_Child_00|0|3|214|2000|1440\n", &r) && r.folder == "Market" && r.ages == "C" && r.floor.empty() &&
          r.name == "Market_Child_00" && r.cam_x == 0 && r.cam_z == 3 && r.height == 214 && r.w == 2000 && r.h == 1440, "an outdoor map's line");
    check(map_row_parse("ShadowTemple|CA|B3|ShadowTemple_B3_Main|-22|7|433|2000|1440", &r) && r.floor == "B3" && r.cam_x == -22, "a floor's line");
    check(!map_row_parse("Market|C||Market_Child_00|0|3|0|2000|1440", &r) && !map_row_parse("Market|C||Market_Child_00|0|3|214|0|1440", &r), "a line without a size");
    // ---- where a picture lies: its width is the capture's height in metres ----
    map_row_parse("Market|C||Market_Child_00|0|3|214|2000|1440", &r);
    float q[4];
    map_row_rect(r, q);
    check(fabsf(q[0] + 107) < 1e-3f && fabsf(q[2] - 107) < 1e-3f && fabsf(q[1] - (3 - 77.04f)) < 1e-3f && fabsf(q[3] - (3 + 77.04f)) < 1e-3f, "the Market's picture's place");
    // (a place 20 m east of the Market's middle and 67 m south of it, by its south gate: 187 pixels right of the 2000 x 1440
    //  picture's middle and 626 below it)
    const float px = (20.0f - q[0]) / (q[2] - q[0]) * r.w, pz = (70.0f - q[1]) / (q[3] - q[1]) * r.h;
    check(fabsf(px - 1186.9f) < 1 && fabsf(pz - 1346.2f) < 1, "a place on the Market's picture");
    // ---- the pictures a map draws ----
    std::vector<MapRow> rows;
    for (const char* line : {"HyruleField|A||LakeHylia_Adult_00|-200|490|422|2000|1440", "HyruleField|C||LakeHylia_Child_00|-200|490|422|2000|1440",
                             "HyruleField|A||HyruleField_Adult_00|-23|197|736|2000|1440", "HyruleField|C||HyruleField_Child_00|-23|197|736|2000|1440",
                             "HyruleCastle|C||HyruleCastle_Child_00|0|-80|242|2000|1440",
                             "ShadowTemple|CA|All|ShadowTemple_All|-22|7|433|2000|1440", "ShadowTemple|CA|B4|ShadowTemple_B4_State00_Main|-22|7|433|2000|1440",
                             "ShadowTemple|CA|B3|ShadowTemple_B3_Main|-22|7|433|2000|1440", "ShadowTemple|CA|B1|ShadowTemple_B1_Main|-22|7|433|2000|1440"}) {
        MapRow x;
        check(map_row_parse(line, &x), line);
        rows.push_back(x);
    }
    int at[3];
    check(map_rows_pick(rows, "HyruleField", 0, "", at, 3) == 2 && rows[at[0]].name == "LakeHylia_Child_00" && rows[at[1]].name == "HyruleField_Child_00", "the child's field: the lake under it");
    check(map_rows_pick(rows, "HyruleField", 1, "", at, 3) == 2 && rows[at[0]].name == "LakeHylia_Adult_00" && rows[at[1]].name == "HyruleField_Adult_00", "the adult's field");
    check(map_rows_pick(rows, "HyruleField", -1, "", at, 3) == 2 && rows[at[1]].name == "HyruleField_Child_00", "an age not known: the child's");
    check(map_rows_pick(rows, "HyruleCastle", 1, "", at, 3) == 1 && rows[at[0]].name == "HyruleCastle_Child_00", "a map with no picture of his age: the one it has");
    check(map_rows_pick(rows, "ShadowTemple", 1, "", at, 3) == 1 && rows[at[0]].floor == "All", "a dungeon with no floor looked at: its shape");
    check(map_rows_pick(rows, "ShadowTemple", 1, "B3", at, 3) == 2 && rows[at[0]].floor == "All" && rows[at[1]].name == "ShadowTemple_B3_Main", "a dungeon's floor over its shape");
    check(map_rows_pick(rows, "GerudoTrainingGround", 1, "", at, 3) == 0, "a map without pictures");
    check(map_rows_pick(rows, "HyruleField", 0, "", at, 1) == 1, "no more than asked for");
    int fl[8];
    check(map_rows_floors(rows, "ShadowTemple", fl, 8) == 3 && rows[fl[0]].floor == "B4" && rows[fl[2]].floor == "B1" && map_rows_floors(rows, "HyruleField", fl, 8) == 0, "a dungeon's floors");
    // ---- a check's floor from the floors' pictures ----
    {   // (three floors, at about 40, 60 and 90. Checks on one picture alone say its height; one where two rooms lie over
        //  each other goes to the nearer in height; one on no picture to the nearest; a floor none is alone on is taken
        //  only by a check on it alone)
        const unsigned bits[] = {1, 1, 2, 2, 2, 4, 3, 3, 6, 0, 0};
        const float y[] = {40, 42, 58, 60, 63, 90, 41, 61, 88, 39, 95};
        int out[11];
        tracker_floors_assign(bits, y, 11, 3, out);
        const int want[] = {0, 0, 1, 1, 1, 2, 0, 1, 2, 0, 2};
        for (int i = 0; i < 11; i++) check(out[i] == want[i], "a check's floor");
        const unsigned lone[] = {1, 1, 6, 4};   // (the middle floor: no check on it alone)
        const float ly[] = {40, 41, 90, 91};
        tracker_floors_assign(lone, ly, 4, 3, out);
        check(out[0] == 0 && out[2] == 2 && out[3] == 2, "floors where one has no check of its own");
        const unsigned none[] = {0, 0};
        const float ny[] = {1, 2};
        tracker_floors_assign(none, ny, 2, 3, out);
        check(out[0] == -1 && out[1] == -1, "no check on any picture: not known");
        const unsigned both[] = {3};   // (one check, on two pictures, neither's height known: the lower)
        tracker_floors_assign(both, ny, 1, 2, out);
        check(out[0] == 0, "a check on two pictures of unknown height");
    }
    if (!failed) puts("ok");
    return failed;
}
"""


def check(ok, why):
    if not ok:
        print("FAIL: %s" % why)
        sys.exit(1)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cxx", default="g++")
    a = p.parse_args()
    spec = importlib.util.spec_from_file_location("map_assets", ROOT / "nx2" / "map_assets.py")
    sys.path.insert(0, str(ROOT / "nx2"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    # ---- which pictures a game's map list gives ----
    menu = [
        {"BancName": ["Market_Child", "Market_Adult"], "TextureName": ["Market_Child_00", "Market_Adult_00", ""]},
        {"BancName": ["HyruleField_Child", "HyruleField_Adult"], "TextureName": ["HyruleField_Child_00", "HyruleField_Adult_00", ""]},
        {"BancName": ["HyruleCastle", "GanonCastle"], "TextureName": ["HyruleCastle_Child_00", "GanonCastle_Adult_00", ""]},
        {"BancName": ["LakeHylia_Child", "LakeHylia_Adult"], "TextureName": ["LakeHylia_Child_00", "LakeHylia_Adult_00", ""]},
        {"BancName": ["KakarikoVillage_Child", "KakarikoVillage_Adult_Alternative"], "TextureName": ["KakarikoVillage_Child_00", "KakarikoVillage_Adult_00", ""]},
        {"BancName": ["ShadowTemple", "ShadowTemple"], "TextureName": ["ShadowTemple", "ShadowTemple", ""]},
        {"BancName": ["SpiritTemple", "SpiritTemple"], "TextureName": ["SpiritTemple", "SpiritTemple", ""]},
        {"BancName": ["GanonCastle", "GanonCastle"], "TextureName": ["GanonCastle_Adult_00", "GanonCastle_Adult_00", ""]},
        {"BancName": ["Nowhere", "Nowhere"], "TextureName": ["Nowhere_00", "Nowhere_00", ""]},   # (no such picture)
        {"BancName": ["Late_Child", "Late_Adult"], "TextureName": ["Market_Child_00", "Market_Adult_00", ""]},   # (no capture: past the list's end)
    ]
    captures = [{"CameraPos": {"X": 0.0, "Z": 3.0}, "Height": 214.0}, {"CameraPos": {"X": -23.0, "Z": 197.0}, "Height": 736.0},
                {"CameraPos": {"Z": -80.0}, "Height": 242.0}, {"CameraPos": {"X": -200.0, "Z": 490.0}, "Height": 422.0},
                {"CameraPos": {"X": -50.0, "Z": 42.0}, "Height": 246.0}, {"CameraPos": {"X": -22.0, "Z": 7.0}, "Height": 433.0},
                {"CameraPos": {"Z": -24.0}, "Height": 202.0}, {"CameraPos": {"X": 61.0, "Z": 297.0}, "Height": 268.0}, {"Height": 100.0}]
    fields = {"Market_Child_00", "Market_Adult_00", "HyruleField_Child_00", "HyruleField_Adult_00", "HyruleCastle_Child_00", "GanonCastle_Adult_00",
              "LakeHylia_Child_00", "LakeHylia_Adult_00", "KakarikoVillage_Child_00", "KakarikoVillage_Adult_00", "Mini_Market_Child_00"}
    dungeons = {"ShadowTemple_All", "ShadowTemple_B1_Main", "ShadowTemple_B1_Alpha", "ShadowTemple_B2_Main", "ShadowTemple_B3_Main",
                "ShadowTemple_B4_State00_Main", "ShadowTemple_B4_State01_Main", "ShadowTemple_B4_Back",
                "SpiritTemple_State00_All", "SpiritTemple_State01_All", "SpiritTemple_1F_Main", "SpiritTemple_3F_State01_Main", "SpiritTemple_3F_State00_Main",
                "ShadowTempleX_1F_Main"}
    rows = m.pictures(menu, captures, fields, dungeons)
    got = [(r[0], r[1], r[2], r[3]) for r in rows]
    check(got == [
        ("GanonCastle", "A", "", "GanonCastle_Adult_00"), ("GanonCastle", "C", "", "GanonCastle_Adult_00"),
        ("HyruleCastle", "C", "", "HyruleCastle_Child_00"),
        ("HyruleField", "A", "", "LakeHylia_Adult_00"), ("HyruleField", "C", "", "LakeHylia_Child_00"),
        ("HyruleField", "A", "", "HyruleField_Adult_00"), ("HyruleField", "C", "", "HyruleField_Child_00"),
        ("KakarikoVillage", "A", "", "KakarikoVillage_Adult_00"), ("KakarikoVillage", "C", "", "KakarikoVillage_Child_00"),
        ("Market", "A", "", "Market_Adult_00"), ("Market", "C", "", "Market_Child_00"),
        ("ShadowTemple", "CA", "All", "ShadowTemple_All"), ("ShadowTemple", "CA", "B4", "ShadowTemple_B4_State00_Main"),
        ("ShadowTemple", "CA", "B3", "ShadowTemple_B3_Main"), ("ShadowTemple", "CA", "B2", "ShadowTemple_B2_Main"), ("ShadowTemple", "CA", "B1", "ShadowTemple_B1_Main"),
        ("SpiritTemple", "CA", "All", "SpiritTemple_State00_All"), ("SpiritTemple", "CA", "1F", "SpiritTemple_1F_Main"), ("SpiritTemple", "CA", "3F", "SpiritTemple_3F_State00_Main"),
    ], "the pictures of a map list:\n" + "\n".join(map(str, got)))
    by = {(r[0], r[1], r[3]): r[4:] for r in rows}
    check(by[("GanonCastle", "A", "GanonCastle_Adult_00")] == (61.0, 297.0, 268.0), "Ganon's Castle's own capture does not take over Hyrule Castle's")
    check(by[("HyruleField", "C", "LakeHylia_Child_00")] == (-200.0, 490.0, 422.0) and by[("HyruleCastle", "C", "HyruleCastle_Child_00")] == (0.0, -80.0, 242.0),
          "a picture's camera is not its own map's")
    check([m.floor_order(f) for f in ("B2", "B1", "1F", "3F")] == [-2, -1, 1, 3], "the floors' order")
    # ---- a made folder is left only when it holds exactly these pictures, of this version ----
    with tempfile.TemporaryDirectory(prefix="map-pictures-") as tmp:
        check(not m.up_to_date(tmp, rows), "an empty folder is taken for made")
        lines = ["%s|%s|%s|%s|%g|%g|%g|2000|1440" % r for r in rows]
        for r in rows:
            Path(tmp, r[3] + ".hmap").write_bytes(b"x")
        Path(tmp, "index.txt").write_text("# map pictures %d\n" % m.VERSION + "\n".join(lines) + "\n", encoding="utf-8")
        check(m.up_to_date(tmp, rows), "a made folder is made again")
        check(not m.up_to_date(tmp, rows[:-1]) and not m.up_to_date(tmp, [("Other",) + rows[0][1:]] + rows[1:]), "a folder of other pictures is left as it is")
        Path(tmp, "index.txt").write_text("# map pictures %d\n" % (m.VERSION + 1) + "\n".join(lines) + "\n", encoding="utf-8")
        check(not m.up_to_date(tmp, rows), "another version's folder is left as it is")
        Path(tmp, "index.txt").write_text("# map pictures %d\n" % m.VERSION + "\n".join(lines) + "\n", encoding="utf-8")
        os.remove(Path(tmp, rows[0][3] + ".hmap"))
        check(not m.up_to_date(tmp, rows), "a folder missing a picture is left as it is")

    # ---- the renderer's side: compiled and run ----
    pics = (ROOT / "gpu" / "vk" / "vk_map_pictures.cpp").read_text(encoding="utf-8")
    menu_cpp = (ROOT / "gpu" / "vk" / "vk_menu.cpp").read_text(encoding="utf-8")
    functions = "\n".join([block(pics, "struct MapRow {") + ";"] + [block(pics, marker) for marker in (
        "bool map_row_parse(const char* line, MapRow* row) {", "void map_row_rect(const MapRow& r, float out[4]) {",
        "int map_rows_pick(const std::vector<MapRow>& rows, const char* folder, int age, const char* floor, int* picked, int max) {",
        "int map_rows_floors(const std::vector<MapRow>& rows, const char* folder, int* picked, int max) {")] +
        [block(menu_cpp, "void tracker_floors_assign(const unsigned* bits, const float* y, int n, int floors, int* out) {")])
    with tempfile.TemporaryDirectory(prefix="map-pictures-") as tmp:
        cpp, exe = Path(tmp) / "fixture.cpp", Path(tmp) / "fixture.exe"
        cpp.write_text(FIXTURE.replace("// FUNCTIONS", functions), encoding="utf-8")
        subprocess.run([a.cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror", str(cpp), "-o", str(exe)], check=True)
        # (llvm-mingw's programs want its libc++.dll, which is beside the compiler and not on PATH)
        beside = os.path.dirname(shutil.which(a.cxx) or "")
        env = dict(os.environ, PATH=beside + os.pathsep + os.environ.get("PATH", ""))
        ran = subprocess.run([str(exe)], capture_output=True, text=True, env=env)
    check(ran.returncode == 0 and ran.stdout.strip() == "ok", "the map pictures' functions:\n" + ran.stdout + ran.stderr)

    # ---- the file's layout is the same on both sides ----
    asset = (ROOT / "nx2" / "map_assets.py").read_text(encoding="utf-8")
    check('b"HWMP" + struct.pack("<IIIIIII", 1, t[1], t[2], t[3], bx, by, len(blocks)) + packer.compress(blocks)' in asset and
          '!std::memcmp(magic, "HWMP", 4) && fread(hd, 4, 7, f) == 7 && hd[0] == 1' in pics and
          "hd[6] == (uint64_t)((hd[2] + hd[4] - 1) / hd[4]) * ((hd[3] + hd[5] - 1) / hd[5]) * 16" in pics and
          "Tegra::Texture::ASTC::DecompressSerial(blocks, w, h, 1, hd[4], hd[5], full);" in pics, "a picture's file is not read as it is written")
    check('lines.append("%s|%s|%s|%s|%g|%g|%g|%d|%d" % (folder, ages, floor, name, x, z, height, t[2], t[3]))' in asset and
          'f.write("# map pictures %d\\n" % VERSION' in asset, "the index is not written as the renderer reads it")
    # ---- the build makes them; the Tracker draws them under its marks ----
    make = (ROOT / "nx2" / "make_game.py").read_text(encoding="utf-8")
    check('os.path.join(HERE, "map_assets.py"), "--romfs", romfs, "--out", os.path.join(out, "maps")], check=False' in make, "the build does not make the map pictures")
    area = block(menu_cpp, "void tracker_area_map(ui::Ctx& c, float x0, float x1, float y0, float y1, int row) {")
    check('const int layer_n = folder ? map_layers(folder, age, floor_now >= 0 ? floor_names[floor_now] : "", layers) : 0;' in area and
          "c.d->AddImage(layers[i].tex->GetTexRef(), ImVec2(ox + layers[i].x0 * scale, oy + layers[i].z0 * scale)," in area and
          area.index("c.d->AddImage(layers[i].tex->GetTexRef(), ImVec2(ox + layers[i].x0 * scale") < area.index("AddTriangleFilled(tip, l, rr,"),
          "the Tracker's map does not draw the map's pictures under Link and the marks")
    check("const int floor_n = dungeon && folder ? map_floors(folder, floor_names) : 0;" in area and
          "tracker_floors_assign(bits.data(), ys.data(), (int)bits.size(), floor_n, got.data());" in area and
          "return floor_now >= 0 && f >= 0 ? f != floor_now : !tracker_same_floor(k.pos[1], floor_at);" in area,
          "a dungeon's floors are not the floor pictures', with the height's as the way back")
    # ---- nothing of the game's pictures is in the repository ----
    tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True).stdout.splitlines()
    check(not [f for f in tracked if f.endswith(".hmap") or re.match(r"(?:.*/)?maps/index\.txt$", f)], "a map picture is in the repository")
    print("PASS: the Tracker's map pictures")


if __name__ == "__main__":
    main()
