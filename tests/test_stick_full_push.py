"""A stick pushed past 92% of its travel is a full push in its direction (host/pad_sdl.c stick_full_push; Triforce v0.8.4).
No game, no controller.

SDL's Switch driver widens an axis's range to the furthest it has read: after a hard click at full tilt the same full push
forward read 31083, then about 30600 (93 to 95%), and the game rolls only from a full one ("clicking the left stick stops
rolling when moving forward"). The function is cut out of the source and run. Checked:
- the readings of that report become a full push, straight and at an angle, the direction kept;
- under 92% nothing changes (walking speeds, the dead zone's zeros), nor does a push that is full already or past it;
- the result never leaves an axis's range;
- pads_poll applies it to both sticks after the dead zone and before the camera's inversion, and HOS_STICK_FULL_PUSH=0
  turns it off.

    python -I -B tests/test_stick_full_push.py [--cc gcc]
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from srccut import block   # noqa: E402

FIXTURE = r"""
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define STICK_FULL 32767.0
#define STICK_FULL_FROM 30146.0
@FUNC@
static int bad;
#define CHECK(x) do { if (!(x)) { printf("FAIL line %d: %s\n", __LINE__, #x); bad = 1; } } while (0)
static void run(int x, int y, int32_t out[2]) { out[0] = x, out[1] = y; stick_full_push(out); }
int main(void) {
    int32_t v[2];
    run(0, 31083, v); CHECK(v[0] == 0 && v[1] == 32767);          /* (the report's reading after the click) */
    run(0, 30600, v); CHECK(v[0] == 0 && v[1] == 32767);
    run(0, -30600, v); CHECK(v[0] == 0 && v[1] == -32767);
    run(-30146, 0, v); CHECK(v[0] == -32767 && v[1] == 0);        /* (at 92%: full) */
    run(30145, 0, v); CHECK(v[0] == 30145 && v[1] == 0);          /* (just under: as it is) */
    run(0, 0, v); CHECK(v[0] == 0 && v[1] == 0);
    run(12000, -9000, v); CHECK(v[0] == 12000 && v[1] == -9000);  /* (a walk) */
    run(0, 32767, v); CHECK(v[0] == 0 && v[1] == 32767);          /* (full already) */
    run(32767, 32767, v); CHECK(v[0] == 32767 && v[1] == 32767);  /* (past the circle: as it is) */
    run(21600, 21600, v);                                         /* (93% at 45 degrees: full, the direction kept) */
    CHECK(v[0] == v[1] && v[0] > 21600);
    CHECK(fabs(sqrt((double)v[0] * v[0] + (double)v[1] * v[1]) - 32767.0) < 2.0);
    for (int a = 0; a < 360; a++) {                               /* (every direction, 92 to 99.9%: full, in range, the same way) */
        for (double share = 0.921; share < 1.0; share += 0.013) {
            const double r = a * 3.14159265358979 / 180.0;
            const int x = (int)(cos(r) * 32767.0 * share), y = (int)(sin(r) * 32767.0 * share);
            if (sqrt((double)x * x + (double)y * y) < 30146.0) continue;
            run(x, y, v);
            const double m = sqrt((double)v[0] * v[0] + (double)v[1] * v[1]);
            CHECK(v[0] >= -32767 && v[0] <= 32767 && v[1] >= -32767 && v[1] <= 32767);
            CHECK(fabs(m - 32767.0) < 2.0);
            CHECK((double)v[0] * x >= 0 && (double)v[1] * y >= 0);
            CHECK(fabs(atan2(v[1], v[0]) - atan2(y, x)) < 0.001 || fabs(fabs(atan2(v[1], v[0]) - atan2(y, x)) - 6.283185307) < 0.001);
        }
    }
    return bad;
}
"""


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cc", default="gcc")
    a = p.parse_args()
    src = (ROOT / "host" / "pad_sdl.c").read_text(encoding="utf-8")
    for needle in ("#define STICK_FULL 32767.0", "#define STICK_FULL_FROM 30146.0"):
        if needle not in src:
            sys.exit("FAIL: host/pad_sdl.c no longer has: " + needle)
    poll = block(src, "static void pads_poll(void) {")
    use = "if (stick_full_push_on()) stick_full_push(v), stick_full_push(v + 2);"
    if use not in poll:
        sys.exit("FAIL: pads_poll no longer makes a push past 92% a full one, on both sticks")
    if not poll.index("hos_filter_stick((int16_t)v[2], (int16_t)v[3], z, v + 2);") < poll.index(use) < poll.index("if (inv_x) v[2] = -v[2];"):
        sys.exit("FAIL: the full push is not made after the dead zone and before the camera's inversion")
    on = block(src, "static int stick_full_push_on(void) {")
    if 'getenv("HOS_STICK_FULL_PUSH")' not in on or "on = !(e && e[0] == '0');" not in on:
        sys.exit("FAIL: HOS_STICK_FULL_PUSH=0 no longer turns it off")
    fixture = FIXTURE.replace("@FUNC@", block(src, "static void stick_full_push(int32_t v[2]) {"))
    with tempfile.TemporaryDirectory(prefix="stick-full-") as tmp:
        c, exe = Path(tmp) / "fixture.c", Path(tmp) / "fixture"
        c.write_text(fixture, encoding="utf-8")
        subprocess.run([a.cc, "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror", str(c), "-o", str(exe), "-lm"], check=True)
        got = subprocess.run([str(exe)], capture_output=True, text=True)
        if got.returncode:
            sys.exit("FAIL: " + got.stdout.strip()[:600])
    print("PASS: a stick past 92% of its travel is a full push in its direction")


if __name__ == "__main__":
    main()
