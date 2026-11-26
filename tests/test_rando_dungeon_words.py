"""A dungeon item found away from its dungeon says whose (bug 141, tools/rando/rando_seed.py DUNGEON_WORDS, fixes 104;
host/hos_main.c hos_oot_get_name): no game data.

The owner's run 2026-11-25: a small key from a Kokiri Forest chest said "You found a small key!", and with keys Anywhere
nothing said it was the Water Temple's. Checked:
- dungeon_words adds each dungeon's small key, boss key, map and compass words ("<item>_<dungeon>_GetMessage", _GetCaption,
  _Name), made from the item's own: English names the dungeon, another language keeps the game's words, a line the text
  has is kept, and a second pass adds nothing;
- every seed adds them with the first bags' words and leaves DUNGEON_WORDS_FILE for the game's side (fixes 104);
- the game's side reads that file and, for a dungeon item of a chest away from its dungeon, points the get window at
  "<item>_<dungeon>" (the same owner lookup the add uses).

    python -I -B tests/test_rando_dungeon_words.py
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
spec = importlib.util.spec_from_file_location("rando_seed", ROOT / "tools" / "rando" / "rando_seed.py")
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)
from test_rando_first_bag import msbt, line   # noqa: E402  (a little MSBT, a line of it)
from srccut import block   # noqa: E402


def check(ok, why):
    if not ok:
        print("FAIL: %s" % why)
        sys.exit(1)


def main():
    S = seed
    lines = {}
    for item, said in (("SmallKey", b"a small key"), ("BossKey", b"the boss key"), ("Map", b"the dungeon map"), ("Compass", b"the compass")):
        lines["Item_Dungeon_%s_GetMessage" % item] = b"You found " + said + b"!"
        lines["Item_Dungeon_%s_GetCaption" % item] = b"Caption of " + said
        lines["Item_Dungeon_%s_Name" % item] = said
    lines["Item_Dungeon_SmallKey_FireTemple_GetMessage"] = b"Kept as it is"
    data = msbt(lines)
    en, n = S.dungeon_words(data, True)
    check(n == 4 * len(S.DUNGEON_FOLDERS) * 3 - 1, "not every dungeon's items got their three lines (%d)" % n)
    check(line(en, "Item_Dungeon_SmallKey_WaterTemple_GetMessage") == b"You found a small key for the Water Temple!",
          "the Water Temple's small key does not name it: %r" % line(en, "Item_Dungeon_SmallKey_WaterTemple_GetMessage"))
    check(line(en, "Item_Dungeon_BossKey_InsideGanonCastle_GetMessage") == b"You found the boss key of Ganon's Castle!",
          "Ganon's Castle's boss key does not name it")
    check(line(en, "Item_Dungeon_Map_IceCavern_GetCaption") == b"Caption of the dungeon map", "a map's caption is not the game's")
    check(line(en, "Item_Dungeon_Compass_ForestTemple_Name") == b"the compass", "an item's name is not the game's")
    check(line(en, "Item_Dungeon_SmallKey_FireTemple_GetMessage") == b"Kept as it is", "a line the text had was replaced")
    check(line(en, "Item_Dungeon_SmallKey_GetMessage") == b"You found a small key!", "the game's own line changed")
    check(S.dungeon_words(en, True)[1] == 0, "a second pass adds lines again")
    other, _ = S.dungeon_words(data, False)
    check(line(other, "Item_Dungeon_SmallKey_WaterTemple_GetMessage") == b"You found a small key!",
          "another language does not keep the game's words")
    check(set(S.DUNGEON_SAY) == set(S.DUNGEON_FOLDERS), "a dungeon has no words for its name")
    check(S.FIXES_VERSION >= 104, "fixes 104 is not the dungeon words'")
    script = (ROOT / "tools" / "rando" / "rando_seed.py").read_text(encoding="utf-8")
    check("text, more = dungeon_words(text, n.startswith(FIRST_BAG_ENGLISH))" in script and "written.append(DUNGEON_WORDS_FILE)" in script,
          "a seed does not add the words or leave DUNGEON_WORDS_FILE")
    host = (ROOT / "host" / "hos_main.c").read_text(encoding="utf-8")
    check('"mods/rando-seed/dungeon_words.txt"' in host and "oot_dungeon_words = f != NULL;" in host,
          "the game's side does not read whether the seed has the words")
    window = block(host, "void hos_oot_get_name(Ctx *c, uint64_t node, int kind) {")
    check("if (oot_dungeon_words && (!strcmp(name, \"Item_Dungeon_SmallKey\")" in window and
          "oot_dungeon_owner(name, owner, sizeof owner, NULL)" in window and 'snprintf(word, sizeof word, "%s_%s", name, owner);' in window,
          "the get window is not pointed at the dungeon's words")
    check("if (!oot_dungeon_owner(name, owner, sizeof owner, &nearest)) return 0;" in block(host, "static int oot_dungeon_item(Ctx *c, const char *name) {"),
          "the add and the window do not share the owner lookup")
    print("PASS: a dungeon item away from its dungeon says whose")


if __name__ == "__main__":
    main()
