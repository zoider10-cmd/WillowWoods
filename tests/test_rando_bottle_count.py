"""Link's bottles are counted from their slots (bug 156, the owner's run 2026-11-26: the Tracker's "Still asked for: a
bottle" with an empty bottle held; host/oot_wheel.c bottles_had, cy_bottle_walk, hos_oot_bottles; host/hos_main.c
oot_item_count): no game data.

The pouch keeps a bottle in a slot of its own, not as a count of Item_Bottle: that count stayed 0 with a bottle got, so the
Tracker's "a bottle", the Debug tab's Empty Bottle and Item buttons' slots_owned saw none. And the pouch names a bottle in
all five slots of a save that has none (seen without a window, a save before the owl): a slot counts only when the game
would list its bottle (CY_LISTABLE). Seen without a window on three save copies: 0 (before the owl), 1 (a red potion's
bottle), 5 (all items).

- bottles_had, compiled alone: a slot counts when it names a bottle and is listed, whatever is in the bottle;
- the walk asks the game whether each slot's bottle is listed, for both ages; the inventory's Item_Bottle is that count.

    python -I -B tests/test_rando_bottle_count.py [--cc clang]
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from srccut import block   # noqa: E402


def need(ok, what):
    if not ok:
        raise SystemExit("FAIL: " + what)


MAIN = r"""
#include <stdint.h>
#include <stdio.h>
@HAD@
int main(void) {
    const char none[5][48] = {"Item_Bottle", "Item_Bottle", "Item_Bottle", "Item_Bottle", "Item_Bottle"};
    const char some[5][48] = {"Item_Bottle_RedPotion", "Item_Bottle", "", "Item_Bottle_Fairy", "Item_Bottle"};
    if (bottles_had(none, 0) != 0) return puts("a save with no bottle has some: the slots name one all the same"), 1;
    if (bottles_had(none, 0x1f) != 5) return puts("five bottles listed are not five"), 1;
    if (bottles_had(some, 0x1) != 1) return puts("a filled bottle is not a bottle"), 1;
    if (bottles_had(some, 0x9) != 2) return puts("two bottles listed, of any content, are not two"), 1;
    if (bottles_had(some, 0x4) != 0) return puts("a listed slot that names nothing is a bottle"), 1;
    return 0;
}
"""


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--cc", default="cc")
    a = p.parse_args()
    wheel = (ROOT / "host" / "oot_wheel.c").read_text(encoding="utf-8")
    host = (ROOT / "host" / "hos_main.c").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as d:
        c, exe = Path(d) / "b.c", Path(d) / "b.exe"
        c.write_text(MAIN.replace("@HAD@", block(wheel, "static int bottles_had(const char found[5][48], uint32_t owned) {")), encoding="utf-8")
        subprocess.run([a.cc, "-std=gnu11", "-Wall", "-Werror", str(c), "-o", str(exe)], check=True)
        r = subprocess.run([str(exe)], capture_output=True, text=True)
        need(r.returncode == 0, "bottles_had: " + r.stdout.strip())
    walk = block(wheel, "static int cy_bottle_walk(Ctx *c, char found[5][48], uint32_t *owned) {")
    need("for (int age = 0; owned && age < 2; age++)" in walk and "cy_guest(c, CY_LISTABLE, 5, list) & 1" in walk and
         "*owned |= 1u << slot" in walk, "the walk does not ask the game whether each slot's bottle is listed, for both ages")
    count = block(wheel, "int hos_oot_bottles(Ctx *c) {")
    need("if (!cy_bottle_walk(c, found, &owned)) return -1;" in count and "bottles_had(found, owned)" in count,
         "the count of bottles is not the listed slots', or is 0 when the pouch cannot be walked (then: not known)")
    item = block(host, "static int oot_item_count(Ctx *c, const char *name) {")
    need('if (!strcmp(name, "Item_Bottle")) {' in item and "const int had = hos_oot_bottles(c);" in item and "return had > n ? had : n;" in item,
         "the inventory's Item_Bottle is not the bottles Link has")
    print("PASS: Link's bottles are counted from their slots")


if __name__ == "__main__":
    main()
