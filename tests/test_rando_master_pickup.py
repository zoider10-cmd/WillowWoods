"""The Master Sword as a pick-up (tools/rando/rando_seed.py MASTER_PICKUP, asked 2026-11-25): no game data.

The game has the sword only as the weapon, so a pot or a Gold Skulltula of the seed holding it could not drop it
("Weapon_Sword_Master is not made from Item_EventObject_Base"). It gets an item of its own made from the Biggoron's
Sword's. Checked on a small pack and lists made here:
- master_item_pack: every file under the new name, the actor named and equipped as the sword (both ages), its model
  file its own (the Biggoron's colour animations gone), nothing of the Biggoron's left;
- master_rows: the new row is the Biggoron item's with the sword's names and model size, the other rows as they were;
- its animations stay the Biggoron's (the game has none of the sword's: an item naming them is never made);
- a pot's and a Skulltula's drop of the sword name the new item (POT_AS), and the game's side adds the sword for it.

    python -I -B tests/test_rando_master_pickup.py
"""
import collections
import importlib.util
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("rando_seed", ROOT / "tools" / "rando" / "rando_seed.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)
D = collections.OrderedDict


def check(ok, why):
    if not ok:
        print("FAIL: %s" % why)
        sys.exit(1)


def text(v):
    return ("string", v)


def biggoron_pack():
    item, weapon = S.MASTER_PICKUP_FROM, S.MASTER_PICKUP_WEAPON_FROM
    table = "GameParameter/GameParameterTable/%s.engine__actor__GameParameterTable.bgyml" % item
    equip = "GameParameter/PlayerEquipmentActor/%s.game__actor__PlayerEquipmentActor.bgyml" % item
    anim = "Component/AnimationParam/%s.engine__component__AnimationParam.bgyml" % item
    actor = ("dict", D((("$parent", text(S.ACTOR_REF % S.CHEST_BASE)), ("Components", ("dict", D((
        ("ActorNameRef", text("?ActorSystem/ActorName/%s.engine__actor__ActorName.bgyml" % weapon)),
        ("AnimationRef", text("?" + anim)),
        ("GameParameterTableRef", text("?" + table)),
        ("ModelInfoRef", text("?" + S.MODEL_INFO_FILE % weapon)),
        ("PouchContentRef", text("?Component/PouchContentParam/WeaponGetTypeMedium.game__component__PouchContentParam.bgyml")))))))))
    model = ("dict", D((("FmdbName", text(weapon)), ("ModelProjectName", text(weapon)),
                        ("ModelVariationAnims", ("array", [("dict", D((("Fmab", text("Work/Model/Weapon/%s_Color.fmab" % weapon)),)))])))))
    files = {
        S.ACTOR_FILE % item: S.byml_build(actor, 7),
        S.ACTOR_FILE % S.CHEST_BASE: S.byml_build(("dict", D((("Components", ("dict", D())),))), 7),
        S.MODEL_INFO_FILE % weapon: S.byml_build(model, 7),
        table: S.byml_build(("dict", D((("Components", ("dict", D((("PlayerEquipmentActor", text("?" + equip)),)))),))), 7),
        equip: S.byml_build(("dict", D((("Adult", text(S.ACTOR_REF % weapon)), ("Child", text(S.ACTOR_REF % weapon))))), 7),
        anim: S.byml_build(("dict", D((("AnimationResources", ("array", [
            ("dict", D((("ModelProjectName", text("Item_Common_Animation")),))),
            ("dict", D((("ModelProjectName", text(weapon + "_Animation")),)))])),))), 7),
        "Component/PouchContentParam/WeaponGetTypeMedium.game__component__PouchContentParam.bgyml":
            S.byml_build(("dict", D((("GetType", (0xD3, struct.pack("<I", 1))),))), 7),
    }
    return S.sarc_write(files)


def strings(node):
    kind, value = node
    if kind == "string":
        yield value
    elif kind == "dict":
        for k, v in value.items():
            yield from strings(v)
    elif kind == "array":
        for v in value:
            yield from strings(v)


def main():
    master = "Weapon_Sword_Master"
    files = S.sarc_read(S.master_item_pack(biggoron_pack()))
    check(not any("Biggoron" in name for name in files), "a file keeps the Biggoron's name: %s" % sorted(files))
    every = [s for name, data in files.items() for s in strings(S.byml_parse(data)[0])]
    # (but its animations: the game has no Weapon_Sword_Master_Animation, and an item naming it is never made. Seen
    #  2026-11-25: nothing where its Skulltula died, until the name was the Biggoron's again)
    check([s for s in every if "Biggoron" in s] == [S.MASTER_PICKUP_ANIMATION],
          "the item names the Biggoron's other than by its animations, or not those: %s" % [s for s in every if "Biggoron" in s])
    check(not any(s.endswith("_Animation") and "Master" in s for s in every), "the item names animations of the sword's, which the game has none of")
    actor, _ = S.byml_parse(files[S.ACTOR_FILE % S.MASTER_PICKUP])
    comps = actor[1]["Components"][1]
    check(comps["ActorNameRef"][1] == "?ActorSystem/ActorName/%s.engine__actor__ActorName.bgyml" % master,
          "the item's name for the pouch is not the sword's (its add would not be the sword)")
    check(comps["ModelInfoRef"][1] == "?" + S.MODEL_INFO_FILE % S.MASTER_PICKUP and S.MODEL_INFO_FILE % S.MASTER_PICKUP in files
          and S.MODEL_INFO_FILE % master not in files, "the model file is not the item's own (bug 78: the cosmetics' look)")
    model, _ = S.byml_parse(files[S.MODEL_INFO_FILE % S.MASTER_PICKUP])
    check(model[1]["FmdbName"][1] == master and "ModelVariationAnims" not in model[1], "the model is not the sword's, or keeps the Biggoron's colours")
    equip = next(data for name, data in files.items() if "/PlayerEquipmentActor/" in name)
    equip, _ = S.byml_parse(equip)
    check(equip[1]["Adult"][1] == equip[1]["Child"][1] == S.ACTOR_REF % master, "the item does not equip the sword for both ages")
    check(actor[1]["$parent"][1] == S.ACTOR_REF % S.CHEST_BASE, "the item is not a chest's (pickup_pack needs one)")
    check(S.MASTER_PICKUP in S.PICKUP_OWN_POUCH, "the item's pouch file is shared with the Biggoron's item: its pick-up would change that one's")

    def row(rid, **kw):
        return ("dict", D([("__RowId", text(rid))] + [(k, text(v) if isinstance(v, str) else v) for k, v in kw.items()]))
    aabb = (0xD2, struct.pack("<f", 7.0))
    table = S.byml_build(("array", [
        row(S.MASTER_PICKUP_FROM, ActorName=S.MASTER_PICKUP_WEAPON_FROM, FmdbName=S.MASTER_PICKUP_WEAPON_FROM,
            ModelVariationFmabName=S.MASTER_PICKUP_WEAPON_FROM + "_Color", CalcRadius=(0xD2, struct.pack("<f", 1.0))),
        row(master, ActorName=master, CalcRadius=aabb), row("Other", ActorName="Other")]), 7)
    rows, _ = S.byml_parse(S.master_rows(table, "ActorInfo"))
    by = {r[1]["__RowId"][1]: r[1] for r in rows[1]}
    check(set(by) == {S.MASTER_PICKUP_FROM, master, "Other", S.MASTER_PICKUP}, "the rows are not the old ones and the item's: %s" % sorted(by))
    new = by[S.MASTER_PICKUP]
    check(new["ActorName"][1] == master and new["FmdbName"][1] == master and "ModelVariationFmabName" not in new
          and new["CalcRadius"] == aabb, "the item's row is not the Biggoron's with the sword's names and size")
    check(by[S.MASTER_PICKUP_FROM]["ActorName"][1] == S.MASTER_PICKUP_WEAPON_FROM, "the Biggoron item's own row changed")
    check([r[1]["__RowId"][1] for r in rows[1]] == sorted(by), "the rows are not sorted")

    check(S.POT_AS.get(master) == S.MASTER_PICKUP, "the sword has no pick-up of its own (POT_AS)")
    src = (ROOT / "tools" / "rando" / "rando_seed.py").read_text(encoding="utf-8")
    check("drops.setdefault(h, POT_AS.get(item, item))" in src, "a Gold Skulltula's sword is dropped as the weapon (no pick-up)")
    check('(s[4] == "skulltula" and placement < MASTER_SKULLS_FROM or KEYS_ENDING_FROM' in src, "a seed placed before 34 may put the sword on a Gold Skulltula")
    check("drop = POT_AS.get(pot_drops[h], pot_drops[h])" in src, "a pot's sword is dropped as the weapon (no pick-up)")
    check("pickups = sorted({POT_AS.get(i, i) for i in pickups})" in src, "the sword's pick-up pack is not made")
    host = (ROOT / "host" / "hos_main.c").read_text(encoding="utf-8")
    check('{"Item_Sword_Master", "Weapon_Sword_Master"}' in host, "the game's side adds the item, not the sword (the check is not found)")
    check(S.MASTER_SKULLS_FROM > S.MASTER_POTS_FROM and S.PLACEMENT >= S.MASTER_SKULLS_FROM, "the placements are not in order")
    print("PASS: the Master Sword's pick-up is its own item, named, equipped and shown as the sword")


if __name__ == "__main__":
    main()
