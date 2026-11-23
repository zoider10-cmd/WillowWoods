"""The Health bars row (asked 2026-11-23): an enemy hit lately has a slot on the game side (host/hos_main.c oot_health_hit:
its life's own address, passed by nx2/oot_patches.py's hit call, the most life seen, its boss's place in OOT_BOSSES), and
each gameplay frame (oot_health_tick, from hos_oot_free_view) every slot sends where its bar goes, its life and its kind;
a slot is let go at 0 life, when the actor is gone, or a while after its last hit unless a boss. The renderer draws a bar
over each enemy and a boss's at the foot of the screen, named. Read from the sources: no game files."""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
failed = []


def check(ok, what):
    if not ok:
        failed.append(what)
        print("FAIL: " + what)


def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


def main():
    ids = read("gpu", "vk", "oot_cheat_items.h")
    slots = int(re.search(r"#define OOT_HEALTH_SLOTS (\d+)", ids).group(1))
    bases = {k: int(re.search(r"#define %s (\d+)" % k, ids).group(1)) for k in ("OOT_HEALTH_AT", "OOT_HEALTH_LIFE", "OOT_HEALTH_KIND")}
    used = set()
    for k, b in bases.items():
        span = set(range(b, b + slots))
        check(not span & used, "%s's slots overlap another range" % k)
        used |= span
    others = {int(v) for k, v in re.findall(r"#define (OOT_\w+) (\d+)\b", ids) if k not in bases and k != "OOT_HEALTH_SLOTS"}
    check(not used & others, "a health slot shares a number with another ID")
    bosses = re.findall(r'B\("(Enemy_\w+)", "([^"]+)"\)', ids)
    check(len(bosses) >= 15 and ("Enemy_DungeonBoss_Gohma", "Queen Gohma") in bosses and not any("Tentacle" in a or "Jellyfish" in a for a, _ in bosses),
          "the bosses' list lacks Gohma or holds a boss part")
    host = read("host", "hos_main.c")
    check("oot_health_hit(c, actor, life, old, next, text);" in host, "a hit does not reach the health bars")
    view = host[host.index("void hos_oot_free_view(Ctx *c, uint64_t view) {"):]
    view = view[:view.index("\n}\n")]
    check(view.index("if (oot_gameplay_view(c) != view) return;") < view.index("oot_health_tick(c);"), "the bars are not sent each gameplay frame")
    tick = host[host.index("static void oot_health_tick(Ctx *c) {"):]
    tick = tick[:tick.index("\n}\n")]
    check("recomp_load64(c, actor) == oot_health[k].vtable && recomp_load64(c, actor + 16) == oot_health[k].resource" in tick,
          "a slot's actor gone from the map is still read as it")
    check("(!life || life > 0xffff || (!oot_health[k].boss && now - oot_health[k].hit_ns > OOT_HEALTH_KEEP_NS))" in tick,
          "a slot is not let go at 0 life, or after a while unless a boss")
    check("rx_option_set(OOT_HEALTH_LIFE + k, 0), oot_health_sent[k] = 0;" in tick, "the renderer is not told a slot is free")
    check(tick.index("rx_option_set(OOT_HEALTH_AT + k") < tick.index("rx_option_set(OOT_HEALTH_LIFE + k, (int)"), "a slot's life comes before its place")
    hit = host[host.index("uint32_t next, const char *name) {\n"):]
    hit = hit[:hit.index("\n}\n")]
    check("if (old > oot_health[k].max) oot_health[k].max = old;" in hit and "!strcmp(name, oot_boss_actors[b])" in hit,
          "the most life seen, or a boss by its actor, is not kept")
    menu = read("gpu", "vk", "vk_menu.cpp")
    check('{TAB_GAMEPLAY, "Health bars", &opts.show_health, 0, 1, 1, tx_onoff,' in menu and "int show_health = 0;" in read("gpu", "vk", "vk_menu.h"),
          "the Gameplay tab has no Health bars row, off by default")
    check(menu.count("if (health) draw_health(c);") == 2 and menu.count("health_shows() && !") == 2, "the bars are not drawn on screen and on a test run's pictures")
    draw = menu[menu.index("void draw_health(ui::Ctx& c) {"):]
    draw = draw[:draw.index("\n}\n")]
    check("now - health_seen[k].load(std::memory_order_relaxed) >= kHealthStale" in draw and "kBossNames[kind - 1]" in draw,
          "a slot not heard of lately is drawn, or a boss's bar is not named")
    # (the Boss health row: Bar, or Hearts as Link's, a quarter heart a point, ten a row)
    check('{TAB_GAMEPLAY, "Boss health", &opts.boss_hearts, 0, 1, 1, tx_boss_health,' in menu and "int boss_hearts = 0;" in read("gpu", "vk", "vk_menu.h"),
          "the Gameplay tab has no Boss health row, Bar by default")
    check("const int hearts = (most + 3) / 4, rows = (hearts + 9) / 10;" in draw and "std::clamp(life - i * 4, 0, 4)" in draw,
          "a boss's hearts are not a heart each 4 points, a quarter each point")
    print("FAIL" if failed else "PASS: health bars")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
