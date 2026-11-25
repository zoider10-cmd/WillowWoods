"""The game's lock-free queues: a late writer returns instead of ending the game (Rekarina's "ringpost", 2026-11-22).

nx2/oot_patches.py patch_ring_post makes the 77 queue writers' tail call to the abort (f_8351c280) return when the host says
so (host/hos_main.c hos_oot_ring_post), and leaves the 78th tail call to it (f_810cdb10, a heap budget's abort) alone.
Checked on lift-shaped text made here; no game files.

python -I -B tests/test_ring_post.py
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nx2"))
import oot_patches as P  # noqa: E402

failed = False


def check(ok, what):
    global failed
    if not ok:
        failed = True
        print("FAIL: " + what)


def main():
    funcs = getattr(P, "RING_POST_FUNCS", frozenset())
    check(len(funcs) == 77 and 0x80d44e50 in funcs and 0x80183b70 in funcs and 0x810cdb10 not in funcs,
          "the 77 queue writers are not listed (the named-value post f_80d44e50 among them), or the heap budget's f_810cdb10 is")
    patch = getattr(P, "patch_ring_post", None)
    check(patch is not None, "no patch_ring_post")
    if patch:
        head = '#include "a64.h"\n'
        writer = "void f_80d44e50(Ctx *__restrict A64_NOESC c) {\n    c->x[0] = 1;\nTAILCALL(f_8351c280);\n}\n"
        budget = "void f_810cdb10(Ctx *__restrict A64_NOESC c) {\nTAILCALL(f_8351c280);\n}\n"
        other = "void f_80000100(Ctx *__restrict A64_NOESC c) {\nTAILCALL(f_80000200);\n}\n"
        src = head + writer + budget + other
        got = patch(src)
        check(got is not None and got[1] == 1, "the writer's abort is not counted once")
        if got:
            out = got[0]
            check(out.count("if (hos_oot_ring_post(c)) return;") == 1 and "extern int hos_oot_ring_post(Ctx *c);\n" in out,
                  "the writer does not ask the host before the abort, or the host's function is not declared")
            w = out[out.index("void f_80d44e50"):out.index("void f_810cdb10")]
            b = out[out.index("void f_810cdb10"):out.index("void f_80000100")]
            check("hos_oot_ring_post" in w and "hos_oot_ring_post" not in b and b.count("TAILCALL(f_8351c280);") == 1,
                  "the heap budget's abort was changed, or the writer's not")
            check("TAILCALL(f_80000200);" in out and patch(out)[0] == out and patch(out)[1] == 1,
                  "another tail call was changed, or a second run changes the text again")
        check(patch(head + other) is None, "a file without the abort is changed")
    src = (ROOT / "nx2" / "oot_patches.py").read_text(encoding="utf-8")
    check('counts["ring post writers"] += ring[1]' in src and 'total["ring post writers"] != len(RING_POST_FUNCS)' in src,
          "patch_file does not count the writers, or apply does not warn when not all 77 are made")
    host = (ROOT / "host" / "hos_main.c").read_text(encoding="utf-8")
    check("int hos_oot_ring_post(Ctx *c) {" in host and 'env_on("HOS_OOT_RING_ABORT")' in host,
          "the host has no hos_oot_ring_post, or no way to keep the game's abort")
    print("FAIL" if failed else "PASS: the game's queue writers return instead of ending the game")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
