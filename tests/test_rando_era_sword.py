"""Bug 68: back to a child, an empty sword slot is not given the Kokiri Sword Link never got.

The game's swap of the two ages' gear (Event/EventFlow/ReplaceEquipmentForEraChange) sets the child's slot,
PlayerStatus.AnotherEraEquipWeapon, to Weapon_Sword_Kokiri whenever it is empty on the way back, with no question of
the pouch. tools/rando/rando_seed.py era_sword_fix passes that one step over (lead_past). Checked by source; the
game's file itself is read by the seed tool, which stops with nothing written if the step is not there once.

python -I -B tests/test_rando_era_sword.py
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "rando"))
import rando_seed as seed  # noqa: E402


def main():
    src = (ROOT / "tools" / "rando" / "rando_seed.py").read_text(encoding="utf-8")
    ok = (seed.ERA_FLOW == "Event/EventFlow/ReplaceEquipmentForEraChange.bfevfl.zs" and seed.FIXES_VERSION >= 41 and
          's.get("name") == "PlayerStatus.AnotherEraEquipWeapon" and s.get("value") == "Weapon_Sword_Kokiri"' in src and
          "return lead_past(data, steps, firsts, set(kokiri) | (set(sword) if master else set()), {})" in src and
          "gift_files[ERA_FLOW] = era_sword_fix(was, a.master_sword)" in src and
          's["value"] = param(u64(e + 0x10), "Value")' in src)
    if not ok:
        print("FAIL: the step that gives an empty child's slot the Kokiri Sword is not passed over")
        sys.exit(1)
    # (Shuffle the Master Sword, the owner's test 2026-11-21: the same flow's step 5 sets an empty adult's slot to the
    #  Master Sword on the way to an adult, so adult Link held one he never got, and young Link too with Swords for
    #  either age. With the sword shuffled that step is passed over as well; the seed's stamp says so, "master sword 2")
    ok = ('s.get("name") == "PlayerStatus.AnotherEraEquipWeapon" and s.get("value") == "Weapon_Sword_Master"' in src and
          "def era_sword_fix(data, master=False):" in src and "era_sword_fix(was, a.master_sword)" in src and
          '(" master sword 2" if a.master_sword else "")' in src)
    if not ok:
        print("FAIL: with Shuffle the Master Sword, an empty adult's slot is still given the Master Sword on the way to an adult")
        sys.exit(1)
    print("PASS: back to a child, an empty sword slot stays empty; with the Master Sword shuffled, an adult's too")


if __name__ == "__main__":
    main()
