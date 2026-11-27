"""No logic (rando_no_logic, asked 2026-11-27): "Logic will behave as the game does now, No logic will completely randomize
everything, a no logic run can be unbeatable." No game data.

The seed tool had the choice as a command line's switch (--no-logic: the placement is made without the rules). The setting
is that switch from the options, and with it the two shuffles of places drop what they keep for the rules' sake. Checked:
- the options' line is the switch: read before the logic is decided, and on the stamp (a seed with it is another seed);
- the placement is given no rules without the logic (place's needs None), and with them otherwise;
- Dungeon entrances: every child's dungeon is in its pool whatever the other settings, mixing needs no Either age's items,
  any dungeon goes behind any door (entrance_mixed free: over many seeds the Deku Tree behind an adult's door, the
  Training Ground behind a child's, pairs entrance_fits refuses) and the Shadow Temple's door holds any;
- Boss shuffle: the child's two change rooms whatever the other settings, and the Shadow Temple's boss's room holds any;
- the setting off: none of that (the pool and the fits as tests/test_rando_entrance_setting.py has them);
- the setting is in the launcher's and the menu's tables, last, its first choice Off (the logic: the way before).

    python -I -B tests/test_rando_no_logic.py
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("rando_seed", ROOT / "tools" / "rando" / "rando_seed.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)


def check(ok, why):
    if not ok:
        print("FAIL: %s" % why)
        sys.exit(1)


src = (ROOT / "tools" / "rando" / "rando_seed.py").read_text(encoding="utf-8")
main = src[src.index("\ndef main():"):]
read, decided = main.index('a.no_logic = a.no_logic or ini["rando_no_logic"] == 1'), main.index("logic_now = (a.event_chests or bool(a.songs)) and not a.no_logic")
check(read < decided and '"rando_no_logic": 0' in src, "the options' line is not read before the logic is decided")
check('logic %d%s%s\\n" % (seed, which, keys_mode, a.event_chests, logic_now, " none" if a.no_logic else "",' in main, "the setting is not on the stamp")
check("logic = logic_now" in main and "needs if logic else None," in main, "the placement is given the rules without the logic")

ALL = S.ENTRANCE_ADULT + S.ENTRANCE_CHILD
free = [S.entrance_mixed(s, ALL, False, False, True) for s in range(400)]
check(all(set(b) == set(b.values()) == set(ALL) for b in free), "No logic: not a one-to-one change of the doors")
seen = {(a, b) for f in free for a, b in f.items()}
check(len(seen) == len(ALL) ** 2, "No logic: over 400 seeds %d of %d door and dungeon pairs came up" % (len(seen), len(ALL) ** 2))
refused = {(a, b) for a in ALL for b in ALL if not S.entrance_fits(a, b, True)}
check(refused and refused <= seen and ("ForestTemple", "InsideTheDekuTree") in refused and ("InsideTheDekuTree", "GerudoTrainingGround") in refused,
      "No logic: a pair the fits refuse never comes, or the fits refuse none")
check(any(f["ShadowTemple"] in S.ENTRANCE_NOCTURNE_WAITS for f in free), "No logic: the Shadow Temple's door never holds a waited temple")
kept = [S.entrance_mixed(s, ALL, True, False) for s in range(120)]
check(not {(a, b) for f in kept for a, b in f.items()} & refused, "with the logic a pair the fits refuse comes up")
for line in ("mixed = a.entrance_mix and (bool((a.ageless or 0) & 2) or a.no_logic)",
             "child_pool = lambda items: ENTRANCE_CHILD if a.no_logic else entrance_child_pool(bool(door_rules), bool(a.open_forest), items)",
             "nocturne_free = NOCTURNE in PROGRESSION or a.no_logic",
             "behind = entrance_mixed(seed, doors, bool((a.ageless or 0) & 4), nocturne_free, a.no_logic)",
             'behind.update(entrance_shuffle(seed, group, nocturne_free, "" if group is ENTRANCE_ADULT else "-child"))',
             "fights = boss_shuffle(seed, (bool(door_rules) and bool(a.open_forest)) or a.no_logic, nocturne_free, behind) if a.boss_shuffle else {}"):
    check(line in main, "the main part lacks: %s" % line)
check(any(S.boss_shuffle(s, True, True)["ShadowTemple"] in S.ENTRANCE_NOCTURNE_WAITS for s in range(40))
      and any(S.boss_shuffle(s, True, True)["InsideTheDekuTree"] == "DodongoCavern" for s in range(40)), "the bosses' change with nothing kept")

header = (ROOT / "gpu" / "vk" / "oot_rando.h").read_text(encoding="utf-8")
launcher = (ROOT / "launcher" / "Launcher.cs").read_text(encoding="utf-8")
check('X(NO_LOGIC, "No logic", "rando_no_logic",' in header and header.index("X(NO_LOGIC,") > header.index("X(BOSS_SHUFFLE,")
      and '"Off", "On")\n\nenum {' in header[header.index("X(NO_LOGIC,"):], "the menu's table: not there, or not last")
check('new object[] { "rando_no_logic", "No logic", new[] { "Off", "On" }, new[] { 0, 1 },' in launcher
      and launcher.index('new object[] { "rando_no_logic"') > launcher.index('new object[] { "rando_boss_shuffle"')
      and '"rando_boss_shuffle", "rando_no_logic" } },' in launcher, "the launcher's table or section")
check(header.count("\n    X(") <= 66, "a seed ID has no room for the settings")
print("ok: No logic")
