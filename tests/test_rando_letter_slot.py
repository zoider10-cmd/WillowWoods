"""Zelda's Letter in a slot of its own (tools/rando/rando_seed.py LETTER_SLOT, pouch_letter_slot): moved from the trade
slot's list to the front of the amiibo slot's, the game's bytes kept and the two lists written after them. On a small
table made here: no game files."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools", "rando"))
import rando_seed as S  # noqa: E402

failed = []


def check(ok, what):
    if not ok:
        failed.append(what)
        print("FAIL: " + what)


def actor(name, child=True):
    d = {"ActorShort": ("string", name)}
    if child:
        d["IsUsableChild"] = (208, (1).to_bytes(4, "little"))
    return ("dict", d)


def table(trade, amiibo):
    return ("dict", {"ItemArray": ("array", [("dict", {"Actor": ("array", [actor(n) for n in trade]), "BtnName": ("string", "Pa_ItemIcon_23")}),
                                             ("dict", {"Actor": ("array", [actor(n) for n in amiibo]), "BtnName": ("string", "Pa_ItemIcon_24")})])})


def names(data, i):
    tree, _ = S.byml_parse(data)
    return [a[1]["ActorShort"][1] for a in tree[1]["ItemArray"][1][i][1]["Actor"][1]]


def main():
    try:
        data = S.byml_build(table(["Item_PocketEgg", "Item_ZeldaLetter", "Item_AlarmCucco", "Item_WeirdEgg"], ["Pouch_Amiibo"]), 7)
    except Exception as e:   # (the builder's version argument and kinds as the seed tool has them)
        print("FAIL: the test's table could not be made: %r" % e)
        return 1
    slots = ("ItemArray", 0, 1, "Item_ZeldaLetter")
    out = S.pouch_letter_slot(data, slots)
    changed = [k for k in range(len(data)) if out[k] != data[k]]
    check(len(changed) <= 8, "the game's bytes are not kept as they were, but the two slots' places of their lists (%d bytes changed)" % len(changed))
    check(names(out, 0) == ["Item_PocketEgg", "Item_AlarmCucco", "Item_WeirdEgg"], "the letter is still in the trade slot, or the others moved: %r" % names(out, 0))
    check(names(out, 1) == ["Item_ZeldaLetter", "Pouch_Amiibo"], "the letter is not first in the amiibo slot: %r" % names(out, 1))
    try:
        S.pouch_letter_slot(out, slots)
        check(False, "moving the letter twice was not refused")
    except ValueError:
        pass
    check(S.LETTER_SLOT == ("ItemArray", 22, 23, "Item_ZeldaLetter"), "the slots are not the trade slot (22) and the amiibo slot (23)")
    script = open(os.path.join(HERE, "..", "tools", "rando", "rando_seed.py"), encoding="utf-8").read()
    check("gift_files[AGELESS_TABLE] = pouch_letter_slot(was)" in script, "the seed does not write the table with the letter moved")
    print("FAIL" if failed else "PASS: Zelda's Letter in a slot of its own")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
