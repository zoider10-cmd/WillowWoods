"""Item buttons: L and R hold items of their own (host/oot_wheel.c, share/design-item-slots.md): no game data.

Checks the wiring a change elsewhere could break, from the sources:
- the Gameplay tab's row (Off / L and R slots) answers HOS_OPT_ITEM_BUTTONS, an id of its own;
- the slots' input runs first in hos_wheel_input (before the item row's and Cycle items' handling), and Cycle items is
  off while the slots are on;
- the HUD's update puts the asked item on ZR (slots_hud) and the pause menu's update reads an assigned one (slots_pause);
- the pause menu's page is known to the wheel (hos_oot_pause_page), the Items page being 2;
- the HUD's L and R icons: the slots' items published (MKWVK_SLOTS_QUERY) and drawn by the overlay;
- and the input's state machine, compiled alone against a fake clock and a fake HUD: L with an item asks for it, holds ZR
  back until the HUD put it there, then holds ZR while L is held; ZR afterwards asks for ZR's own back first; an item seen
  to work so is forced on Link at his update and ZR keeps its own (the Slingshot and the Bow with it: the game's two
  lookups of their ammunition are given the forced item, and the bottles' three), an item not tried forced goes on ZR; the put-back made on
  its own waits while Link holds an item (a Deku Stick taken out stays out).

    python -I -B tests/test_item_buttons.py [--cc clang]
"""
import argparse
import re
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


