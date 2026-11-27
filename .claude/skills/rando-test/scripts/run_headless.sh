#!/bin/bash
# run_headless.sh <label> <step>...: the game without a window, on a copy of a save, then each step in turn.
#
# A step is "<seconds to wait first>:<what>" (the seconds may be a fraction). What is one of:
#   GO x y z Folder ages    the Tracker tab's Go there (ages: C, A or CA; the map must be the age Link is now)
#   0:A  0:B  0:Y  0:R/2000  0:LUP/1500  ...   a live input line (button or stick, /ms held: host/control.c)
#   !cheat 999              a debug cheat line (999: switch Link's age; 1003: the Market's fountain)
#   MENU <key or word>      the Insert menu, as RX_VK_MENU_LIVE takes it (gpu/vk/vk_menu.cpp menu_tick): a key (INS, UP, DOWN,
#                           LEFT, RIGHT, ENTER, ESC, TABL, TABR, PADS...) or a word that goes somewhere by name: OPEN, CLOSE,
#                           TAB:Tracker, ROW:Hyrule Castle, CHECK:Pot #3 (or CHECK:2; CHECK:0 the row's own words)
#   SHOT <name> [part]      the next picture kept as $WORK/named/<label>_<name>.png; part (needs ffmpeg) cuts it out and
#                           makes it three times the size: map (the Tracker's map), panel (its whole right side), rows (its
#                           list), minimap (the game's, bottom right), or w:h:x:y of the 960 x 540 picture
# The steps start once the save is loaded (the log's "rando: bottles: Link has", then a few seconds; after 100 s without
# it), and the game is stopped when they are done.
#
# Environment:
#   GAME   the game folder (default /f/Games/OOT Remake Rando)
#   SAVE   a save copy's name under <GAME>/user/save_copies/save_rando (default: the live saves, the newest loaded)
#   WORK   where the run's files go (default: $TEMP/rando-test); pictures in $WORK/shots, the kept ones in $WORK/named
#   EVERY  a picture every this many frames (default 60)
#   SETFLAG  flags set at the start (HOS_OOT_SETFLAG: hash=value,...)
#
# Prints the log's lines about items given, Go there, crashes and the exit code (124: ran to the end; 139: a crash).
# The player's saves are never written: the run uses its own user folder. What a run's game writes into the game folder is
# kept before and put back after: the game's own log files (it keeps five, and a run would push the player's out), the
# Tracker's record and junk marks, and Go there's place. Nothing runs while the game or the launcher is open.
set -u
label="$1"; shift
GAME="${GAME:-/f/Games/OOT Remake Rando}"
WORK="${WORK:-${TEMP:-/tmp}/rando-test}"
WORK="$(cygpath -u "$WORK" 2>/dev/null || echo "$WORK")"
if tasklist 2>/dev/null | grep -qi "hookshot.exe\|Mako Launcher\|Willow Woods Launcher"; then echo "the game or the launcher is running: not started"; exit 1; fi
mkdir -p "$WORK/shots" "$WORK/user" "$WORK/named"
rm -rf "$WORK/user/save_rando"
if [ -n "${SAVE:-}" ]; then
  src="$GAME/user/save_copies/save_rando/$SAVE"
  [ -d "$src" ] || { echo "no save copy named \"$SAVE\""; ls "$GAME/user/save_copies/save_rando/"; exit 1; }
  cp -r "$src" "$WORK/user/save_rando"
else
  cp -r "$GAME/user/save_rando" "$WORK/user/save_rando"
