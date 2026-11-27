"""The Tracker's map (asked 2026-11-23): the whole game's row shows an overview of Hyrule (gpu/vk/vk_menu.cpp kWorldMap,
kWorldEdges, tracker_world_map) and an area's row its checks as dots (tracker_area_map) under its list. Checked: every
area the seed tool names (its AREAS' and the Tracker's names: tools/rando/rando_seed.py) has a box once, every line and
dungeon joins boxes that are there, no two boxes of the sketch's layout meet, and the panels are drawn where they belong.
Read from the sources: no game files."""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
failed = []


def check(ok, what):
    if not ok:
        failed.append(what)
        print("FAIL: " + what)


def main():
    menu = open(os.path.join(ROOT, "gpu", "vk", "vk_menu.cpp"), encoding="utf-8").read()
    table = menu[menu.index("constexpr WorldArea kWorldMap[] = {"):menu.index("constexpr const char* kWorldEdges")]
    rows = re.findall(r'\{"([^"]+)", "([^"]+)", ([0-9.]+)f, ([0-9.]+)f, ([01]), (?:"([^"]+)"|nullptr)\}', table)
    names = [r[0] for r in rows]
    check(len(rows) == 31 and len(set(names)) == len(names), "not 31 areas, each once: %d" % len(rows))
    for name, label, x, y, dungeon, parent in rows:
        check(0 <= float(x) <= 1 and 0 <= float(y) <= 1, "%s lies off the map" % name)
        check((dungeon == "1") == bool(parent) and (not parent or parent in names), "%s's dungeon or its area is wrong" % name)
    edges = menu[menu.index("constexpr const char* kWorldEdges[][2] = {"):]
    edges = re.findall(r'\{"([^"]+)", "([^"]+)"\}', edges[:edges.index("};")])
    check(len(edges) >= 20 and all(a in names and b in names for a, b in edges), "a line joins an area the map has not")
    joined = {a for e in edges for a in e}
    check(all(n in joined for n, _, _, _, d, _ in rows if d == "0"), "an area is joined to none")
    # (the seed's area names, as the Tracker's rows have them: each has a box)
    seed = open(os.path.join(ROOT, "tools", "rando", "rando_seed.py"), encoding="utf-8").read()
    for want in ("Kokiri Forest", "Lost Woods", "Hyrule Field", "Kakariko Village", "Gerudo's Fortress", "Inside the Deku Tree",
                 "Inside Jabu-Jabu's Belly", "Bottom of the Well", "Gerudo Training Ground", "Inside Ganon's Castle",
                 "Ganon's Castle (outside)"):
        check(want in names and want in seed, "the map has no box for %s, or the seed tool names it otherwise" % want)
    check("tracker_world_map(c, hx0, hx1, top, top + map_h);" in menu and "selr.tracker == 0 && tracker_check_count && cur_tab == TAB_TRACKER" in menu,
          "the whole game's row does not show the map")
    check("if (bar_top - 12 * s - end >= 150 * s) tracker_area_map(c, hx0, hx1, end + 10 * s, bar_top - 12 * s, selr.tracker);" in menu,
          "an area's row does not show its checks' map under its list")
    # (2026-11-26: a box of the overview says one number, the checks to get now, else those left: not both)
    world = menu[menu.index("float tracker_world_map(ui::Ctx& c,"):menu.index("/// An area's checks as marks where they are")]
    check('snprintf(line, sizeof line, n.in ? "%d now" : "%d left", n.in ? n.in : n.left);' in world and '", %d left"' not in world,
          "an area's box of the overview says two counts")
    check("top + std::max(room * 0.55f, room - 420 * s)" in menu, "the list can take the whole panel, leaving the map no room")
    body = menu[menu.index("void tracker_area_map(ui::Ctx& c,"):]
    body = body[:body.index("\n}\n")]
    check("ox + k.at[0] * scale, oy + k.at[2] * scale" in body and "&k == picked" in body, "the dots are not x across and z down, or the stepped check not ringed")
    check("rx_option_set(OOT_LINK_X, (int)lrintf(oot_link_place[0] * 100));" in open(os.path.join(ROOT, "host", "hos_main.c"), encoding="utf-8").read()
          and "if (link) {" in body and "here && !strcmp(here, tracker_name[row])" in body, "Link is not on the map of the area he is in")
    # (bug 160: Link stood at Hyrule Castle's Pot #3 and #4 and his arrow, drawn last, covered both dots: "no dot near".
    #  The arrow is drawn first and the dots over it, so a check he stands on shows on him)
    check("AddTriangleFilled(tip, l, rr," in body and "for (int pass = 0; pass < 3; pass++)" in body and
          body.index("AddTriangleFilled(tip, l, rr,") < body.index("for (int pass = 0; pass < 3; pass++)"),
          "Link's arrow is drawn over the checks' dots: a check he stands on is hidden under it")
    # (the Minimap checks row: the area's square of the world on the game's minimap, fitted to the owner's screenshots)
    check('{TAB_GAMEPLAY, "Minimap checks", &opts.minimap_checks, 0, 1, 1, tx_onoff,' in menu and "int minimap_checks = 0;" in
          open(os.path.join(ROOT, "gpu", "vk", "vk_menu.h"), encoding="utf-8").read(), "no Minimap checks row, off by default")
    mini = menu[menu.index("constexpr MiniMapArea kMiniMaps[] = {"):menu.index("constexpr MiniMapArea kMiniLake")]
    # (measured 2026-11-23: each area's u + a*x across from the right edge, v + a*z down, of the window's height)
    mini_areas = re.findall(r'\{"([^"]+)", (-?[0-9.]+)f, (-?[0-9.]+)f, ([0-9.]+)f\}', mini)
    check(len(mini_areas) >= 11 and all(a in names for a, _, _, _ in mini_areas) and
          all(-0.5 < float(u) < 0 and 0.3 < float(v) < 1 and 0.0003 < float(a) < 0.005 for _, u, v, a in mini_areas),
          "the minimaps' areas are not the field areas the map has, or a measured fit is off the corner")
    # (Hyrule Castle measured 2026-11-26. Never: Ganon's Castle's grounds, where the game shows no minimap; Gerudo's Fortress and
    #  the Sacred Forest Meadow, whose minimaps scroll with Link)
    check(not any(a in ("Ganon's Castle (outside)", "Gerudo's Fortress", "Sacred Forest Meadow") for a, _, _, _ in mini_areas),
          "an area not measured has dots (they would be in the wrong place)")
    castle = [(float(u), float(v), float(a)) for area, u, v, a in mini_areas if area == "Hyrule Castle"]
    check(len(castle) == 1 and abs(castle[0][2] - 1 / (2.245 * 242)) < 2e-6, "Hyrule Castle's minimap is not the size its capture says (Height 242)")
    # (Link at 23.7 -62.0 stood 895.9 462.1 on a 960 x 540 picture: the fit puts him within a pixel and a half of it)
    check(abs((960 + (castle[0][0] + castle[0][2] * 23.7) * 540) - 895.9) < 1.5 and abs((castle[0][1] + castle[0][2] * -62.0) * 540 - 462.1) < 1.5,
          "Hyrule Castle's fit does not put Link where his arrow was seen")
    check("at.x > c.w ||" in menu, "a check off the screen's right edge is drawn on the minimap's corner")
    draw = menu[menu.index("void draw_minimap_checks(ui::Ctx& c) {"):]
    draw = draw[:draw.index("\n}\n")]
    check("c.w + (m->u + m->a * k.at[0]) * c.h, (m->v + m->a * k.at[2]) * c.h" in draw and
          "tracker_done[i].load(std::memory_order_relaxed) == 1 || tracker_junk[i]" in draw and "else if (in_ranch(lx, lz)) m = &kMiniRanch;" in draw,
          "the dots are not the checks left on the measured minimap, or the ranch's picture not within 100 of it")
    # (the owner's run 2026-11-25: a child's pots collected kept their dots, the adult's pots at the same places)
    # (the test of a check's age is a function since 2026-11-26, the area map's too: tests/test_tracker_map_marks.py runs it)
    check("const int age = link_age.load(std::memory_order_relaxed)" in draw and "if (!tracker_of_age(k.ages, age)) continue;" in draw,
          "the minimap shows the other age's checks")
    check(menu.count("if (minimap) draw_minimap_checks(c);") == 2 and "next = now + 5000, tracker_load();" in menu,
          "the minimap's dots are not drawn on screen and on test pictures, or the seed's checks are never read with the menu shut")
    print("FAIL" if failed else "PASS: the Tracker's map")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
