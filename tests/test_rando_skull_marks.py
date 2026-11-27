"""A Gold Skulltula's drop is its check's by the save's own marks, never by a guess that is written into the save
(host/hos_main.c oot_skull_item, oot_skull_waited; asked 2026-11-26, "every dropped item carries its own check"). No game.

The drop was matched to "the nearest check not yet collected that gives the item, within 60 m", and the check guessed had
its mark written into the save: of two Skulltulas near each other giving the same item the wrong one could be ticked, and
a Skulltula never killed marked collected. The save keeps a mark by each Skulltula's own hash. When the game sets it was
not known when this was written, so the two functions are compiled and run through each way it may be:
- the mark is set before the add: that Skulltula is ticked, the nearer one is not, and no mark is written;
- the mark was set at its death and the record ticked it then: the add claims it, once, and ticks no other;
- the mark comes after the add: the add waits, and the one the save marks is the drop's, the nearest left alone;
- the save marks none in the wait: only then the nearest is taken and its mark written, as before;
- a second add while one is waited for settles the first, each its own; an item no Skulltula here gives is not theirs.
A chest that gives an item the same way, by the game's own opened flag (oot_chest_item; a chest of rupees gives no add and
was ticked by that flag already): open at the add, it is ticked; ticked by its flag a while ago, the add claims it; else the
chests here that give the item are handed back to be waited for, and the wait settles as a Skulltula's.

    python -I -B tests/test_rando_skull_marks.py [--cc gcc]
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from srccut import block   # noqa: E402

RUN_ALL_ARGS = ["--cc", "{cc}"]
FIXTURE = r"""
#include <math.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef struct Ctx { int unused; } Ctx;
#define OOT_TRACKER_MAX 16
#define OOT_CHECK_NEAR 60.0f
static struct {
    char item[64], folder[40];
    float place[3];
    signed char done, sold, skull, claimed;
    char ages[4];
    uint64_t key;
    uint32_t opened;
    int64_t marked_at;
} oot_checks[OOT_TRACKER_MAX];
static int oot_check_count;
static char oot_link_map[80] = "KakarikoVillage_Child";
static float oot_link_place[3];
static int oot_link_child = 1;
static int64_t clock_ns = 1000000000000LL;
static int64_t hos_now_ns(void) { return clock_ns; }
static char said[1024];
static void hos_log(const char *fmt, ...) { va_list a; va_start(a, fmt); vsnprintf(said, sizeof said, fmt, a); va_end(a); }
static int saves;
static void oot_tracker_save(void) { saves++; }
static int oot_banc_in_folder(const char *banc, const char *folder) { const size_t n = strlen(folder); return !strncmp(banc, folder, n) && (!banc[n] || banc[n] == '_'); }
static int family_of(const char *name) { return !strncmp(name, "Bag", 3) ? 1 : -1; }
static int oot_family_of(const char *name, int *spelling) { (void)spelling; return family_of(name); }
static int marks[OOT_TRACKER_MAX];   /* (the save's truth value by each check's key: its index + 1) */
static int oot_gamedata_keyed_bool(Ctx *c, uint64_t key, int *out) { (void)c; if (!key || key > OOT_TRACKER_MAX) return 0; *out = marks[key - 1]; return 1; }
static int opens[OOT_TRACKER_MAX];   /* (the game's opened flag of each chest: its index + 1) */
static int oot_gamedata_bool(Ctx *c, uint32_t hash, int *value) { (void)c; if (!hash || hash > OOT_TRACKER_MAX) return 0; *value = opens[hash - 1]; return 1; }
static int oot_dungeon_check = -1;
static int64_t oot_dungeon_check_at;
// DEFINES
// WAITED
// ITEM
// CHEST
static int failed;
static void check(int ok, const char *what) { if (!ok) printf("FAIL: %s (the log: %s)\n", what, said), failed = 1; }
static int add(const char *item, float x, float z, const char *folder, const char *ages, int skull) {
    const int i = oot_check_count++;
    memset(&oot_checks[i], 0, sizeof oot_checks[i]);
    snprintf(oot_checks[i].item, sizeof oot_checks[i].item, "%s", item);
    snprintf(oot_checks[i].folder, sizeof oot_checks[i].folder, "%s", folder);
    snprintf(oot_checks[i].ages, sizeof oot_checks[i].ages, "%s", ages);
    oot_checks[i].place[0] = x, oot_checks[i].place[2] = z, oot_checks[i].skull = skull, oot_checks[i].key = i + 1;
    return i;
}
static void fresh(void) {
    oot_check_count = 0, saves = 0, oot_skull_wait.n = 0, oot_chest_wait.n = 0, oot_dungeon_check = -1, said[0] = 0, clock_ns += 100000000000000LL;
    memset(marks, 0, sizeof marks), memset(opens, 0, sizeof opens);
}
/* the record's second: a mark the save has is ticked, as oot_shelf_flags does, then the wait is looked at */
static int second(void) {
    for (int i = 0; i < oot_check_count; i++)
        if ((oot_checks[i].done == 1) != marks[i] && !oot_checks[i].sold) oot_checks[i].done = marks[i], oot_checks[i].claimed = 0, oot_checks[i].marked_at = marks[i] ? hos_now_ns() : 0;
    return oot_skull_waited();
}
int main(void) {
    Ctx c = {0};
    int near, far, other, chest;
    /* ---- the mark set before the add ---- */
    fresh();
    near = add("Seeds", 5, 0, "KakarikoVillage", "CA", 1), far = add("Seeds", 40, 0, "KakarikoVillage", "CA", 1);
    marks[far] = 1;
    check(oot_skull_item(&c, "Seeds", -1) == 1 && oot_checks[far].done == 1 && oot_checks[far].claimed && !oot_checks[far].sold, "the Skulltula the save marked is not the drop's");
    check(oot_checks[near].done != 1 && !oot_checks[near].sold && !oot_skull_wait.n && saves == 1 && oot_dungeon_check == far, "the nearer one was ticked or written, or the record not saved");
    /* ---- marked at its death, ticked by the record's second, the drop taken after ---- */
    fresh();
    near = add("Seeds", 5, 0, "KakarikoVillage", "CA", 1), far = add("Seeds", 40, 0, "KakarikoVillage", "CA", 1);
    marks[far] = 1;
    second();
    clock_ns += 20000000000LL;
    check(oot_checks[far].done == 1 && oot_checks[far].marked_at && !oot_checks[far].claimed, "the record's second did not tick the marked one");
    check(oot_skull_item(&c, "Seeds", -1) == 1 && oot_checks[far].claimed && oot_checks[near].done != 1 && !oot_skull_wait.n, "the add did not claim the one the save marked a while ago");
    /* (the nearer one's own drop, later: the first is claimed, so this add waits for the nearer's mark) */
    check(oot_skull_item(&c, "Seeds", -1) == 1 && oot_skull_wait.n == 1 && oot_skull_wait.at[0] == near && oot_checks[near].done != 1, "a second drop claimed the first one's mark again");
    marks[near] = 1, clock_ns += 400000000LL;
    check(second() == 0 && oot_checks[near].done == 1 && oot_checks[near].claimed && !oot_checks[near].sold && !oot_skull_wait.n, "the one the save marked after the add is not the drop's");
    /* ---- the mark comes after the add: the farther one was the one killed ---- */
    fresh();
    near = add("Seeds", 5, 0, "KakarikoVillage", "CA", 1), far = add("Seeds", 40, 0, "KakarikoVillage", "CA", 1);
    check(oot_skull_item(&c, "Seeds", -1) == 1 && oot_skull_wait.n == 2 && oot_skull_wait.at[0] == near && oot_checks[near].done != 1 && oot_checks[far].done != 1 && !saves,
          "an add with no mark yet did not wait, or ticked on a guess");
    clock_ns += 1000000000LL;
    check(second() == 0 && oot_skull_wait.n == 2, "the wait ended before its time with no mark");
    marks[far] = 1, clock_ns += 1000000000LL;
    check(second() == 0 && oot_checks[far].done == 1 && oot_checks[far].claimed && oot_checks[near].done != 1 && !oot_checks[near].sold && !oot_skull_wait.n,
          "the one the save marked during the wait is not the drop's, or the nearest was taken");
    /* ---- the save marks none: the nearest, as before, and its mark written ---- */
    fresh();
    near = add("Seeds", 5, 0, "KakarikoVillage", "CA", 1), far = add("Seeds", 40, 0, "KakarikoVillage", "CA", 1);
    oot_skull_item(&c, "Seeds", -1);
    clock_ns += 2900000000LL;
    check(second() == 0 && oot_checks[near].done != 1, "the nearest was taken before the wait's end");
    clock_ns += 200000000LL;
    check(second() == 1 && oot_checks[near].done == 1 && oot_checks[near].sold && oot_checks[far].done != 1 && !oot_skull_wait.n && strstr(said, "as before"),
          "with no mark after the wait the nearest is not taken, or the log does not say so");
    /* ---- Link's age's first among those waited for (bug 125) ---- */
    fresh();
    near = add("Seeds", 5, 0, "KakarikoVillage", "A", 1), far = add("Seeds", 40, 0, "KakarikoVillage", "C", 1);
    oot_skull_item(&c, "Seeds", -1);
    check(oot_skull_wait.n == 2 && oot_skull_wait.at[0] == far, "the other age's Skulltula comes before Link's own");
    /* ---- a second add while one is waited for: each its own ---- */
    fresh();
    near = add("Seeds", 5, 0, "KakarikoVillage", "CA", 1), far = add("Seeds", 40, 0, "KakarikoVillage", "CA", 1), other = add("Nuts", 6, 0, "KakarikoVillage", "CA", 1);
    oot_skull_item(&c, "Seeds", -1);
    check(oot_skull_item(&c, "Nuts", -1) == 1 && oot_checks[near].done == 1 && oot_checks[near].sold && oot_skull_wait.n == 1 && oot_skull_wait.at[0] == other &&
          !strcmp(oot_skull_wait.item, "Nuts") && oot_checks[other].done != 1, "a second add did not settle the first and wait for its own");
    /* ---- not theirs: another item, another map, a chest, a family ---- */
    fresh();
    near = add("Seeds", 5, 0, "KakarikoVillage", "CA", 1), far = add("Nuts", 6, 0, "Graveyard", "CA", 1), chest = add("Arrows", 7, 0, "KakarikoVillage", "CA", 0);
    other = add("Bag_Big", 8, 0, "KakarikoVillage", "CA", 1);
    check(oot_skull_item(&c, "Nuts", -1) == 0 && oot_skull_item(&c, "Arrows", -1) == 0 && !oot_skull_wait.n, "an item no Skulltula of this map gives is taken for one's");
    check(oot_skull_item(&c, "Bag_Small", family_of("Bag_Small")) == 1 && oot_skull_wait.n == 1 && oot_skull_wait.at[0] == other, "a family's next is not its Skulltula's");
    (void)chest, (void)far, (void)near;
    /* ---- chests, by the game's opened flag ---- */
    struct oot_wait w;
    fresh();
    near = add("Nuts", 2, 0, "KokiriForest", "CA", 0), far = add("Nuts", 4, 0, "KokiriForest", "CA", 0), other = add("Nuts", 3, 0, "KokiriForest", "CA", 1);
    oot_checks[near].opened = near + 1, oot_checks[far].opened = far + 1;
    snprintf(oot_link_map, sizeof oot_link_map, "KokiriForest_Child");
    opens[far] = 1;
    check(oot_chest_item(&c, "Nuts", -1, &w) == 1 && oot_checks[far].done == 1 && oot_checks[far].sold && oot_checks[far].claimed && oot_checks[near].done != 1 &&
          oot_checks[other].done != 1 && saves == 1, "the chest open by the game's flag at the add is not the item's");
    /* (ticked by its flag a while ago, the item added after the scene) */
    fresh();
    near = add("Nuts", 2, 0, "KokiriForest", "CA", 0), far = add("Nuts", 4, 0, "KokiriForest", "CA", 0);
    oot_checks[near].opened = near + 1, oot_checks[far].opened = far + 1;
    oot_checks[far].done = 1, oot_checks[far].marked_at = hos_now_ns() - 4000000000LL;
    check(oot_chest_item(&c, "Nuts", -1, &w) == 1 && oot_checks[far].claimed && oot_checks[near].done != 1 && !oot_checks[near].sold, "the add did not claim the chest its flag ticked");
    check(oot_chest_item(&c, "Nuts", -1, &w) == 0 && w.n == 1 && w.at[0] == near, "a second add claimed the same chest again");
    /* (none open yet: the chests here that give it, the nearest first, for the record to wait for; then the wait) */
    fresh();
    far = add("Nuts", 4, 0, "KokiriForest", "CA", 0), near = add("Nuts", 2, 0, "KokiriForest", "CA", 0), other = add("Seeds", 1, 0, "KokiriForest", "CA", 0);
    oot_checks[near].opened = near + 1, oot_checks[far].opened = far + 1, oot_checks[other].opened = other + 1;
    check(oot_chest_item(&c, "Nuts", -1, &w) == 0 && w.n == 2 && w.at[0] == near && w.at[1] == far && !strcmp(w.item, "Nuts") && oot_checks[near].done != 1 && !saves,
          "an add with no chest open by its flag ticked one, or did not hand back those that could be it");
    oot_chest_wait = w;
    oot_checks[far].done = 1, clock_ns += 200000000LL;   /* (the record's second ticked the one whose flag the game set) */
    check(oot_wait_settle(&oot_chest_wait, "chest") == 0 && oot_checks[far].claimed && oot_checks[near].done != 1 && !oot_chest_wait.n && strstr(said, "chest"),
          "the chest the save marked during the wait is not the item's");
    oot_chest_wait = w, oot_chest_wait.since = hos_now_ns(), oot_checks[far].done = 0, oot_checks[far].claimed = 0;
    clock_ns += 3100000000LL;
    check(oot_wait_settle(&oot_chest_wait, "chest") == 1 && oot_checks[near].done == 1 && oot_checks[near].sold && oot_checks[far].done != 1, "no flag after the wait: the nearest chest is not taken as before");
    snprintf(oot_link_map, sizeof oot_link_map, "KakarikoVillage_Child");
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
    p.add_argument("--cc", default="gcc")
    a = p.parse_args()
    host = (ROOT / "host" / "hos_main.c").read_text(encoding="utf-8")
    defines = "\n".join(line for line in host.splitlines() if line.startswith(("#define OOT_SKULL_WAIT_NS", "#define OOT_SKULL_CLAIM_NS", "#define OOT_SKULL_WAITING")))
    wait = "\n".join(line for line in host.splitlines() if line.startswith(("struct oot_wait {", "static struct oot_wait oot_skull_wait, oot_chest_wait;")))
    check(wait.count("\n") == 1, "the wait's record is not declared as the fixture takes it")
    settle = block(host, "static int oot_wait_settle(struct oot_wait *w, const char *what) {")
    one = next(line for line in host.splitlines() if line.startswith("static int oot_skull_waited(void) { return oot_wait_settle(&oot_skull_wait,"))
    fixture = (FIXTURE.replace("// DEFINES", defines + "\n" + wait).replace("// WAITED", settle + "\n" + one)
               .replace("// ITEM", block(host, "static int oot_skull_item(Ctx *c, const char *name, int family) {"))
               .replace("// CHEST", block(host, "static int oot_chest_item(Ctx *c, const char *name, int family, struct oot_wait *wait) {")))
    with tempfile.TemporaryDirectory(prefix="skull-marks-") as tmp:
        src, exe = Path(tmp) / "fixture.c", Path(tmp) / "fixture.exe"
        src.write_text(fixture, encoding="utf-8")
        subprocess.run([a.cc, "-std=c11", "-Wall", "-Wextra", "-Werror", str(src), "-o", str(exe), "-lm"], check=True)
        beside = os.path.dirname(shutil.which(a.cc) or "")
        ran = subprocess.run([str(exe)], capture_output=True, text=True, env=dict(os.environ, PATH=beside + os.pathsep + os.environ.get("PATH", "")))
    check(ran.returncode == 0 and ran.stdout.strip() == "ok", "a drop's or a chest's check by the save's marks:\n" + ran.stdout + ran.stderr)
    # ---- the record uses them: a pick-up's add goes their way first, and the second's look settles a wait ----
    item = block(host, "static void oot_tracker_item(Ctx *c, const char *name, int shop, int price, int pickup) {")
    check("if (pickup && !shop && oot_pot_chosen < 0 && oot_piece_chosen < 0 && oot_skull_item(c, name, family)) {" in item and
          item.index("oot_skull_item(c, name, family)") < item.index("for (int pass = 0; pass < 1 + left && best < 0; pass++) {"),
          "a pick-up's add is not asked of the Skulltulas before the nearest check is looked for")
    check("oot_tracker_item(c, name, shop, price, c->x[30] != 0x828d50acULL);" in host, "the record is not told which adds are a pick-up's")
    # (a lying Piece of Heart's item, a boss's Heart Container's, the lake's Fire Arrows': the check found at the piece's own
    #  place is the one ticked, not the nearest check that gives its item)
    gives = block(host, "static int oot_piece_gives(char *out, size_t size, int boss) {")
    check("oot_piece_chosen = best;" in gives and "best = oot_piece_chosen;" in item and
          item.index("best = oot_piece_chosen;") > item.index("for (int pass = 0; pass < 1 + left && best < 0; pass++) {") and
          host.index("oot_piece_chosen = -1;", host.index("int hos_oot_pouch_add(Ctx *c) {")) < host.index("oot_piece_gives(gives, sizeof gives, 0)"),
          "a lying piece's item is not ticked at the piece's own check, or an add before it leaves its check chosen")
    # (an event's add goes the chests' way first; the nearest check a chest not open by its flag: waited for, not ticked)
    check("if (!pickup && !shop && oot_chest_item(c, name, family, &chests)) {" in item and
          "if (best >= 0 && chests.n && oot_checks[best].opened) {" in item and "oot_chest_wait = chests;" in item and
          item.index("if (best >= 0 && chests.n && oot_checks[best].opened) {") < item.index("oot_checks[best].done = 1;"),
          "a chest's item is ticked on a guess before its chest's flag is waited for")
    flags = block(host, "static int oot_shelf_flags(Ctx *c) {")
    check('marks += oot_wait_settle(&oot_chest_wait, "chest");' in flags, "the record's second does not settle a chest's wait")
    check("marks += oot_skull_waited();" in flags and
          "if (now && flips < OOT_MARK_FLIPS) flip[flips] = i;" in flags and
          "if (flips && flips <= OOT_MARK_FLIPS && oot_link_map[0] && hos_now_ns() - map_since > OOT_MARK_STEADY_NS)" in flags,
          "the record's second does not note when the save marked a check in play (not a load's many marks), or does not settle a wait")
    check('oot_checks[oot_check_count].skull = !strncmp(kind, "Gold Skulltula", 14)' in host, "a Gold Skulltula's check is not known by its name")
    print("PASS: a Gold Skulltula's drop and a chest's item by the save's marks")


if __name__ == "__main__":
    main()
