"""The Damage numbers row (asked 2026-11-23, the quick version first): the game side sends each hit an enemy takes
(host/hos_main.c hos_oot_hit, OOT_DAMAGE_HIT: the hit, and 1 << 16 when it defeated it), the renderer keeps the newest with
when they came and, while the row is on and the menu shut, draws each as a number rising and fading in the middle of the
screen, gold for a defeating hit. Read from the sources: no game files."""
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
    m = re.search(r"#define OOT_DAMAGE_HIT (\d+)", ids)
    taken = {int(v) for k, v in re.findall(r"#define (OOT_\w+) (\d+)\b", ids) if k != "OOT_DAMAGE_HIT"}
    check(m and int(m.group(1)) not in taken, "OOT_DAMAGE_HIT is missing or shares a number with another ID")
    host = read("host", "hos_main.c")
    fn = host[host.index("void hos_oot_hit(Ctx *c, uint64_t actor, uint32_t old, uint32_t next, uint32_t hit, uint64_t life) {"):]
    fn = fn[:fn.index("\n}\n")]
    check("rx_option_set(OOT_DAMAGE_HIT, (int)(hit > 0xffff ? 0xffff : hit) | (next == 0) << 16);" in fn,
          "the game side does not send each hit, with whether it defeated the enemy")
    check(fn.index("hos_oot_is_player(c, actor)) return;") < fn.index("rx_option_set("), "Link's own losses are sent too")
    # (above the enemy: its place, [actor +0x18] +0x31c, a little over it, through the gameplay camera; sent before the hit)
    check("const uint64_t body = recomp_load64(c, actor + 0x18);" in fn and "body + 0x31c + 4 * i" in fn and "place[1] += OOT_DAMAGE_ABOVE;" in fn,
          "the hit's place is not the actor's own, a little above it")
    check(fn.index("rx_option_set(OOT_DAMAGE_AT, at);") < fn.index("rx_option_set(OOT_DAMAGE_HIT"), "the place is not sent before its hit")
    scr = host[host.index("static int oot_damage_screen(Ctx *c, const float p[3]) {"):]
    scr = scr[:scr.index("\n}\n")]
    check("view + 0x13c" in scr and "view + 0x140" in scr and "!(-cz > znear)) return -1;" in scr and "return y << 15 | x;" in scr,
          "the place is not put through the camera's field of view and aspect, or one behind it is not refused")
    menu = read("gpu", "vk", "vk_menu.cpp")
    check("if (id == OOT_DAMAGE_AT) {" in menu and "damage_next_at.exchange(-1" in menu, "the renderer does not keep a hit's place with it")
    opts = read("gpu", "vk", "vk_menu.h")
    check("int show_damage = 0;" in opts, "the row is not off by default")
    check('{TAB_GAMEPLAY, "Damage numbers", &opts.show_damage, 0, 1, 1, tx_onoff,' in menu, "the Gameplay tab has no Damage numbers row")
    check("if (id == OOT_DAMAGE_HIT) {" in menu and "damage_hit(value);" in menu, "the renderer does not keep the hits it is sent")
    check(menu.count("if (damage) draw_damage(c);") == 2, "the numbers are not drawn both on screen and on a test run's pictures")
    check(menu.count("damage_shows() && !") == 2 and "!clock && !damage && !health && !minimap) {" in menu and "!clock && !damage && !health && !minimap) return;" in menu,
          "nothing draws the numbers while nothing else shows, or they show under the open menu")
    body = menu[menu.index("void draw_damage(ui::Ctx& c) {"):]
    body = body[:body.index("\n}\n")]
    check("age >= kDamageShown" in body and "value >> 16 ? ui::rgba(255, 205, 60, alpha)" in body and '"%d", value & 0xffff' in body,
          "a number is not drawn for its time, or a defeating hit not in gold")
    print("FAIL" if failed else "PASS: damage numbers")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
