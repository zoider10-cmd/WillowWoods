"""The menu script's words and its live file, and the randomizer's test run that uses them (2026-11-26). No game data.

A test run that had to count Down presses to reach a Tracker row landed on the wrong row three times in a day, timed its
menu keys from the game's start, and had its game push the player's log files out. Checked:
- the menu's script takes words that go somewhere by name (OPEN, CLOSE, TAB:, ROW:, CHECK:), from RX_VK_MENU_SCRIPT and,
  a line at a time, from the file RX_VK_MENU_LIVE names; a row chosen by name is left to scroll_rows to bring into view;
- RX_VK_MENU_LIVE has its row in the switch table and the guide, and a settings file cannot set it (it presses menu keys);
- the test run (.claude/skills/rando-test/scripts/run_headless.sh) sends MENU steps to that file, keeps a SHOT's picture
  under a name, starts its steps on a log emptied before the game starts, and puts the game folder's files back.

    python -I -B tests/test_menu_script_words.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from srccut import block   # noqa: E402


def check(ok, why):
    if not ok:
        print("FAIL: %s" % why)
        sys.exit(1)


def main():
    menu = (ROOT / "gpu" / "vk" / "vk_menu.cpp").read_text(encoding="utf-8")
    tick = block(menu, "void menu_tick() {")
    for word in ('!strcmp(key, "OPEN") || !strcmp(key, "CLOSE")', '!strcmp(key, "TAB") && !what.empty()', '!strcmp(key, "ROW")', '!strcmp(key, "CHECK")', '!strcmp(key, "TYPE")'):
        check(word in tick, "the menu's script has no %s" % word)
    check("if (open_now.load() != (key[0] == 'O')) press[0] = true;" in tick, "OPEN and CLOSE turn the menu over whatever it is")
    check("if (same(tab_titles[tab], what.c_str())) cur_tab = tab, menu_refresh = true;" in tick, "TAB: does not go to the tab of that title")
    check("if (same(rows[tab_row_to_global(cur_tab, k)].name, what.c_str())) tab_selected[cur_tab] = k, menu_refresh = true;" in tick,
          "ROW: does not choose the row of that name, or keeps scroll_rows from bringing it into view (scrolled_to)")
    check("if (pick >= 0 && pick <= checks) tracker_pick[row] = pick, menu_refresh = true;" in tick and
          "c && same(c->kind, what.c_str())) pick = k;" in tick and "if (row < kTrackerFirstArea) return;" in tick, "CHECK: does not step the Tracker's row to that check")
    check('static const char* live = getenv("RX_VK_MENU_LIVE");' in tick and r"fgets(line, sizeof line, f) && strchr(line, '\n')" in tick and
          "live_at = ftell(f);" in tick, "the live file is not read a whole line at a time, from where it was left")
    check("script_run(key, what);" in tick and "script_run(line, colon ? std::string(colon + 1) : std::string());" in tick,
          "the script and the live file do not take the same keys and words")
    table = (ROOT / "gpu" / "vk" / "switches.def").read_text(encoding="utf-8")
    guide = (ROOT / "docs" / "development.md").read_text(encoding="utf-8")
    host = (ROOT / "host" / "hos_main.c").read_text(encoding="utf-8")
    check("SW(RX_VK_MENU_LIVE, diag, string," in table and "`RX_VK_MENU_LIVE=<file>`" in guide and "`ROW:<a row's name>`" in guide,
          "RX_VK_MENU_LIVE has no row in the switch table or the guide")
    check('"RX_VK_MENU_SCRIPT", "RX_VK_MENU_LIVE"};' in host, "a settings file can name a file of menu keys")
    run = (ROOT / ".claude" / "skills" / "rando-test" / "scripts" / "run_headless.sh").read_text(encoding="utf-8")
    check(r'MENU\ *) echo "${what#MENU }" >> "$WORK/menu.txt";;' in run and 'RX_VK_MENU_LIVE="$(cygpath -w "$WORK/menu.txt")"' in run, "a MENU step does not reach the menu")
    check(r"SHOT\ *) shot ${what#SHOT };;" in run and 'out="$WORK/named/${label}_$1.png"' in run, "a SHOT step keeps no picture under its name")
    check(run.index(': > "$WORK/stdout.txt"') < run.index("exec timeout") < run.index('grep -q "rando: bottles: Link has" "$WORK/stdout.txt"'),
          "the steps can start on the last run's log")
    check('for f in "$GAME"/logs/hookshot_log*.txt "$GAME"/logs/hookshot_frames.csv; do [ -f "$f" ] && cp -p "$f" "$WORK/keep/logs/"; done' in run and
          'kept="collected.txt junk.txt goto_check.txt"' in run and run.count("put_back") == 2 and run.index("wait $pid") < run.rindex("put_back"),
          "the game folder's files are not kept before the run and put back after the game is gone")
    check("the game or the launcher is running: not started" in run, "the run starts under the player's own game")
    bash = shutil.which("bash")
    if bash:
        ran = subprocess.run([bash, "-n", str(ROOT / ".claude" / "skills" / "rando-test" / "scripts" / "run_headless.sh")], capture_output=True, text=True)
        check(ran.returncode == 0, "run_headless.sh does not parse:\n" + ran.stderr)
    print("PASS: the menu script's words and the test run")


if __name__ == "__main__":
    main()
