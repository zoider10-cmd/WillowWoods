#!/usr/bin/env python3
"""The Tracker in a window of its own, beside the game (Willow Woods, asked 2026-11-27: "viewable while playing.
Something like a pop out window"; then "i want it to be able to start the pop-out while in-game too" and "more detailed").

The window works nothing out. The menu writes what it knows to <game folder>\\rando\\tracker_live.txt while the randomizer's
game runs (gpu/vk/vk_menu.cpp tracker_live_write, from menu_tick, a few checks a frame: the seed's stamp, the area Link is
in, a letter a check, the checks in logic nearest first, a line a dungeon, then what each collected check gave and what
each one not in logic lacks), and the launcher's TrackerForm shows it with the seed's own files and the game's records of
the doors, boss rooms and stones found. The window is a program of its own (the launcher's exe with "--tracker <game
folder>"), so it stays when the launcher closes as the game starts, and the Tracker tab's Tracker window row starts it
from the game. This check reads both sides' source, and where the .NET Framework's compiler is, builds the launcher and
has the window list a made-up seed's rows, narrow and wide.
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
    # ---- the menu's side: the file's lines ----
    one = block(menu, "void tracker_live_check(int i, TrackerLive& live) {")
    check("live.states += done == 1 ? 'c' : tracker_junk[i] ? 'j' : done < 0 || state < 0 ? '?' : state > 0 ? 'i' : 'o';" in one
          and 'live.detail += "gave " + std::to_string(i) + "|" + tracker_item_name(tracker_checks[i].gives) + "\\n";' in one
          and 'std::string words = missing.empty() ? std::string() : "needs " + missing;' in one
          and 'if (!after.empty()) words += (words.empty() ? "" : "; ") + ("after " + after);' in one
          and 'live.detail += "note " + std::to_string(i) + "|" + words + "\\n";' in one,
          "a check's letter, what it gave or what it lacks are not written as the window reads them")
    words = block(menu, "std::string tracker_live_words(const TrackerLive& live) {")
    check('std::string out = "seed " + tracker_junk_stamp + "\\n";' in words and '(here ? here : "") + "\\nstates " + live.states + "\\n";' in words
          and 'std::string nearest = "near";' in words and "for (const int i : tracker_near)" in words
          and 'out += std::string("dungeon ") + kDungeonTitles[d] + "|"' in words and "return out + live.detail;" in words,
          "the live file's lines are not the ones the window reads")
    # (written from menu_tick whether the menu is open or not: a look every two seconds, a few checks a frame (made in one go
    #  the words took 5 to 7 ms, measured 2026-11-27), only when they changed, by a thread of its own, whole)
    write = block(menu, "void tracker_live_write() {")
    check("next = now + 2000;" in write and "if (!tracker_on.load(std::memory_order_relaxed)) return;" in write
          and "for (int n = 0; n < kLiveSlice && at < count; n++, at++) tracker_live_check(at, live);" in write
          and re.search(r"constexpr int kLiveSlice = (\d+);", menu) and int(re.search(r"constexpr int kLiveSlice = (\d+);", menu).group(1)) <= 16
          and "if (count != tracker_check_count) {" in write and "if (words == last) return;" in write
          # (and with it: the map's pictures handed over once the window has asked, and Link's place in a small file of its own)
          and "mkwvk::map_export_wanted();" in write and 'path = game_folder_path() + "rando\\\\tracker_link.txt"] {' in write
          and 'std::thread([words, path = game_folder_path() + "rando\\\\tracker_live.txt"] {' in write
          and "std::filesystem::rename(fresh, path, ec);" in write and "if (!tracker_check_count) tracker_load(false);" in write,
          "the live file is not made a few checks a frame, or not written only when it changed, whole, off the frame's thread")
    check("tracker_live_write();" in block(menu, "void menu_tick() {"), "the live file is not written from the menu's tick")
    # (a load for the file or the minimap is not the tab coming on screen: its rows are laid out when it does)
    load = block(menu, "void tracker_load(bool shown) {")
    check("if (shown) {" in load and "if (sort && shown) {" in load and "void tracker_load(bool shown = true);" in menu,
          "a load with the tab off screen lays its rows out, or counts as the tab shown")
    # ---- the window started from the game: the Tracker window row ----
    start = block(menu, "bool tracker_window_open() {")
    check('L"\\\\Willow Woods Launcher.exe";' in start and 'std::wstring cmd = L"\\"" + exe + L"\\" --tracker \\"" + folder + L"\\"";' in start
          and "CreateProcessW(nullptr, cmd.data()," in start and "GetModuleFileNameW(nullptr, folder, MAX_PATH);" in start,
          "the game does not start the launcher as the Tracker's window, by wide paths")
    check("constexpr int kTrackerWindowRow = 7;" in menu and "tracker_window_started = tracker_window_open();" in menu
          and '"Tracker window"};' in menu, "the Tracker tab has no Tracker window row that starts it")
    # (the owner, 2026-11-27: a click on the row's "Open it beside the game" did nothing: a Tracker row's value took a click
    #  as Left or Right, which this row has not. The rows that only confirm take a click anywhere as the confirm)
    check("if (d.tracker == kTrackerWindowRow || d.tracker == kTrackerHomeRow || (d.tracker >= kTrackerFirstArea && tracker_kind[d.tracker] == 'D'))\n"
          "                            press[7] = true;\n                        else if (hit.side != 0) press[hit.side < 0 ? 3 : 4] = true;" in menu,
          "a click on the Tracker window row (or Return home, or Finished areas) is not its confirm")
    # ---- the launcher's side ----
    check('Path.Combine(dir, "rando", name)' in src and 'Rando("tracker_live.txt")' in src and 'mine = stamp.Length > 0 && line.Substring(5) == stamp;' in src
          and "live = mine && states.Length == checks.Count && checks.Count > 0;" in src, "the window takes a live file of another seed, or of other checks")
    check('widgets.Add(new Btn { Text = "Tracker", R = new RectangleF(cx + 236, 542, 84, 36), Page = RandoPage, Click = OnTracker });' in src
          and 'Process.Start(new ProcessStartInfo(Application.ExecutablePath, "--tracker \\"" + dir + "\\"")' in src,
          "the Randomizer page has no Tracker button, or the window is not a program of its own (it would close with the launcher)")
    check('var one = new Mutex(true, "WillowWoodsTracker", out alone);' in src and "TrackerForm.Others(h => { ShowWindow(h, 9); SetForegroundWindow(h); });" in src,
          "a second start opens a second window instead of bringing the first to the front")
    check(src.index("TrackerForm.CloseOthers();") < src.index("Close();   // (the builder rebuilds this folder, this launcher with it)"),
          "an open Tracker window is not shut before the builder replaces the launcher's exe")
    items = (ROOT / "gpu" / "vk" / "oot_cheat_items.h").read_text(encoding="utf-8")
    check("const int MostChecks = 1024;" in src and re.search(r"#define OOT_TRACKER_MAX 1024\b", items) and "constexpr int kTrackerChecks = OOT_TRACKER_MAX;" in menu
          or "constexpr int kTrackerChecks = 1024;" in menu, "the window counts another number of checks than the menu keeps")
    # (the dungeons among the areas: the menu's map's)
    world = menu[menu.index("constexpr WorldArea kWorldMap[] = {"):menu.index("constexpr const char* kWorldEdges")]
    dungeons = [m.group(1) for m in re.finditer(r'\{"([^"]+)", "[^"]+", [\d.]+f, [\d.]+f, 1, "', world)]
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
        nothing = ["#|In logic now|", " |Nothing known until the game runs.|", ""]
        # (before the game has run: the seed's checks, nothing known of them)
        got = rows(exe, game, 1)
        check(got[0] == "4 checks in this seed. / Start the game: the tracker fills in while it runs.", "no live file: the window does not say to start the game: %r" % got[0])
        check(got[1:] == ["#|Overworld|", " |Kokiri Forest|2 checks", " |Market|1 check", "#|Dungeons|", " |Forest Temple|1 check", ""],
              "the areas are not listed in the menu's groups before the game has run: %r" % got[1:])
        check(rows(exe, game, 0)[1:] == nothing, "no live file: something is said to be in logic")
        # (the game's word: A collected, B in logic, C not, the pot junk; Link in the forest; the pot is not near, being junk)
        live = ("seed placement 42 seed 7\nhere Kokiri Forest\nstates cioj\nnear 1\ndungeon Forest Temple|2|5|1|0|1\ndungeon Deku Tree|0|0|1|1|-\n"
                "gave 0|Zelda's Lullaby\nnote 2|needs Hookshot; after the Forest Temple\nnote 9|out of range\n")
        (rando / "tracker_live.txt").write_text(live, encoding="utf-8")
        (rando / "doors_seen.txt").write_text("seed placement 42 seed 7\nForestTemple\n", encoding="utf-8")
        (rando / "boss_rooms_seen.txt").write_text("seed placement 42 seed 7\nForestTemple\n", encoding="utf-8")
        (rando / "hints_heard.txt").write_text("seed placement 42 seed 7\nStone 1\n", encoding="utf-8")
        now = ["#|In logic now|1 check, nearest first", "#|Kokiri Forest|here", "i|Chest B (child)|"]
        forest = ["#|Kokiri Forest|1 of 2 left, 1 in logic", "i|Chest B (child)|", "c|Chest A|Zelda's Lullaby"]
        doors = ["#|Door of|leads to", " |Forest Temple|Fire Temple", " |Fire Temple|?", "#|Boss room of|has the boss of", " |Forest Temple|its own boss"]
        items = ["#|Dungeon items|keys in hand", " |Forest Temple|2 of 5 keys|map yes, compass no, Boss Key yes", " |Deku Tree|no keys|map yes, compass yes"]
        hints = ["#|1 of 2 hints heard|", " |They say the Market hides a sword.|"]
        got = rows(exe, game, 0)
        check(got[0].startswith("1 of 4 collected, 1 junk, 1 in logic now / Link is in: Kokiri Forest"), "the top line does not count the checks: %r" % got[0])
        check(got[1:] == now + [""], "In logic now does not list the checks in logic under their areas: %r" % got[1:])
        got = rows(exe, game, 1)
        check(got[1:] == ["#|Overworld|", "i|Kokiri Forest  (here)|1 left, 1 in logic", "#|Dungeons|", "o|Forest Temple|1 left",
                          "#|Finished areas|", " |Market|all collected", ""], "the areas' groups, counts and finished ones are not the menu's: %r" % got[1:])
        got = rows(exe, game, 1, "Kokiri Forest")
        check(got[1:] == [" |<  Back to the areas|"] + forest + [""],
              "an area's checks are not listed the ones to get first, with what a collected one gave: %r" % got[1:])
        got = rows(exe, game, 1, "Forest Temple")
        check(got[2:] == ["#|Forest Temple|1 of 1 left, 0 in logic", "o|Chest C (adult)||needs Hookshot; after the Forest Temple", ""],
              "a check not in logic does not say what it lacks: %r" % got[2:])
        check(rows(exe, game, 2)[1:] == doors + [""], "a door or a boss room is told before it is found, or not once it is")
        check(rows(exe, game, 3)[1:] == items + [""], "the dungeons' keys and items are not the live file's")
        check(rows(exe, game, 4)[1:] == hints + [""], "the hints heard are not listed, or one not heard is")
        # (wide, on a second screen: the areas, the checks of the one chosen or all in logic now, and the rest, at once)
        left = ["i|In logic now|1 check", " |Dungeon items|2 keys, 4 items", " |Doors and bosses|2 of 3 found", " |Hints heard|1 of 2", "#|Overworld|",
                "i|Kokiri Forest|1 left, 1 now", "#|Dungeons|", "o|Forest Temple|1 left", "#|Finished areas|", " |Market|all collected", "--"]
        check(rows(exe, game, -1)[1:] == left + now + [""], "wide, the left pane is not what to look at, or the middle not what is in logic now: %r" % rows(exe, game, -1)[1:])
        check(rows(exe, game, -1, "Kokiri Forest")[1:] == left + forest + [""], "wide, an area chosen does not show its checks in the middle")
        # (the owner, 2026-11-27: the dungeons' items, the doors and bosses and the hints "there own selectable pane")
        check(rows(exe, game, -1, "*dungeons")[1:] == left + items + [""] and rows(exe, game, -1, "*doors")[1:] == left + doors + [""]
              and rows(exe, game, -1, "*hints")[1:] == left + hints + [""], "wide, the other views are not shown in the middle when chosen on the left")
        # (and the right pane the map: the area of what is open or clicked, else the one Link is in, its pictures as the menu
        #  picks them: an outdoor map's of the check's age, a dungeon's shape and the floor)
        (game / "maps").mkdir()
        (game / "maps" / "index.txt").write_text("# map pictures 1\nKokiriForest|A||Kokiri_Adult|0|0|100|2000|1440\nKokiriForest|C||Kokiri_Child|0|0|100|2000|1440\n"
                                                 "ForestTemple|CA|All|Forest_All|0|0|100|2000|1440\nForestTemple|CA|1F|Forest_1F|0|0|100|2000|1440\n", encoding="utf-8")
        say = lambda *a: subprocess.run([str(exe), "--tracker-map", str(game)] + list(a), capture_output=True, timeout=60).stdout.decode("utf-8").strip()
        # (the owner, 2026-11-27: no overview of Hyrule; with nothing open or clicked, the map of the area Link is in)
        check(say("", "-1") == "Kokiri Forest|Kokiri_Child||", "with nothing open the map is not the area's Link is in: %r" % say("", "-1"))
        check(say("*doors", "-1") == "Kokiri Forest|Kokiri_Child||", "with another view open the map is not the area's Link is in")
        check(say("Kokiri Forest", "-1") == "Kokiri Forest|Kokiri_Child||" and say("Kokiri Forest", "1") == "Kokiri Forest|Kokiri_Child|Chest B|",
              "an area's map is not its picture of the age, or the check clicked is not the one ringed: %r" % say("Kokiri Forest", "1"))
        check(say("", "2") == "Forest Temple|Forest_All|Chest C|", "a check clicked in In logic now does not take the map to its area: %r" % say("", "2"))
        check((game / "maps" / "view" / "wanted.txt").is_file(), "the window does not ask the game for the map's pictures")
        # (another seed's live file, and one of other checks: not taken)
        (rando / "tracker_live.txt").write_text(live.replace("seed 7", "seed 8"), encoding="utf-8")
        check(rows(exe, game, 0)[1:] == nothing, "another seed's live file is shown")
        (rando / "tracker_live.txt").write_text(live.replace("states cioj", "states cio"), encoding="utf-8")
        check(rows(exe, game, 0)[1:] == nothing, "a live file of fewer checks is shown")
        check(not (rando / "tracker_window.txt").exists(), "a window never shown wrote its place")
        # (a picture the game handed over: made a .png, the .raw taken away)
        raw = game / "maps" / "view" / "Kokiri_Child.raw"
        raw.write_bytes(b"HWRV" + (2).to_bytes(4, "little") + (1).to_bytes(4, "little") + bytes([255, 0, 0, 255, 0, 0, 255, 128]))
        subprocess.run([str(exe), "--tracker-map", str(game), "Kokiri Forest", "-1", "convert"], capture_output=True, timeout=60)
        png = raw.with_suffix(".png")
        check(png.is_file() and not raw.exists() and png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" and int.from_bytes(png.read_bytes()[16:20], "big") == 2,
              "a picture handed over by the game is not made a .png")
    print("PASS: the Tracker's window, and the file the game writes for it")


if __name__ == "__main__":
    main()
