"""What each overworld check needs from a new game's start, worked out from the other randomizers' logic of the remake
(as tools/rando/dungeon_logic.py does for the dungeons, with its world: OotrR's engine and world, ootrr 0.8.2's
dungeons; tools/rando/ootrr/README.md). Asked by the owner 2026-11-21: the overworld's rules were each area's hardest
check (rando_seed.py RULES), so a young Link with the forest and Kakariko's gate open had few checks in logic.

    py -I tools/rando/overworld_logic.py [--variant open,open,1] [--area "Kakariko Village"] [--write tools/rando/overworld_rules.json]

From a new game (Link a child at Root; an adult only once the Master Sword is pulled, the engine's Time Travel), with
the game's events where the game has them (the bosses' stones and medallions, the Master Sword, sticks and nuts dropped
by Deku Babas and pots, bugs, fish, Blue Fire), every item held but the ones tried, as dungeon_logic.py does: an item is
NEEDED where the check can't be had without it, and where those alone aren't enough the ways that are. Tried besides
the dungeons' items: buying Deku Sticks (the shops are shuffled: sticks are then only the drops the engine knows, and
the seed tool reads it as the Kokiri Sword, which its sticks step widens) and Zelda's Letter (Kakariko's gate).

One table for each of the seed's settings that the engine knows (the forest, Kakariko's gate, the Door of Time):
{"variants": {key: {"by_actor": {...}, "named": {location: [way, ...]}}}} (named: NAMED, the checks taken by name). The seed tool (rando_seed.py
OVERWORLD_RULES) takes its seed's variant and ties each location to the remake's actors by ootrr's pins, as the
dungeons' table.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dungeon_logic as D  # noqa: E402
from oot_rando.logic.rules import Logic  # noqa: E402

EXTRA_TRIED = [("Buy Deku Stick (1)", 1), ("Zeldas Letter", 1)]
TRIED = D.TRIED + EXTRA_TRIED
EVENT_TYPES = ("Event", "Boss", "Drop")
# (the seed's settings, as the engine's: the forest (both open, the way out only, closed), Kakariko's gate (open from
#  the start, or after Zelda's Letter is shown), the Door of Time (open, or by the Song of Time))
# (the checks the seed takes by name, not by an actor of a map: the characters' gifts and the shops' first shelves,
#  rando_seed.py OVERWORLD_GIFTS and OVERWORLD_SHOPS)
NAMED = ("GC Darunias Joy", "LW Target in Woods", "Deku Theater Skull Mask", "Deku Theater Mask of Truth", "ZD Diving Minigame",
         "LH Child Fishing", "LH Adult Fishing", "Market Shooting Gallery Reward", "Kak Shooting Gallery Reward",
         "Kak Anju as Child", "GF HBA 1000 Points", "GF HBA 1500 Points", "GC Rolling Goron as Adult", "ZD King Zora Thawed",
         "GC Rolling Goron as Child", "Kak Man on Roof", "LW Skull Kid", "LW Ocarina Memory Game", "Market Lost Dog",
         "KF Shop Item 1", "Market Bazaar Item 1", "Market Potion Shop Item 1", "Market Bombchu Shop Item 1", "GC Shop Item 1",
         "ZD Shop Item 1", "Kak Bazaar Item 1", "Kak Potion Shop Item 1")
# (bug 118, 2026-11-23) The remake's checks the other logic doesn't have (pinned to no location, or only to a pool of
# unlike ones): OWN_FILE's rules of our own, each put in its region as the location "OWN <hash>" and worked out as the
# others are; written in each variant's "own" ({the actor's hash in decimal: [way, ...]}), which the seed tool reads
# from its placement 26 (rando_seed.py OWN_FROM), so the tables' other parts stay as they were.
OWN_FILE = os.path.join(HERE, "overworld_own.json")
OWN_PREFIX = "OWN "


def own_rules():
    """{hex hash: {"region", "rule", ...}} of OWN_FILE; {} without it"""
    try:
        with open(OWN_FILE, encoding="utf-8") as f:
            return json.load(f)["rules"]
    except (OSError, ValueError, KeyError):
        return {}


FORESTS = ("open", "closed_deku", "closed")
GATES = ("open", "zelda")
DOORS = (True, False)


def variant_key(forest, gate, door, master=False):
    """the table's key; master: Shuffle the Master Sword (the engine's shuffle_master_sword), only with the Door of Time
    open, as the seed tool has it: ",ms" after the key"""
    return "%s,%s,%d%s" % (forest, gate, 1 if door else 0, ",ms" if master else "")


class Over(D.Calc):
    def __init__(self, forest, gate, door, master=False):
        self.data, settings, self.pins = D.world()
        regions = {r["region_name"]: r for r in self.data.regions}
        for h, e in own_rules().items():   # (OWN_FILE's: our own rules of the remake's checks)
            if e["region"] not in regions:
                raise ValueError("%s: no region %s" % (h, e["region"]))
            regions[e["region"]].setdefault("locations", {})[OWN_PREFIX + h] = e["rule"]
            self.data.location_table[OWN_PREFIX + h] = {"type": "Item", "scene": None, "vanilla": None, "categories": [e.get("area", "")]}
        settings = dict(settings, open_forest=forest, open_kakariko=gate, open_door_of_time=door, shuffle_master_sword=bool(master))
        self.logic = Logic(self.data, settings)
        self.ages_now = None
        tried = {name for name, _ in TRIED}
        self.fixed = {}
        for loc in self.logic.location_names():
            item = self.data.vanilla_item(loc)
            if not item or item in tried:
                continue
            if any(w in item for w in ("Key", "Silver Rupee")) or self.data.location_table.get(loc, {}).get("type") in EVENT_TYPES:
                self.fixed[loc] = item
        dungeon_areas = set(D.DUNGEONS)
        self.locations = {"overworld": set()}
        for loc in self.logic.location_names():
            areas = {a.replace("'", "") for a in self.data.location_areas(loc)}
            if not areas & dungeon_areas:
                self.locations["overworld"].add(loc)
        self.always = {item: 9 for item in self.data.item_table if item not in tried and not any(item.startswith(w) for w in D.NEVER)}
        for item in set(self.fixed.values()) | {"Time Travel"}:   # (what the events give is had there: the medallions, the
            self.always.pop(item, None)                         #  stones, an adult only by the Master Sword's pedestal)

    def reached(self, dungeon, held):
        counts = dict(self.always)
        counts.update({k: v for k, v in held.items() if v})
        state = self.logic.new_state(counts)
        state, _, _ = self.logic.sweep(self.fixed, state)
        return {loc for loc in self.locations["overworld"] if self.logic.accessible(state, loc)}

    def ways(self, dungeon, loc, full):
        found = []
        order = [name for name, _ in TRIED]
        for start in range(0, len(order), max(1, len(order) // D.WAYS_MOST)):
            held = dict(full)
            for name in order[start:] + order[:start]:
                while held.get(name, 0) > 0:
                    trial = dict(held, **{name: held[name] - 1})
                    if loc not in self.reached(dungeon, trial):
                        break
                    held = trial
            way = {k: v for k, v in held.items() if v}
            if not any(all(w.get(k, 0) >= v for k, v in way.items()) and w != way for w in found):
                found = [w for w in found if not all(w.get(k, 0) >= v for k, v in way.items())] + [way]
        return found

    def rules(self, dungeon="overworld"):
        full = {name: top for name, top in TRIED}
        everything = self.reached(dungeon, full)
        needed = {loc: {} for loc in everything}
        for name, level in [(name, k) for name, top in TRIED for k in range(1, top + 1)]:
            for loc in everything - self.reached(dungeon, dict(full, **{name: level - 1})):
                needed[loc][name] = max(level, needed[loc].get(name, 0))
        out = {loc: [] for loc in self.locations["overworld"] - everything}
        by_set = {}
        for loc, need in needed.items():
            by_set.setdefault(tuple(sorted(need.items())), []).append(loc)
        for key, locs in by_set.items():
            ok = self.reached(dungeon, dict(key))
            for loc in locs:
                out[loc] = [dict(key)] if loc in ok else self.ways(dungeon, loc, full)
        return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--variant", action="append", help="forest,gate,door[,ms] (e.g. open,open,1); all of them without it")
    p.add_argument("--master-sword", action="store_true", help="the variants with the Master Sword shuffled (door 1, ',ms') in place of the others")
    p.add_argument("--area")
    p.add_argument("--write")
    a = p.parse_args()
    wanted = a.variant or ([variant_key(f, g, True, True) for f in FORESTS for g in GATES] if a.master_sword else
                           [variant_key(f, g, d) for f in FORESTS for g in GATES for d in DOORS])
    out = {}
    for key in wanted:
        forest, gate, door = key.split(",")[:3]
        calc = Over(forest, gate, door == "1", key.endswith(",ms"))
        rules = calc.rules()
        out[key] = {"by_actor": D.by_actor({"overworld": {k: v for k, v in rules.items() if not k.startswith(OWN_PREFIX)}}, calc.pins),
                    "named": {n: rules[n] for n in NAMED if n in rules},
                    "own": {str(int(k[len(OWN_PREFIX):], 16)): v for k, v in rules.items() if k.startswith(OWN_PREFIX)}}
        missing = [n for n in NAMED if n not in rules]
        if missing:
            print("not in the logic: %s" % ", ".join(missing))
        print("== %s: %d locations, %d pinned actors" % (key, len(rules), len(out[key]["by_actor"])))
        if a.area or len(wanted) == 1:
            for loc, ways in sorted(rules.items()):
                areas = calc.data.location_areas(loc)
                if a.area and a.area not in areas:
                    continue
                if re.search(r"Pot|Recovery Heart|Fairy|Crate|Beehive|Grass|Rupee \d|Wonderitem|Hint|Bug|Fish|Butterfly", loc):
                    continue
                print("%-48s %s" % (loc, " | ".join(D.show(w) for w in ways) if ways else "UNREACHED"))
    if a.write:
        with open(a.write, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"source": "tools/rando/overworld_logic.py", "variants": out}, f, indent=1, sort_keys=True)


if __name__ == "__main__":
    main()
