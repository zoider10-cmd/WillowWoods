#!/usr/bin/env python3
"""The Tracker in a window of the launcher's, beside the game (Willow Woods, asked 2026-11-27: "viewable while playing.
Something like a pop out window").

The window works nothing out. The menu writes what it knows to <game folder>\\rando\\tracker_live.txt while the randomizer's
game runs (gpu/vk/vk_menu.cpp tracker_live_write, from menu_tick: the seed's stamp, the area Link is in, a letter a check,
the checks in logic nearest first, a line a dungeon), and the launcher's TrackerForm shows it with the seed's own files and
the game's records of the doors, boss rooms and stones found. This check reads both sides' source for the file's form, and
where the .NET Framework's compiler is, builds the launcher and has the window list a made-up seed's rows.
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))   # (tests/srccut.py: python -I leaves this folder off the path)
from srccut import block   # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def check(ok, what):
    if not ok:
        raise SystemExit("FAIL: " + what)


def rows(exe, game, view, area=None):
    ran = subprocess.run([str(exe), "--tracker-rows", str(game), str(view)] + ([area] if area else []), capture_output=True, timeout=60)
    check(ran.returncode == 0, "the window's rows could not be listed: %r" % ran.stderr)
    return ran.stdout.decode("utf-8").replace("\r\n", "\n").split("\n")


def main():
    menu = (ROOT / "gpu" / "vk" / "vk_menu.cpp").read_text(encoding="utf-8")
    src = (ROOT / "launcher" / "Launcher.cs").read_text(encoding="utf-8-sig")
    # ---- the menu's side: the file, written from menu_tick whether the menu is open or not, and only when it changed ----
    words = block(menu, "std::string tracker_live_words() {")
    check('std::string out = "seed " + tracker_junk_stamp + "\\n";' in words and 'out += std::string("here ") + (here ? here : "") + "\\nstates ";' in words
          and "out += done == 1 ? 'c' : tracker_junk[i] ? 'j' : done < 0 || state < 0 ? '?' : state > 0 ? 'i' : 'o';" in words
          and 'std::string nearest = "near";' in words and "for (const int i : tracker_near)" in words
          and 'out += std::string("dungeon ") + kDungeonTitles[d] + "|"' in words, "the live file's lines are not the ones the window reads")
    write = block(menu, "void tracker_live_write() {")
    check("next = now + 2000;" in write and "if (!tracker_on.load(std::memory_order_relaxed)) return;" in write
          and "if (words == last) return;" in write and 'game_folder_path() + "rando\\\\tracker_live.txt", fresh = path + ".new";' in write
          and "std::filesystem::rename(fresh, path, ec);" in write and "if (!tracker_check_count) tracker_load(false);" in write,
          "the live file is not written every two seconds at most, only when it changed, whole (a file beside it renamed)")
    check("tracker_live_write();" in block(menu, "void menu_tick() {"), "the live file is not written from the menu's tick")
    # (a load for the file or the minimap is not the tab coming on screen: its rows are laid out when it does)
    load = block(menu, "void tracker_load(bool shown) {")
    check("if (shown) {" in load and "if (sort && shown) {" in load and "void tracker_load(bool shown = true);" in menu,
          "a load with the tab off screen lays its rows out, or counts as the tab shown")
    # ---- the launcher's side ----
    check('Path.Combine(dir, "rando", name)' in src and 'Rando("tracker_live.txt")' in src and 'mine = stamp.Length > 0 && line.Substring(5) == stamp;' in src
          and "live = mine && states.Length == checks.Count && checks.Count > 0;" in src, "the window takes a live file of another seed, or of other checks")
    check('widgets.Add(new Btn { Text = "Tracker", R = new RectangleF(cx + 236, 542, 84, 36), Page = RandoPage, Click = OnTracker });' in src
          and "if (tracker == null || tracker.IsDisposed) { tracker = new TrackerForm(dir); tracker.Show(); return; }" in src,
          "the Randomizer page has no Tracker button, or it opens a second window")
    check("const int MostChecks = 1024;" in src and "constexpr int kTrackerChecks = 1024;" in menu or
          re.search(r"kTrackerChecks = OOT_TRACKER_MAX|#define OOT_TRACKER_MAX 1024", menu + (ROOT / "gpu/vk/oot_cheat_items.h").read_text(encoding="utf-8")),
          "the window counts more checks than the menu keeps")
    # (the dungeons among the areas: the menu's map's)
    world = menu[menu.index("constexpr WorldArea kWorldMap[] = {"):menu.index("constexpr const char* kWorldEdges")]
    dungeons = [m.group(1).replace("\\'", "'") for m in re.finditer(r'\{"([^"]+)", "[^"]+", [\d.]+f, [\d.]+f, 1, "', world)]
    mine = re.search(r"public static readonly string\[\] Dungeons = \{(.*?)\};", src, re.S).group(1)
    check(sorted(re.findall(r'"([^"]+)"', mine)) == sorted(dungeons) and len(dungeons) == 12, "the window's dungeons are not the menu's map's")

    csc = Path(os.environ.get("WINDIR", "")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
    if os.name != "nt" or not csc.is_file():
        print("PASS: the Tracker's window (the source only: no .NET Framework compiler here)")
        return
    with tempfile.TemporaryDirectory() as tmp:
        exe, game = Path(tmp) / "launcher_test.exe", Path(tmp) / "game"
        seed, rando = game / "mods" / "rando-seed", game / "rando"
        seed.mkdir(parents=True)
        rando.mkdir()
        built = subprocess.run([str(csc), "/nologo", "/target:winexe", "/out:" + str(exe), "/r:System.Windows.Forms.dll", "/r:System.Drawing.dll",
                                "/r:System.IO.Compression.dll", "/r:System.IO.Compression.FileSystem.dll", "/r:Microsoft.VisualBasic.dll", "/r:System.Core.dll",
                                str(ROOT / "launcher" / "Launcher.cs"), str(ROOT / "launcher" / "Mods.cs")], capture_output=True, text=True)
        check(built.returncode == 0, "the launcher does not compile:\n" + built.stdout + built.stderr)
        (seed / "rando_stamp.txt").write_text("placement 42 seed 7\nmore\n", encoding="utf-8")
        (seed / "checks.txt").write_text(
            "# the checks\n"
            "Kokiri Forest|Chest A|KokiriForest|CA|1.0 2.0 3.0|-|aa|Item_Melody_ZeldaLullaby|1.0 2.0 3.0\n"
            "Kokiri Forest|Chest B|KokiriForest|C|1.0 2.0 3.0|KS|bb|TBox_Rupee_Red\n"
            "not a check\n"
            "Forest Temple|Chest C|ForestTemple|A|1.0 2.0 3.0|HS|cc|-\n"
            "Market|Pot #1|Market|CA|1.0 2.0 3.0|-|dd|-\n", encoding="utf-8")
        (seed / "entrances.txt").write_text("ForestTemple|FireTemple|Forest Temple|Fire Temple\nFireTemple|ForestTemple|Fire Temple|Forest Temple\n", encoding="utf-8")
        (seed / "boss_doors.txt").write_text("ForestTemple|ForestTemple|Forest Temple|Forest Temple\n", encoding="utf-8")
        (seed / "rando_hints.txt").write_text("Stone 1|Market|0 0 0|They say the Market hides a sword.\nStone 2|Market|0 0 0|They say nothing.\n", encoding="utf-8")
        # (before the game has run: the seed's checks, nothing known of them)
        got = rows(exe, game, 1)
        check(got[0] == "4 checks in this seed. / Start the game: the tracker fills in while it runs.", "no live file: the window does not say to start the game: %r" % got[0])
        check(got[1:] == ["#|Overworld|", " |Kokiri Forest|2 checks", " |Market|1 check", "#|Dungeons|", " |Forest Temple|1 check", ""],
              "the areas are not listed in the menu's groups before the game has run: %r" % got[1:])
        check(rows(exe, game, 0)[1:] == [" |Nothing known until the game runs.|", ""], "no live file: something is said to be in logic")
        # (the game's word: A collected, B in logic, C not, the pot junk; Link in the forest; the pot is not near, being junk)
        live = "seed placement 42 seed 7\nhere Kokiri Forest\nstates cioj\nnear 1\ndungeon Forest Temple|2|5|1|0|1\ndungeon Deku Tree|0|0|1|1|-\n"
        (rando / "tracker_live.txt").write_text(live, encoding="utf-8")
        (rando / "doors_seen.txt").write_text("seed placement 42 seed 7\nForestTemple\n", encoding="utf-8")
        (rando / "boss_rooms_seen.txt").write_text("seed placement 42 seed 7\nForestTemple\n", encoding="utf-8")
        (rando / "hints_heard.txt").write_text("seed placement 42 seed 7\nStone 1\n", encoding="utf-8")
        got = rows(exe, game, 0)
        check(got[0].startswith("1 of 4 collected, 1 junk, 1 in logic now / Link is in: Kokiri Forest"), "the top line does not count the checks: %r" % got[0])
        check(got[1:] == ["#|Kokiri Forest|here", "i|Chest B (child)|", ""], "In logic now does not list the checks in logic under their areas: %r" % got[1:])
        got = rows(exe, game, 1)
        check(got[1:] == ["#|Overworld|", "i|Kokiri Forest  (here)|1 left, 1 in logic", "#|Dungeons|", "o|Forest Temple|1 left",
                          "#|Finished areas|", " |Market|all collected", ""], "the areas' groups, counts and finished ones are not the menu's: %r" % got[1:])
        got = rows(exe, game, 1, "Kokiri Forest")
        check(got[1:] == [" |<  Back to the areas|", "#|Kokiri Forest|", "c|Chest A|Melody Zelda Lullaby", "i|Chest B (child)|", ""],
              "an area's checks are not listed with their marks and what a collected one gave: %r" % got[1:])
        check(rows(exe, game, 2)[1:] == ["#|Door of|leads to", " |Forest Temple|Fire Temple", " |Fire Temple|?",
                                         "#|Boss room of|has the boss of", " |Forest Temple|its own boss", ""],
              "a door or a boss room is told before it is found, or not once it is")
        check(rows(exe, game, 3)[1:] == ["#|Dungeon|keys, map, compass, Boss Key", " |Forest Temple|2 of 5 keys, map yes, compass no, Boss Key yes",
                                         " |Deku Tree|no keys, map yes, compass yes", ""], "the dungeons' keys and items are not the live file's")
        check(rows(exe, game, 4)[1:] == ["#|1 of 2 hints heard|", " |They say the Market hides a sword.|", ""], "the hints heard are not listed, or one not heard is")
        # (another seed's live file, and one of other checks: not taken)
        (rando / "tracker_live.txt").write_text(live.replace("seed 7", "seed 8"), encoding="utf-8")
        check(rows(exe, game, 0)[1:] == [" |Nothing known until the game runs.|", ""], "another seed's live file is shown")
        (rando / "tracker_live.txt").write_text(live.replace("states cioj", "states cio"), encoding="utf-8")
        check(rows(exe, game, 0)[1:] == [" |Nothing known until the game runs.|", ""], "a live file of fewer checks is shown")
        check(not (rando / "tracker_window.txt").exists(), "a window never shown wrote its place")
    print("PASS: the Tracker's window, and the file the game writes for it")


if __name__ == "__main__":
    main()
