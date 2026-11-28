#!/usr/bin/env python3
"""Either age's tunics: young Link wears a tunic and keeps his own clothes (bug 107; the owner, 2026-11-27).

The adult's tunic on a child was the adult's body's model on bones he has not: red spikes and a blue lump over his head
and body (seen without a window with the Zora Tunic worn as the age changed), though the effect was there. The seed
makes an actor of each tunic for him (tools/rando/rando_seed.py TUNIC_CHILD: the adult's as its parent, its ArmorParam
hiding every material of the tunic's own model in place of the body's groups), and the game's side makes the name of the
tunic worn the age's own as it is read (host/hos_main.c hos_oot_equip_name, at f_80a9a860's way out: nx2/oot_patches.py
patch_equip_name). Seen without a window, 2026-11-27, a child with his own clothes: on Lake Hylia's floor with the Zora
Tunic, hearts whole after a minute (drowned in under one with the game's empty model in the tunic's place); in the Fire
Temple with the Goron Tunic, hearts whole after a minute, and a game over in under one with no tunic.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(ok, what):
    if not ok:
        raise SystemExit("FAIL: " + what)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    sys.dont_write_bytecode = True
    S = load("rando_seed", ROOT / "tools" / "rando" / "rando_seed.py")
    sys.path.insert(0, str(ROOT / "nx2"))   # (oot_patches imports its neighbours: python -I leaves the folder off the path)
    P = load("oot_patches", ROOT / "nx2" / "oot_patches.py")
    od = __import__("collections").OrderedDict
    text = lambda s: ("string", s)
    adult, child = "Armor_Adult_Zora", "Armor_Child_Zora"
    armor_was = "Component/ArmorParam/Armor_Zora.game__component__ArmorParam.bgyml"
    armor = ("dict", od((("$parent", text("Work/Component/ArmorParam/Default.game__component__ArmorParam.gyml")),
                         ("ArmorEffect", ("array", [text("a"), text("b")])),
                         ("HiddenMaterialGroupList", ("array", [("dict", od((("GroupName", text("G_Zora_Glove")),
                                                                              ("MaterialNameList", ("array", [text("Mt_Glove")])))))])),
                         ("HideMaterialGroupNameList", ("array", [text("G_Body"), text("G_Vest")])))))
    actor = ("dict", od((("Components", ("dict", od((("ArmorRef", text("?" + armor_was)), ("ModelInfoRef", text("?Component/ModelInfo/Armor_Zora.x.bgyml")))))),)))
    pack = S.sarc_write({S.ACTOR_FILE % adult: S.byml_build(actor, 7), armor_was: S.byml_build(armor, 7), "Other/file.bin": b"1234"})
    # (the materials of a tunic's model: the names that are not a texture's)
    model = b"..Mt_Vest\0Mt_Vest_Armor_Adult_Zora_Alb\0Mt_Inner\0Mt_Inner_Player_Adult_Nrm\0Mt_Parts\0Mt_Hat_Player_Child_Alb\0"
    mats = S.tunic_materials(model)
    check(mats == ["Mt_Inner", "Mt_Parts", "Mt_Vest"], "a tunic's materials are not its model's own names: %r" % mats)
    try:
        S.tunic_materials(b"no material here")
        check(False, "a model with no material makes an actor that hides nothing")
    except ValueError:
        pass
    new, parts = S.tunic_child_pack(adult, child, pack, mats)
    files = S.sarc_read(new)
    check(sorted(parts) == sorted([S.ACTOR_FILE % child, S.ARMOR_FILE % child]) and all(p in files for p in parts) and
          files[S.ACTOR_FILE % adult] == S.sarc_read(pack)[S.ACTOR_FILE % adult] and files["Other/file.bin"] == b"1234",
          "young Link's pack is not the adult's with his actor's and his armour's files added")
    his = S.byml_parse(files[S.ACTOR_FILE % child])[0][1]
    check(his["$parent"][1].endswith("Actor/%s.engine__actor__ActorParam.gyml" % adult) and
          {k: v[1] for k, v in his["Components"][1].items()} == {"ArmorRef": "?" + S.ARMOR_FILE % child},
          "his actor is not the adult's with only the armour's file his own (the tunic's model must stay: without it the effect is lost)")
    own = S.byml_parse(files[S.ARMOR_FILE % child])[0][1]
    check([v[1] for v in own["HideMaterialGroupNameList"][1]] == [S.TUNIC_GROUP], "his armour hides his own body's groups, or not the tunic's")
    groups = {g[1]["GroupName"][1]: [m[1] for m in g[1]["MaterialNameList"][1]] for g in own["HiddenMaterialGroupList"][1]}
    check(groups == {"G_Zora_Glove": ["Mt_Glove"], S.TUNIC_GROUP: mats} and [v[1] for v in own["ArmorEffect"][1]] == ["a", "b"] and "$parent" in own,
          "the tunic's materials are not a group of their own beside the game's, or its effect is not kept: %r" % groups)
    for bad in (S.sarc_write({"Other/file.bin": b"1"}),
                S.sarc_write({S.ACTOR_FILE % adult: S.byml_build(actor, 7)}),
                S.sarc_write({S.ACTOR_FILE % adult: S.byml_build(actor, 7), armor_was: S.byml_build(("dict", od((("ArmorEffect", ("array", [])),))), 7)})):
        try:
            S.tunic_child_pack(adult, child, bad, mats)
            check(False, "a pack that is not the tunic's makes an actor")
        except ValueError:
            pass
    check(list(S.TUNIC_CHILD.items()) == [("Armor_Adult_Goron", "Armor_Child_Goron"), ("Armor_Adult_Zora", "Armor_Child_Zora")] and
          all(len(a) == len(c) and a[:6] == c[:6] and a[11:] == c[11:] for a, c in S.TUNIC_CHILD.items()),
          "his actors' names are not the adult's with Child for Adult (the game's side writes five letters in place)")
    script = (ROOT / "tools" / "rando" / "rando_seed.py").read_text(encoding="utf-8")
    check("if a.ageless & 4:   # (the tunics: young Link's own actor of each, his clothes kept, TUNIC_CHILD)" in script and
          "tunic_materials(model))" in script and 'shop_packs["Pack/Actor/%s.pack" % child] = len(new)' in script and
          "table = custom_rows(table, kind, child, adult)" in script and "AGELESS_TUNICS = (\"Armor_Adult_Goron\", \"Armor_Adult_Zora\")" in script,
          "the seed does not make his actors with Either age's tunics, or not their rows of the three lists of actors")

    # ---- the game's side: the name of the tunic worn, the age's own as it is read ----
    host = (ROOT / "host" / "hos_main.c").read_text(encoding="utf-8")
    hook = host[host.index("void hos_oot_equip_name(Ctx *c, unsigned long long out, unsigned long long hash) {"):]
    hook = hook[:hook.index("\n}\n") + 3]
    check("#define OOT_EQUIP_ARMOR 0xb5f9aac7u" in host and S.murmur3(b"EquipArmor") == 0xb5f9aac7 and "if ((uint32_t)hash != OOT_EQUIP_ARMOR) return;" in hook,
          "the hook is not for the tunic's name alone")
    check('const int his_own = child && made && hos_rando_ageless_tunics();' in hook and "if (his_own == childs) return;" in hook and
          'const char *word = his_own ? "Child" : "Adult";' in hook and "recomp_store8(c, text + 6 + (uint64_t)i, (uint8_t)word[i]);" in hook and
          '"mods/rando-seed/romfs/Pack/Actor/Armor_Child_Zora.pack.zs"' in hook and "if (!oot_gamedata_bool(c, 0xcea220d3u, &child)) return;" in hook,
          "the name does not follow Link's age, or a child's name is left where the setting is off or the seed has not his actors")
    sample = ('#include "a64.h"\nvoid f_80a9a860(Ctx *__restrict A64_NOESC c) {\n    c->x[0] = 1;\nL_80a9a8f4:;\n    return;\n}\n')
    got = P.patch_equip_name(sample)
    check(got and got[1] == 1 and "L_80a9a8f4:;\n    hos_oot_equip_name(c, c->x[19], c->x[20]);" in got[0] and
          "extern void hos_oot_equip_name(Ctx *c, unsigned long long out, unsigned long long hash);" in got[0],
          "the reader's way out is not hooked")
    check(P.patch_equip_name(got[0]) == (got[0], 1) and P.patch_equip_name('#include "a64.h"\nvoid f_1(Ctx *c) {\n}\n') is None,
          "the hook is put twice, or in a file that has not the reader")
    patches = (ROOT / "nx2" / "oot_patches.py").read_text(encoding="utf-8")
    check('if protect_hearts and total["equip name"] != 1:' in patches, "a build that did not hook the reader does not say so")
    print("PASS: young Link's tunics: his own actor of each, and the name of the tunic worn by his age")


if __name__ == "__main__":
    main()