fi
total=0; for s in "$@"; do total=$(awk "BEGIN{print $total + ${s%%:*}}"); done
secs=$(awk "BEGIN{print int(100 + $total + 30)}")
rm -f "$WORK"/shots/*.png "$WORK"/named/"${label}"_*.png; : > "$WORK/live.txt"; : > "$WORK/menu.txt"; : > "$WORK/stdout.txt"   # (the log emptied here: the last run's said "loaded" before this one's game had started, 2026-11-26)
# (kept here and put back after the run, so the player's are as they were: the Tracker's record of what is collected and
#  the junk marks (rando/collected.txt, junk.txt: the game folder's, not the save's; 2026-11-19: test runs on a test seed
#  left the owner's record another seed's), Go there's place, and the game's log files (2026-11-26: kept by hand before
#  every run until then))
# (2026-11-27: and the run's stats, which a test run's seconds were added to, and the pop-out Tracker's file, which a test
#  run's save would fill in)
kept="collected.txt junk.txt goto_check.txt run_stats.txt tracker_live.txt"
rm -rf "$WORK/keep"; mkdir -p "$WORK/keep/logs"
for f in $kept; do [ -f "$GAME/rando/$f" ] && cp -p "$GAME/rando/$f" "$WORK/keep/$f"; done
for f in "$GAME"/logs/hookshot_log*.txt "$GAME"/logs/hookshot_frames.csv; do [ -f "$f" ] && cp -p "$f" "$WORK/keep/logs/"; done
put_back() {
  for f in $kept; do if [ -f "$WORK/keep/$f" ]; then cp -p "$WORK/keep/$f" "$GAME/rando/$f"; else rm -f "$GAME/rando/$f"; fi; done
  rm -f "$GAME"/logs/hookshot_log*.txt "$GAME"/logs/hookshot_frames.csv
  for f in "$WORK"/keep/logs/*; do [ -f "$f" ] && cp -p "$f" "$GAME/logs/"; done
}
# the next picture, kept under a name (and a part of it cut out, three times the size)
shot() {
  local name="$1" part="${2:-}" last new crop="" out="$WORK/named/${label}_$1.png"
  last="$(ls "$WORK/shots" | tail -1)"
  for _ in $(seq 1 40); do sleep 0.25; new="$(ls "$WORK/shots" | tail -1)"; [ "$new" != "$last" ] && break; done
  sleep 0.3   # (written whole)
  [ -n "$new" ] || { echo "SHOT $name: no picture"; return; }
  case "$part" in
    map) crop=380:260:575:280;; panel) crop=380:470:575:40;; rows) crop=545:470:20:40;; minimap) crop=260:240:700:300;;
    "") ;; *) crop="$part";;
  esac
  if [ -n "$crop" ] && command -v ffmpeg > /dev/null; then
    ffmpeg -y -loglevel error -i "$WORK/shots/$new" -vf "crop=$crop,scale=iw*3:ih*3:flags=lanczos" "$out" || cp "$WORK/shots/$new" "$out"
  else cp "$WORK/shots/$new" "$out"; fi
}
(cd "$GAME" && HOS_OOT_SETFLAG="${SETFLAG:-}" HOS_HEADLESS=1 HOS_AUDIO=0 HOOKSHOT_NO_UPDATE_CHECK=1 HOS_NO_SAVE_FOLDER=1 RX_VK_FRAMEGEN=0 \
  RX_VK_SHOTS="$(cygpath -w "$WORK/shots")" RX_VK_SHOT_EVERY=${EVERY:-60} RX_VK_SHOT_W=960 RX_VK_SHOT_H=540 RX_VK_SHOT_MENU="${RX_VK_SHOT_MENU:-1}" \
  RX_VK_MENU_LIVE="$(cygpath -w "$WORK/menu.txt")" \
  HOS_INPUT_LIVE="$(cygpath -w "$WORK/live.txt")" HOS_INPUT_SCRIPT_BACKGROUND=1 HOS_INPUT_SCRIPT="30:A,44:A,46:A,49:A,60:A" \
  exec timeout "$secs" ./hookshot.exe --user "$(cygpath -w "$WORK/user")" > "$WORK/stdout.txt" 2>&1) &
pid=$!
loaded=0
for _ in $(seq 1 200); do   # (100 s at most)
  grep -q "rando: bottles: Link has" "$WORK/stdout.txt" 2>/dev/null && { loaded=1; break; }
  kill -0 $pid 2>/dev/null || break
  sleep 0.5
done
[ $loaded = 1 ] && sleep 6   # (the area around Link loaded)
for s in "$@"; do
  kill -0 $pid 2>/dev/null || break
  sleep "${s%%:*}"; what="${s#*:}"
  case "$what" in
    GO\ *) echo "${what#GO }" > "$GAME/rando/goto_check.txt"; echo "!cheat 5" >> "$WORK/live.txt";;
    MENU\ *) echo "${what#MENU }" >> "$WORK/menu.txt";;
    SHOT\ *) shot ${what#SHOT };;
    *) echo "$what" >> "$WORK/live.txt";;
  esac
done
ended=0
if kill -0 $pid 2>/dev/null; then sleep 1; kill $pid 2>/dev/null && ended=1; fi
wait $pid; code=$?
# (stopped here at the steps' end: "ran to the end", as the timeout's 124)
[ $ended = 1 ] && { [ $code = 143 ] || [ $code = 124 ] || [ $code = 0 ]; } && code=124
echo "exit $code" >> "$WORK/stdout.txt"
for _ in $(seq 1 20); do tasklist 2>/dev/null | grep -qi "hookshot.exe" || break; sleep 0.5; done   # (gone before its files are put back)
put_back
cp "$WORK/stdout.txt" "$WORK/stdout_$label.txt"
echo "run $label: $(ls "$WORK/shots" | wc -l) pictures in $WORK/shots, the log in $WORK/stdout_$label.txt$([ $loaded = 1 ] || echo " (the save's loading was not seen: the steps began after 100 s)")"
ls "$WORK/named" 2>/dev/null | grep "^${label}_" | sed "s|^|kept: $WORK/named/|"
grep -n "pouch add\|go to a check\|tracker: .* got\|CRASH: exception\|CRASH: guest\|exit " "$WORK/stdout.txt" | sed 's/\[hos [A-Za-z0-9:]*\] //' | cut -c1-200 | tail -30
