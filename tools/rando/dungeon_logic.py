"""What each dungeon check needs inside its dungeon, worked out from the other randomizers' logic of the remake
(tools/rando/ootrr/README.md: OotrR's engine and world, MIT; ootrr's 0.8.2 dungeon files and remake pins, GPL-3.0;
copied 2026-11-21 with the owner's go-ahead).

    py -I tools/rando/dungeon_logic.py [--dungeon "Forest Temple"] [--write tools/rando/dungeon_rules.json]

The world: OotrR's (the Archipelago OoT world with its remake layer), its dungeons replaced by ootrr 0.8.2's (rewritten
for the remake's layout), each replaced region keeping the events the overworld waits on.

For every location of a dungeon: the dungeon's way in is given (to the ages that can go in), every item is held but
the ones tried, the keys and silver rupees lie where the game has them, and then:
  - an item is NEEDED when the location can't be reached without it (one sweep for each item, all locations at once);
  - the needed items are checked to be ENOUGH (with them alone, the location is reached); where they aren't (a choice
    of ways), items are taken away one at a time while it stays reachable, in several orders, which leaves each way
    that is enough: the rule is any of them.
So a rule asks for enough, never too little. A tier of a family is an item of its own: ("Progressive Hookshot", 2) is
the Longshot.

The written table ({"rules": {location: [way, ...]}, "pins": {location: {...}}}) is read by the seed tool
(rando_seed.py DUNGEON_RULES), which turns each way into its own items and ties each location to the remake's actors by
ootrr's pins.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OOTRR = os.path.join(HERE, "ootrr")
THEIRS = os.path.join(OOTRR, "ootrando")
sys.path.insert(0, OOTRR)
from oot_rando.logic.world import World  # noqa: E402
from oot_rando.logic.rules import Logic  # noqa: E402

# The dungeons, the region entered from outside, and who can go in (the remake: the Forest, Fire, Water and Shadow
# Temples, the Ice Cavern, the Training Ground and Ganon's Castle are an adult's; Jabu-Jabu, the Deku Tree and the well
# a child's).
DUNGEONS = {
    "Deku Tree": ("Deku Tree Lobby", ("child",)),
    "Dodongos Cavern": ("Dodongos Cavern Beginning", ("child", "adult")),
    "Jabu Jabus Belly": ("Jabu Jabus Belly Beginning", ("child",)),
    "Bottom of the Well": ("Bottom of the Well", ("child",)),
    "Forest Temple": ("Forest Temple Lobby", ("adult",)),
    "Fire Temple": ("Fire Temple Lower", ("adult",)),
    "Water Temple": ("Water Temple Lobby", ("adult",)),
    "Shadow Temple": ("Shadow Temple Entryway", ("adult",)),
    "Spirit Temple": ("Spirit Temple Lobby", ("child", "adult")),
    "Ice Cavern": ("Ice Cavern Beginning", ("adult",)),
    "Gerudo Training Ground": ("Gerudo Training Ground Lobby", ("adult",)),
    "Ganons Castle": ("Ganons Castle Lobby", ("adult",)),
}
FILES = ["Deku Tree", "Dodongos Cavern", "Jabu Jabus Belly", "Bottom of the Well", "Forest Temple", "Fire Temple",
         "Water Temple", "Shadow Temple", "Spirit Temple", "Ice Cavern", "Gerudo Training Ground", "Ganons Castle", "Bosses"]
# What is tried: every item a dungeon could ask for, as (name, tiers). The rest is always held.
TRIED = [("Kokiri Sword", 1), ("Master Sword", 1), ("Slingshot", 1), ("Boomerang", 1), ("Bomb Bag", 1), ("Bombchus", 1),
         ("Lens of Truth", 1), ("Bow", 1), ("Megaton Hammer", 1), ("Iron Boots", 1), ("Hover Boots", 1),
         ("Progressive Hookshot", 2), ("Progressive Strength Upgrade", 3), ("Progressive Scale", 2), ("Mirror Shield", 1),
         ("Goron Tunic", 1), ("Zora Tunic", 1), ("Magic Meter", 1), ("Dins Fire", 1), ("Farores Wind", 1), ("Nayrus Love", 1),
         ("Fire Arrows", 1), ("Ice Arrows", 1), ("Light Arrows", 1), ("Ocarina", 1), ("Bottle", 1), ("Stone of Agony", 1),
         ("Gerudo Membership Card", 1), ("Deku Shield", 1), ("Hylian Shield", 1), ("Biggoron Sword", 1),
         ("Zeldas Lullaby", 1), ("Eponas Song", 1), ("Sarias Song", 1), ("Suns Song", 1), ("Song of Time", 1),
         ("Song of Storms", 1), ("Minuet of Forest", 1), ("Bolero of Fire", 1), ("Serenade of Water", 1),
         ("Requiem of Spirit", 1), ("Nocturne of Shadow", 1), ("Prelude of Light", 1)]
NEVER = ("Small Key", "Boss Key", "Silver Rupee", "Triforce", "Heart Container", "Piece of Heart")
SETTINGS = {"open_forest": "open", "open_door_of_time": True, "open_kakariko": "open"}
WAYS_MOST = 10
# The dungeons that both ages enter by one door, worked out for each age alone and for both (AGE_MODES): the Spirit
# Temple, whose child's and adult's sides need different things and different ways in. Its door from the Colossus is
# closed in the logic here (CLOSED_DOORS), so that an age not given the way in can't walk round to it.
AGE_SPLIT = ("Spirit Temple",)
AGE_MODES = {"child": ("child",), "adult": ("adult",), "both": ("child", "adult")}
CLOSED_DOORS = (("Desert Colossus", "Spirit Temple Lobby"),)


def load_commented(path):
    """ootrr's JSON: # comments to the line's end outside strings, strings over several lines, trailing commas"""
    text = open(path, encoding="utf-8").read()
    out, i, n, in_str = [], 0, len(text), False
    while i < n:
        ch = text[i]
        if in_str:
            if ch == "\\":
                out.append(text[i:i + 2])
                i += 2
                continue
            if ch == '"':
                in_str = False
            out.append(" " if ch in "\r\n\t" else ch)
        elif ch == '"':
            in_str = True
            out.append(ch)
        elif ch == "#":
            while i < n and text[i] != "\n":
                i += 1
            continue
        else:
            out.append(ch)
        i += 1
    return json.loads(re.sub(r",(\s*[}\]])", r"\1", "".join(out)))


KEY_ITEMS = {"fire": "Small_Key_Fire_Temple", "water": "Small_Key_Water_Temple", "spirit": "Small_Key_Spirit_Temple"}


def keys_plain(text):
    """ootrr's fire_keys(n) and the like, with the remake's vanilla key layout written out: n - 1 keys when n > 1"""
    return re.sub(r"\b(fire|water|spirit)_keys\((\d+)\)",
                  lambda m: "(%s, %d)" % (KEY_ITEMS[m.group(1)], int(m.group(2)) - 1 if int(m.group(2)) > 1 else int(m.group(2))), text)


def world():
    """OotrR's world with ootrr 0.8.2's dungeons, their locations, items and helpers"""
    data = World()
    theirs = {name: load_commented(os.path.join(THEIRS, "World", name + ".json")) for name in FILES}
    for regions in theirs.values():
        for r in regions:
            for part in ("locations", "exits", "events"):
                if part in r:
                    r[part] = {k: keys_plain(v) for k, v in r[part].items()}
    by_name = {r["region_name"]: i for i, r in enumerate(data.regions)}
    for regions in theirs.values():
        for r in regions:
            if r["region_name"] in by_name:
                old = data.regions[by_name[r["region_name"]]]
                events = dict(old.get("events", {}))
                events.update(r.get("events", {}))
                if events:
                    r = dict(r, events=events)
                data.regions[by_name[r["region_name"]]] = r
            else:
                data.regions.append(r)
    known = {r["region_name"] for r in data.regions}
    for name, exits in (("Desert Colossus Hands", {"Desert Colossus": "True"}), ("Farores Wind Warp", {})):
        if name not in known:   # (places their dungeons lead out to that the overworld here names otherwise)
            data.regions.append({"region_name": name, "exits": exits})
    pins = json.load(open(os.path.join(THEIRS, "locations.json"), encoding="utf-8"))
    vanilla = json.load(open(os.path.join(THEIRS, "vanilla.json"), encoding="utf-8"))["locations"]
    for entry in pins["locations"] + pins["unmatched_oot"]:
        if entry["name"] not in data.location_table:
            data.location_table[entry["name"]] = {"type": entry.get("kind", "Item"), "scene": None, "vanilla": entry.get("vanilla"),
                                                  "categories": [entry.get("area", "")]}
    for regions in theirs.values():
        for r in regions:
            for name in r.get("locations", {}):
                if name not in data.location_table:
                    data.location_table[name] = {"type": "Item", "scene": None, "vanilla": vanilla.get(name),
                                                 "categories": [r.get("dungeon") or ""]}
    for item in set(vanilla.values()) | {e.get("vanilla") for e in pins["locations"] + pins["unmatched_oot"]}:
        if item and item not in data.item_table:
            data.item_table[item] = {"type": "Item", "progression": any(w in item for w in ("Silver Rupee", "Key"))}
    helpers = load_commented(os.path.join(THEIRS, "LogicHelpers.json"))
    shims = load_commented(os.path.join(THEIRS, "shims.json")).get("helpers", {})
    ours = {k.split("(")[0] for k in data.helpers}
    pool = {k: v for k, v in list(helpers.items()) + list(shims.items())
            if isinstance(v, str) and k.split("(")[0] not in ours and k.split("(")[0] not in Logic.SPECIAL_NAMES}
    by_short = {k.split("(")[0]: k for k in pool}
    todo = [rule for regions in theirs.values() for r in regions for part in ("locations", "exits", "events")
            for rule in r.get(part, {}).values()]
    wanted = set()
    while todo:   # (only the helpers their dungeons use, and the ones those use)
        for word in set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", todo.pop())):
            if word in by_short and word not in wanted:
                wanted.add(word)
                todo.append(pool[by_short[word]])
    for word in wanted:
        data.helpers[by_short[word]] = pool[by_short[word]]
    settings = dict(SETTINGS)
    for k, v in load_commented(os.path.join(THEIRS, "settings.json")).items():
        if not isinstance(v, (dict, list)):
            settings.setdefault(k, v)
    return data, settings, pins


def tiers():
    """every tried tier, as (item, level)"""
    return [(name, k) for name, top in TRIED for k in range(1, top + 1)]


class Calc:
    def __init__(self):
        self.data, settings, self.pins = world()
        # (the Spirit Temple's door from the Colossus closed: its way in is given to the ages asked for, AGE_SPLIT)
        self.logic = Logic(self.data, settings, extra_exit_requirements={DOOR: ["Never Held"] for DOOR in CLOSED_DOORS})
        self.ages_now = None
        self.fixed = {loc: self.data.vanilla_item(loc) for loc in self.logic.location_names()
                      if self.data.vanilla_item(loc) and any(w in self.data.vanilla_item(loc) for w in ("Key", "Silver Rupee"))}
        self.locations = {}
        for loc in self.logic.location_names():
            areas = {a.replace("'", "") for a in self.data.location_areas(loc)}
            for dungeon in DUNGEONS:
                if dungeon in areas:
                    self.locations.setdefault(dungeon, set()).add(loc)
        tried = {name for name, _ in TRIED}
        self.always = {item: 9 for item in self.data.item_table if item not in tried and not any(item.startswith(w) for w in NEVER)}
        self.always["Time Travel"] = 1

    def reached(self, dungeon, held):
        """the dungeon's locations reached with held ({item: level}) and its way in"""
        lobby, ages = DUNGEONS[dungeon]
        ages = self.ages_now or ages
        counts = dict(self.always)
        counts.update({k: v for k, v in held.items() if v})
        state = self.logic.new_state(counts)
        for age in ("child", "adult"):
            state.reached[age].add("Root")
        for age in ages:
            state.reached[age].add(lobby)
        state, _, _ = self.logic.sweep(self.fixed, state)
        return {loc for loc in self.locations.get(dungeon, ()) if self.logic.accessible(state, loc)}

    def ways(self, dungeon, loc, full):
        """the ways that are enough for loc: items taken away one at a time while it stays reachable, in a few orders"""
        found = []
        order = [name for name, _ in TRIED]
        for start in range(0, len(order), max(1, len(order) // WAYS_MOST)):
            held = dict(full)
            for name in order[start:] + order[:start]:
                while held.get(name, 0) > 0:   # (each item down as far as it goes, a tier at a time)
                    trial = dict(held, **{name: held[name] - 1})
                    if loc not in self.reached(dungeon, trial):
                        break
                    held = trial
            way = {k: v for k, v in held.items() if v}
            if not any(all(w.get(k, 0) >= v for k, v in way.items()) and w != way for w in found):
                found = [w for w in found if not all(w.get(k, 0) >= v for k, v in way.items())] + [way]
        return found

    def rules(self, dungeon):
        """{location: [way, ...]} for the dungeon's locations ([]: not reached at all)"""
        full = {name: top for name, top in TRIED}
        everything = self.reached(dungeon, full)
        needed = {loc: {} for loc in everything}
        for name, level in tiers():
            for loc in everything - self.reached(dungeon, dict(full, **{name: level - 1})):
                needed[loc][name] = max(level, needed[loc].get(name, 0))
        out = {loc: [] for loc in self.locations.get(dungeon, set()) - everything}
        by_set = {}
        for loc, need in needed.items():
            by_set.setdefault(tuple(sorted(need.items())), []).append(loc)
        for key, locs in by_set.items():
            ok = self.reached(dungeon, dict(key))
            for loc in locs:
                out[loc] = [dict(key)] if loc in ok else self.ways(dungeon, loc, full)
        return out


def show(way):
    return ", ".join("%s%s" % (k, ":%d" % v if v > 1 else "") for k, v in sorted(way.items())) or "-"


def both(a, b, most=12):
    """ways that meet both rules (each a list of ways): every pair joined, the bigger of each tier, those over another
    dropped; at most `most`, the smallest (enough either way: each is one of a's and one of b's together)"""
    joined = []
    for x in a:
        for y in b:
            way = dict(x)
            for k, v in y.items():
                way[k] = max(v, way.get(k, 0))
            joined.append(way)
    kept = [w for w in joined if not any(o != w and all(w.get(k, 0) >= v for k, v in o.items()) for o in joined)]
    unique = []
    for w in sorted(kept, key=lambda w: (sum(w.values()), sorted(w.items()))):
        if w not in unique:
            unique.append(w)
    return unique[:most]


def by_actor(rules, pins, ages=None):
    """{a remake actor's hash (decimal, as the pins have it): {"names": [N64 locations], "conf": ..., "ways": [...]}}: a
    pinned actor takes its location's ways; one pinned only as one of a pool of equal items, or left unmatched with
    candidates, takes the ways that meet every candidate's (it may be any of them)"""
    flat = {loc: ways for locs in rules.values() for loc, ways in locs.items()}
    by_age = {}   # (location: {mode: ways}, for AGE_SPLIT's dungeons)
    for modes in (ages or {}).values():
        for mode, locs in modes.items():
            for loc, ways in locs.items():
                by_age.setdefault(loc, {})[mode] = ways
    pools = {}
    for e in pins["locations"]:
        if e.get("pool"):
            pools.setdefault(e["pool"], []).append(e["name"])
    out = {}
    entries = [(e, [e["name"]] if e.get("conf") != "pool" else pools.get(e.get("pool"), [e["name"]]), e.get("conf"))
               for e in pins["locations"]]
    entries += [(e, list(e.get("cands", [])), "unmatched") for e in pins["unmatched_remake"]]
    for e, names, conf in entries:
        names = [n for n in names if n in flat]
        if not names or any(not flat[n] for n in names):
            continue
        ways = flat[names[0]]
        for n in names[1:]:
            ways = both(ways, flat[n])
        age_ways = None
        if all(n in by_age for n in names):   # (a dungeon both ages enter: the ways of each age alone, and of both)
            age_ways = {}
            for mode in AGE_MODES:
                got = by_age[names[0]][mode]
                for n in names[1:]:
                    got = both(got, by_age[n][mode]) if got and by_age[n][mode] else []
                age_ways[mode] = got
        for ref in e.get("refs", []):
            out[ref["hash"]] = {"names": names, "conf": conf, "folder": e.get("folder"), "kind": e.get("kind"), "ways": ways}
            if age_ways:
                out[ref["hash"]]["age_ways"] = age_ways
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dungeon", action="append")
    p.add_argument("--write")
    p.add_argument("--all", action="store_true", help="list pots, hearts and the like too")
    a = p.parse_args()
    calc = Calc()
    result, ages = {}, {}
    for dungeon in a.dungeon or DUNGEONS:
        result[dungeon] = calc.rules(dungeon)
        if dungeon in AGE_SPLIT:
            for mode, age in AGE_MODES.items():
                calc.ages_now = age
                ages.setdefault(dungeon, {})[mode] = calc.rules(dungeon)
            calc.ages_now = None
        for loc, ways in sorted(result[dungeon].items()):
            if not a.all and re.search(r"Pot|Recovery Heart|Fairy|Crate|Beehive|Grass|Silver Rupee|Wonderitem|Rupee \d", loc):
                continue
            print("%-52s %s" % (loc, " | ".join(show(w) for w in ways) if ways else "UNREACHED"))
    if a.write:
        with open(a.write, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"source": "tools/rando/dungeon_logic.py", "rules": result, "ages": ages, "by_actor": by_actor(result, calc.pins, ages)},
                      f, indent=1, sort_keys=True)


if __name__ == "__main__":
    main()
