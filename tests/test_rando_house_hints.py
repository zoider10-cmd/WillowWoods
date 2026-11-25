"""Skulltula House hints (rando_house_hints, asked 2026-11-23, share/todo.md): the cursed man's next-goal lines
(GatheringTokenGold's NextGoal, Npc_SkullDad Talk_28 and Talk_23 to _26) go on, after a page of their own, with what each
reward of 10 to 50 tokens gives in the seed. A made-up text file (no game files): the line kept, the list after a new
page, three lines a page, no reward split between pages, and a line changed once only. Then the wiring: the rewards
from the seed's gifts (the game's own without Quest rewards), the setting read (off by default), on the stamp's line of
settings that move no item, the in-game menu's row last, the launcher's row in its Quality of life section.

python -I -B tests/test_rando_house_hints.py
"""
import os
import re
import struct
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools", "rando"))
import rando_seed as seed  # noqa: E402

failed = False


def check(ok, what):
    global failed
    if not ok:
        failed = True
        print("FAIL: " + what)


def msbt(lines):
    """a small UTF-8 text file: LBL1 (one group a label) and TXT2, as the game's"""
    labels = list(lines)
    lbl = struct.pack("<I", len(labels))
    off = 4 + 8 * len(labels)
    names = b""
    for i, l in enumerate(labels):
        lbl += struct.pack("<II", 1, off + len(names))
        names += bytes([len(l)]) + l.encode() + struct.pack("<I", i)
    lbl += names
    txt = struct.pack("<I", len(labels))
    body = b""
    for l in labels:
        txt += struct.pack("<I", 4 + 4 * len(labels) + len(body))
        body += lines[l] + b"\0"
    txt += body
    out = b""
    for kind, sec in ((b"LBL1", lbl), (b"TXT2", txt)):
        out += kind + struct.pack("<I", len(sec)) + bytes(8) + sec + b"\xab" * (-len(sec) % 16)
    head = b"MsgStdBn" + b"\xff\xfe" + bytes(2) + bytes([0, 3]) + struct.pack("<H", 2) + bytes(2) + struct.pack("<I", 0x20 + len(out)) + bytes(10)
    return head + out


def main():
    src = open(seed.__file__, encoding="utf-8").read()
    check(all(hasattr(seed, n) for n in ("house_hint_pages", "house_hint_line", "HOUSE_HINT_LABELS")), "no Skulltula House hints")
    if failed:
        print("FAIL")
        return 1
    rewards = {10: "Obj_Heart_Piece", 20: "TBox_Rupee_Purple", 30: "Item_Wallet_Large", 40: "Item_Hookshot", 50: "Item_Token_Gold"}
    pages = seed.house_hint_pages(rewards)
    lines = [p.split("\n") for p in pages]
    check(all(len(p) <= seed.HOUSE_HINT_ROWS for p in lines), "a page has more lines than the box: %s" % lines)
    check(all(len(l) <= seed.HOUSE_HINT_WIDTH for p in lines for l in p), "a line is wider than the box: %s" % lines)
    flat = [l for p in lines for l in p]
    check(flat[0] == seed.HOUSE_HINT_HEAD and [l.split(" tokens:")[0] for l in flat[1:]] == ["10", "20", "30", "40", "50"],
          "not the head then the rewards in order: %s" % flat)
    check("20 tokens: a purple rupee" in flat and "40 tokens: the Hookshot" in flat, "the rewards are not named as the hints name them: %s" % flat)
    own = {label: b"\x0e\x03\x00\x00\x00\x03\x00\x00\x00\x00If you collect a total of " + label.encode() + b" tokens..."
           for label in seed.HOUSE_HINT_LABELS + ("Talk_27", "Talk_00")}
    text = msbt(own)
    for label in seed.HOUSE_HINT_LABELS:
        text = seed.house_hint_line(text, label, pages)
    for label in own:
        s, e = seed.msbt_text(text, label)
        got = bytes(text[s:e]).rstrip(b"\0")
        if label in seed.HOUSE_HINT_LABELS:
            want = own[label] + b"".join(seed.HOUSE_HINT_PAGE + p.encode() for p in pages)
            check(got == want, "%s is not its own line then the list on pages of their own: %r" % (label, got))
        else:
            check(got == own[label], "%s, not a next-goal line of a reward to come, was changed" % label)
    try:
        seed.house_hint_line(text, seed.HOUSE_HINT_LABELS[0], pages)
        check(False, "a line with the list already gets it again")
    except ValueError:
        pass
    check(seed.HOUSE_HINT_LABELS == ("Talk_28", "Talk_23", "Talk_24", "Talk_25", "Talk_26") and seed.HOUSE_HINT_TEXT == "EventFlowMsg/Npc_SkullDad.msbt",
          "not the cursed man's next-goal lines of 10 to 50 tokens")
    main_src = src[src.index("\ndef main():"):]
    check("house[HOUSE_TOKENS[g.key]] = gives.get(h, g.item) if h in gifts else g.item" in main_src
          and "text = house_hint_line(text, label, pages)" in main_src
          and main_src.index("house_hint_line(text, label, pages)") < main_src.index("    # ---- the size table ----"),
          "the seed does not write the list from its gifts, before the size table")
    check('"rando_house_hints": 0' in src and 'a.house_hints = ini["rando_house_hints"] != 0' in src, "not read from the options, off by default")
    check('(a.house_hints, " house hints")' in src, "it is not on the stamp's second line (moves no item)")
    header = open(os.path.join(ROOT, "gpu", "vk", "oot_rando.h"), encoding="utf-8").read()
    order = re.findall(r"^    X\(([A-Z_]+),", header, re.M)
    check("HOUSE_HINTS" in order and order.index("HOUSE_HINTS") > order.index("GERUDO_GUARDS"), "the in-game menu's row is not after the ones before it")
    launcher = open(os.path.join(ROOT, "launcher", "Launcher.cs"), encoding="utf-8").read()
    check('new object[] { "rando_house_hints", "Skulltula House hints", new[] { "Off", "On" }, new[] { 0, 1 },' in launcher, "no launcher row")
    no_item = launcher[launcher.index("NoItemKeys = new HashSet<string>"):launcher.index("static bool MovesNoItem")]
    check('"rando_house_hints"' in no_item, "the launcher does not count it as moving no item")
    qol = launcher[launcher.index('Title = "QUALITY OF LIFE"'):]
    check('"rando_house_hints"' in qol[:qol.index("} },")], "it is not in the launcher's Quality of life section")
    print("FAIL" if failed else "PASS: the cursed man lists the Skulltula House's rewards")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
