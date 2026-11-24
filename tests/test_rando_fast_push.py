"""Faster block pushing (rando_fast_push, asked 2026-11-23, share/todo.md): a Quality of life setting, off by default, that
moves no item. fast_push_param runs a block's push curve (GrabMoveActorParam's MoveSpeed, a Hermit2DSplit curve of how
far along a push is by its frames) FAST_PUSH times as fast: every point's frame and MaxX divided, the slopes multiplied,
how far along (y) and the rest of the file kept. A file with no curve of its own (it takes its parent's) is left alone, and
a curve not as known stops the seed. The file is built here with the seed tool's own BYML writer (no game files); the
setting's wiring is checked by source.

python -I -B tests/test_rando_fast_push.py
"""
import os
import re
import struct
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools", "rando"))
import rando_seed as seed  # noqa: E402

failed = False


def check(ok, what):
    global failed
    if not ok:
        failed = True
        print("FAIL: " + what)


F = lambda v: (210, struct.pack("<f", v))   # noqa: E731
V = lambda node: struct.unpack("<f", node[1])[0]   # noqa: E731
# (Obj_MovableBox_A_01's curve: x, y, the slopes; 44 frames a push)
CURVE = [0, 0, 0, 0, 8, 0, 0, 0, 18, 0.06, 0.00759788, 0.00759788, 35, 0.55, 0.049759, 0.049759, 43, 1, 0, 0]


def param(with_curve=True):
    d = {"IfCliffNearThenPushRate": F(0.25)}
    if with_curve:
        d["MoveSpeed"] = ("dict", {"Data": ("array", [F(v) for v in CURVE]), "MaxX": F(44), "Type": ("string", "Hermit2DSplit")})
    return seed.byml_build(("dict", d), 7)


def main():
    if not hasattr(seed, "fast_push_param"):
        print("FAIL: no fast_push_param")
        return 1
    tree, _ = seed.byml_parse(seed.fast_push_param(param(), 2.0))
    curve = tree[1]["MoveSpeed"][1]
    got = [V(n) for n in curve["Data"][1]]
    want = []
    for k in range(0, len(CURVE), 4):
        want += [CURVE[k] / 2, CURVE[k + 1], CURVE[k + 2] * 2, CURVE[k + 3] * 2]
    check(all(abs(a - b) < 1e-5 for a, b in zip(got, want)) and len(got) == len(want), "the curve is not run twice as fast: %s" % got)
    check(abs(V(curve["MaxX"]) - 22) < 1e-5, "MaxX is not halved")
    check(curve["Type"] == ("string", "Hermit2DSplit") and abs(V(tree[1]["IfCliffNearThenPushRate"]) - 0.25) < 1e-6,
          "the rest of the file changed")
    check(seed.fast_push_param(param(False)) is None, "a file with no curve of its own is changed")
    bad = seed.byml_build(("dict", {"MoveSpeed": ("dict", {"Data": ("array", [F(1)] * 3), "MaxX": F(1), "Type": ("string", "Hermit2DSplit")})}), 7)
    try:
        seed.fast_push_param(bad)
        check(False, "a curve not of groups of four is taken")
    except ValueError:
        pass
    check(seed.FAST_PUSH == 2.0 and "Obj_MovableBox_A_01" in seed.FAST_PUSH_PARAMS and "Obj_ShadowTemple_Statue_A_01" in seed.FAST_PUSH_PARAMS,
          "not twice as fast, or the common block or the Shadow Temple's statue left out")
    src = open(seed.__file__, encoding="utf-8").read()
    check('"rando_fast_push": 0' in src and 'a.fast_push = ini["rando_fast_push"] != 0' in src, "the setting is not read, off by default")
    check('(a.fast_push, " fast push")' in src, "it is not on the stamp's second line (moves no item)")
    body = src[src.index("    if a.fast_push:"):src.index("    # ---- bombs without the Goron's Bracelet")]
    check("pack_parts.add(part)" in body and "pack_sizes[rel[:-3]]" in body, "the changed packs' sizes are not given to the size table")
    header = open(os.path.join(ROOT, "gpu", "vk", "oot_rando.h"), encoding="utf-8").read()
    order = re.findall(r"^    X\(([A-Z_]+),", header, re.M)
    check("FAST_PUSH" in order and order.index("FAST_PUSH") > order.index("ARCHERY_WINS"), "the setting is not a row after the ones before it")
    launcher = open(os.path.join(ROOT, "launcher", "Launcher.cs"), encoding="utf-8").read()
    check('new object[] { "rando_fast_push", "Faster block pushing", new[] { "Off", "On" }, new[] { 0, 1 },' in launcher,
          "the launcher has no Off / On row for it")
    no_item = launcher[launcher.index("NoItemKeys = new HashSet<string>"):launcher.index("static bool MovesNoItem")]
    qol = launcher[launcher.index('Title = "QUALITY OF LIFE"'):]
    check('"rando_fast_push"' in no_item and '"rando_fast_push"' in qol[:qol.index("} },")],
          "the launcher does not count it as moving no item, or it is not in Quality of life")
    print("FAIL" if failed else "PASS: Faster block pushing")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
