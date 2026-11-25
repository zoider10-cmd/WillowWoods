"""Link crawls faster (rando_fast_crawl, asked 2026-11-23, share/todo.md): a crawl's forward speed comes through the move
setter f_809552f0 called from the crawl's own step (OOT_CRAWL_CALLER, seen without a window 2026-11-24: 0.025 m a frame
in Kokiri Forest's crawlspace, a walk's from 0x827f38e0), which host/hos_main.c hos_oot_cct_speed already sees for the
Debug tab's Movement speed; with the setting on it is doubled (seen: 0.62 m between place logs became 1.24, Link out of
the far end). Game-free: the sources.

python -I -B tests/test_rando_fast_crawl.py
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def read(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


def main():
    host = read("host", "hos_main.c")
    fn = host[host.index("void hos_oot_cct_speed(Ctx *c, uint64_t controller, int per_second) {"):]
    fn = fn[:fn.index("\n}\n")]
    assert "#define OOT_CRAWL_CALLER 0x82e98270ULL" in host and "#define OOT_CRAWL_FASTER 2.0f" in host
    crawl = fn.index("c->x[30] == OOT_CRAWL_CALLER")
    assert crawl < fn.index("controller != __atomic_load_n(&oot_speed_controller"), "the crawl waits for the Debug tab's speed"
    assert "!per_second &&" in fn[:crawl + 40] and "hos_rando_fast_crawl()" in fn and "fabsf(crawl) <= 0.1f" in fn
    assert "__atomic_store_n(&oot_link_controller, link, __ATOMIC_RELAXED);" in host, "Link's controller is known only with the speed cheat on"
    rando = read("host", "oot_rando.c")
    assert "return rando_active && rando.v[OOT_RANDO_FAST_CRAWL] != 0;" in rando
    header = read("gpu", "vk", "oot_rando.h")
    assert 'X(FAST_CRAWL, "Link crawls faster", "rando_fast_crawl",' in header
    launcher = read("launcher", "Launcher.cs")
    no_item = launcher[launcher.index("NoItemKeys = new HashSet<string>"):launcher.index("static bool MovesNoItem")]
    qol = launcher[launcher.index('Title = "QUALITY OF LIFE"'):]
    assert '"rando_fast_crawl"' in no_item and '"rando_fast_crawl"' in qol[:qol.index("} },")], "not a Quality of life setting that moves no item"
    print("PASS: Link crawls faster")
    return 0


if __name__ == "__main__":
    sys.exit(main())