FAKE = r"""
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
enum { B_A = 0, B_B, B_X, B_Y, B_LS, B_RS, B_L, B_R, B_ZL, B_ZR, B_PLUS, B_MINUS };
#define HOLD_BUTTONS ((1ULL << B_R) | (1ULL << B_L))
#define CY_ITEMS 54
#define SLOTS_RESTORE_NS 1500000000LL
static int64_t pause_tick_ns;
static int playing = 1;
static int in_play(int64_t now) { (void)now; return playing; }
static int wheel_trace(void) { return 0; }
static void hos_log(const char *f, ...) { (void)f; }
int hos_oot_pause_page(void) { return 2; }
static int slots_on(void) { return 1; }
static int slot_had[2] = {1, 1};
static int slots_has(int slot) { return slot_had[slot]; }
static int env_on(const char *name) { (void)name; return 1; }
#define SLOT_L 0
#define SLOT_R 1
static volatile int slot_item[2][2] = {{-1, -1}, {7, -1}};   /* (the child's L: item 7) */
static volatile int slot_age = 1;
static volatile int swap_want = -1, swap_seq, swap_done;
static volatile int zr_own_on = 1;
static volatile int link_done, link_own_on = 1;
static volatile int assign_state, assign_which;
static volatile int hand_item = -1;
static volatile int forced_now = -1;
#define SLOTS_OWN -2
#define SLOTS_WHEN_FREE -3
@WAITS@
@FORCE@
@ITEM@
@TARGET@
@LINK@
@ASK@
@INPUT@
int main(void) {
    const uint64_t L = 1ULL << B_L, ZR = 1ULL << B_ZR;
    int64_t t = 1000000000LL;
    uint64_t out = slots_input(0, t);
    out = slots_input(L, t += 16000000);   /* L pressed */
    if (swap_want != 7 || swap_seq != 1) return printf("L did not ask for its item (%d, %d)\n", swap_want, swap_seq), 1;
    if (out & (L | ZR)) return printf("L or ZR reached the game before the item was on ZR (%llx)\n", (unsigned long long)out), 1;
    swap_done = link_done = swap_seq, zr_own_on = 0;   /* (the HUD put it there) */
    out = slots_input(L, t += 16000000);
    if (!(out & ZR) || (out & L)) return printf("ZR not held for L's item (%llx)\n", (unsigned long long)out), 1;
    out = slots_input(0, t += 16000000);
    if (out & ZR) return printf("ZR still held after L was let go\n"), 1;
    out = slots_input(ZR, t += 16000000);   /* ZR pressed: its own item first */
    if (swap_want != SLOTS_OWN || swap_seq != 2 || (out & ZR)) return printf("ZR did not ask for its own item first (%d, %llx)\n", swap_want, (unsigned long long)out), 1;
    swap_done = link_done = swap_seq, zr_own_on = 1;
    out = slots_input(ZR, t += 16000000);
    if (!(out & ZR)) return printf("ZR not given once its own item was back\n"), 1;
    slots_input(0, t += 16000000);
    /* L used and let go: ZR's own item back on its own once nothing is pressed for a while, ZR not pressed for the game */
    slots_input(L, t += 16000000);
    swap_done = link_done = swap_seq, zr_own_on = 0;
    slots_input(L, t += 16000000);
    slots_input(0, t += 16000000);
    const int asked = swap_seq;
    out = slots_input(0, t += 1000000000LL);
    if (swap_seq != asked) return printf("ZR's own asked back too soon\n"), 1;
    out = slots_input(0, t += 600000000LL);
    /* (the put-back made on its own is the one that waits for Link's hand: a Deku Stick out stays out) */
    if (swap_seq != asked + 1 || swap_want != SLOTS_WHEN_FREE || (out & ZR)) return printf("ZR's own not put back after L (%d, %d)\n", swap_seq, swap_want), 1;
    if (!slots_waits(SLOTS_WHEN_FREE, 0) || slots_waits(SLOTS_WHEN_FREE, -1)) return printf("the put-back made on its own does not wait for Link's empty hand\n"), 1;
    if (slots_waits(SLOTS_OWN, 0) || slots_waits(7, 0)) return printf("ZR's press or a button's item waits for Link's hand\n"), 1;
    /* the forced item (Link's update), for an item seen to work so (0, the Deku Stick): written over none, kept while he
       holds it, taken off once his hand is empty; an item the game forces itself is left alone; the Slingshot (4) is
       never forced */
    swap_done = link_done = swap_seq;
    if (!slots_forced(0) || !slots_forced(6) || !slots_forced(7) || !slots_forced(4) || !slots_forced(30) || !slots_forced(47) || !slots_forced(14) || !slots_forced(50) || slots_forced(2) || slots_forced(1)) return printf("the forced items are not the ones seen to work\n"), 1;
    slots_ask(0);
    if (hos_oot_slots_link(-1, -1) != 0 || link_done != swap_seq || link_own_on) return printf("L's item not forced\n"), 1;
    if (hos_oot_slots_link(0, 0) != -2) return printf("the forced item written twice\n"), 1;
    slots_ask(SLOTS_WHEN_FREE);
    if (hos_oot_slots_link(0, 0) != -2 || link_done == swap_seq) return printf("the forced item taken off under an item Link holds\n"), 1;
    if (hos_oot_slots_link(-1, 0) != -1 || link_done != swap_seq || !link_own_on) return printf("the forced item not taken off once his hand is empty\n"), 1;
    if (hos_oot_slots_link(-1, -1) != -2) return printf("no forced item written again\n"), 1;
    slots_ask(0);
    if (hos_oot_slots_link(-1, 30) != -2) return printf("the game's own forced item written over\n"), 1;
    slots_ask(SLOTS_OWN);
    if (hos_oot_slots_link(-1, 30) != -2) return printf("the game's own forced item taken off\n"), 1;
    slots_ask(0);
    hos_oot_slots_link(-1, -1);
    if (hos_oot_slots_item(2) != 0) return printf("the ammunition's lookup is not given the forced item\n"), 1;
    slots_ask(2);   /* (an item not forced after a forced one: the forced one taken off, ZR's the HUD's to change) */
    if (hos_oot_slots_link(-1, 0) != -1 || link_done != swap_seq || !link_own_on) return printf("the forced item kept under an item that goes on ZR\n"), 1;
    hos_oot_slots_link(-1, -1);
    if (hos_oot_slots_item(2) != 2) return printf("the ammunition's lookup is given an item with none forced\n"), 1;
    /* the input waits for both answers before it holds ZR, and ZR is not its own while an item is forced */
    swap_done = link_done = swap_seq, zr_own_on = 1, link_own_on = 1;
    slots_input(0, t += 16000000);
    out = slots_input(L, t += 16000000);
    swap_done = swap_seq;
    out = slots_input(L, t += 16000000);
    if (out & ZR) return printf("ZR held before Link's update answered\n"), 1;
    link_done = swap_seq, link_own_on = 0;
    out = slots_input(L, t += 16000000);
    if (!(out & ZR)) return printf("ZR not held once both answered\n"), 1;
    slots_input(0, t += 16000000);
    const int forced_seq = swap_seq;
    out = slots_input(ZR, t += 16000000);
    if (swap_seq != forced_seq + 1 || swap_want != SLOTS_OWN || (out & ZR)) return printf("ZR under a forced item did not ask for its own first\n"), 1;
    link_own_on = 1;
    slots_input(0, t += 16000000);
    swap_done = link_done = swap_seq, zr_own_on = 1;
    slots_input(0, t += 16000000);
    slot_item[1][1] = -1;
    const int before_r = swap_seq;
    out = slots_input(1ULL << B_R, t += 16000000);   /* R with no item: nothing asked, R kept from the game */
    if (swap_seq != before_r || (out & (1ULL << B_R))) return printf("R with no item asked or reached the game\n"), 1;
    slots_input(0, t += 300000000);
    /* a scene takes over while L is held (a bottle's bugs let out): the put-back is asked once play is back */
    swap_done = link_done = swap_seq, zr_own_on = 1, link_own_on = 1;
    slots_input(L, t += 16000000);
    swap_done = link_done = swap_seq, link_own_on = 0;
    slots_input(L, t += 16000000);
    playing = 0;
    slots_input(L, t += 16000000);
    slots_input(0, t += 16000000);
    playing = 1;
    const int scene_seq = swap_seq;
    slots_input(0, t += 2000000000LL);
    if (swap_seq != scene_seq + 1 || swap_want != SLOTS_WHEN_FREE) return printf("no put-back after a scene took over L's item (%d, %d)\n", swap_seq - scene_seq, swap_want), 1;
    swap_done = link_done = swap_seq, link_own_on = 1;
    slots_input(0, t += 300000000);
    slot_had[0] = 0;   /* (L's item gone from the pouch: nothing asked) */
    const int before_gone = swap_seq;
    out = slots_input(L, t += 16000000);
    if (swap_seq != before_gone || (out & (L | ZR))) return printf("L asked for an item Link no longer has\n"), 1;
    puts("PASS: L's item put on ZR before ZR is held, ZR's own back before its use and after L's");
    return 0;
}
"""


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cc", default="cc")
    a = p.parse_args()
    wheel = (ROOT / "host" / "oot_wheel.c").read_text(encoding="utf-8")
    menu = (ROOT / "gpu" / "vk" / "vk_menu.cpp").read_text(encoding="utf-8")
    replay = (ROOT / "gpu" / "vk" / "vk_replay.cpp").read_text(encoding="utf-8")
    state = (ROOT / "gpu" / "vk" / "oot_wheel_state.h").read_text(encoding="utf-8")
    pause = (ROOT / "host" / "oot_menu.c").read_text(encoding="utf-8")
    ids = [int(n) for n in re.findall(r"HOS_OPT_\w+ = (\d+)", state + (ROOT / "gpu" / "vk" / "vk_api.h").read_text(encoding="utf-8"))]
    need("HOS_OPT_ITEM_BUTTONS = 103" in state and ids.count(103) == 1, "the Item buttons row has no option id of its own")
    need('{TAB_GAMEPLAY, "Item buttons", &opts.item_buttons, 0, 1, 1, tx_item_buttons,' in menu, "the Gameplay tab has no Item buttons row")
    need("if (id == HOS_OPT_ITEM_BUTTONS) return opts.item_buttons;" in replay, "the game side is not told the Item buttons row")
    inp = block(wheel, "uint64_t hos_wheel_input(uint64_t buttons, int32_t stick[4]) {")
    first = inp.index("buttons = slots_input(buttons, now);")
    need(first < inp.index("row_tick_ns") and first < inp.index("Cycle Items"), "the slots' input does not run first")
    need("if (slots_on()) return 0;" in block(wheel, "static int cycle_level(void) {"), "Cycle items stays on with the slots")
    tick = block(wheel, "int hos_wheel_menu_tick(Ctx *c, uint64_t screen_arg) {")
    need("if (slots_on()) slots_hud(c);" in tick and "if (vt == CY_PLUS_VTABLE && slots_on()) slots_pause(c);" in tick,
         "the HUD's or the pause menu's update does not run the slots")
    need("int hos_oot_pause_page(void) { return page_now; }" in pause and "hos_oot_pause_page() == 2" in wheel,
         "the pause menu's page is not known to the slots")
    backend = (ROOT / "host" / "rx_backend.c").read_text(encoding="utf-8")
    vkmenu_draw = menu.count("if (slots) draw_item_buttons(c);")
    need("if (index == MKWVK_SLOTS_QUERY) return (const char *)hos_slots_state();" in backend and "slots_publish(c, age);" in wheel,
         "the HUD's L and R icons are not told the slots' items")
    need(vkmenu_draw == 2 and menu.count("&& item_buttons_shows();") == 2,
         "the overlay does not draw the L and R icons (both of its drawings, with the window and the headless shots)")
    hud = block(wheel, "static void slots_hud(Ctx *c) {")
    need("if (slots_waits(want, __atomic_load_n(&hand_item, __ATOMIC_ACQUIRE))) return;" in hud and
         hud.index("slots_waits(") < hud.index("cy_guest(c, CY_SETTER") and hud.index("slots_waits(") < hud.index("&swap_done, seq"),
         "the HUD's update puts ZR's own item back under an item Link holds")
    need("hos_oot_slots_link(" in block((ROOT / "host" / "hos_main.c").read_text(encoding="utf-8"), "void hos_oot_lift_player(Ctx *c, uint64_t actor) {"),
         "Link's update does not tell the slots what he holds")
    need("want == SLOTS_OWN || want == SLOTS_WHEN_FREE || slots_forced(want)" in hud and "target = zr_put >= 0 ? zr_own[age] : cur, zr_put = -1;" in hud,
         "the HUD's update puts a forced item on ZR, or does not give ZR its own back under one")
    patches = (ROOT / "nx2" / "oot_patches.py").read_text(encoding="utf-8")
    need(all('"c->x[30] = 0x%sULL; f_8019b6e0(c);"' % lr in patches for lr in ("833c784c", "80c23ab4", "82a3d97c", "828e2ce0", "8293650c")) and
         "patch_slots_item(out)" in patches and 'total["slots item answers"] != len(SLOTS_ITEM_CALLS)' in patches,
         "the game's two lookups of a shooting item's ammunition are not given the forced item")
    src = FAKE.replace("@WAITS@", block(wheel, "static int slots_waits(int want, int hand) {")).replace(
        "@FORCE@", block(wheel, "static int slots_forced(int item) {")).replace(
        "@TARGET@", block(wheel, "static int slots_force_target(int want, int hand, int forced, int *answered) {")).replace(
        "@ITEM@", block(wheel, "unsigned long long hos_oot_slots_item(unsigned long long item) {")).replace(
        "@LINK@", block(wheel, "int hos_oot_slots_link(int hand, int forced) {")).replace("@ASK@", block(wheel, "static int slots_ask(int item) {")).replace(
        "@INPUT@", block(wheel, "static uint64_t slots_input(uint64_t buttons, int64_t now) {"))
    with tempfile.TemporaryDirectory() as d:
        c, exe = Path(d) / "t.c", Path(d) / "t.exe"
        c.write_text(src, encoding="utf-8")
        subprocess.run([a.cc, "-std=gnu11", "-Wall", "-Werror", "-Wno-unused-function", str(c), "-o", str(exe)], check=True)
        r = subprocess.run([str(exe)], capture_output=True, text=True)
        print(r.stdout.strip())
        need(r.returncode == 0, "the slots' input")
    print("PASS: Item buttons: the row, the wiring and the input")


if __name__ == "__main__":
    main()
