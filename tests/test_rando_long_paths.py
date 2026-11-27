"""A seed whose files the game could not list from a deep game folder is not written (tools/rando/rando_seed.py too_long;
the idea: OOTRR 1507454; share/port-survey/ootrr-2026-11-26b.md, 2026-11-27). No game data.

On Windows the game's side lists a mod's files with names of at most 259 characters (host/mods.c index_romfs: char
host[MAX_PATH] and FindFirstFileA) and leaves a longer one out without a word, so the game reads its own file in that
one's place: a seed applied in part. The seed tool counts first and stops with plain words. Checked:
- a short game folder passes every file; a file of 259 passes and one of 260 does not; a folder of 247 passes and one of
  248 does not; the count is the longer of UTF-16 units and UTF-8 bytes; nothing is refused where the limit is not
  Windows';
- the longest comes first with how far it is over, and the words name the file, the folder, its length and the most it
  may be: a folder that much shorter passes;
- the main part asks before the last seed's files are taken away, for the files below romfs and the shelves' tiers;
- the limits are the game's side's: host/mods.c still lists with MAX_PATH names (when it reads long paths, this goes).

    python -I -B tests/test_rando_long_paths.py
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


LONGEST = "romfs/Phive/StaticCompoundBody/HyruleField/HyruleField_Adult_X7_Z10.Nin_Ounce_NVN2.bphsc.zs"
SHORT = "romfs/Pack/Actor/Item_HeldOcarina_Fairy.pack.zs"


def mod_of(length):
    """a mod's folder whose path is `length` characters"""
    tail = "\\mods\\rando-seed"
    return "C:\\" + "g" * (length - 3 - len(tail)) + tail


def full(mod, rel):
    return mod + "\\" + rel.replace("/", "\\")


# a short folder: nothing refused
mod = "F:\\Games\\OOT Remake Rando\\mods\\rando-seed"
check(S.too_long(mod, [LONGEST, SHORT], windows=True) == [], "a short game folder is refused")

# a file of 259 passes, of 260 does not
at = mod_of(259 - 1 - len(SHORT))
check(len(full(at, SHORT)) == 259 and S.too_long(at, [SHORT], windows=True) == [], "a file of 259 characters is refused")
at = mod_of(260 - 1 - len(SHORT))
check(len(full(at, SHORT)) == 260 and S.too_long(at, [SHORT], windows=True) == [(1, SHORT)], "a file of 260 characters is passed")
check(S.too_long(at, [SHORT], windows=False) == [], "refused where the limit is not Windows'")
check(S.too_long(at + "\\", [SHORT], windows=True) == [(1, SHORT)], "a folder given with its last \\ counts differently")

# a folder of 247 passes, of 248 does not (the file's own name is short)
rel = "romfs/Deep/a"
at = mod_of(247 - len("\\romfs\\Deep"))
check(len(full(at, rel).rsplit("\\", 1)[0]) == 247 and S.too_long(at, [rel], windows=True) == [], "a folder of 247 characters is refused")
at = mod_of(248 - len("\\romfs\\Deep"))
check(S.too_long(at, [rel], windows=True) == [(1, rel)], "a folder of 248 characters is passed")

# the longer of the two counts: a name of letters that are 3 bytes each in UTF-8
kana = "C:\\" + "\u30bc" * 60 + "\\mods\\rando-seed"
check(len(full(kana, LONGEST)) < 260 and S.too_long(kana, [LONGEST], windows=True), "a folder long in bytes only is passed")
check(S.path_length("\U0001F600") == 4 and S.path_length("ab") == 2, "path_length")

# the longest first, and the words
at = mod_of(230)
long = S.too_long(at, [SHORT, LONGEST, "romfs/a.zs"], windows=True)
check([rel for _, rel in long] == [LONGEST, SHORT] and long[0][0] == len(full(at, LONGEST)) - 259, "the order or the excess: %r" % (long,))
words = S.too_long_words(at, long)
game = at[:-len("\\mods\\rando-seed")]
most = len(game) - long[0][0]
check(LONGEST in words and game in words and "%d characters" % len(game) in words and "%d at most" % most in words
      and "2 of the seed's files" in words and "Nothing written" in words, "the words: %s" % words)
check(S.too_long(mod_of(most + len("\\mods\\rando-seed")), [SHORT, LONGEST], windows=True) == [], "the folder the words allow is still too long")
check(S.too_long(mod_of(most + 1 + len("\\mods\\rando-seed")), [SHORT, LONGEST], windows=True) != [], "the words allow less than fits")

# the main part: asked before the last seed's files go, for every file written
src = (ROOT / "tools" / "rando" / "rando_seed.py").read_text(encoding="utf-8")
main = src[src.index("\ndef main():"):]
ask, gone = main.index("long = too_long("), main.index("removed = remove_old(mod)")
check(ask < gone and "sys.exit(too_long_words(" in main[ask:gone], "the main part does not stop before remove_old")
call = main[ask:gone]
writes = main[gone:main.index("written.append(SHELF_TIER_DIR")]
for name in ("changed", "new_tables", "flag_files", "pack_files", "gift_files", "shop_files", "scene_files", "tier_files"):
    check(name in writes and name in call, "%s is written and not counted (or no longer written)" % name)

# the limit is the game's side's
mods = (ROOT / "host" / "mods.c").read_text(encoding="utf-8")
walk = mods[mods.index("static int index_romfs("):mods.index("typedef struct { char path[MAX_PATH]")]
check("char host[MAX_PATH], key[MAX_PATH];" in walk and "FindFirstFileA(pat, &fd)" in walk,
      "host/mods.c index_romfs no longer lists with MAX_PATH names: the seed tool's limit (too_long) is to go with it")
check(S.PATH_MOST == 259 and S.FOLDER_MOST == 247, "the limits")
print("ok: a seed too deep for Windows is not written")
