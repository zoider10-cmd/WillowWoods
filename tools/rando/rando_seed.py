"""Randomizer, stage 2: shuffles what the chests hold across the whole game, as a mod.

Reads the Randomizer settings the launcher keeps in <game folder>\\hookshot_options.ini (rando_on, rando_seed,
rando_chests, rando_keys, rando_major, rando_open_deku, rando_open_forest, rando_skip_intro) and writes changed map
files, an updated size table and, for the last three, the game's list of flags and its opening event to
<game folder>\\mods\\rando-seed\\romfs\\..., which Mako loads in place of the game's own. The game's files are not
touched. The same seed and settings give the same shuffle.

    python -I tools/rando/rando_seed.py "F:\\Games\\OOT Remake Rando\\romfs"
    python -I tools/rando/rando_seed.py <romfs> [--game <folder>] [--seed N] [--chests 0..3] [--keys 0..2] [--event-chests] [--no-logic] [--dry-run]

The launcher runs it at Play (the copy the build puts in <game folder>\\rando, with --if-changed), so it only needs
running by hand to try something. With the randomizer off (or Chests Off) it removes the files it wrote before, so
the game is as shipped again.

Settings:
  Chests        1 the overworld's chests take part, 2 the dungeons', 3 all. Their items are shuffled among them, across
                areas: a Kokiri Forest chest can hold what a Fire Temple chest held.
  Dungeon keys  Off: a dungeon's small keys, Boss Key, map and compass stay in their own chests. Own dungeon: they are
                shuffled among that dungeon's chests. Anywhere is treated as Own dungeon for now: the game counts a
                small key for the dungeon it is picked up in, so one from another dungeon would be miscounted.
  Major items   On: the same as --event-chests, below.
  Open Deku Tree, Open forest exit   On: a new game starts with that way of Kokiri Forest open (OPEN, below). The logic
                does not count on either: its rules still ask for the sword and the Slingshot before anything out of
                the forest, so an open way is the player's to use and never the only way to an item.
  Skip opening   On: a new game starts in Link's house (OPENING, below).
What it leaves alone: a mini-game's chests, a chest whose item depends on what Link already has, and, unless
Major items is On or --event-chests is given, a chest that starts an event when opened (most of the big items: the Kokiri Sword, the Fairy
Bow, the Megaton Hammer...).
  --event-chests  Those take part too. The event stays with its chest and the item is the chest's: the Kokiri Sword's
                  chest with a purple Rupee in it gave the Rupee, then played its sword scene and left a sword in
                  Link's hand that was gone after a reload; the sword from another chest was a whole sword (in the
                  inventory, kept by a save, and Mido let Link pass).
The logic (with --event-chests, unless --no-logic): the thirteen items that gate the game and come from chests are
placed so that each can be reached with the ones before it, by rules of what every area's chests ask for (RULES,
below). The rules are written from the original game and ask for too much where the remake is not known; they have not
been checked against the remake chest by chest, and they do not look at a dungeon's keys (leave Dungeon keys Off).
So a seed is meant to be finishable, not proven to be. Without --event-chests no gating item moves, and the game's own
order holds. mods\\rando-seed\\spoiler.txt says where everything went and the order the rules found.

How a map file is changed (each step shown to work in game, one chest at a time, before this was written):
  - a changed chest gets a parameter block of its own at the end of the file (the files store equal blocks once, so
    changing the shared one would change its twins);
  - item names the file does not have yet go into a copy of its string table at the end, after the names it has;
  - the file grows, so its entry in the game's size table (System/Resource/ResourceSizeTable...rsizetable) is raised:
    the game does not load a file larger than its entry.
Needs the zstandard package.
"""
import argparse
import collections
import itertools
import json
import math
import os
import random
import struct
import sys
import zlib

ZSTD = b"\x28\xb5\x2f\xfd"
MOD = "rando-seed"
# (raised whenever the same settings would place something else than before: the launcher's run at Play, --if-changed,
# then makes the seed again. A seed being played changes under its save when that happens, so not lightly)
PLACEMENT = 29  # 29: Lake Hylia's chest there once the Water Temple is done asks for that temple's ending (AFTER_WATER_FROM); 28: Lake Hylia's Fire Arrows (the sun's shot) a check, their Fire Arrows in the pool (SUN_FROM); 27: the rainy Kakariko's own check (the windmill chest #1, there only from the Nocturne scene until the Shadow Temple is done) holds junk only (RAINY_FROM, bug 131), Lake Hylia's lab diving game is a gift of the shuffle (GIFTS_FROM, lab_dive), and the frogs' two prizes are two gifts (FROGS_SPLIT_FROM, bug 132); 26: the remake's own overworld checks by rules of their own (OWN_FROM, bug 118), adult checks ask for the Master Sword only where a fight needs it with the sword shuffled (SWORD_FROM), the Bottom of the Well a young Link's by the Song of Storms (WELL_FROM, bug 121), the Forest Stage by the Happy Mask Shop's masks (MASKS_FROM, bug 120), the two Business Scrubs' hearts where the game has them (SCRUB_SWAP_FROM, bug 126); 25: each dungeon check by the other randomizer's newer dungeons (ootrr a253c9a: the Spirit Temple and Gerudo Training Ground rewritten, Ganon's trials, three of Dodongo's Cavern's), DUNGEON_RULES2_FROM; 24: Kakariko's watchtower Gold Skulltula by the Boomerang too (OVERWORLD_MORE); 23: each overworld check asks for its own ways from a new game's start, from the same logic (OVERWORLD_FROM), Bombchu Bowling a child's alone (BOWLING_FREE), and Kakariko's gate Open is on the stamp; 22: the Spirit Temple's checks by age, each age's ways with its own way in (DUNGEON_AGES_FROM); 21: each dungeon check asks for its own ways, from the other randomizers' logic of the remake (DUNGEON_RULES_FROM); 20: with the Deku Tree and the forest's way out open, Deku Sticks from Goron City's pots do for the Kokiri Sword (STICKS_FROM); 19: with Open Door of Time, an adult's place asks for the Song of Time only where its area has Song of Time blocks (TIME_BLOCK_AREAS); 18: Malon's lesson asks for its own rule again with Songs: Anywhere, not for everything (MALON_FREE_FROM); 17: the tunics by the game's own hot rooms and deep water: the Zora Tunic wherever the Iron Boots sink Link, Zora's Fountain's checks above its water asking for neither (TUNIC_WATER_FROM); 16: the Great Fairies' offerings are rolled as the shops' prices are, and a fairy whose price needs a bigger wallet asks for it (FAIRY_PRICES); 15: the Deku Tree's third floor (room 3: a chest and a Gold Skulltula) asks for the Slingshot (DEKU_THIRD_FLOOR); 14: the Great Fairies of the three spells are gifts of the shuffle with Quest rewards, each holding what a lesson asked about by name may (FAIRY_GIFTS); 13: a bottle is a gating item where the bottles are shuffled (Quest rewards), and a Gold Skulltula in bean soil asks for one, its bugs (BOTTLE, soil_need: bug 84); 12: the Goron and Zora Tunics are gifts of the shuffle, and the rules ask for them (TUNICS); the chests with a substitute take part (SUBSTITUTE_CHESTS); the Gold Skulltulas and the Pieces of Heart lying in the world take part as chests do (SHUFFLED_FROM), and the Skulltula house's rewards, with the 40 tokens' one, ask for their tokens, counted (HOUSE_TOKENS); 2: the chests of LOCKED_ROOMS kept their items; 3: they take part again, their rooms opened by FIXES;
                # 4: the Market's shops ask for nothing with Open forest exit, the Bombchu Shop not for Dodongo's Cavern (shop_need);
                # 5: rules with alternatives (Either): Zora's Domain by the river or by the lake, and Open forest exit not
                #    asking for the forest's way out (forest_open)
                # 6: Impa's and Saria's lessons keep the Deku Tree done with Open forest exit (DEKU_STORY)
                # 7: the Deku Tree's Slingshot room's two chests ask for the Slingshot (SLINGSHOT_ROOM)
                # 8: Open forest exit no longer lightens the Gold Skulltulas' rules (skull_door)
                # 9: the Potion Shop keeper's bottle is a gift of the shuffle (GIFTS_FROM)
                # 10: Hyrule Field's Piece of Heart chest asks for having been an adult and coming back (CHEST_NEEDS)
                # 11: Kakariko's Bazaar and Potion Shop are shops of their own, the adult's, apart from the Market's (SHOP_TOWNS)
# (a chest with one of these parameters is left as it is: see the top of this file)
# SUBSTITUTE_CHESTS (bug 62, placement 12): a chest with Drop__CheckActor and Drop__DropActor_Substitute gives its item,
# or the substitute when Link has the CheckActor's already (the Graveyard grave's Hylian Shield chest: a red rupee when
# Link has the shield; Deku Shields in the Bottom of the Well, Dodongo's Cavern and the Spirit Temple; two of the
# Gerudo Training Ground's). With only those two of KEEP_IF it takes part: rewrite() writes the shuffled item into
# both its item and its substitute, so it gives that item whatever Link holds.
KEEP_IF = ("GetEventName", "CheckEventName", "CheckEventNameIndoor", "Drop__CheckActor", "Drop__DropActor_Substitute",
           "DropViewActor", "IsEnableRepeatOpen", "SpawnType")
# (a chest's GetEventName that is known not to care what the chest holds: Mido's house's chests, whose event only
# quiets Navi. They gave other items in the tests and played as usual)
# Chests whose room cannot be left without the item they hold (by their event), found in play: with anything else in
# them the player is shut in. The Forest Temple's Stalfos room: no way out without the Bow or a key, and the warp
# songs do not work in it. Placement 2 kept their items; since then FIXES gives their rooms a way out.
LOCKED_ROOMS = ("ForestTemple_GetBow",)
# Dampe's race (bug 62, placement 12): its prize chests sit at one spot under the Graveyard (Graveyard_Adult_Static), each
# shown by the race's own state (MiniGame_DampeRace: Minigame_DampeRace_TreasureBoxState, set by its clear count and
# its HookShot_Event63 flag, not by the pouch) and opened through its GetEventName MiniGame_DampeRace_OpenGoalTBox,
# which sets the state and gives nothing itself; the Piece of Heart won is the tomb's map logic's flag
# (UnderTheGrave_DampeRace_HeartGeted, Logic/UnderTheGrave_Prefab_6971), not the item. So the Piece of Heart chest
# takes part. The Hookshot chest stays: the rules have no Hookshot (an adult is taken to have it from here) and the tomb
# can't be left without it; shuffling it needs the Hookshot as a gating item in every rule that leans on it.
DAMPE_RACE_CHESTS = frozenset((0x4ccffbd5778b67e2,))
# Shuffle Dampe's Hookshot (rando_dampe_hookshot, the owner's go-ahead 2026-11-21; the audit: share/hookshot-audit.md).
# With it the race's Hookshot chest takes part too, and the Hookshot is a gating item of the rules (HOOK, hook_need).
# The race's flow asks "has Link the Hookshot" (in the pouch, or got once) to mean "is the first race's prize won", and
# asks for the Longshot the same way (MiniGame_DampeRace steps 39, 74-75, 90, 95, 108, 165-167, 422-424); the tomb's
# two logic files read IsGet.Item_Hookshot (UnderTheGrave_Prefab_0a7f, _6971). So the chest is a place asked about by
# name, as a lesson is (it may hold only lesson_items: got nowhere else, with flags of its own), and each of those
# questions is made to name what the chest gives now (race_words): a Hookshot found first does not skip the chest, and
# the race goes on to its second prize once Link has the chest's item. The rules: where the audit found the Hookshot
# needed (HOOK_AREAS, HOOK_GIFTS, HOOK_SKULLS, and the race's own chests, DAMPE_EVENT: the tomb can't be left without
# it) the Hookshot or the Longshot is asked for. NOT SEEN IN PLAY yet.
HOOK = "Item_Hookshot"
DAMPE_HOOK_CHEST = 0xde9e62394333948e
DAMPE_EVENT = "MiniGame_DampeRace_OpenGoalTBox"
DAMPE_FLOW = "Event/EventFlow/MiniGame_DampeRace.bfevfl.zs"
DAMPE_LOGIC = ("Logic/UnderTheGrave_Prefab_0a7f.logic.module.ainb", "Logic/UnderTheGrave_Prefab_6971.logic.module.ainb")
HOOK_AREAS = frozenset(("ForestTemple", "FireTemple"))   # (the temple's way in: the meadow's branch; the crater's grab points)
HOOK_GIFTS = frozenset(("song_bolero",))                 # (Sheik on the crater's middle platform)
# The Gold Skulltulas whose own rule (SKULLTULA_RULES, from the original's logic) says an adult kills them with the
# Hookshot, which those rules folded into ADULT: Lake Hylia's lab tank, Kakariko's, the Kokiri Forest's, the Sacred
# Forest Meadow's, Zora's River's two and Zora's Fountain's (night ones on walls), the Ice Cavern's three ("hookshot or
# boomerang": the Boomerang is a child's, and only an adult goes in). Zora's Domain's takes the Bow as well (HOOK_OR).
# The temples' and the desert's are covered by their areas or ask for the Longshot already. (Added 2026-11-21, the
# owner's ask to make the Gold Skulltulas' logic accurate.)
HOOK_SKULLS = frozenset((0xfbbc2d490276c68e,             # (Goron City's adult Gold Skulltula by the Lost Woods exit)
                         0x6689bdebc95368eb, 0x2df265292516bdf0, 0x62c340f0b876c195, 0xc8db3346f78ea31b, 0x97824c2ffeaa877c,
                         0x8325fea55edfbe97, 0x845ba51dc18c855e, 0xcdb49f5d0a67fcf6, 0x63701a2cf70b201c, 0x165fc0bc0aca1f6c,
                         0x853b892663c0215d))
HOOK_OR = {0x853b892663c0215d: "Item_Range_Bow"}         # (another item that does as well, by the Skulltula's rule)
HOOK_SHUFFLED = False   # (main sets it)
DAMPE_HOOK_FROM = 19   # (the owner, 2026-11-21: "it should be randomized the same as most general items", no setting)
# Changes to the map that a shuffled game needs, written with every seed (and so only with the randomizer on):
# {an actor's hash: {a key of its Dynamic block: the truth value it gets}}.
# The Stalfos room's shutter (opened by an eye switch, so by the Bow) no longer turns saving and the warp songs off
# while it is shut: without the Bow the room is left by a warp song, as any other. Nothing new to learn for a player.
FIXES = {0x74fb0489585fe0e2: {"IsDisableSaveAndWarp": False}}
FIXES_VERSION = 94   # (93: before a boss's Heart Container that gives another item showed that item, CONTAINER_LOOK. 92: before a Piece of Heart lying in the world that gives another item showed that item, PIECE_LOOK. 91: before the Silver and Golden Gauntlets' shelves posed their pair as the get scene does, SHELF_OWN_POSE. 90: before the Silver and Golden Gauntlets' shelves showed their own pair a third its size, not the Bracelet. 89: before a Gold Skulltula's drop of a family was shown as the family's next, its tiers made pick-ups, SKULL_TIERS. 88: before the bean-soil Gold Skulltulas were there for a bottle got, no bugs, SOIL_FILES. 87: before Bombchu Bowling's first two wins gave its two checks, the bag's then the Piece of Heart's, BOWLING_FLOW. 86: before the climbing boxes over Lake Hylia's dead tree's vines, baked, were a Hookshot catch and its baked Wood was not, CLIMB_WALL_ENTRY (bug 119). 85: before Lake Hylia's dead tree was baked again, its climbing boxes as the game has them, and its baked Wood a Hookshot catch, BAKED_TREE_FILES (bug 119). 84: before Lake Hylia's dead tree was placed without Bakeable, a body of its own, TREE_NAME (bug 119). 83: before the climbing boxes over Lake Hylia's dead tree's vines were a Hookshot catch, TREE_CLIMB_SHAPE, and its mesh's Wood was left as it was (bug 119). 82: before Lake Hylia's dead tree's wood was a Hookshot catch (83 only). 81: before Lake Hylia's tree had its hookshot-stopping wall taken out again (its own HitOnlyHookshot: it stops the Hookshot; 79 had kept it). 80: before Darunia's gift was had after Dodongo's Cavern, DARUNIA_LATE (bug 128). 79: before Goron City's sign-order grotto gave its right chest after a wrong try, SIGN_GROTTO_LOGIC (bug 127). 78: before Lake Hylia's dead tree kept the Hookshot's catch along its vines, there always (TREE_WALL keep, bug 119; 73 had taken it out). 77: before a new game started with the mask salesman's trade done, MASK_TRADE (bug 133). 76: before the second magic's chest was named by the blue rupee it held, not "Doubled Magic". 75: before the Fire Temple's way out kept its Kakariko video (Link frozen after Volvagia), SCENE_VIDEOS_KEPT. 74: before the gauntlets' own spellings had "You got" words, COPY_WORDS. 73: before every mask was the Happy Mask Shop's from the start, MASK_EXPS (bug 120). 72: before Lake Hylia's dead tree took the Longshot before the Water Temple's room 7, TREE_WALL (bug 119). 71: before a hint named an item by its file name ("the Fairy Bless MPDouble"), HINT_WORDS (bug 116). 70: before a shelf's Empty Bottle was sold without an empty bottle, SHOP_BOTTLE (bug 113). 69: before the Forest Temple's Bow room opened its barred door once its Stalfos were dead, BOW_ROOM_LOGIC. 68: before the rolling Goron's and King Zora's gifts were kept when their quest was moved on first, QUEST_LATE. 67: before the Fire Temple's Boss Key chest (Room 17) was unlocked with its Goron gone, FIRE_CHESTS. 66: before a new game stopped starting with the Water Temple's gate flags, which the game's side sets by the Water Temple gate setting, WATER_GATE. 65: before a starting stick or nut bag's first pick-up came without a box, START_PICKUPS. 65: before Zelda's Letter had the amiibo slot of its own, LETTER_SLOT. 64: before the Fire Temple's jailed Gorons were gone with Skip cutscenes, FIRE_GORONS. 63: before the first rupee, heart, magic jar, arrows and seeds came without a box with Skip cutscenes, FIRST_PICKUPS. 62: before the lake's logic was the game's again (61 gave its switch's boots check another input, on a wrong reading: with the Iron Boots on it changed nothing). 60: before the Water Temple's gate was open from the start, WATER_GATE. 59: before Bombchu Bowling and the Bombchu Shop were open from the start, the shop day and night, and the Water Temple's gate switch was free of the Ice Cavern, ALWAYS_EXP, WATER_WALL. 58: before the two-handed swords were the child's, with the adult's 02 and 03 clips, AGELESS_BIGGORON. 57: before the Goron and Zora Tunics were the child's too, AGELESS_TUNICS. 56: before the boots were the child's again to try, AGELESS_BOOTS. 55: before the child's Bow shot arrows of its own, AGELESS_ARROWS, and the magic arrows were his again. 54: before the child's Biggoron's Sword, boots and magic arrows were taken out of either age's items, AGELESS_NOT_CHILD. 53: before either age's items lent each Link the other's shootable actors, AGELESS_SHOOTERS. 52: before a quieted scene's own music was passed over, SCENE_MUSIC (the owl's played on). 51: before either age's items lent each Link the other's holders, AGELESS_HOLDERS. 50: before every Great Fairy's fountain answered Zelda's Lullaby from the start, FOUNTAIN_FLOW. 49: before the first Deku Nut and Deku Stick bags had "You got" words, FIRST_BAG_WORDS, bug 48. 48: before a shield's pick-up (a Skulltula's drop) had a model file of its own, bug 78, and King Zora's move aside was kept with Skip cutscenes, bug 88. 47: before the Gold Skulltulas by day had their AI never told it is day, bug 82. 46: before a Heart Container on a shelf was made a piece's size, bug 72. 45: before the empty bottle stood up on its shelf, and Kakariko's Potion Shop had its own turns and sizes, SHELF_TURN_SHOP. 44: before the royal tomb's opening, the Sun's Song's lesson and its sunrise were skipped, SCENE_SILENT. 43: before the cucco lady's game wanted one cucco, CUCCO_LOGIC. 42: before Death Mountain Trail's and Goron City's intros were left to play (their arrivals take the Fire quest a step), and an adult's first visit to Goron City went on to the rolling Goron, goron_arrival_fix. 41: before an empty child's sword slot was given the Kokiri Sword on the way back, era_sword_fix. 40: before the areas' first-visit intros were marked played with Skip cutscenes, AREA_INTROS. 39: before a map with two shops' shelves of a family had one list of tiers, and the tiers' maps kept its other edits (the Market went black). 38: before a shelf of a family showed the item Link would get, SHELF_FAMILIES (Progressive items). 37: before Hyrule Field's Piece of Heart chest was a child's on the Tracker tab, CHEST_AGES. 36: before the Tracker tab had the directions to a check, CHECK_WAYS. 35: before an adult had the sword's prompt with Open Door of Time, SWORD_PROMPT_LOGIC. 34: before the Potion Shop keeper's calm schedule's mark was set with his errand skipped. 33: before the bug of the Potion Shop keeper's errand was taken away too. 32: before the Potion Shop keeper's errand of the bug was passed over. 31: before a shelf's shield had a model file of its own (SHELF_OWN_MODEL) and a song's harp faced out. 30: before a shelf item the game never sells kept its capitals in the keeper's line, SHOP_NAME_CAPS. 29: before the empty bottle stood clear of its shelf's price board. 28: before the Kokiri girl in front of the shop was quieted, SCENE_STOPS. 27: before a song's harp stood up on its shelf. 26: before a song looked like Sheik's harp, SONG_LOOK. 25: before Hyrule Castle's drawbridge had three red rupees, DRAWBRIDGE_RUPEES. 24: before the stump chest by the bridge was an adult's on the Tracker tab, CHEST_AGES. 23: before Go there to the stump chest by the bridge went to the bridge's forest end, CHEST_GO. 22: before the minimap was there from a new game's start, MINIMAP. 21: before the Bombchu Shop's keeper was there from the start, BOMBCHU_ACTORS. 20: before the Bombchu Shop's door opened at night from the start, BOMBCHU_DOOR_LOGIC. 19: before Link's door was open from the start with Skip opening, LINK_DOOR. 18: before a gift's scene without talk was quieted, SCENE_GIFTS. 17: before the story's flows a lesson calls were quieted. 16: before a fork kept only the branches left, and counted them. 15: before the song lessons went to their gift, SCENE_LESSON. 14: before Zelda's last line, EventTalkIgnoreSameTalkAS, was passed over. 13: before a question whose answers all come to the same step was passed over. 12: before the story's videos were left out, SCENE_VIDEOS. 11: before Zelda's questions of three and four answers were passed over. 10: before the d-pad's HUD was there from a new game's start, DPAD_HUD. 9: before the smallest arrows' bundle lay across its shelf and the bracelet stood over the price board. 8: before the bomb's file was changed in the bomb flowers' packs too. 7: before the bomb's file was changed in place: written anew, the game fell reading it. 6: before bombs were lifted without the Goron's Bracelet, bomb_lift. 1: the eye switch took the Hookshot. 2: before the Kokiri Sword's chest's own cutscene was left out. 4: before Hyrule Field's clock ran from a new game's start, FIELD_CLOCK)
# The forest's two closed ways. Each is a flag of the game that starts set and is put out by the story: Mido stands in
# the way to the Deku Tree until Link has a sword and a shield (KokiriForest_Npc_Kokiri_Mido_Child_Blocker), and a
# Kokiri in the forest's way out until the Deku Tree is done (KokiriForest_Npc_Kokiri_007_Child_Blocker_00). An
# invisible wall of KokiriForest_Child_Dynamic is there while its flag is set (its Presence), and the character acts on
# the flag too: with the walls alone moved away both still stopped Link (seen in play). --open-deku and --open-forest
# make the flag start put out, in the game's list of flags (FLAG_LIST): {the setting: {a flag: the value it starts
# with}}. A flag is kept in a save, so this is a new game's; a save made before keeps the way as it was.
OPEN = {
    "deku": {"KokiriForest_Npc_Kokiri_Mido_Child_Blocker": False},
    "forest": {"KokiriForest_Npc_Kokiri_007_Child_Blocker_00": False},
}
# The Door of Time (rando_open_door, --open-door): the Temple of Time's inner door is a gate of the Market's logic
# (Logic/Market_Common_f252: isOpen is the flag Market_Child_TimeTempleDoor_Opened OR the quest DoorOfTime at its
# step Step06), and the flag is what the story's scene of the door opening sets (DoorOfTime_OpenDoor). A new game
# starts with the flag set. THAT DID NOT OPEN IT: reported from play, 2026-11-14, a new game with the setting on and
# the flag set (the game's log), the door shut. (What was seen without a window before was Link put in the sword's
# chamber by the debug tools, past the door: the door itself was never looked at.) So the door is also taken out of
# the way in the map files (door_away): its actor, of the child's Market and of the adult's, is put far under the
# map, as the shops' bundle boards are, not taken out of the file, so that the logic that names it still finds it.
# Seen without a window: Link put in the doorway by the debug tools, the door filling the view on a seed without
# this, and with it the doorway open on the sword's chamber. Not seen: Link walking through it.
# The sword is another matter. Its logic (Market_Child_Prefab_e700) asks for the story's own drawing only when the
# quest is at Step06, and for the plain way through time (the flow Market_Child_Field_ChildToAdult) only once that
# is past: before, the button does nothing (seen). The story's drawing ends the whole quest (SageRoom_MeetRauru:
# Complete), and the quest is Zelda's too (the meeting, Impa's lesson, the Ocarina of Time): drawn early, those would
# be lost. So the game's side asks for the plain way itself when the button is pressed at the sword and nothing of
# the game's answers (host/hos_main.c oot_time_door), in both directions, and the story is left as it is: its own
# drawing, with the Sage of Light, still comes at Step06. Seen without a window: asked for by name in that early
# save, the flow made Link an adult at the pedestal.
# The rules with it (door_need). "ADULT" stands for all it takes to pull the Master Sword, the three stones' items,
# and nearly every rule has it, a child's place as an adult's: so only what it takes to BE an adult is taken off,
# and only from a place that only an adult has (its map files are the adult's, or its dungeon is one a child cannot
# enter: DOOR_ADULT_AREAS) and whose rule has the whole of ADULT:
#   - the Boomerang, an adult's only as the Zora's Sapphire's price (a child's item: an adult cannot throw it);
#   - the Silver Scale that Quest rewards adds wherever an adult is, for Ruto's Letter and so for the same stone
#     (not where the rule has the Golden Scale: Progressive items then asks for the Silver one of its own right);
#   - with Open forest exit, the Kokiri Sword, the Slingshot and the Deku Shield, which are the way out of the forest
#     and a child's: the forest is left without them, and the Master Sword is given at its stone.
# Bombs and what Songs adds for an adult (the Lullaby, Saria's Song, the Song of Time, the Song of Storms) are another
# matter: an adult's own places need them in some rooms, and the rules do not say which. They stay, but for the
# dungeons that only an adult enters, gone through one by one by the ORIGINAL game's layout (asked for: "real adult
# logic"; the remake's rooms have not been walked for this, so each line is to be seen in play):
#   - the Silver Scale stays where the way in is past King Zora, who moves aside for a child with Ruto's Letter, the
#     bottle at the lake's bottom: Zora's Fountain and the Ice Cavern (DOOR_SCALE);
#   - bombs, and the bracelet Quest rewards asks for with them, are not asked for where no room needs them: the Forest
#     Temple and the Ice Cavern (DOOR_NO_BOMBS). The Fire, Water and Shadow Temples and the Training Ground have walls
#     and rocks that do;
#   - of the four songs, each such dungeon keeps the ones it needs (DOOR_SONGS): the Forest Temple Saria's Song (Mido
#     bars the way to the meadow without it) and the Song of Time (its blue block); the Fire Temple, the Shadow
#     Temple and the Training Ground the Song of Time; the Ice Cavern the Lullaby (the way into Zora's Domain); the
#     Water Temple the Lullaby (its water) and the Song of Time. None needs the Song of Storms.
# The overworld's places of an adult's alone keep bombs and the four songs: where each is and what it needs is not
# known. Too much, never too little. A place a child has too is as it was.
# The adult's Market had no minimap (reported from play, 2026-11-14): its location's area (LocationArea "Market" of
# Market_Adult_Static) is there only once the story's scene of an adult leaving the temple has played
# (HavePlayedEvent.Dm_TimeTemple_0065), and that scene waits for the story's own step (the quest AllSage at Step01),
# which the plain way through time does not reach. So the flag starts true too. Seen without a window: an adult in
# the Market's square without the flag has no minimap, and with it has one. (The game's side sets both in a save
# from before: host/hos_main.c oot_time_door.)
OPEN_DOOR = {"Market_Child_TimeTempleDoor_Opened": True, "HavePlayedEvent.Dm_TimeTemple_0065": True}
DOOR_ACTOR, DOOR_AREA, DOOR_AWAY = "Obj_TimeTemple_Door_A_01", "Market", 2000.0
# The adult's "A" at the sword (reported from play, 2026-11-14: putting the sword back works, no prompt). The adult's
# sword logic (SWORD_PROMPT_LOGIC, 4 nodes) deletes the sword's attention, the prompt, while the Forest Temple is not
# done (node 0 SageOfForest_IsCompleted_Exp, node 1 InvBool, into node 2's Logic_Delete). With Open Door of Time that
# input is unlinked (sword_prompt_open), as the file's other unlinked inputs are: the prompt is always there. Tried
# before: another expression in its place (none is true that early) and the plain flag in the expression's place (the
# node reads expressions only).
SWORD_PROMPT_LOGIC = "Logic/Market_Adult_Prefab_89da.logic.module.ainb"
SWORD_PROMPT_INPUT = 0x4E0   # (node 2's Logic_Delete input: its name, node, output, flags, default)
# Sheik. Reported from play, 2026-11-14: an adult cannot go back, "he stops you until you beat the forest temple".
# Seen without a window: he stands at the sword's stone (Npc_Hylia_Sheik_Adult of the adult's Market, 1.4 m from the
# sword), so the button there is his talk, and the game's side asks for nothing when the game answers the button
# (host/hos_main.c oot_time_door). The game keeps him there until the Forest Temple is done (his schedule's
# SageOfForest_IsCompleted_Exp; the sword's own logic of the adult's Market waits for the same), and then has him
# teach the Prelude of Light. So he is put to the side of the room (DOOR_SHEIK_ASIDE, along the map's Z): still
# there for his talk and for his lesson, which is an event with places of its own. Where he stands is not his own
# place in the file but the places his schedule sends him to, the actors his links name (AnchorAction1 and 2, before
# the sword): with his own place moved alone he stood at the stone as before (seen without a window). So he and the
# places he is linked to are all put aside.
DOOR_SHEIK, DOOR_SHEIK_ASIDE, DOOR_SHEIK_SPOT = "Npc_Hylia_Sheik_Adult", 5.0, "AnchorAction"
DOOR_ADULT_AREAS = frozenset(("ForestTemple", "FireTemple", "IceCavern", "WaterTemple", "ShadowTemple", "GerudoTrainingGround"))
DOOR_SCALE = frozenset(("ZoraFountain", "IceCavern"))
DOOR_NO_BOMBS = frozenset(("ForestTemple", "IceCavern"))
_ZL, _SARIA, _TIME, _STORMS = ("Item_Melody_" + n for n in ("ZeldaLullaby", "SariaSong", "TimeSong", "StormSong"))   # (ZL and the rest, named below)
# The Song of Time by the remake's own blocks (placement 19, TIME_BLOCKS_FROM; the owner's ask 2026-11-21: "make the
# logic ask for more exact items"). Its blue blocks (Obj_SongOfTimeBlock_A_01) are in these areas' maps and no others
# (actors.py): the Sacred Forest Meadow (8), the Gerudo Training Ground (7), the Spirit Temple, the Ice Cavern and the
# Fire Temple (3 each), the Forest Temple and Ganon's Castle (1 each). None in the Water or Shadow Temple, none in the
# rest of the overworld. So with the door open an adult's place asks for the song only in those areas (the Forest
# Temple's way in is the meadow's), and the Ice Cavern, which kept only the Lullaby, asks for it too. (Adult Mido in
# the Lost Woods stands aside for Saria's Song, Npc_Kokiri_Mido_Adult_OcarinaReactionStop: the meadow keeps it.)
TIME_BLOCK_AREAS = frozenset(("SacredForestMeadow", "GerudoTrainingGround", "SpiritTemple", "IceCavern", "FireTemple", "ForestTemple",
                              "InsideGanonCastle"))
TIME_BLOCKS_FROM = 19
TIME_BLOCKS = False   # (main sets it: placement >= TIME_BLOCKS_FROM)
DOOR_SONGS = {"ForestTemple": frozenset((_SARIA, _TIME)), "FireTemple": frozenset((_TIME,)), "IceCavern": frozenset((_ZL,)),
              "WaterTemple": frozenset((_ZL, _TIME)), "ShadowTemple": frozenset((_TIME,)), "GerudoTrainingGround": frozenset((_TIME,))}


def door_away(data, door=True):
    """A map file with the Door of Time put far under the map (DOOR_AWAY) and Sheik to the side of the sword's room
    (DOOR_SHEIK_ASIDE): (the file written anew, or None when it has neither; how many doors; how many Sheiks). Its
    other fields are as they were. door False: Sheik alone (the door by the Song of Time, DOOR_SONG: the game's side
    takes the door away)."""
    tree, version = byml_parse(data)
    actors = tree[1].get("Actors")
    actors = actors[1] if actors and actors[0] == "array" else ()
    doors = sheiks = 0
    spots = set()   # (the places Sheik's links name: their hashes)
    for actor in actors:
        links = actor[1].get("Links")
        if actor[1].get("Gyaml", ("", ""))[1] == DOOR_SHEIK and links and links[0] == "array":
            spots.update(link[1]["Dst"][1] for link in links[1] if "Dst" in link[1])
    for actor in actors:
        at = actor[1].get("Translate")
        name = actor[1].get("Gyaml", ("", ""))[1]
        spot = name.startswith(DOOR_SHEIK_SPOT) and actor[1].get("Hash", ("", None))[1] in spots
        if (not ((door and name == DOOR_ACTOR) or name == DOOR_SHEIK or spot) or not at or at[0] != "array" or len(at[1]) != 3 or
                any(not isinstance(v[1], bytes) or len(v[1]) != 4 for v in at[1])):
            continue
        axis, by = (1, -DOOR_AWAY) if name == DOOR_ACTOR else (2, DOOR_SHEIK_ASIDE)
        at[1][axis] = (at[1][axis][0], struct.pack("<f", struct.unpack("<f", at[1][axis][1])[0] + by))
        doors += name == DOOR_ACTOR
        sheiks += name == DOOR_SHEIK
    return (byml_build(tree, version) if doors or sheiks else None), doors, sheiks


def door_need(need, adult_only, open_forest=False, area=None, song=False, sword_asked=True):
    """what a place asks for with the Door of Time open (see above): `need` as the other settings made it;
    adult_only: only an adult has the place; open_forest: Open forest exit is on too; area: the place's (its Banc
    folder), for the dungeons gone through one by one"""
    if not adult_only:
        return need
    sword = {MASTER} if MASTER_SHUFFLED and sword_asked else set()   # (Shuffle the Master Sword: an adult's place asks for it; not where its own rule says, SWORD_FROM)
    if not need >= ADULT:
        return frozenset(need) | sword
    free = {BM}
    if "Item_Scale_Gold" not in need and area not in DOOR_SCALE:
        free.add(SSC)
    if open_forest:
        free.update((S, SL, DS))
    if area in DOOR_NO_BOMBS:
        free.update((BB, BR))
    if area in DOOR_SONGS:
        free.update({_ZL, _SARIA, _TIME, _STORMS} - DOOR_SONGS[area])
    if TIME_BLOCKS:   # (placement 19: the Song of Time where its area has blocks, and only there)
        if area in TIME_BLOCK_AREAS:
            free.discard(_TIME)
        else:
            free.add(_TIME)
    return frozenset(need - free) | ({_TIME} if song else frozenset()) | sword   # (DOOR_SONG: the door opens by the Song of Time)
FLAG_LIST = "GameData"   # (the folder of the romfs: GameDataList.Product.<n>.byml.zs in it)
# The clock of Hyrule Field. Until the owl's first cutscene there, the field's sky stays the day's whatever the time is
# set to: no day turns to night, and the Sun's Song's night is day again at once (seen in play). What ends it is the
# flag HyruleField_ArriveEntrance, the first thing the owl's event sets (the flow Goto_HyruleCastle, its entry
# Goto_HyruleCastle_Kaepora_00). Found with a save made before the owl and runs without a window: a night asked for
# stayed day at the forest's way out and far in the field; with the flag set first, it was night and stayed so; and
# with the flag set the owl's event began all the same when Link walked on (it is not what starts it).
# A seed can give the Sun's Song before the owl is met, and a way out of the forest that does not pass the owl leaves
# the sky so for good: so every seed's new game starts with the flag set (FIELD_CLOCK, in the list of flags), and the
# game's side sets it for a save that has it put out (host/hos_main.c).
# Tried first, and left: the flag HyruleField_ChangeENV, which leaving the forest sets and the owl's event puts out. It
# chooses the field's time table of palettes (WorldParam HyruleField_Child: ConditionEnvTimePalette) and is not what
# holds the day: with its step passed over the song failed as before.
FIELD_CLOCK = {"HyruleField_ArriveEntrance": True}
# The areas' first-visit intros (bug 66, asked 2026-11-17): a camera flyover and the area's title, the first time Link
# comes in (Dm_<area>_0000, e.g. Death Mountain Crater's from Goron City). They have no talk, so quiet_scene leaves them.
# With Skip cutscenes on, a new game starts with each one's HavePlayedEvent set, so none plays (REALAZK's OOTRR does the
# same, start_state.rs FIRST_VISIT). Left out, as each does more than show the place: the Forest Temple's (it moves its
# quest a step), the Water, Shadow and Spirit Temples' (each sets a flag of its own: the lake's pillars, rooms), and
# the Deku Tree's, Zora's Domain's and the Desert Colossus's arrivals (a quest step follows them). Read elsewhere, and
# harmless when set early: Gerudo Valley's (a common logic's event, with the Deku Tree done), Zora's River's (the
# owl's event waits for it), Goron City's (a Goron's talk branch).
# Also left out, found 2026-11-18 (bug 64): Death Mountain Trail's and Goron City's. A map picks the first-visit
# arrival by the intro's flag (Kakariko's maps for the trail, Death Mountain Trail's for the city), and only that
# arrival takes the Goron's Ruby quest a step (Dm_SY_BancChangeArrive's DeathMountainTrail_Arrive and
# GoronCity_InitDemo_Arrive call Get_StoneOfFire's DeathMtTrailIn and ArriveCity): with the flag set the quest would
# stay a step behind. Every other arrival that leads into an intro was read: none takes a step (the Crater's sets its
# first-entry flag and Navi's warning after the intro, whatever the intro does).
AREA_INTROS = {"HavePlayedEvent.Dm_%s_0000%s" % (n, x): True for n, x in (
    ("DeathMtCrater", ""), ("DeathMtCrater", "_FromTop"), ("DodongoCave", ""), ("FireTemple", ""),
    ("GanonCastle", ""), ("InsideGanonCastle", ""), ("GerudoValley", ""), ("Gerudo", ""),
    ("Graveyard", ""), ("HrlCastle", ""), ("Kakariko", ""), ("LakeHrl", ""), ("SacredForest", ""), ("TimeTemple", ""),
    ("ZoraFountain", ""), ("ZoraRiver", ""))}
# With Skip cutscenes, the small things picked up over and over (rupees, a heart, magic jars, arrows and Deku Seeds) come
# without the first time's "You got" box: the scene of each is marked played (HavePlayedGetEvent.<actor>) in a new game.
# The other randomizer's setting (OOTRR 43d29e1, "Skip first pickup text"), with its list. Not the bags' first ones
# (Item_Bomb, Item_DekuNut, Item_DekuStick: their scene gives the bag), nor a chest's or a gift's (their own scenes).
FIRST_PICKUPS = {"HavePlayedGetEvent." + n: True for n in (
    "Obj_Rupee_Green", "Obj_Rupee_Blue", "Obj_Rupee_Red", "Obj_Rupee_Purple", "Obj_Heart", "Obj_MagicJar_Small",
    "Obj_MagicJar_Large", "Obj_ArrowBundle_Small", "Obj_ArrowBundle_Medium", "Obj_ArrowBundle_Large", "Obj_DekuSeed")}
# (the owner's test, 2026-11-21) A new game that starts with the Deku Stick or the Deku Nut bag (Starting items DK, DN)
# has its bag already: the first stick's or nut's box, whose scene gives the bag in an ordinary game, then only says so
# again. With Skip cutscenes it is marked played too, for the starting bag only (START_PICKUPS)
START_PICKUPS = {"DK": "HavePlayedGetEvent.Item_DekuStick", "DN": "HavePlayedGetEvent.Item_DekuNut"}
# (bug 123, the owner's run 2026-11-23) A small arrow bundle from a pot showed "You got" each time, with Obj_ArrowBundle_Small's
# scene marked played (FIRST_PICKUPS). The pick-up's event AI (AI/PouchContent.event.root.ainb) names Item_Arrow_Normal with
# it: the arrows' own scene, which a game whose Bow came from the shuffle never played (the owner's save: 0; the finished
# story's, played the game's way: 1). Every new game of a seed has it marked played, Skip cutscenes or not.
SHUFFLED_FIRSTS = {"HavePlayedGetEvent.Item_Arrow_Normal": True}
# The HUD of the d-pad's items (Navi and the boots, by the hearts). A new game has none of it until the first scene in
# the Deku Tree; with a seed's items found long before that, the owner asked for it from the start. What shows it is a
# flag of the list that no event, AI or logic file names: only its hash is known (no string of the game's files or its
# code hashes to it), so it is given as "#<hash>" (flag_hash). Found from two saves, one from a new game's start and one
# in the Deku Tree: of the 99 truth values they differ in, each set on the first in turn, by halves, without a window,
# this one alone brought the HUD at the next load of the area, and the 98 others did not. It is a plain truth value,
# false in a new game. The game's side sets it for a save that has it put out (host/hos_main.c).
DPAD_HUD = {"#7be57cb0": True}
# The minimap, the same way (2026-11-15: in play it came only after the owl's scenes in Hyrule Field). Another flag no
# file names, found from the same two saves by halving the 98 values left, without a window and on the owner's "All
# Items unlocked" save (a new game's start): 2e315eb6 alone brought the minimap at the next load of an area; the last
# other one, 2e59a755, did not. A seed's new game starts with it set, and the game's side sets it for an older save.
MINIMAP = {"#2e315eb6": True}
# Link's door. A new game's Link is in his house, the door shut until he walks up to it: the scene at the door
# (Dm_Kokiri_0045, the event at it) plays Link's waking (Dm_Kokiri_0050) and sets the door's flag and the scene's own,
# and asks the door's flag first (open: nothing plays). The house's logic (Land_Kokiri_House_A_Prefab) opens the door
# by the same flag. With Skip opening on a new game starts with both set: the door open, nothing at it (asked for by the
# game's owner: the Kokiri Sword given with the Debug tab did as much).
LINK_DOOR = {"KokiriForest_LinkHouseDoor_Open": True, "Dm_Kokiri_0050_After_Near_End": True}
# Starting rupees: the list's whole number PlayerStatus.CurrentRupee is what Link has, 0 in a new game. With the
# setting on a new game starts with START_RUPEES of them (flag_defaults, kind "Int"). A game already begun keeps
# what its save says.
# 200 is what the child's wallet holds in this game (its owner's word; the original's held 99): a full wallet, and not
# more than it can hold.
RUPEES = "PlayerStatus.CurrentRupee"
START_RUPEES = 200
# A new game's opening is the event flow OpeningEvent: two entry points that each play a cutscene and go on. Neither
# cutscene sets anything of the game: Dm_Kokiri_0000 is the narration, Dm_Kokiri_0030 Navi's flight to Link's house.
#   Opening_LoadingKokiriForest: event 7 (plays Dm_Kokiri_0000) -> 14 (is the forest loaded?) -> the fades
#   Opening_Introduction: 5 -> the clock, the first challenge step, the camera -> 23 (a wait) -> 0 (plays
#     Dm_Kokiri_0030) -> 17 (was it skipped?) -> 19 (the fade, Navi beside Link, the camera) -> the music, the autosave
# --skip-intro starts the first at 14 and sends 23 on to 19: what the flow does after each cutscene, without it.
OPENING = "Event/EventFlow/OpeningEvent.bfevfl.zs"
PLAIN_EVENTS = ("KokiriForest_TreasureBox_NaviChatOff",)
# Skip cutscenes, the talks (rando_skip_cutscenes). The game's side skips a cutscene that is a timeline (a flow file of
# one timeline: 98 of the Dm_ scenes). The others (226) are flowcharts: camera moves, waits, animations and talks, with
# what the scene does to the game among them, and the game's skip ends the whole event when asked of one (seen: the
# event began over and over). Saria's first talk (the event KokiriForest_StopInFrontOfLinkHouse plays Dm_Kokiri_0060,
# 12 talks, nothing else) and the owl's (Dm_HrlField_0010, Dm_LostWood_0000, Dm_ZoraRiver_0000...) are such scenes. So
# the seed takes their presentation out of the flowchart (quiet_scene): each step that only shows something
# (SCENE_SHOWS) is passed over, every way into it led to what follows it, and what the scene does stays: flags, items,
# quest steps, the time, fades, warps, other events. A question is passed over only when one of its answers comes back
# to it (the owl's "Do you want to hear it again?", Zelda's "Is there anything else?" of three answers): the other
# answer is taken; any other question stays, with its talk. A branch of a fork, or an entry point, left with nothing goes to one of the scene's own steps that does nothing
# (SCENE_NOTHING, the comments its makers left), so every scene so changed must have one. The scenes are the Dm_
# flowcharts with a talk, less those where the player pays or plays a game (SCENE_KEEP_IF: the Great Fairies, Lon
# Lon's horse, the games) and the Royal Family's Tomb (SCENE_KEEP). The song lessons are taken too (SCENE_LESSON).
SCENE_FLOWS = "Event/EventFlow"
# The videos (Event/Movie, a player of their own: the game's skip, asked of one, did nothing, and nor did the buttons;
# seen without a window). Seen in the owner's play: the goddesses' story in Zelda's courtyard played whole. Each is
# started by one step of another flow (an EventTransition naming it) and sets nothing itself (its file is one
# timeline), so the seed passes over that step (pass_videos). These are the story's; kept: the title's, the credits',
# the opening narration (Skip opening) and the ending's. The Royal Family's Tomb's sunrise after the Sun's Song's lesson
# (Dm_MelodyGet_Sun_01, _04 to _10: one by Link's age, the time of day and the story, GimmickFlow_RoyalFamilyTomb) is left
# out too (bug 61): the step after each sets the time as the video would have, then the lesson's gift (Dm_MelodyGet_Sun_03).
# (the owner's run 2026-11-23: after Volvagia's blue warp Link stood frozen in Kakariko. Dm_Kakariko_0025 is the video the
#  Fire Temple's way out plays on arrival in Kakariko (Dm_SY_BancChange_EscapeDungeon's FireTemple_SageOfFire_Kakariko),
#  and the step after it reserves the change to the Chamber of Sages (Darunia's medallion): with the video passed over,
#  that change never came. It plays again from fixes 76: SCENE_VIDEOS_KEPT)
SCENE_VIDEOS_KEPT = ("Dm_Kakariko_0025",)
SCENE_VIDEOS = ("Dm_HrlCastle_0045", "Dm_Kokiri_0095", "Dm_Kokiri_0160", "Dm_LostWood_0021",
                "Dm_TimeTemple_0095", "Dm_TimeTemple_0115") + tuple("Dm_MelodyGet_Sun_%02d" % n for n in (1, 4, 5, 6, 7, 8, 9, 10))
SCENE_SHOWS = frozenset((
    "EventTalk", "EventTalkIgnoreSameTalkAS", "EventWait", "EventMoveCameraAnimationInstructionsForFlowchart", "EventMoveToTargetPosCamera",
    "EventPlayAS", "EventPlayASWithClothWarp", "EventPlayASWithRate", "EventPlayerPlayASForFlowchart",
    "EventTriggerEmitXLink", "EventTriggerXLinkFadeByKey", "EventSetAdvancedDoFForFlowchart", "EventSetDoFForFlowchart",
    "EventTriggerControllerRumble", "EventNorifyCutChangeForGraphics", "EventNaviMoveAroundToPlayer",
    "EventNaviLookAtObject", "EventTriggerPlayerLookAtObject", "EventTriggerLookAtObject", "EventLookAtObjectImmediate",
    "EventTriggerRequestLookAtTheFront", "EventTriggerPlayerRequestLookAtTheFrontLock", "EventNaviRequestLookAtTheFront",
    "EventPlayerTurnAndLook", "EventPlayerTurnAndLookNow", "EventNPCTurnToTarget", "EventTriggerChangeEmotion",
    "EventTriggerEmitNpcOrPlayerVoice", "EventSoundStartSound", "EventNaviRequestBallonMessage",
    "EventTriggerRequestCameraShake", "EventNodeEffectEmit", "EventCloseMessageDialog", "EventPlayerPlayOcarinaFree"))
# An animation that moves its character is no show (bug 88, the owner's run 2026-11-19): King Zora given Ruto's Letter
# moves aside by his animation C10 (Dm_Zora_0010's entry C10, IsAnimeDriven: the animation carries him), and without it
# he stayed in the way until the map was loaded again. Kept, by (the actor, the animation's name).
SCENE_MOVES = frozenset((("Npc_Zora_KingZora_child", "C10"),))
# A scene's own music is shown too (bug, the owner's run 2026-11-20): the owl's first scene in Hyrule Field
# (Dm_HrlField_0010) starts its music (EventTriggerStartBgmSimple, BGM_Dm_HrlField_0005, CommandLife 2: the event's), which
# its talk's end let go in the game. Quieted, the scene ended at once and the owl's music played on, across areas, the
# title and a new game. So a scene's music for the event (CommandLife 2: 91 of the game's 99) is passed over with the
# talks; one that lasts (CommandLife 0: an area's music changed) stays, as do the steps that stop music or bring the
# area's back.
SCENE_MUSIC = ("EventTriggerStartBgmSimple", 2)
SCENE_SHOWS_SUB = ("Common_Camera_Pln",)   # (sub-flows of these flows only set the camera's focus)
# A song lesson (Dm_MelodyGet_...): the teacher plays the song, Link plays it back, the ocarina plays it by itself (the
# ocarina's own flow, these entries), then the lesson's gift step gives what the lesson gives (GetPouchContent, its item
# made the shuffle's as a gift's is). The auto-play adds the song too (made the lesson's item, SONG_PLAY_FLOW), but every
# lesson but the Royal Family's Tomb's has its own gift step, and none asks how the playing went (looked at: their
# questions are of the pouch, flags, places). So in a lesson the three are passed over with the talk, and Link's free
# playing (EventPlayerPlayOcarinaFree): the lesson goes to "You learned..." (asked for by the game's owner, 2026-11-15).
SCENE_LESSON = (("Dm_SY_Ocarina", "LearningOcarinaPlayExample"), ("Dm_SY_Ocarina", "LearningOcarinaFollowExample"),
                ("Dm_SY_Ocarina", "LearningOcarinaPlayAuto"), ("Dm_SY_Ocarina", "LearningOcarinaPlayAutoForSeek"))
# (bug 61, 2026-11-18: the Royal Family's Tomb's lesson, Dm_MelodyGet_Sun, kept before, is quieted as the others are: its
# gift is the scene after it, Dm_MelodyGet_Sun_03, and its auto-play's add of the song was a stray green rupee in play)
SCENE_KEEP = ()
# Scenes with no talk and no gift taken all the same (bug 60): the royal tomb's opening after Zelda's Lullaby on the
# Triforce mark (camera moves and Link's poses; its flag GraveYard_RoyalFamilyTomb_Open and warps stay).
SCENE_SILENT = ("Dm_Graveyard_0010",)
# A lesson also calls entry points of the story's flows: Sheik's words before the Requiem and the Prelude are in AllSage
# (MelodyOfSpirit_01/_02, MelodyOfShine: a switch on the Shadow Temple's quest step, then the talk), the windmill man's
# after the Song of Storms in his own flow. Seen in play: Sheik's three lines before "You learned...", at the Colossus.
# Those entry points are quieted too, only what they come to (quiet_scene's entries); the flows they are in are not.
SCENE_LESSON_SKIP_CALLS = ("GetPouchContent", "Dm_SY_Ocarina", "Common_Camera_Pln")
# Characters who stop Link as he walks past (an EventRequestActor in the map starts an entry of their own flow), quieted
# as those entry points are. Seen in play 2026-11-15: a Kokiri girl in front of the Kokiri shop, "So that was your
# fairy who flew past me earlier" (Npc_Kokiri_011_Child, KokiriForest_Kokiri_011_StopInFrontOfShop_00).
SCENE_STOPS = {"Npc_Kokiri_011_Child": ("KokiriForest_Kokiri_011_StopInFrontOfShop_00",)}
# A scene that gives an item and has no talk (Saria's ocarina after her goodbye, Dm_Kokiri_0155; Zelda's Light Arrows,
# Dm_TimeTemple_0130) is taken too: its presentation goes and its gift stays (seen in play: the ocarina's scene played
# whole after the goodbye's was skipped).
SCENE_GIFTS = ("GetPouchContent", "Dm_SY_GetInEvent")   # (the Royal Family's Tomb: its gift is a scene of its own, Dm_MelodyGet_Sun_03, after the tomb's play)
SCENE_NOTHING = ("EventDemoProductSupportComment", "EventDoNothing")
SCENE_CHOICE = ("EventQueryTalkChoice2", "EventQueryTalkChoice3", "EventQueryTalkChoice4")
SCENE_KEEP_IF = ("EventWaitForKeyInput", "EventOpenDoCommand",
                 "RupeeDisplay", "EventTriggerSkipAcceptStart", "EventRequestQuit", "Dm_FairyFountain_",
                 "EventTriggerRequestRideMe", "MiniGame")
# The Kokiri Sword's chest starts an event of its own (GetSword, of the flow below): the chest is opened
# (Dm_SY_Treasurebox, as every chest's), then Link puts the sword on his back (Dm_Kokiri_0063), then Navi speaks if
# Mido is still in the way. With another item in the chest the second still played: Link put a sword on his back
# that he did not have, and could use it until the next load, with none in the inventory (seen in play). So where
# the chest holds another item the event goes from the first cutscene to what follows the second (sword_chest_plain).
SWORD_EVENT = "Get_StoneOfForest_GetSword"
SWORD_FLOW = "Event/EventFlow/Get_StoneOfForest.bfevfl.zs"
DUNGEON_ITEMS = ("Item_Dungeon_SmallKey", "Item_Dungeon_BossKey", "Item_Dungeon_Map", "Item_Dungeon_Compass")
# ---- Maps and compasses (rando_maps, asked 2026-11-23; share/dungeon-items-plan.md) ----
# 0 with the keys (Dungeon keys' setting, as before), 1 Anywhere, 2 From the start. The save keeps each dungeon's own
# DungeonInfo.<its Banc folder>.IsGetMap / IsGetCompass (and SmallKeyNum, IsGetBossKey); a chest's map or compass is one
# item for every dungeon, counted by the pouch for the dungeon Link is in.
# From the start: every dungeon's two flags start set (MAPS_START, the list of flags' defaults) and the chests that held
# them hold rupees instead (MAPS_START_JUNK), which join the shuffle as any chest's item.
# Anywhere: they go to any chest of the shuffle (not a gift, a shelf, a Skulltula or a piece: what gave it is then always
# a chest), and each is told the dungeon it belongs to in DUNGEON_ITEMS_FILE (a chest's hash, the dungeon, the item):
# the game's side, at a dungeon item's add from a chest of that file in another place than its dungeon, takes the add
# away and sets that dungeon's flag (host/hos_main.c oot_dungeon_item). Maps and compasses gate nothing: no rule asks.
MAP, COMPASS = "Item_Dungeon_Map", "Item_Dungeon_Compass"
DUNGEON_FOLDERS = ("InsideTheDekuTree", "DodongoCavern", "InsideJabuJabuBelly", "BottomOfTheWell", "ForestTemple", "FireTemple",
                   "IceCavern", "WaterTemple", "ShadowTemple", "SpiritTemple", "GerudoTrainingGround", "InsideGanonCastle")
MAPS_START = {"DungeonInfo.%s.%s" % (d, f): True for d in DUNGEON_FOLDERS for f in ("IsGetMap", "IsGetCompass")}
MAPS_START_JUNK = {MAP: "TBox_Rupee_Red", COMPASS: "TBox_Rupee_Blue"}
MAPS_LOOSE = frozenset((MAP, COMPASS))
DUNGEON_ITEMS_FILE = "dungeon_items.txt"
# ---- Boss Keys (rando_boss_keys, asked 2026-11-23; share/dungeon-items-plan.md stage 2) ----
# 0 with the keys (as before), 1 Anywhere: a dungeon's Boss Key can be in any chest of the game, told its dungeon in
# DUNGEON_ITEMS_FILE as a map is (the game's side sets DungeonInfo.<folder>.IsGetBossKey). The rules stand for "a
# dungeon done" by the items it takes (MEDALS3 and the like), not by its Boss Key: so a Boss Key goes only to a chest
# whose rule its own boss's rule already covers (boss_key_fits: one of the chest's ways within what the dungeon's ending
# asks for, boss_need), and never a dungeon's own key behind another dungeon done. Ganon's Castle's asks for everything:
# it may be anywhere. While the shuffle places them each is an item of its own, BOSS_KEY "@" its dungeon (boss_key_tag);
# the tag is taken off before anything else reads the items. The Tracker's rules do not name them (no letters).
BOSS_KEY = "Item_Dungeon_BossKey"
# (found 2026-11-24 with Boss Keys: Anywhere: the Water Temple's own Boss Key went to the chest below, there only once
#  that temple is done.) Lake Hylia's "Chest (red rupee) #1" is a remake change, there once the Water Temple is beaten
# and the lake filled (overworld_own.json: is_adult and 'Water Temple Clear'); the overworld table's run gave it no
# item at all (the engine's event counted as had). From placement AFTER_WATER_FROM it asks for the Water Temple's
# ending's rule too (boss_need), so nothing it needs to get there lies in it.
AFTER_WATER = (0xec3f782c547551a1,)
AFTER_WATER_FROM = 29
# ---- Small keys: Anywhere (Dungeon keys' third choice, rando_keys 2; share/dungeon-items-plan.md stage 3) ----
# Each dungeon's small keys in chests are items of the shuffle (SMALL_KEY "@" its dungeon "#" a number, key_tags), told
# their dungeon in DUNGEON_ITEMS_FILE as a map is (the game's side raises DungeonInfo.<folder>.SmallKeyNum). The dungeon
# rules are worked out with the keys where the game has them, so they never ask for one: tools/rando/dungeon_keyless.py
# found which dungeon checks are reached with no small key at all (KEYLESS_FILE); every other check of a dungeon with
# keys that move asks for all of them (too much, never too little). The rules stand for "a dungeon done" by its items, not
# its keys: so a dungeon's keys go only where its ending's rule reaches, with its own keys (boss_key_fits, as the Boss
# Keys), and the other spots' keys are kept out of them. With Small keys: Anywhere, the Boss Keys and the maps and
# compasses left "With the keys" are anywhere too. The Tracker's rules do not name the keys (no letters).
SMALL_KEY = "Item_Dungeon_SmallKey"
# ---- Pots (rando_pots, "Potsanity", asked 2026-11-23; share/todo.md) ----
# The pots the logic's tables know (POT_TABLES' actors of kind "pot": a house's, a grotto's, a dungeon room's, 67 in all)
# take part as a Gold Skulltula does: each a spot holding its own item (POT_OWN, a Deku Nut bundle) in the pool, giving
# what a Gold Skulltula may drop (skull_may), by the rule its table gives it (heart_asks, as a piece lying in the world,
# over its actor's hash). Its map's pot drops that item (add_drop: Drop__DropActor; its random Drop__DropTable taken
# away), and the Tracker has it as "Pot". A pot is back after about a day (bug 96): the game's side gives its item once
# (host/hos_main.c oot_pot_again: a pot's check collected, the same item picked up by it again is nothing). Only the pots
# the tables rule: the others' rules would be guesses, and the Tracker keeps CHECK_ROWS checks.
POT_OWN = "TBox_DekuNutBundle"
POT_TABLES = ("overworld_rules.json", "dungeon_rules.json")


def pot_actors():
    """{a pot's actor hash: its folder} of the logic's tables (POT_TABLES, kind "pot"); {} without them"""
    out = {}
    here = os.path.dirname(os.path.abspath(__file__))
    for name in POT_TABLES:
        try:
            with open(os.path.join(here, name), encoding="utf-8") as f:
                table = json.load(f)
        except (OSError, ValueError):
            continue
        rows = table.get("by_actor") or next(iter(table.get("variants", {}).values()), {}).get("by_actor", {})
        for h, e in rows.items():
            if e.get("kind") == "pot":
                out[int(h)] = e.get("folder")
    return out
KEYLESS_FILE = "dungeon_keyless.json"


def key_tags(spots, which=3):
    """{a chest's hash: its small key's own name for the shuffle} of the chests in a dungeon (DUNGEON_FOLDERS) holding one
    that take part (no reason to stay, s[3]; dungeon chests with the Chests setting's, which), numbered in each dungeon by
    hash; spots: hash -> [area, item, a dungeon's, why it stays, its kind (Obj_TBox...), ...]. A key that stays is the
    game's, got where it lies (a key of the shuffle there would need itself)."""
    out, count = {}, collections.Counter()
    for h in sorted(spots):
        s = spots[h]
        if s[3] or which == 1 and s[2]:
            continue
        if s[1] == SMALL_KEY and str(s[4]).startswith("Obj_TBox") and s[0] in DUNGEON_FOLDERS:
            count[s[0]] += 1
            out[h] = "%s@%s#%d" % (SMALL_KEY, s[0], count[s[0]])
    return out


def keyless_actors():
    """the dungeon checks' actors (hashes) reached with no small key (KEYLESS_FILE); an empty set without it"""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), KEYLESS_FILE), encoding="utf-8") as f:
            return frozenset(int(h) for h in json.load(f)["keyless"])
    except (OSError, ValueError, KeyError):
        return frozenset()


def boss_key_tag(folder):
    """the shuffle's own name for a dungeon's Boss Key"""
    return "%s@%s" % (BOSS_KEY, folder)


def boss_key_fits(need, cap):
    """whether a chest of this rule may hold a Boss Key whose boss asks for cap (a frozenset; None: anything)"""
    if cap is None:
        return True
    if need is None:
        return False
    return any(isinstance(way, frozenset) and way <= cap for way in (need if isinstance(need, Either) else (need,)))


def dungeon_owners(rng, spots, gives, loose):
    """{a chest's hash: the dungeon (its area) the dungeon item it now gives belongs to} for the items of `loose` the
    shuffle moved: each copy's dungeon is one of the chests that held that item before (spots: hash -> [area, item, ...]),
    the same number for each dungeon; which copy is which does not matter (they gate nothing)."""
    out = {}
    for item in sorted(loose):
        was = sorted(spots[h][0] for h in gives if spots[h][1] == item)
        now = sorted(h for h in gives if gives[h] == item)
        if len(was) != len(now):
            raise ValueError("%s: %d were in the shuffle and %d are given" % (item, len(was), len(now)))
        rng.shuffle(was)
        out.update(zip(now, was))
    return out
Chest = collections.namedtuple("Chest", "hash gyaml dyn_where dyn_at item params pos event")

# ---- the logic: what Link needs before a chest can be opened ----
# Thirteen items gate the game and come from chests. Everything else that gates it (songs, the Ocarina, the Hookshot
# from Dampe's race, tunics, magic, bottles, the stones and medallions) stays where the game has it, so it is folded
# into the rules below: "ADULT" stands for all it takes to pull the Master Sword, and so on.
# The rules are by area, with exceptions for chests known by their event. They are written from the original game's
# layout and are meant to ask for too much, never too little: a chest whose place in the remake is not known asks for
# what its whole area can ask for, and an area that is not known asks for everything, so it only ever gets items the
# game can be finished without. They have NOT been checked against the remake chest by chest.
S, SL, BB, BM = "Item_Sword_Kokiri", "Item_Range_SlingShot", "Item_BombBag_Small", "Item_Boomerang"
LENS, BOW, HAM, IRON = "Item_GlassTruth", "Item_Range_Bow", "Item_Hammer", "Item_HeavyBoot"
HOVER, LONG, SG, MS, GG = "Item_HoverBoot", "Item_Longshot", "Item_Gauntlet_Silver", "Item_Shield_Mirror", "Item_Gauntlet_Gold"
PROGRESSION = frozenset((S, SL, BB, BM, LENS, BOW, HAM, IRON, HOVER, LONG, SG, MS, GG))
THIRTEEN = PROGRESSION   # (the thirteen, as they are here: main adds a seed's other gating items to PROGRESSION)
NONE = frozenset()
# Found in play: bombs cannot be used before Darunia gives the Goron's Bracelet (the original game has no such tie).
# No rule asks for bombs alone: each that names BB also names the sword and the Slingshot, with which Link is out of
# the forest and can get the bracelet (Zelda's Lullaby, Saria's Song, Darunia). A rule that asks for BB below that
# would have to ask for those too.
CHILD = frozenset((S, SL))                 # out of the forest: the Deku Tree done
ADULT = frozenset((S, SL, BB, BM))         # the three stones: Dodongo's Cavern (bombs) and Jabu-Jabu (Boomerang) done
MEDALS3 = ADULT | {BOW, HAM, IRON, LONG}   # the Forest, Fire and Water Temples done: the way to the Shadow Temple
DESERT = ADULT | {LONG, HOVER, LENS}       # across the Haunted Wasteland
# area (the Banc folder): (what its chests ask for, {a chest's event: what that chest asks for})
RULES = {
    "KokiriForest": (ADULT, {"KokiriForest_TreasureBox_NaviChatOff": NONE, "Get_StoneOfForest_GetSword": NONE}),
    "InsideTheDekuTree": (frozenset((S,)), {}),
    "DodongoCavern": (CHILD | {BB}, {"DodongoCavern_GetMap": CHILD, "DodongoCavern_GetCompass": CHILD, "Get_StoneOfFire_GetBombBag": CHILD}),
    "InsideJabuJabuBelly": (ADULT, {"InsideJabuJabuBelly_TreasureBoxWithRuto09": CHILD | {BB}}),
    "BottomOfTheWell": (ADULT | {LENS}, {"BottomOfTheWell_GetGlassTruth": ADULT, "BottomOfTheWell_GetCompass": ADULT}),
    "ForestTemple": (ADULT | {BOW}, {"ForestTemple_GetBow": ADULT, "ForesetTemple_GetMap": ADULT}),
    "FireTemple": (ADULT | {HAM, BOW}, {"FireTemple_GetHammer": ADULT}),
    "IceCavern": (ADULT, {}),
    "WaterTemple": (ADULT | {IRON, LONG, BOW}, {"WaterTemple_Room07_LongHook_FocusOnGimmick": ADULT | {IRON}}),
    "ShadowTemple": (MEDALS3 | {LENS, HOVER}, {"SageOfShdawo_GetHoverBoots": MEDALS3 | {LENS}}),
    "SpiritTemple": (DESERT | {SG, BOW, MS}, {}),
    "DesertColossus": (DESERT | {SG, BOW, MS}, {"SageOfSpirit_NaboorIsTakenAway": DESERT, "SageOfSpirit_GetShield": DESERT | {SG}}),
    "GerudoTrainingGround": (MEDALS3 | {LENS, HOVER, SG}, {}),
    "InsideGanonCastle": (PROGRESSION, {"InsideGanonCastle_Get_Gauntlet_Gold": PROGRESSION - {GG}}),
    # the overworld: where a chest is in the remake is not known, so each asks for what its area's hardest chest did
    "HyruleField": (ADULT | {HAM}, {}), "KakarikoVillage": (ADULT, {}), "Graveyard": (ADULT, {}), "LostWood": (ADULT, {}),
    "SacredForestMeadow": (ADULT, {}), "DeathMountainTrail": (ADULT, {}), "DeathMountainCrater": (ADULT | {HAM}, {}),
    "GoronCity": (ADULT | {HAM, SG}, {}), "ZoraRiver": (ADULT, {}), "ZoraDomain": (ADULT, {}), "ZoraFountain": (ADULT | {IRON}, {}),
    "GerudoValley": (ADULT | {HAM, LONG}, {}), "GerudoFortress": (ADULT | {HOVER, LONG, BOW}, {}),
    "HountedWasteland": (DESERT | {BOW}, {}),
}


# ---- Quest rewards: the gifts that take part, and what they add to the rules ----
# With Quest rewards on, what some characters give takes part with the chests: a gift is a spot like a chest, its
# item goes into the pool and the scene gives what the shuffle put there (gift_items). Which scenes, who gives and what
# each asks for were gone through with the game's owner (the list of every gift of the game's flows, 164 lines, and
# the answers: <game folder>\rando\gifts_to_check.txt).
# Two of the gifts' items gate the game, so with the setting on they are gating items too (QUEST_GATES) and the rules
# name them (quest_need): the Goron's Bracelet, without which bombs cannot be used (found in play) nor Dodongo's
# Cavern entered, and the Silver Scale, for Ruto's Letter at the bottom of Lake Hylia, so for Jabu-Jabu and all that
# an adult does. Off, they are where the game has them and the rules are as they were: the seeds made before keep
# their shuffle.
# NOT in the shuffle yet, each for a reason found in its flow (they stay as the game has them):
#   the Great Fairies of magic and   ask "has Link got my item" (IsGet.Item_...): another item would be given at
#   defence (three)                  every visit, and theirs found elsewhere would shut the fountain (the three of
#                                    the spells take part from placement 14 as the lessons do: FAIRY_GIFTS)
#   Biggoron's Sword, the lake       the same (Weapon_Sword_Giant; Item_Scale_Gold)
#   scientist's Piece of Heart
#   the two ocarinas                 put in the pouch by the scene itself, not through the gift's flow
#   the Gerudo's card                many scenes ask for it: to be looked at
#   Dampe's Piece of Heart           is dropped from the hole as an actor of its own, then picked up
BR, SSC = "Item_Gauntlet_Goron", "Item_Scale_Silver"
QUEST_GATES = frozenset((BR, SSC))
# The tunics (bug 65, placement 12): the adult rolling Goron's Goron Tunic and the thawed King Zora's Zora Tunic are
# gifts of the shuffle. Read in their flows (2026-11-18): each is given once, on its own story's path (SageOfFire's
# rolling Goron stopped, a quest step; SageOfWater's first talk after the thaw, which sets
# SageOfWater_KingZora_adult_Talk_Event198); the flows' questions of the pouch (Armor_Adult_Goron, Armor_Adult_Zora)
# only choose Navi's hints and which branch of the Ice Cavern's Serenade lesson plays, both of which give the song.
# (The note here before said they asked the pouch for the gift: it was not so.) In the remake heat and deep water hurt
# Link slowly, with no timer (the owner, 2026-11-17), so the rules ask for the tunics (TUNIC_AREAS: an adult's checks
# there, and every rule that has the Fire and Water Temples done). Not the Ice Cavern (asked for with a "?"; its water
# is short). Hard logic, later, may leave them out (the owner, 2026-11-18; not yet tried in play).
GT, ZT = "Obj_Armor_Goron", "Obj_Armor_Zora"
TUNICS = frozenset((GT, ZT))
TUNIC_AREAS = {"DeathMountainCrater": GT, "FireTemple": GT, "WaterTemple": ZT, "ZoraFountain": ZT}
# From placement 17 (TUNIC_WATER_FROM, the owner's ask 2026-11-21 "make the logic more accurate"), checked against the
# game's own data. Heat: each dungeon's rooms are marked hot in Scene/Component/DungeonParam (EnvParamFile
# ScorchingRoom): Death Mountain Crater's whole field (its grottos and the Great Fairy's fountain are not, but are
# reached through it), Fire Temple rooms (the temple is reached through the crater), the Gerudo Training Ground's rooms
# 4 and 6, Ganon's Castle's room 10, Volvagia's. All already ask for the Goron Tunic: the crater and the Fire Temple
# by TUNIC_AREAS, the others by every rule past the Fire and Water Temples. No other place is hot (Dodongo's Cavern,
# Goron City and the trail are not). Deep water has no mark of its own: it is where the Iron Boots sink Link. So from
# 17 a way of a rule that asks for the Iron Boots asks for the Zora Tunic too (deep_need), which adds Lake Hylia's lab
# tank Gold Skulltula (it asked for the boots alone), and Zora's Fountain leaves TUNIC_AREAS: only its Piece of Heart
# at the bottom (70.9 m; the others stand at 103-133 m, on the ice and the shore) asks for the boots and the tunic.
# Its purple rupee chest and its Piece of Heart on the ice ask for an adult alone (TUNIC_DRY), not its area's boots.
# The "ColdRoom" mark (the Ice Cavern, adult Zora's Domain and Fountain while frozen, two of Ganon's Castle's rooms) is
# not a tunic's: the original asks for none there, and the owner has met no harm from cold.
TUNIC_WATER_FROM = 17
TUNIC_DRY = {0xd0ee852c5e8a8bea: ADULT, 0xac2e26b5ec7da3a2: ADULT}   # (Zora's Fountain: the purple rupee chest; Piece of Heart #2)
CHILD_BOMBS = CHILD | {BB}   # (with the bracelet too, until a bomb was lifted without it: bomb_lift)
GROWN = ADULT | QUEST_GATES
Gift = collections.namedtuple("Gift", "key flow olds item area name need when entry", defaults=(None,))
# key: its name in the seed (never changed: a gift's place in the shuffle). flow: the scene's flow. olds: the items
# the flow names for this gift (a prize of sizes names two: the one Link has not got yet is given); each is made the
# gift's new item. item: what goes into the pool for it. area: the Banc folder its rules and the tracker count it in.
# need: what Link needs (meant to ask for too much, never too little; where the way to it is not known in the terms of
# the rules it asks for everything: such a gift only ever holds what the game can be finished without).
# when: None, or the setting of its own it waits for ("frogs", "light"; "scrubs": Deku Scrubs, which does not wait
# for Quest rewards). entry: None, or the one entry point of the flow whose calls are the gift's (two sales of one
# flow that name the same item: the Business Scrubs' two Pieces of Heart), or a tuple of them (the frogs' game).
# (a gift added after seeds were made takes part from the placement that added it: the seeds before keep their shuffle)
# The Golden Scale a gating item with Quest rewards from placement 27 (GOLD_SCALE_FROM): Lake Hylia's lab dive asks for it
# (the other logic's "LH Lab Dive": Progressive Scale 2), which overworld_rule drops while it is no gating item (the check
# then asked for nothing). The fishing pond's adult prize puts it in the pool; the Tracker's letters "GS".
GOLD_SCALE = "Item_Scale_Gold"
GOLD_SCALE_FROM = 27
GIFTS_FROM = {"potion_bottle": 9, "goron_tunic": 12, "zora_tunic": 12, "skulltula_house_40": 12,
              "fairy_din": 14, "fairy_farore": 14, "fairy_nayru": 14, "lab_dive": 27, "frogs_game": 27}
EVERYTHING = PROGRESSION | QUEST_GATES | TUNICS
# The Skulltula house's rewards (bug 67, placement 12): each asks for its number of tokens, counted by the logic
# (tokens), and for what it takes to come to the house in Kakariko, a child's or an adult's: out of the forest
# (HOUSE_NEED, as the cucco lady's). Before 12 they asked for everything (the logic counted no tokens). The 40 tokens'
# reward, the large Bombchu bundle (GatheringTokenGold's TakenReward_Common_Event, TakenRewardActor), takes part from
# 12. The 100 tokens' (Obj_Rupee_Gold, given again at each talk: TakenReward_Common_Event_200Rupee) stays the game's,
# as the owner said (2026-11-17).
HOUSE_TOKENS = {"skulltula_house_10": 10, "skulltula_house_20": 20, "skulltula_house_30": 30, "skulltula_house_40": 40, "skulltula_house_50": 50}
HOUSE_NEED = CHILD
HOUSE_FROM = 12


def house_need(key, need, placement):
    """what a gift asks for: a Skulltula house's reward its tokens and the way to the house (from HOUSE_FROM), any
    other gift `need`"""
    return frozenset(HOUSE_NEED | {tokens(HOUSE_TOKENS[key])}) if placement >= HOUSE_FROM and key in HOUSE_TOKENS else need
GIFTS = (
    Gift("darunia", "Dm_Goron_0030", ("Item_Gauntlet_Goron",), BR, "GoronCity", "Darunia's gift", CHILD, None),
    Gift("lostwood_target", "Dm_LostWood_0040", ("Item_BulletBag_Medium", "Item_BulletBag_Large"), "Item_BulletBag_Medium", "LostWood",
         "the Lost Woods target", CHILD, None),
    Gift("skulltula_house_10", "GatheringTokenGold", ("Item_Wallet_Medium",), "Item_Wallet_Medium", "KakarikoVillage",
         "the Skulltula house: 10 tokens", EVERYTHING, None),   # (tokens: counted from placement 12, house_need)
    Gift("skulltula_house_20", "GatheringTokenGold", ("Item_AgonyStone",), "Item_AgonyStone", "KakarikoVillage",
         "the Skulltula house: 20 tokens", EVERYTHING, None),
    Gift("skulltula_house_30", "GatheringTokenGold", ("Item_Wallet_Large",), "Item_Wallet_Large", "KakarikoVillage",
         "the Skulltula house: 30 tokens", EVERYTHING, None),
    Gift("skulltula_house_40", "GatheringTokenGold", ("Item_BombchuBundle_Large",), "Item_BombchuBundle_Large", "KakarikoVillage",
         "the Skulltula house: 40 tokens", EVERYTHING, None),
    Gift("skulltula_house_50", "GatheringTokenGold", ("Obj_Heart_Piece",), "Obj_Heart_Piece", "KakarikoVillage",
         "the Skulltula house: 50 tokens", EVERYTHING, None),
    Gift("forest_stage_skull", "LostWood_ScrubForestStageElder_SkullMaskFirst", ("Item_StickBag_Medium", "Item_StickBag_Large"),
         "Item_StickBag_Medium", "LostWood", "the Forest Stage: the Skull Mask", CHILD, None),
    Gift("forest_stage_truth", "LostWood_ScrubForestStageElder_TrueMaskFirst", ("Item_NutBag_Medium", "Item_NutBag_Large"),
         "Item_NutBag_Medium", "LostWood", "the Forest Stage: the Mask of Truth", GROWN, None),
    Gift("bowling_bag", "MiniGame_BombchuBowling", ("Item_BombBag_Medium", "Item_BombBag_Large"), "Item_BombBag_Large", "Market",
         "Bombchu Bowling: the bag", CHILD_BOMBS, None),
    Gift("bowling_heart", "MiniGame_BombchuBowling", ("Obj_Heart_Piece",), "Obj_Heart_Piece", "Market",
         "Bombchu Bowling: the Piece of Heart", CHILD_BOMBS, None),
    Gift("diving", "MiniGame_Diving", ("Item_Scale_Silver",), SSC, "ZoraDomain", "the Zoras' diving game", CHILD_BOMBS, None),
    Gift("fishing_child", "MiniGame_Fishing", ("Obj_Heart_Piece",), "Obj_Heart_Piece", "HyruleField", "the fishing pond, as a child", CHILD, None),
    Gift("fishing_adult", "MiniGame_Fishing", ("Item_Scale_Gold",), "Item_Scale_Gold", "HyruleField", "the fishing pond, as an adult", GROWN, None),
    Gift("frogs", "MiniGame_FrogTenors", ("Obj_Heart_Piece",), "Obj_Heart_Piece", "ZoraRiver", "the frogs of Zora's River", GROWN, "frogs"),
    # (the frogs' second prize, their ocarina game, from placement 27: FROGS_SPLIT_FROM)
    Gift("frogs_game", "MiniGame_FrogTenors", ("Obj_Heart_Piece",), "Obj_Heart_Piece", "ZoraRiver", "the frogs of Zora's River: their ocarina game",
         GROWN, "frogs", ("FrogMiniGame_Insectrepellent", "FrogMiniGame_RetryFlow")),
    Gift("gallery_market", "MiniGame_HitTarget", ("Item_BulletBag_Medium", "Item_BulletBag_Large"), "Item_BulletBag_Large", "Market",
         "the Market's shooting gallery", CHILD, None),
    Gift("gallery_kakariko", "MiniGame_HitTarget", ("Item_Quiver_Medium", "Item_Quiver_Large"), "Item_Quiver_Medium", "KakarikoVillage",
         "Kakariko's shooting gallery", GROWN | {BOW}, None),
    Gift("cucco_lady", "Minigame_CatchCucco", ("Item_Bottle",), "Item_Bottle", "KakarikoVillage", "the cucco lady", CHILD, None),
    Gift("archery_heart", "Minigame_HorsebackArchery", ("Obj_Heart_Piece",), "Obj_Heart_Piece", "GerudoFortress",
         "horseback archery: 1000 points", GROWN | {BOW}, None),
    Gift("archery_quiver", "Minigame_HorsebackArchery", ("Item_Quiver_Medium", "Item_Quiver_Large"), "Item_Quiver_Large", "GerudoFortress",
         "horseback archery: 1500 points", GROWN | {BOW}, None),
    Gift("goron_tunic", "SageOfFire", ("Obj_Armor_Goron",), GT, "GoronCity", "the rolling Goron, as an adult", GROWN | {BB}, None),
    Gift("zora_tunic", "SageOfWater", ("Obj_Armor_Zora",), ZT, "ZoraDomain", "King Zora, thawed", EVERYTHING, None),   # (the thaw's Blue Fire: its way not in the rules' terms)
    Gift("rolling_goron", "Npc_Goron_006_Child", ("Item_BombBag_Medium", "Item_BombBag_Large"), "Item_BombBag_Medium", "GoronCity",
         "the rolling Goron", CHILD_BOMBS, None),
    Gift("roof_man", "Npc_Hylia_001_Adult", ("Obj_Heart_Piece",), "Obj_Heart_Piece", "KakarikoVillage",
         "the man on the roof", GROWN, None),   # (the Hookshot, said its owner, not sure: it is Dampe's, an adult's)
    Gift("skull_kid_song", "Npc_SkullKid_Child", ("Obj_Heart_Piece",), "Obj_Heart_Piece", "LostWood", "the Skull Kid: Saria's Song", CHILD, None),
    Gift("skull_kid_game", "Npc_SkullKid_Child_02", ("Obj_Heart_Piece",), "Obj_Heart_Piece", "LostWood", "the Skull Kids' memory game", CHILD, None),
    Gift("dog_lady", "SubEvent_FindRichard", ("Obj_Heart_Piece",), "Obj_Heart_Piece", "Market", "the dog lady", CHILD, None),
    # (Lake Hylia's lab, placement 27, asked 2026-11-23: the scientist's diving game, either age, hands over a Piece of
    #  Heart, Npc_Hylia_045_Child's DivingChallenge_Common. Its rule is the other logic's "LH Lab Dive", OVERWORLD_GIFTS:
    #  the Golden Scale (the owner tried the Iron Boots as an adult: they do not count); EVERYTHING without the table)
    Gift("lab_dive", "Npc_Hylia_045_Child", ("Obj_Heart_Piece",), "Obj_Heart_Piece", "HyruleField", "the Lake Hylia lab's diving game", EVERYTHING, None),
    Gift("potion_bottle", "Npc_Hylia_020_Shop_Child", ("Item_Bottle",), "Item_Bottle", "Market",
         "the Potion Shop keeper's bottle", CHILD, None),   # (his errand of the bug passed over: potion_errand_skip)
    Gift("light_arrows", "Dm_TimeTemple_0130", ("Item_Arrow_Light",), "Item_Arrow_Light", "Market", "Zelda: the Light Arrows",
         MEDALS3 | DESERT | {LENS, HOVER, SG, BOW, MS} | QUEST_GATES, "light"),
    # (the Great Fairies of the spells, placement 14: FAIRY_GIFTS. Each behind a wall bombs open, and the Lullaby on
    #  the mark: the Lullaby is CHILD's without Songs, SONG_GIFTS's with them)
    Gift("fairy_din", "Dm_FairyFountain_Din", ("Item_DinFire",), "Item_DinFire", "DeathMountainTrail",
         "the Great Fairy of Death Mountain Trail", CHILD | {BB}, None),
    Gift("fairy_farore", "Dm_FairyFountain_Frore", ("Item_FaroreWind",), "Item_FaroreWind", "ZoraFountain",
         "the Great Fairy of Zora's Fountain", GROWN, None),   # (an adult's, as Jabu-Jabu's ending asks for Zora's Fountain)
    Gift("fairy_nayru", "Dm_FairyFountain_Nayru", ("Item_NayruLove",), "Item_NayruLove", "DesertColossus",
         "the Great Fairy of the Desert Colossus", DESERT | QUEST_GATES, None),
)
# ---- Deku Scrubs: the Business Scrubs' one-time sales ----
# A Business Scrub's wares are named in its map file (ScrubBusiness_ShopItemActorName0..2), and its flow
# (Enemy_Scrub_Business_Common) finds the sale by that name: the name is put in the game's data and compared
# (EventQueryIsGameDataString64), and the sale that matches is a sub-flow call with the item, its price and its
# text. So the map's name is the sale's key and is left as it is; what is sold is the call's ActorName.
# 21 scrubs outside the Dream World (the Dream's are left alone: the game's owner's word). Most sell what can be
# bought again and again (seeds, nuts, bombs, arrows, potions): those stay. Four sales are made once, and are the
# setting's: a Piece of Heart (Hyrule Field), another from the scrub with a secret (Death Mountain Crater), the Deku
# Stick upgrade (Kokiri Forest and the Lost Woods: the same sale) and the Deku Nut upgrade (the Lost Woods). An
# upgrade's sale names two sizes, the one Link has not; both are made the new item, and the bigger size goes into
# the pool (the Forest Stage's gifts, with Quest rewards, put in the middle ones).
# What each asks for is in the rules' words before Quest rewards; with it on, quest_need adds its two.
SCRUB_FLOW = "Enemy_Scrub_Business_Common"
# (bug 126, the owner's run 2026-11-23: the Hyrule Field grotto's scrub asked for the password and gave the item put on
# "the Business Scrub with a secret" (Death Mountain Crater), and the crater's gave Hyrule Field's: neither marked. The
# flow's entries are the other way round from the names: its "Secret" entry is the Hyrule Field grotto's scrub (who sells
# only for the password, Hyrule Field's note 07, an adult's), its pouch entry the crater's.) From SCRUB_SWAP_FROM each of
# the two keeps its entry and item and takes the other's area, place and name (scrubs_swapped); seeds made before keep theirs.
SCRUB_SWAP_FROM = 26
SCRUBS = (
    Gift("scrub_heart_field", SCRUB_FLOW, ("Obj_Heart_Piece",), "Obj_Heart_Piece", "HyruleField",
         "a Business Scrub: a Piece of Heart", ADULT | {HAM}, "scrubs", "SimpleShopRoot_Enemy_Scrub_Business_Pouch"),
    Gift("scrub_heart_secret", SCRUB_FLOW, ("Obj_Heart_Piece",), "Obj_Heart_Piece", "DeathMountainCrater",
         "the Business Scrub with a secret: a Piece of Heart", ADULT | {HAM}, "scrubs", "Secret"),
    Gift("scrub_sticks", SCRUB_FLOW, ("Item_StickBag_Medium", "Item_StickBag_Large"), "Item_StickBag_Large", "LostWood",
         "a Business Scrub: the Deku Stick upgrade", CHILD, "scrubs", "SimpleShopRoot_Enemy_Scrub_Business_Pouch"),
    Gift("scrub_nuts", SCRUB_FLOW, ("Item_NutBag_Medium", "Item_NutBag_Large"), "Item_NutBag_Large", "LostWood",
         "a Business Scrub: the Deku Nut upgrade", CHILD, "scrubs", "SimpleShopRoot_Enemy_Scrub_Business_Pouch"),
)


# ---- Shops: four shelves of each shop sell a shuffled item, once ----
# What a shop sells is three things that say the same (found with a Boomerang put on the Kokiri shop's shelf):
#   - the shelf's actor in the map file (Shop_DekuStick, with its place in the row, ShopItemIndex: none is 0): what
#     is seen on the shelf and what is given;
#   - the keeper's goods list (Component/ShopParam/<keeper>...ShopParam.bgyml in the keeper's pack, a copy in each of
#     the keeper's packs: GoodsList, by the same place): the actor whose price is asked, and how many there are
#     (StockNum; all of them without end but the masks, and the Kokiri shop's first nuts and stick);
#   - the three lists of the game's actors (RSDB: ActorInfo, GameActorInfo, PouchActorInfo). A shelf actor that is not
#     in them is not made, and its keeper, asked for his wares, stopped the game (seen in play).
# A shelf actor is Shop_Item_Base with an item's own name, model, animation and place in the pouch, and a price
# (Shop_Armor_Goron is that of the Goron Tunic). So an item of the chests is given one, Shop_Rando_<item>
# (shop_pack), with its rows in the three lists (shop_rows), and put on the shelf (shelf_actors) and in the goods
# list with one in stock (shop_goods). Seen in play: the Boomerang on the Kokiri shop's shelf, named, bought and
# got; its price was the Deku Stick's, 10, the goods list still naming that, and it had no words under its name:
# those are the line <the item's name>_ShopCaption of ActorMsg/PouchContent.msbt, which only what the game sells
# has. An item without one is given its own description under that label, in every language (shop_caption).
# Four shelves of each of six shops take part (SHOPS): not the Happy Mask Shop (its owner's word: the masks stay),
# and not what a game needs to buy again and again or by its own scenes (the shields, the tunics, bombs, arrows,
# the first nuts and stick, the potions and the fairy). What a shelf sold goes into the pool as the chests' own
# kind of it (SHELF_ITEMS), a red rupee for what no chest holds. Child and adult have one shop each of a kind, with
# the same goods: both sell the shuffled items, and what was bought as a child may be there again for the adult.
# A shop's need is what its place asks for in the rules' words, meant to ask for too much. Its place, for the
# tracker, is before its counter: three metres from its keeper, away from the shelves (the keeper's own place put
# Link behind the Bombchu Shop's counter, where a wall he could not see kept him: seen in play), or the game's own
# place for Link there (the Kokiri shop's ShopPosition_Link, the anchor before the Goron's and the Zora's keeper).
# The Bombchu Shop is young Link's alone (the adult's Market has its ruin), and its door is shut ("Closed due to bomb
# shortage") until two things hold, by the Market's logic for it (Logic/Market_Child_Prefab_0c76: the door's EnableOpen
# is Get_StoneOfFire_IsCompleted_Exp AND the time's division Night): it is night, and the Goron's Ruby's quest is at
# its last step, Complete (the list of flags: an enum of 21 steps from NotReady, through Darunia, Saria's Song,
# DungeonStart, BossBattle and EscapeDungeon). So its shelves ask for what Dodongo's Cavern asks for, DODONGO_DONE:
# the quest's step, not an item, is the gate, and bombs found early do not open it. Seen in play: shut at night
# before King Dodongo. Its name says so for the tracker.
DODONGO_DONE = CHILD | {BB}
# The door opened at night from a new game's start (asked for by the game's owner, 2026-11-13 and 2026-11-15). The
# door's logic (BOMBCHU_DOOR_LOGIC, an AI file of 8 nodes) has two OperateAND nodes, the quest AND the night: node 0
# feeds the door's EnableOpen, node 4 its EnableDo. Each is made an OperateOR (its name's place in the file's strings
# and the name's hash taken from the file's own OperateOR, node 5: a node's kind is its name, and AND and OR take the
# same inputs): the door is open at night, and by day once the quest is done. The shop's inside, the keeper with it,
# is made when the door opens (the file's PrefabAllCreate; the keeper's own schedule asks for nothing: seen when Link
# was put inside, the shelves were there and the keeper was not). The file keeps its size. The shelves' rule is left
# as it was (DODONGO_DONE: asking for too much, and the same items for a seed made before).
BOMBCHU_DOOR_LOGIC = "Logic/Market_Child_Prefab_0c76.logic.module.ainb"
# The door so opened, the shop was empty and its "Closed" sign stayed (seen in play): the child's Market map makes
# three actors by the same quest (their Presence: FlagName Get_StoneOfFire_IsCompleted_Exp), the keeper and the shop's
# music when it is done, the sign (Land_HrlCity_ShopSign_A_01, IsNegation) while it is not. bombchu_presence takes the
# keeper's and the music's Presence away (they are there from the start; the door keeps the shop shut by day) and the
# sign out of the map.
BOMBCHU_QUEST = "Get_StoneOfFire_IsCompleted_Exp"
BOMBCHU_ACTORS = ("Npc_Hylia_021_Shop_Child", "BGM_Shop_Market_Bombchu")
BOMBCHU_SIGN = "Land_HrlCity_ShopSign_A_01"
# Which shelves (rando_shop_shelves, --shop-shelves). Off: the four of each shop above (slots). On: its other four
# too (rest), every shelf of a keeper's goods list, each sold once: the shields, the tunics, the potions and the bombs,
# arrows, nuts and sticks a game buys again and again are then not for sale, and come from grass, pots and enemies
# (the tunics from the Goron and King Zora, who give them still). What such a shelf sold goes into the pool as the
# chests' kind of it where there is one (SHELF_ITEMS: the shields are TBox_Shield_Deku and TBox_Shield_Hylian), a red
# rupee for the rest (a potion, a tunic, a fairy, a heart).
# One shelf is its own setting's: the Kokiri shop's Deku Shield (SHIELD_SHELF), with the Kokiri Sword's chest
# (rando_sword_shield, --sword-shield). Off: the sword is in its chest and the shield on its shelf whatever the
# other settings say. On: the chest takes part as an event's chest does (with Major items) and the shelf as a
# shop's does (with Shops, whichever its shelves). Mido lets Link by with a sword and a shield (OPEN), so with the shelf
# shuffled the shield is a gating item (DS, SHIELD_GATES): every rule that asks for the sword asks for it too, unless
# Open Deku Tree is on (shield_need). A Deku Shield burns: one found and lost after Mido is passed is not needed again.
DS = "TBox_Shield_Deku"
SHIELD_GATES = frozenset((DS,))
SHIELD_SHELF = ("kokiri", 6, "Shop_Weapon_Shield_Deku")
Shop = collections.namedtuple("Shop", "key params areas name need place ages slots rest")


def shop_need(shop, placement, open_forest):
    """What a shop's shelves ask for (before their prices' wallets), by the seed's placement (PLACEMENT) and Open forest
    exit. From placement 4 (asked for by the game's owner, 2026-11-15: with Shops, a shelf under the child's wallet
    should have a chance to be had from the start): the Bombchu Shop asks for a child only, its door opening at night
    from the start (BOMBCHU_DOOR_LOGIC); and with Open forest exit the Market's shops (the Bazaar, the Potion Shop, the
    Bombchu Shop) ask for nothing, a child walking there from the start (CHILD is the forest's way out: the sword and
    the Slingshot, the Deku Tree done). The Zora shop asks for what a child's way into Zora's Domain asks for, as the
    Zoras' diving game does (CHILD_BOMBS; Zelda's Lullaby with it where the songs are named, SONG_AREAS): it was an
    adult's, and the owner's word is that a child has it as soon as he reaches Zora's Domain. The Goron shop keeps
    its own: a child reaches Goron City past Kakariko's gate and asks for bombs there."""
    need = shop.need
    if placement >= 4:
        if shop.key == "bombchu":
            need = CHILD
        if shop.key == "zora":
            need = CHILD_BOMBS
        if open_forest and shop.areas[0] == "Market":
            need = frozenset(need - CHILD)
    return need
POTION_KEEPER, POTION_ADULT = "Npc_Hylia_020_Shop_Adult", "Npc_Hylia_020_Shop_Adult"   # (the adult Potion Shop keeper's pack; his goods list's name, SHOP_TOWNS)
SHOPS = (
    Shop("kokiri", ("Npc_Kokiri_001_Shop_Child", "Npc_Kokiri_001_Shop_Child_ShortStock"), ("KokiriForest",), "the Kokiri shop", NONE,
         (-1.9, 110.7, -22.6), "CA", ((0, "Shop_Heart"), (1, "Shop_DekuSeedBundle_02"), (3, "Shop_DekuNutBundle_02"), (5, "Shop_DekuStickBundle_Medium")),
         ((2, "Shop_DekuNutBundle_01"), (4, "Shop_DekuSeedBundle_01"), (7, "Shop_DekuStick"))),   # (and SHIELD_SHELF, 6)
    Shop("general", ("Npc_Hylia_018_Shop",), ("Market",), "the Bazaar", CHILD,
         (19.5, 100.4, 16.1), "C", ((0, "Shop_Heart"), (1, "Shop_MagicJar_Small"), (2, "Shop_DekuSeedBundle_02"), (7, "Shop_DekuStick")),
         ((3, "Shop_ArrowBundle_01"), (4, "Shop_BombBundle_01"), (5, "Shop_DekuNutBundle_01"), (6, "Shop_Weapon_Shield_Hylian"))),
    Shop("medicine", ("Npc_Hylia_020_Shop",), ("Market",), "the Potion Shop", CHILD,
         (20.6, 100.1, 6.0), "C", ((2, "Shop_Bottle_HalfMilk"), (5, "Shop_Bottle_Poe"), (6, "Shop_Bottle_Bug"), (7, "Shop_Bottle_Fish")),
         ((0, "Shop_Bottle_RedPotion"), (1, "Shop_Bottle_GreenPotion"), (3, "Shop_Bottle_Fairy"), (4, "Shop_Bottle_BlueFire"))),
    Shop("bombchu", ("Npc_Hylia_021_Shop",), ("Market",), "the Bombchu Shop (at night, after Dodongo's Cavern)", DODONGO_DONE,
         (-24.1, 100.4, 32.4), "C", ((4, "Shop_BombchuBundle_01"), (5, "Shop_BombchuBundle_07"), (6, "Shop_BombchuBundle_02"), (7, "Shop_BombchuBundle_08")),
         ((0, "Shop_BombchuBundle_03"), (1, "Shop_BombchuBundle_04"), (2, "Shop_BombchuBundle_05"), (3, "Shop_BombchuBundle_06"))),
    Shop("goron", ("Npc_Goron_011_Shop_Child",), ("GoronCity",), "the Goron shop", CHILD | {BB},
         (-16.6, 98.0, -20.2), "CA", ((0, "Shop_Heart"), (2, "Shop_Bottle_Bug"), (6, "Shop_BombBundle_03"), (7, "Shop_BombBundle_04")),
         ((1, "Shop_Bottle_RedPotion"), (3, "Shop_Armor_Goron"), (4, "Shop_BombBundle_01"), (5, "Shop_BombBundle_02"))),
    Shop("zora", ("Npc_Zora_011_Shop",), ("ZoraDomain",), "the Zora shop", ADULT,
         (-27.1, 104.9, 18.2), "CA", ((2, "Shop_Bottle_Bug"), (5, "Shop_ArrowBundle_02"), (6, "Shop_Bottle_Fish"), (7, "Shop_ArrowBundle_03")),
         ((0, "Shop_Bottle_RedPotion"), (1, "Shop_Bottle_GreenPotion"), (3, "Shop_Armor_Zora"), (4, "Shop_ArrowBundle_01"))),
    # (placement 11 on, SHOP_TOWNS: Kakariko's Bazaar and Potion Shop, the adult's, apart from the Market's)
    Shop("kgeneral", ("Npc_Hylia_018_Shop_Adult",), ("KakarikoVillage",), "Kakariko's Bazaar", ADULT,
         (-73.9, 104.2, 8.0), "A", ((0, "Shop_Heart"), (1, "Shop_MagicJar_Small"), (2, "Shop_DekuSeedBundle_02"), (7, "Shop_DekuStick")),
         ((3, "Shop_ArrowBundle_01"), (4, "Shop_BombBundle_01"), (5, "Shop_DekuNutBundle_01"), (6, "Shop_Weapon_Shield_Hylian"))),
    Shop("kmedicine", (POTION_ADULT,), ("KakarikoVillage",), "Kakariko's Potion Shop", ADULT,
         (-37.5, 107.4, 8.4), "A", ((2, "Shop_Bottle_HalfMilk"), (5, "Shop_Bottle_Poe"), (6, "Shop_Bottle_Bug"), (7, "Shop_Bottle_Fish")),
         ((0, "Shop_Bottle_RedPotion"), (1, "Shop_Bottle_GreenPotion"), (3, "Shop_Bottle_Fairy"), (4, "Shop_Bottle_BlueFire"))),
)
# Until placement 11 the Bazaar and the Potion Shop were one shop each in two towns, the child's Market and the adult's
# Kakariko: the same shelves' items written in both towns' maps and goods lists, one check each, under the Market (the
# owner noticed Kakariko's adult shops missing from the Tracker, and asked for them to be shops of their own, selling
# other items, 2026-11-16). From placement 11 (SHOP_TOWNS) the Market's shops are the Market's and Kakariko's two are
# shops of their own, the adult's (their rule: an adult, ADULT, as the Zora shop's was; their place for the Tracker
# three metres from their keeper, away from his shelves, as the Market's). Their keepers have goods lists of their own:
# the Bazaar's adult keeper has always had one (Npc_Hylia_018_Shop_Adult); the Potion Shop's adult keeper had the
# child's (his actor's parent's ShopRef), so he is given one, POTION_ADULT, a copy of it in his pack (potion_adult).
# Each shelf has a "still for sale" flag of its own (shelf_flags), so a shelf bought in one town is not in the other.
SHOP_TOWNS = 11
SHOPS_JOINT = {"general": Shop("general", ("Npc_Hylia_018_Shop", "Npc_Hylia_018_Shop_Adult"), ("Market", "KakarikoVillage"), "the Bazaar", CHILD,
                               SHOPS[1].place, "C", SHOPS[1].slots, SHOPS[1].rest),
               "medicine": Shop("medicine", ("Npc_Hylia_020_Shop",), ("Market", "KakarikoVillage"), "the Potion Shop", CHILD,
                                SHOPS[2].place, "C", SHOPS[2].slots, SHOPS[2].rest)}


def shops(placement=PLACEMENT):
    """the shops a seed of this placement has (SHOPS; before SHOP_TOWNS, the Bazaar and the Potion Shop one shop each
    in both towns, as the seeds made then have them)"""
    if placement >= SHOP_TOWNS:
        return SHOPS
    return tuple(SHOPS_JOINT.get(shop.key, shop) for shop in SHOPS if shop.key not in ("kgeneral", "kmedicine"))


def potion_adult(pack_data):
    """The adult Potion Shop keeper's pack with a goods list of his own (POTION_ADULT, a copy of the child's) and his
    actor naming it (ShopRef, which he took from his parent, the child's actor): (the pack written anew, the goods
    list's file, the actor's file). ValueError: the pack is not what it was."""
    parts = sarc_read(pack_data)
    child, mine = SHOP_PARAM % "Npc_Hylia_020_Shop", SHOP_PARAM % POTION_ADULT
    actor = ACTOR_FILE % POTION_KEEPER
    if child not in parts or actor not in parts:
        raise ValueError("the adult Potion Shop keeper's pack has no goods list or no actor of his")
    if mine not in parts:
        parts[mine] = parts[child]
    tree, version = byml_parse(parts[actor])
    comps = tree[1].setdefault("Components", ("dict", collections.OrderedDict()))
    comps[1]["ShopRef"] = ("string", "?" + mine)
    tree[1]["Components"] = ("dict", collections.OrderedDict(sorted(comps[1].items())))
    parts[actor] = byml_build(tree, version)
    return sarc_write(parts), mine, actor


def shop_slots(shop, every=False, shield=False):
    """the shelves of a shop that sell a shuffled item, [(its place in the goods list, the game's own actor there)]:
    its four; every: its other shelves too; shield: the Deku Shield's (the Kokiri shop's), whichever the others are.
    The four come first, in their order: a shelf's number in its name is its place here."""
    slots = list(shop.slots) + (list(shop.rest) if every else [])
    if shield and shop.key == SHIELD_SHELF[0]:
        slots.append(SHIELD_SHELF[1:])
    return slots


def shield_need(need):
    """what a rule asks for with the Deku Shield's shelf shuffled and Mido in the way: the shield wherever the sword"""
    return frozenset(need | SHIELD_GATES) if S in need else need

SHELF_ITEMS = (("Shop_DekuSeedBundle", "Item_ScrubBusinessSeed"), ("Shop_DekuNutBundle", "TBox_DekuNutBundle"), ("Shop_DekuStick", "Item_DekuStickBundle_Small"),
               ("Shop_MagicJar", "Tbox_MagicJar_Large"), ("Shop_BombBundle", "Item_BombBundle_Small"), ("Shop_BombchuBundle", "Item_BombchuBundle_Small"),
               ("Shop_ArrowBundle", "TBox_ArrowBundle_Medium"), ("Shop_Weapon_Shield_Deku", DS), ("Shop_Weapon_Shield_Hylian", "TBox_Shield_Hylian"))
SHELF_OTHER = "TBox_Rupee_Red"
SHOP_BASE, SHOP_SAMPLE = "Shop_Item_Base", "Shop_ArrowBundle_01"
SHOP_TABLES = ("ActorInfo", "GameActorInfo", "PouchActorInfo")
SHOP_ROW, SHOP_ROW_HEAPS = "Shop_DekuStick", "Shop_Armor_Goron"   # (a shelf's rows to go by; the heaps of a shelf that is another item)
SHOP_PARAM = "Component/ShopParam/%s.game__component__ShopParam.bgyml"
SHOP_TEXT = "ActorMsg/PouchContent.msbt"
ACTOR_FILE = "Actor/%s.engine__actor__ActorParam.bgyml"
ACTOR_REF = "Work/Actor/%s.engine__actor__ActorParam.gyml"
# A shelf's price is rolled by the seed, 1 to SHOP_PRICE_MAX rupees, whatever is put on it (its owner's word: always
# rolled, in one of two ways: 1, most of them low; 2, any price as likely as another). What Link can pay is what his
# wallet holds: 200 as a child (the wallet he starts with, in this game), 500 with the Adult's Wallet, 1000 with the
# Giant's (WALLETS: its owner's numbers). So with Shops the two wallets are gating items (SHOP_GATES): they are
# shuffled, by the two Gold Skulltula family's gifts that give them taking part (SHOP_WALLET_GIFTS, whether Quest
# rewards is on or not), and a shelf asks for the wallet its price needs (wallet_need) with what its shop asks for.
# A price up to 500 asks for the Adult's Wallet though the Giant's would do: too much, never too little. Seen in
# play: a green rupee bought for 150 gave one rupee and was sold out after, in its shop and when it was come back to.
# The most a shelf costs was 1000 and is 750 (its owner's word, 2026-11-13), and a price within the child's wallet
# comes up a little more often than its share of the range, in both ways (SHOP_CHILD_MORE: that often the price is
# rolled within the child's 200 alone). A seed made before keeps its prices.
WM, WL = "Item_Wallet_Medium", "Item_Wallet_Large"
SHOP_GATES = frozenset((WM, WL))
SHOP_WALLET_GIFTS = ("skulltula_house_10", "skulltula_house_30")
SHOP_PRICE_MAX = 750
SHOP_CHILD, SHOP_CHILD_MORE = 200, 0.15
# How low the Low prices are: the power an even roll is raised to. It was 3, the cube: one shelf in eight cost 1 rupee
# (seen in play: seven of a seed's 48 shelves, four of them Gold Skulltula tokens, and asked about). 2, the square,
# is gentler (its owner's word, 2026-11-13): 1 rupee on one shelf in 25, six in ten within the child's wallet.
SHOP_LOW_POWER = 2
SHOP_TENS_FROM = 12      # (the placement from which prices are in tens: shop_price)
# ---- The Great Fairies' offerings (asked for 2026-11-19: rolled as the shops' prices are) ----
# Each fountain's scene asks EventQueryHasRuppe for its price and calls Dm_FairyFountain_Din:Pay with minus it; the fairy's
# words name it by a tag (GreatFairy_Price1 to 6), a number the game's code fills in, not in any file, so the tag is
# replaced by the number in each language's words (EventFlowMsg/Dm_FairyFountain_Din.msbt, FAIRY_PRICE_TEXT). With Shops,
# from placement FAIRY_PRICES_FROM: the price is shop_price's, and a fairy of the shuffle whose price is past the child's
# wallet asks for the wallet that holds it (wallet_need). The game's prices: {scene: (its tag's number, its price, gift)}.
FAIRY_PRICES = {"Dm_FairyFountain_Din": (1, 25, "fairy_din"), "Dm_FairyFountain_Power": (2, 50, "fairy_power"),
                "Dm_FairyFountain_Frore": (3, 100, "fairy_farore"), "Dm_FairyFountain_Wisdom": (4, 200, "fairy_wisdom"),
                "Dm_FairyFountain_Nayru": (5, 300, "fairy_nayru"), "Dm_FairyFountain_Courage": (6, 500, "fairy_courage")}
FAIRY_PRICES_FROM = 16
FAIRY_PRICE_TEXT = "EventFlowMsg/Dm_FairyFountain_Din.msbt"


# The Great Fairy prices setting (rando_fairy_prices, asked 2026-11-23: a setting of their own, with the shops' choices):
# 0 as the shops (the way before it, the default), 1 the game's own, 2 and 3 rolled as Shops' Low prices and Affordable
# (shop_price's modes 1 and 3), whatever Shops is. (2026-11-25: "Any price" taken out, a seed ID holds 4 choices a setting;
# Affordable was 4 then, and a 4 still read is Affordable: FAIRY_PRICE_OLD.)
FAIRY_PRICE_MODES = {1: 0, 2: 1, 3: 3}
FAIRY_PRICE_OLD = {4: 3}


def fairy_price_mode(setting, shops):
    """shop_price's mode for the fairies' offerings (0: the game's own prices) by the setting and Shops"""
    return shops if setting == 0 else FAIRY_PRICE_MODES.get(setting, 0)


def fairy_prices(seed, mode):
    """{scene: the price its fairy asks}: shop_price's, one roll of its own a fountain"""
    return {flow: shop_price(random.Random("fairy price:%d:%s" % (seed, flow)), mode) for flow in FAIRY_PRICES}


def fairy_price_flow(data, price):
    """A fountain's scene with its price made `price`: the one EventQueryHasRuppe's Value and the one call of Pay's Value
    (its minus): the new bytes, of the same size. ValueError: not one of each."""
    u16 = lambda at: struct.unpack_from("<H", data, at)[0]
    u64 = lambda at: struct.unpack_from("<Q", data, at)[0]
    if data[:6] != b"BFEVFL" or u16(0x20) != 1:
        raise ValueError("not an event flow file of one flowchart")
    chart = u64(u64(0x28))
    actors, count, events = u64(chart + 0x28), u16(chart + 0x16), u64(chart + 0x30)
    text = lambda ptr: bytes(data[ptr + 2:ptr + 2 + u16(ptr)]).decode("utf-8", "replace") if 0 < ptr < len(data) - 2 else ""
    out, asks, pays = bytearray(data), 0, 0
    for i in range(count):
        e = events + 0x30 * i
        kind, at = data[e + 8], u64(e + 0x10)
        if kind == 1:
            actor = actors + 0x38 * u16(e + 0x0c)
            what = text(u64(u64(actor + 0x20) + 8 * u16(e + 0x0e)))
        elif kind == 4:
            what = "call " + text(u64(e + 0x20))
        else:
            continue
        if what not in ("EventQueryHasRuppe", "call Pay"):
            continue
        keys = u64(at + 8) if at else 0
        for k in range(u16(at + 2) if at and keys else 0):
            item = u64(at + 0x10 + 8 * k)
            if text(u64(keys + 8 + 16 * (k + 1) + 8)) == "Value" and data[item] == 2:
                struct.pack_into("<i", out, item + 0x10, price if what == "EventQueryHasRuppe" else -price)
                if what == "EventQueryHasRuppe":
                    asks += 1
                else:
                    pays += 1
    if asks != 1 or pays != 1:
        raise ValueError("%d price questions and %d payments where one of each was expected" % (asks, pays))
    return bytes(out)


def fairy_price_words(data, prices):
    """The fairies' words (FAIRY_PRICE_TEXT, one language) with each GreatFairy_Price<n> tag made the number `prices[n]`:
    (the file written anew, how many lines changed). A tag: 0x0E, its group, type and size (16 bits each), then its
    parameters, the tag's name among them."""
    lines = 0
    for label in msbt_labels(data):
        start, end = msbt_text(data, label)
        raw = bytes(data[start:end]).rstrip(b"\0")
        new, at = bytearray(), 0
        while True:
            found = raw.find(b"GreatFairy_Price", at)
            if found < 0:
                new += raw[at:]
                break
            tag = found - 9   # (0x0E, group, type, size, then the name's length before it)
            if tag < at or raw[tag] != 0x0E or raw[found - 2:found] != b"\x11\x00":
                raise ValueError("%s: a price tag not as expected" % label)
            size = struct.unpack_from("<H", raw, tag + 5)[0]
            n = raw[found + 16] - 0x30
            if n not in prices:
                raise ValueError("%s: GreatFairy_Price%d is not a fountain's" % (label, n))
            new += raw[at:tag] + str(prices[n]).encode()
            at = tag + 7 + size
        if bytes(new) != raw:
            data = msbt_set(data, label, bytes(new))
            lines += 1
    return data, lines
SHOP_AFFORDABLE = 10     # (Shops: Affordable, every shelf's price)
WALLETS = ((200, NONE), (500, frozenset((WM,))), (SHOP_PRICE_MAX, frozenset((WL,))))


# How an item stands on its shelf (SHELF_POSE, for the name: there is no such table). A shelf's actor had the item's
# own pose and animation (ASInfoRef, ASRef, AnimationRef), which are those of the scene where Link gets it: they
# lift it, turn it and, for some, draw it twice. Seen in play with them: the Iron Boots twice, one pair under the
# other; the compass tilted and half behind its price board; the Light Arrows and the Deku Stick bundle well over
# their shelf. So a shelf's actor has none of the three (shop_pack), and the item is as its model is made: seen
# without them, the boots once, the compass flat on its board, the hammer, bow, key and Longshot lying on theirs.
# Then the model's box tells where it is (the list of actors has it, ModelAabbMin and ModelAabbMax):
# - one that reaches under its own origin is put that much higher (shelf_lift): a Gold Skulltula's token reaches
#   0.19 under and was half in its board; the Megaton Hammer's 0.28;
# - one made where it is worn is put that much lower (SHELF_WORN): the gauntlets' box is 1.17 m up, and without the
#   pose they were at the top of the picture; lowered by it, on their shelf (seen in play);
# - and an item's own number where its box is not how it shows (SHELF_LIFT): the three magic arrows' boxes take in
#   their glow, and they hung a hand over the shelf; the Deku Stick bundle stands where its origin is.
# The Lens of Truth took the longest. Its model is made where it is worn, before young Link's eyes: its box is 0.92
# to 1.04 m up, 22 cm wide, and faces forward. It is 11 cm tall: put down by its box at its own size it stood behind
# its shelf's price board, which is as tall, and was not seen (the tries before this took that for a model that does
# not show, and turned it, which swung it off its shelf). So its shelf's actor is 0.67 m lower (SHELF_LIFT), its
# lenses a hand over the board, facing the shop, at its own size. It was 1.5 times its size for a while, and the
# shop's arrows round the shelf looked at were then far under it (reported from play): they go by the model's box as
# the list of actors has it, which is the model's own size, so a model far from its origin is not made larger here.
# At its own size the arrows are round it. Seen so in the Kokiri shop, the Bazaar and the Goron shop.
# (the empty bottle, Item_Bottle, put on a shelf: its model lies on its side, 0.18 tall, and at its own lift of 0.09
#  sat low behind the price board, seen in play (bug 5); raised clear of the board)
SHELF_LIFT = {"Item_Bottle": 0.25, "Item_Arrow_Fire": 0.1, "Item_Arrow_Ice": 0.1, "Item_Arrow_Light": 0.1, "Item_DekuStickBundle_Small": 0.0, "Item_GlassTruth": -0.67, "Item_Range_Bow": 0.15, "Item_Range_SlingShot": 0.15, "TBox_ArrowBundle_Small": 0.2, "Item_Sword_Kokiri": 0.15, "Item_Shield_Mirror": 0.35, "TBox_Shield_Hylian": 0.35,
              "TBox_Shield_Deku": 0.3}


def shelf_lift(item, floor):
    """how much higher an item's shelf actor is put: its own number, or what its model reaches under its origin
    (floor: the lowest of its box, or None), when that is a hand's breadth and not a model made elsewhere"""
    if item in SHELF_LIFT:
        return SHELF_LIFT[item]
    return round(-floor, 2) if floor is not None and -0.5 < floor < -0.02 else 0.0


def model_floor(data, item):
    """the lowest of an item's model's box in the game's list of actors (ActorInfo: ModelAabbMin.Y), or None"""
    tree, _ = byml_parse(data)
    for row in tree[1]:
        if row[1].get("__RowId", ("", ""))[1] == item:
            low = row[1].get("ModelAabbMin", ("dict", {}))[1].get("Y")
            return struct.unpack("<f", low[1])[0] if low and low[0] == 0xD2 else None
    return None


def model_box(data, item):
    """an item's model's box in the game's list of actors (ActorInfo: ModelAabbMin, ModelAabbMax): ((x, y, z) the
    lowest, (x, y, z) the highest), or None"""
    tree, _ = byml_parse(data)
    for row in tree[1]:
        if row[1].get("__RowId", ("", ""))[1] == item:
            ends = []
            for key in ("ModelAabbMin", "ModelAabbMax"):
                at = row[1].get(key, ("dict", {}))[1]
                if not all(axis in at and at[axis][0] == 0xD2 for axis in "XYZ"):
                    return None
                ends.append(tuple(struct.unpack("<f", at[axis][1])[0] for axis in "XYZ"))
            return tuple(ends)
    return None


# How large an item is on its shelf. A shelf's own goods are up to 1.1 m long (the Deku Stick); the Megaton Hammer
# (1.78 m) and the Fairy Bow (1.36 m) filled the shop's wall (seen in play). An item longer than SHELF_LONG is made
# SHELF_LONG long, and one smaller than SHELF_SMALL (the compass, 16 cm and flat: half hidden by its shelf's price
# board; the Stone of Agony, 8 cm) is made SHELF_SMALL, at most three times its size. The size is the shelf actor's
# Scale in the map file. An item's own number, where its box does not say it: the Small Key, tall and thin, stood
# over its shelf's whole height.
SHELF_LONG = 0.9
# (the Goron's Bracelet is very small on a shelf: its owner asked for it a little bigger, 2026-11-14, with a picture of
#  the Potion Shop. Half as large again, as it is where it lies to be picked up (PICKUP_SCALES). NOT SEEN YET)
SHELF_SCALE = {"Item_Dungeon_SmallKey": 0.6, "Item_Dungeon_Compass": 1.5, "Item_GlassTruth": 1.0,
               "Item_Gauntlet_Gold": 0.35, "Item_Gauntlet_Silver": 0.35, "Item_Gauntlet_Goron": 1.5, "TBox_ArrowBundle_Small": 0.8,
               # (bug 72, the owner's picture 2026-11-18: a boss's Heart Container on a Kokiri shop shelf stood twice the
               #  size of the Pieces of Heart beside it, over the shelf above. Its model is 0.79 m wide and 0.73 tall, a
               #  piece's 0.44 and 0.40: made the piece's size)
               "Obj_Heart_Container": 0.55}
# (the Fairy Bow's model is long front to back, 1.36 m along its own Z: on the Kokiri shop's shelf it lay pointing at
# the viewer, its end alone to be seen behind the price board (its owner's picture, 2026-11-13). A quarter turn about
# the upright laid it across, flat: a thin line. With a quarter turn about Z too it lies across with its curve and
# string to the viewer: seen so on a shelf of the Bazaar and one of the Goron shop, whose own angles differ (of four
# turns tried on each, the one that showed it the same in both). The hammer, the sword and the stick bundle are long
# the same way and lie as they did: seen, and left.)
# (the Kokiri Sword is long the same way, 0.65 m: on the Kokiri shop's shelf a small dark shape behind the price board
# (its owner's picture, 2026-11-13). With the bow's turn it stands on that shop's shelves, blade up, plain to see:
# seen on two of them. Not seen with it in the Bazaar or the Goron shop, where the bow lies across with that turn.
# The Megaton Hammer with it stood on end, taller than its shelf's space, and is left lying; the Deku Stick bundle
# leans as the game's own stick does, with the turn or without, and is left.)
# (the three shields lay flat on their faces (reported from play: the Mirror Shield). A quarter turn about X stands the
# Mirror Shield and the Deku Shield up, their faces to the shop; the same turn showed the Hylian Shield's face upside
# down and the other way its back, so it has the other quarter turn and a half turn about the upright. Each seen so
# on shelves of the Kokiri shop, the Bazaar and the Goron shop, whose own angles differ, raised to stand over the
# price board.)
# (the Fairy Slingshot lay flat and low, half behind its price board: reported from play, 2026-11-14, the Kokiri shop.
#  It is given the bow's turn and lift: seen without a window on the Kokiri shop's four shelves, standing as a Y
#  over its price board)
# (the smallest bundle of arrows, "Five Arrows", is two arrows crossed, lying flat and pointing at the viewer: on the
#  Kokiri shop's shelf they lay at the shelf's foot, half behind the price board (its owner's picture, 2026-11-14;
#  the two larger bundles have a ring and stand over the board). A quarter turn about the upright lays them across,
#  feathers and heads to the viewer; lifted over the board and a little smaller, the arrows being as long as the
#  shelf is wide. Seen without a window on the Kokiri shop's shelves, among four turns tried)
SHELF_TURN = {"TBox_ArrowBundle_Small": (0.0, 1.57, 0.0), "Item_Range_Bow": (0.0, 1.57, 1.57), "Item_Range_SlingShot": (0.0, 1.57, 1.57), "Item_Sword_Kokiri": (0.0, 1.57, 1.57), "Item_Shield_Mirror": (1.57, 0.0, 0.0),
              "TBox_Shield_Deku": (-1.57, 3.14, 0.0), "TBox_Shield_Hylian": (-1.57, 3.14, 0.0)}
# (the empty bottle, Item_Bottle, lay on its side with its mouth to the viewer (bug 53, the Kokiri shop). Of eight turns
#  tried on the Kokiri shop's shelves (seen without a window, 2026-11-18), a quarter turn the other way about X stands it
#  up, cork up; the same turn the other way stood it on its cork)
SHELF_TURN["Item_Bottle"] = (-1.57, 0.0, 0.0)
# A shop whose shelves face otherwise than the Kokiri shop's, the Bazaar's and the Goron shop's: its own turns (bug 63).
# Kakariko's Potion Shop (placement 11, the cabinet's arches): with the turns of the others the Fairy Slingshot lay on its
# side, its fork past the shelf's front, and the Deku Stick bundle lay large over the shelf's front (seen without a window,
# 2026-11-18). A quarter turn about X stands the stick bundle up, plain on its shelf.
SHELF_TURN_SHOP = {"kmedicine": {"Item_DekuStickBundle_Small": (1.57, 0.0, 0.0), "Item_Range_SlingShot": (0.0, 3.14, 1.57)}}
# (and its own sizes and heights, its arches being narrow: standing, the stick bundle reached through the shelf over it.
#  (how much higher, size) for an item, in place of shelf_fit's)
SHELF_FIT_SHOP = {"kmedicine": {"Item_DekuStickBundle_Small": (0.3, 0.4)}}
# (the Market's Potion Shop has the same cabinet (the owner's pictures, 2026-11-18: the Deku Sticks lying at the back of
#  their arch, the Kokiri Sword small and on its side, the bomb bag behind its price board, the Hylian Shield large and
#  over its shelf's edge): the same turns and fits as Kakariko's)
SHELF_TURN_SHOP["medicine"] = dict(SHELF_TURN_SHOP["kmedicine"])
SHELF_FIT_SHOP["medicine"] = dict(SHELF_FIT_SHOP["kmedicine"])
# (bug 74, test pictures 2026-11-19 in "Child Potion Shop at day ...": the Kokiri Sword unturned and 1.3 times its size
#  shows its whole blade, its usual turn lay edge-on and small; the Hylian Shield at 0.75 and 0.15 m up fits its arch,
#  as it was it hung over the shelf's edge)
SHELF_TURN_SHOP["medicine"]["Item_Sword_Kokiri"] = (0.0, 0.0, 0.0)
SHELF_FIT_SHOP["medicine"].update({"Item_Sword_Kokiri": (0.15, 1.3), "TBox_Shield_Hylian": (0.15, 0.75)})
# (bug 76, test pictures 2026-11-19 in "Child Bazaar at Day ...": the Hookshot's model has its middle at the handle, and
#  lying as it does it reached left past its spot; turned half round and at 0.8 it sits on its spot. Every shop: the
#  others' shelves are no wider)
SHELF_TURN["Item_Hookshot"] = (0.0, 3.14, 0.0)
SHELF_SCALE["Item_Hookshot"] = 0.8
# (bug 80, test pictures 2026-11-19 in "Child Goron Shop ...": the Goron shop's shelves are long boxes; the smallest
#  arrow bundle turned the other way and 0.25 m up lies on its spot, its usual turn ran off the shelf's left edge)
SHELF_TURN_SHOP["goron"] = {"TBox_ArrowBundle_Small": (0.0, -1.57, 0.0)}
SHELF_FIT_SHOP["goron"] = {"TBox_ArrowBundle_Small": (0.25, 0.8)}


def shelf_shop(actor):
    """the shop key of a shelf actor (Shop_Rando_<shop>_<place>[_<tier>]), or an empty string"""
    return actor[len(shop_actor("")):].split("_")[0] if actor.startswith(shop_actor("")) else ""


def shelf_turn(actor, item):
    """an item's turn on a shelf of a shop actor: the shop's own, else SHELF_TURN's, else None"""
    if item in SHELF_POSE_AS:   # (the game's own shelf's model and pose: no turn of ours, bug 77)
        return None
    return SHELF_TURN_SHOP.get(shelf_shop(actor), {}).get(item) or SHELF_TURN.get(item)


# An item whose model is made where it is worn, not at its own origin (the gauntlets: 1.17 m up): its shelf's actor is
# put that much lower (shelf_fit). The gauntlets keep their size: their box is the pair's, 1.6 m from one to the other.
SHELF_WORN = 0.5
# (the Goron's Bracelet, small and low: on a shelf of the Kokiri shop with a price board only its top showed over the
#  board (seen without a window, 2026-11-14). It is put this much higher than its box says)
SHELF_MORE = {"Item_Gauntlet_Goron": 0.15}
# (bug 55: the Silver and Golden Gauntlets' only model is the pair Link wears, which shows on no shelf, with its pose
#  or without (seen without a window 2026-11-18 and 19, eight shelves of the Kokiri shop empty). Their shelves show
#  the Goron's Bracelet's model, its row of the list of actors and its box; the name, words and item are their own)
# (the owner, 2026-11-24, with bug 55's own picture: the gauntlets did show, one glove over the Hookshot's shelf beside and
#  one in the shelf's wall. Their model is the worn pair, a glove at each of Link's hands, 1.6 m apart and 0.16 m tall
#  (ModelAabb), shown at its full size. So their shelves show their own model again, a third its size (SHELF_SCALE 0.35:
#  0.56 m from glove to glove), no longer the Bracelet's)
SHELF_MODEL_AS = {"TBox_Shield_Deku": "Shop_Weapon_Shield_Deku", "TBox_Shield_Hylian": "Shop_Weapon_Shield_Hylian"}
# (the owner, 2026-11-24, seeing the small pair at the shelf's edges: "use the same image as the get scene". The get scene
#  poses the worn pair with the item's own animation (ASInfo Item_GetDemo, its AS and Animation), the gloves together;
#  a shelf actor had none (shop_pack leaves them out), so the gloves stood where Link's hands would be. These items'
#  shelves keep their own pose. Bug 55 tried it at full size, the gloves then out of sight in the shelf's walls)
SHELF_OWN_POSE = frozenset(("Item_Gauntlet_Silver", "Item_Gauntlet_Gold"))
# (posed, the pair's box (the worn one) says nothing of what shows: its lift and size by eye, without a window in Kakariko's
#  Potion Shop on the owner's save, 2026-11-24: at 0.1 and 1.0 it sank into the shelf, at 0.35 and 1.2 it floated a little;
#  at 0.27 and 1.2 the pair rests on the shelf, the Skulltula tokens' size. SHELF_SCALE's 0.35 for them is not used)
SHELF_POSE_FIT = {"Item_Gauntlet_Silver": (0.27, 1.2), "Item_Gauntlet_Gold": (0.27, 1.2)}
# (bug 77: a shield bought lay flat in its "You got" scene. The game's own shield shelves (Shop_Weapon_Shield_*) show the
#  worn model with the shop's pose files: a shield's shelf takes those too (SHELF_POSE_AS), and no turn of its own)
SHELF_POSE_AS = frozenset(("TBox_Shield_Deku", "TBox_Shield_Hylian"))
# (bug 56: the Hookshot bought was held up to Link's left. A shop's purchase holds the shelf actor's item by its pouch
#  param's GetDemoOffsetPos (seen without a window: X 0.6 put it to his right, 0.3 over his head), so the Hookshots'
#  shelves have that param's own copy with these X, Y, Z; their chests' scene is the item's own, unchanged)
SHELF_HOLD_OFFSET = {"Item_Hookshot": (0.3, 0.2, 0.0), "Item_Longshot": (0.3, 0.2, 0.0)}
SHELF_MORE.update({"Item_Gauntlet_Silver": 0.15, "Item_Gauntlet_Gold": 0.15})
# (the fields of the list of actors' row that are the model's; ActorName is the item's: it names the shelf, seen
#  2026-11-19 as "Goron Bracelet" with the whole row taken)
SHELF_MODEL_FIELDS = ("FmdbName", "ModelProjectName", "ModelAabbMin", "ModelAabbMax", "AnimationResources")


def shelf_fit(item, box):
    """(how much higher an item's shelf actor is put, how large it is made: 1.0 its own size), by its model's box
    (model_box, or None) and its own numbers"""
    if item in SHELF_POSE_FIT:   # (posed, its box is the worn pair's, not what shows: SHELF_POSE_FIT)
        return SHELF_POSE_FIT[item]
    scale = SHELF_SCALE.get(item, 1.0)
    floor = None
    if box:
        size = max(high - low for low, high in zip(*box))
        if item not in SHELF_SCALE and size > 0:
            if size > SHELF_LONG * 1.3:
                scale = round(SHELF_LONG / size, 2)
        floor = box[0][1]
    if item in SHELF_LIFT:
        return SHELF_LIFT[item], scale
    if floor is not None and floor > SHELF_WORN:
        return round(-floor * scale + SHELF_MORE.get(item, 0.0), 2), scale
    return round(shelf_lift(item, floor) * scale + SHELF_MORE.get(item, 0.0), 2), scale


# A shelf of bundles has a board beside it with how many are in one ("x 10": Shop_Board_Bundle_05, _10, _20, ...),
# an actor of its own in the map file. With another item on the shelf it stayed, and said x 10 under a Kokiri Sword
# (seen in play). The board next to a shelf that sells a shuffled item (within SHELF_BOARD_NEAR of it) is put far
# under the map: not taken out of the file, so nothing that names it is left without it.
SHELF_BOARD, SHELF_BOARD_NEAR, SHELF_BOARD_AWAY = "Shop_Board_Bundle_", 0.5, 2000.0


# ---- Progressive items: what the rules ask for when an upgrade found gives the next one Link has not ----
# The game's side (host/hos_main.c hos_oot_pouch_add) puts the next of an upgrade's family in the pouch whatever was
# found. So Link has the family's second when he has found two of it: a rule that asks for the Silver Gauntlets
# asks for them and for the Goron's Bracelet, the Giant's Wallet for the Adult's too (progressive_need). Only the
# ones the seed shuffles are added: the others are where the game has them, and the rules count on that already.
# Too much, never too little: with both found he has the second, whichever came first.
# The hookshots (Shuffle Dampe's Hookshot): the Longshot asks for the Hookshot under it only when the Hookshot is
# shuffled; before, Dampe's race gave it first, as the rules count on.
PROGRESSIVE_TIERS = (("Item_Gauntlet_Goron", "Item_Gauntlet_Silver", "Item_Gauntlet_Gold"), ("Item_Wallet_Medium", "Item_Wallet_Large"),
                     ("Item_Scale_Silver", "Item_Scale_Gold"), ("Item_Hookshot", "Item_Longshot"))


def progressive_need(need, shuffled):
    """what a rule asks for with Progressive items: each upgrade it names, and the ones under it of its family that
    the seed shuffles"""
    more = set(need)
    for tiers in PROGRESSIVE_TIERS:
        for k, item in enumerate(tiers):
            if item in need:
                more.update(i for i in tiers[:k] if i in shuffled)
    return frozenset(more)


def shelf_item(actor):
    """what goes into the pool for a shelf's own actor: the chests' kind of it, or a red rupee"""
    return next((item for start, item in SHELF_ITEMS if actor.startswith(start)), SHELF_OTHER)


def shop_actor(name):
    """the shelf actor made for an item, or for a shelf (its shop's key and its place: one shelf, one price)"""
    return "Shop_Rando_" + name


# ---- Progressive items on a shelf: the shelf shows what Link would get ----
# With Progressive items a shelf's item of a family gives the family's next for what Link has (host/hos_main.c
# hos_oot_pouch_add), and the shelf showed and named the item the shuffle put there: "Bigger Quiver" with no bow (asked
# for 2026-11-14). A shelf's look, name and the keeper's words are its actor's, which its map file names. So such a
# shelf has an actor for each of its family (SHELF_FAMILIES: the shuffled item's is the shelf's own, the others <the
# shelf's actor>_<k>, k the tier from 0, each at the shelf's price, with its own place, size and turn on the shelf), and
# its map is written once for each choice of them
# (shelf_tier_maps: <mod>/SHELF_TIER_DIR/<the map's path>.<k>[_<k>...], the shelves in their order in SHELF_TIERS).
# The game's side reads the list and, as the map is opened, gives the game the one for what Link has then
# (host/hos_main.c hos_oot_shelf_map): the next of the family, or the shelf's own item when he has the family whole.
# Still sold once: what keeps a shelf sold is its goods list's flag (shelf_flags), whichever actor stands there, and its
# price is the goods list's actor's, the same for each. At most SHELF_TIER_MOST such shelves in one map (each multiplies
# its files by its family's size); the others show their own item. (Tried before this: all the tiers' actors in the map,
# each there by a flag of its own, Presence. The keeper made the game fall as he was talked to, seen without a window
# 2026-11-16, whatever the actors' hashes, links and flags: the map's own two copies of a shelf, before and after the
# Deku Tree, are what the keepers find. So the map keeps its shape, and only the shelf's actor and its place change.)
SHELF_FAMILIES = (("Item_BombBag_Small", "Item_BombBag_Medium", "Item_BombBag_Large"),
                  ("Item_Range_Bow", "Item_Quiver_Medium", "Item_Quiver_Large"),
                  ("Item_Range_SlingShot", "Item_BulletBag_Medium", "Item_BulletBag_Large"),
                  ("Item_Hookshot", "Item_Longshot"),
                  ("Item_Gauntlet_Goron", "Item_Gauntlet_Silver", "Item_Gauntlet_Gold"),
                  ("Item_Scale_Silver", "Item_Scale_Gold"),
                  ("Item_Wallet_Medium", "Item_Wallet_Large"),
                  ("Item_StickBag_Small", "Item_StickBag_Medium", "Item_StickBag_Large"),
                  ("Item_NutBag_Small", "Item_NutBag_Medium", "Item_NutBag_Large"))
SHELF_TIERS, SHELF_TIER_DIR, SHELF_TIER_MOST = "shelf_tiers.txt", "shelf_tiers", 3
# (the owner's run 2026-11-24: a Gold Skulltula's Golden Gauntlets showed the gauntlets, in the world and in the get scene,
# and gave the Goron Bracelet, the family's next.) With Progressive items each tier of a Skulltula drop's family is made a
# pick-up too, and named in SKULL_TIERS beside the seed: the game's side (host/hos_main.c hos_oot_drop_name) shows a
# Skulltula's drop as the family's next when the seed made that a pick-up. Bug 114 had stopped that renaming: the next tier
# was then no pick-up and could not be taken. Not the Bow's and the Slingshot's: their first tier has no words of its own
# (a chest shows them as Weapon_*), so their drop stays the seed's item.
SKULL_TIERS = "skull_tiers.txt"
SKULL_TIERS_NOT = ("Item_Range_Bow", "Item_Range_SlingShot")


def skull_tiers(drops):
    """the family tiers to make pick-ups beside a Skulltula's drops (SKULL_TIERS), sorted: every tier of each family
    (SHELF_FAMILIES) one drop is of, but the Bow's and the Slingshot's"""
    return sorted({t for item in drops for fam in SHELF_FAMILIES if item in fam and fam[0] not in SKULL_TIERS_NOT for t in fam})


def shelf_family(item):
    """the family (SHELF_FAMILIES) an item on a shelf is of, or None"""
    return next((f for f in SHELF_FAMILIES if item in f), None)


def shelf_tier_swap(data, chosen, lifts=None, scales=None, turns=None):
    """A map file whose shelves are already the seed's (shelf_actors) with some of them made another actor: chosen {a
    shelf's actor: the actor in its place}. Each such actor's place, size and turn are its own in place of the shelf's
    (lifts, scales, turns as shelf_actors'): what one adds is taken off and the other's put on. Every other edit of the
    file is kept. Returns the file written anew (the same bytes when nothing is chosen)."""
    tree, version = byml_parse(data)
    actors = tree[1].get("Actors")
    f32 = lambda node: struct.unpack("<f", node[1])[0] if isinstance(node[1], (bytes, bytearray)) and len(node[1]) == 4 else None
    for actor in actors[1] if actors and actors[0] == "array" else ():
        gyaml = actor[1].get("Gyaml", ("", ""))
        new = chosen.get(gyaml[1]) if gyaml[0] == "string" else None
        if not new or new == gyaml[1]:
            continue
        was = gyaml[1]
        actor[1]["Gyaml"] = ("string", new)
        lift = (lifts or {}).get(new, 0.0) - (lifts or {}).get(was, 0.0)
        at = actor[1].get("Translate")
        if lift and at and at[0] == "array" and len(at[1]) == 3 and f32(at[1][1]) is not None:
            at[1][1] = (at[1][1][0], struct.pack("<f", f32(at[1][1]) + lift))
        size, size_was = (scales or {}).get(new, 1.0), (scales or {}).get(was, 1.0)
        if size != size_was:
            actor[1]["Scale"] = ("array", [(0xD2, struct.pack("<f", size))] * 3)
        turn, turn_was = (turns or {}).get(new, (0.0, 0.0, 0.0)), (turns or {}).get(was, (0.0, 0.0, 0.0))
        if turn != turn_was:
            rot = actor[1].get("Rotate")
            angles = [f32(x) or 0.0 for x in rot[1]] if rot and rot[0] == "array" and len(rot[1]) == 3 else [0.0, 0.0, 0.0]
            actor[1]["Rotate"] = ("array", [(0xD2, struct.pack("<f", x - y + z)) for x, y, z in zip(angles, turn_was, turn)])
    return byml_build(tree, version)


def shelf_tier_maps(data, held, tiers, lifts=None, scales=None, turns=None):
    """A map file's versions for the tiers of its shelves of a family: held, the shelves' actors in it that have tiers,
    in order (at most SHELF_TIER_MOST); tiers {a shelf's actor: [its family's actors, smallest first]}. data is the map
    as the seed leaves it, every other edit made. Returns {"<k>_<k>...": the map file with those tiers' actors}."""
    versions = {}
    for combo in itertools.product(*[range(len(tiers[actor])) for actor in held]):
        versions["_".join(str(k) for k in combo)] = shelf_tier_swap(
            data, {actor: tiers[actor][k] for actor, k in zip(held, combo)}, lifts, scales, turns)
    return versions


def shop_price(rng, mode, placement=PLACEMENT):
    """A shelf's price, 1 to SHOP_PRICE_MAX. mode 1: most of them low (an even roll to the power SHOP_LOW_POWER: about
    six in ten within the child's wallet, one in seven past the Adult's), in fives from 10 up; 2: any price as likely as
    another, but for the child's wallet's, which come up a little more often (about four in ten). In both, SHOP_CHILD_MORE
    of the prices are rolled within the child's wallet alone. From placement SHOP_TENS_FROM every price is in tens, 10 at
    least (asked for 2026-11-16: the wallets' 200, 500 and 750 are tens, so no shelf asks for a bigger wallet than it
    did); mode 3, Affordable: every shelf SHOP_AFFORDABLE (the rolls made all the same, so the seed's other choices stay)."""
    most = SHOP_CHILD if rng.random() < SHOP_CHILD_MORE else SHOP_PRICE_MAX
    if mode == 2:
        price = rng.randint(1, most)
    else:
        price = 1 + int((most - 1) * rng.random() ** SHOP_LOW_POWER)
        price = price if price < 10 else min(SHOP_PRICE_MAX, 5 * round(price / 5))
    if mode == 3:
        return SHOP_AFFORDABLE
    return price if placement < SHOP_TENS_FROM else min(most, max(10, 10 * round(price / 10)))


def wallet_need(price):
    """the wallet a price asks for: nothing while the child's holds it"""
    return next((need for most, need in WALLETS if price <= most), WALLETS[-1][1])


# A shield on a shelf names its model in a file the shield Link carries names too (Component/ModelInfo/Weapon_Shield_Deku), and
# the game keeps the first copy of a file's name it loads. The shelf's pack had the game's own copy, so after the Potion Shop's
# Deku Shield was loaded, the shield on Link's back lost the look the cosmetics give it (rando_cosmetics.py SHIELD_PACKS) until
# the game was started again (seen in play, 2026-11-16). The shelf's copy now has the shelf's own name, and the shelf's actor
# names that one: the shield's own name is only ever loaded from the game's packs and the cosmetics'. (The shelf shows the
# shield's own look.)
SHELF_OWN_MODEL = ("Weapon_Shield_Deku", "Weapon_Shield_Hylian", "Weapon_Shield_Mirror")
MODEL_INFO_FILE = "Component/ModelInfo/%s.engine__component__ModelInfo.bgyml"


def own_model_pack(item, pack):
    """(bug 78, the owner's run 2026-11-18) A pick-up's pack (pickup_pack) whose actor names a shield's model file
    (SHELF_OWN_MODEL) with that file renamed the actor's own (MODEL_INFO_FILE % item) and the actor naming it: the
    pick-up of TBox_Shield_Deku, a Skulltula's drop, was opened at the session's start with the game's own copy of
    Weapon_Shield_Deku's model file, and Link's shield lost the cosmetics' look until a restart, as the shelf's had (bug
    44). The pack as it was when its actor names no such file. ValueError: not an archive of the actor's files."""
    files = sarc_read(pack)
    actor = ACTOR_FILE % item
    if actor not in files:
        return pack
    tree, version = byml_parse(files[actor])
    comps = tree[1].get("Components", ("dict", collections.OrderedDict()))[1]
    ref = comps.get("ModelInfoRef")
    model_file = ref_file(ref[1]) if ref else ""
    if not ref or model_file.split("/")[-1].split(".")[0] not in SHELF_OWN_MODEL or model_file not in files:
        return pack
    own = MODEL_INFO_FILE % item
    files[own] = files.pop(model_file)
    comps["ModelInfoRef"] = ("string", "?" + own)
    files[actor] = byml_build(tree, version)
    return sarc_write(files)


def shop_pack(item, item_pack, base_pack, sample_pack, price, pouch=None, name=None, model_pack=None):
    """An item's shelf actor (name: its actor's, shop_actor(item) when not given): (its pack, the names of the three files it has that no other pack has, the name its
    texts go by). The pack is the shelf base's files and the item's; its actor has the base's as its parent and the
    item's own name, model, animation and place in the pouch; its table of game parameters is the item's entries,
    the base's table as its parent, and a price of its own. pouch: pouch files to take in place of the item's ({name:
    bytes}: the ones a pick-up's pack changed, of which the game uses the first copy it loads). model_pack: the pack of
    the item whose model the shelf shows in place of its own (SHELF_MODEL_AS), or None."""
    base, own, sample = sarc_read(base_pack), sarc_read(item_pack), sarc_read(sample_pack)
    name = name or shop_actor(item)
    chain = actor_chain(item, own)
    if not chain:
        raise ValueError("%s: its pack has no actor of that name" % item)
    files = collections.OrderedDict(base)
    for k, v in own.items():
        files.setdefault(k, v)
    for k, v in (pouch or {}).items():
        if k in files:
            files[k] = v

    def part(key):
        for _, tree, _ in chain:
            ref = tree[1].get("Components", ("dict", {}))[1].get(key)
            if ref and ref[0] == "string" and ref[1]:
                return ref
        return None

    if not part("ModelInfoRef") or not part("PouchContentRef"):
        raise ValueError("%s has no model or no place in the pouch: it cannot be put on a shelf" % item)
    actor_name = ACTOR_FILE % name
    table_name = "GameParameter/GameParameterTable/%s.engine__actor__GameParameterTable.bgyml" % name
    price_name = "GameParameter/PriceParam/%s.game__pouchcontent__PriceParam.bgyml" % name
    sample_actor, sample_table = ACTOR_FILE % SHOP_SAMPLE, "GameParameter/GameParameterTable/%s.engine__actor__GameParameterTable.bgyml" % SHOP_SAMPLE
    sample_price = "GameParameter/PriceParam/%s.game__pouchcontent__PriceParam.bgyml" % SHOP_SAMPLE
    if ACTOR_FILE % SHOP_BASE not in base or not {sample_actor, sample_table, sample_price} <= set(sample):
        raise ValueError("the shelf base's pack or the sample shelf's is not what it was")
    _, version = byml_parse(sample[sample_actor])
    # (not the item's pose and animation, ASInfoRef, ASRef and AnimationRef: they are its "item got" scene's: SHELF_POSE, above SHELF_LIFT)
    comps = collections.OrderedDict((key, part(key)) for key in ("ActorNameRef", "ModelInfoRef", "PouchContentRef") if part(key))
    if item in SHELF_OWN_POSE:   # (the item's own pose, its get scene's: SHELF_OWN_POSE)
        comps.update((key, part(key)) for key in ("ASInfoRef", "ASRef", "AnimationRef") if part(key))
    if model_pack is not None:   # (bug 55: another item's model, SHELF_MODEL_AS)
        other = actor_chain(SHELF_MODEL_AS[item], sarc_read(model_pack))
        ref = next((tree[1].get("Components", ("dict", {}))[1].get("ModelInfoRef") for _, tree, _ in other
                    if tree[1].get("Components", ("dict", {}))[1].get("ModelInfoRef")), None)
        source = sarc_read(model_pack).get(ref_file(ref[1])) if ref and ref[0] == "string" else None
        if source is None:
            raise ValueError("%s: the model of %s is not in its pack" % (item, SHELF_MODEL_AS[item]))
        files[MODEL_INFO_FILE % name] = source
        comps["ModelInfoRef"] = ("string", "?" + MODEL_INFO_FILE % name)
        if item in SHELF_POSE_AS:   # (the game's own shelf's pose files, SHELF_POSE_AS)
            parts_of = sarc_read(model_pack)
            for key in ("ASInfoRef", "ASRef", "AnimationRef"):
                ref = next((tree[1].get("Components", ("dict", {}))[1].get(key) for _, tree, _ in other
                            if tree[1].get("Components", ("dict", {}))[1].get(key)), None)
                if ref and ref[0] == "string":
                    comps[key] = ref
                    if ref_file(ref[1]) in parts_of:
                        files.setdefault(ref_file(ref[1]), parts_of[ref_file(ref[1])])
    # (a shield's model file is the shelf's own, under the shelf's name: SHELF_OWN_MODEL)
    model_file = ref_file(comps["ModelInfoRef"][1])
    if model_file.split("/")[-1].split(".")[0] in SHELF_OWN_MODEL and model_file in files:
        own_model = MODEL_INFO_FILE % name
        files[own_model] = files.pop(model_file)
        comps["ModelInfoRef"] = ("string", "?" + own_model)
    if item in SHELF_HOLD_OFFSET:   # (bug 56: the get scene's offset of the item held up, its pouch param's own copy)
        pouch_file = ref_file(comps["PouchContentRef"][1])
        if pouch_file in files:
            tree, ver = byml_parse(files[pouch_file])
            offset = tree[1].setdefault("GetDemoOffsetPos", ("dict", collections.OrderedDict()))[1]
            for axis, value in zip("XYZ", SHELF_HOLD_OFFSET[item]):
                offset[axis] = (0xD2, struct.pack("<f", value))
            own_pouch = "Component/PouchContentParam/%s.game__component__PouchContentParam.bgyml" % name
            files[own_pouch] = byml_build(tree, ver)
            comps["PouchContentRef"] = ("string", "?" + own_pouch)
    comps["GameParameterTableRef"] = ("string", "?" + table_name)
    files[actor_name] = byml_build(("dict", collections.OrderedDict((("$parent", ("string", ACTOR_REF % SHOP_BASE)),
                                                                     ("Components", ("dict", collections.OrderedDict(sorted(comps.items()))))))), version)
    entries = collections.OrderedDict()
    table_ref = part("GameParameterTableRef")
    if table_ref and ref_file(table_ref[1]) in own:
        entries.update(byml_parse(own[ref_file(table_ref[1])])[0][1].get("Components", ("dict", {}))[1])
    entries["PriceParam"] = ("string", "?" + price_name)
    table, table_version = byml_parse(sample[sample_table])   # (the sample's: the shelf base's table as its parent)
    table[1]["Components"] = ("dict", collections.OrderedDict(sorted(entries.items())))
    files[table_name] = byml_build(table, table_version)
    cost, cost_version = byml_parse(sample[sample_price])
    cost[1]["BuyingPrice"] = (cost[1]["BuyingPrice"][0], struct.pack("<I", price))
    files[price_name] = byml_build(cost, cost_version)
    named = part("ActorNameRef")
    return sarc_write(files), [actor_name, table_name, price_name], ref_file(named[1]).split("/")[-1].split(".")[0] if named else item


def shop_rows(data, kind, item, price, name=None):
    """One of the game's three lists of actors (kind: SHOP_TABLES) with the row of an item's shelf actor (name: its
    actor's, shop_actor(item) when not given), in its place
    by name: the item's own row in the list of actors (its model, with a shelf's heaps where they are larger) and
    in the pouch's (with what it costs), a shelf's in the game's."""
    tree, version = byml_parse(data)
    name = name or shop_actor(item)
    by = {r[1]["__RowId"][1]: r for r in tree[1]}
    need = (SHOP_ROW,) if kind == "GameActorInfo" else (item, SHOP_ROW_HEAPS if kind == "ActorInfo" else SHOP_ROW) + (
        (SHELF_MODEL_AS[item],) if kind == "ActorInfo" and item in SHELF_MODEL_AS else ())
    if any(n not in by for n in need):
        raise ValueError("the game's %s has no row of %s" % (kind, " or of ".join(n for n in need if n not in by)))
    number = lambda node, value: (node[0], struct.pack("<I", value))
    if kind == "ActorInfo":   # (the item's row; its model's fields those of the item it is shown as, SHELF_MODEL_AS)
        row = ("dict", collections.OrderedDict(by[item][1]))
        if item in SHELF_MODEL_AS:
            row[1].update((k, v) for k, v in by[SHELF_MODEL_AS[item]][1].items() if k in SHELF_MODEL_FIELDS)
        for k in ("InstanceHeapSize", "PreActorRenderInfoHeapSize"):
            if k in row[1] and k in by[SHOP_ROW_HEAPS][1]:
                row[1][k] = number(row[1][k], max(struct.unpack("<I", row[1][k][1])[0], struct.unpack("<I", by[SHOP_ROW_HEAPS][1][k][1])[0]) + 32768)
    elif kind == "GameActorInfo":
        row = ("dict", collections.OrderedDict(by[SHOP_ROW][1]))
    else:
        row = collections.OrderedDict(by[item][1])
        row["BuyingPrice"] = number(by[SHOP_ROW][1]["BuyingPrice"], price)
        row["SellingPrice"] = number(by[SHOP_ROW][1]["SellingPrice"], 1)
        row = ("dict", collections.OrderedDict(sorted(row.items())))
    row[1]["__RowId"] = ("string", name)
    rows = [r for r in tree[1] if r[1]["__RowId"][1] != name] + [row]
    rows.sort(key=lambda r: r[1]["__RowId"][1])
    return byml_build((tree[0], rows), version)


# ---- Bombchus: a limit of their own ----
# The game counts Bombchus against the Bomb Bag: their row of the list of pouch actors (RSDB/PouchActorInfo) names
# the bombs' limit (MaxNumGameData "Bomb", the flag PouchContentMaxNum.Bomb, 0 until a bag is got) and the small bag
# as what they are carried in. So Bombchus found before a Bomb Bag were lost: a chest of five gave none, the Items
# screen "0/0" (reported from play, the save without a bag). The game has another kind of limit, one of the item's
# own (FixedMaxNum: the Magic Beans' 10, the Gold Skulltula tokens' 100). Every seed gives the Bombchus that
# (BOMBCHU_LIMIT) and takes the bag's two fields away: seen without a window on a save with its Bomb Bag taken out,
# three Bombchus given one by one were 1, 2, 3, a bundle of five made 8, and bombs given the same way stayed 0 (the
# bag is still what bombs ask for: the rules' gating item is as it was). The same change to the file of the
# Bombchu's own pack did nothing: the list is what the game reads. Not seen: a Bombchu used without a bag.
BOMBCHU, BOMBCHU_LIMIT = "Item_Bombchu", 50
POUCH_TABLE = "PouchActorInfo"


# ---- Bombs without the Goron's Bracelet ----
# Found in play, long ago: bombs cannot be used before Darunia gives the bracelet (the original game has no such tie),
# and the rules asked for the bracelet wherever they asked for bombs. Why (looked for when its owner asked for bombs
# without it, 2026-11-14): what Link can lift has a grade. The bracelet and the two gauntlets each give one
# (ExpansionAbilityActor's LiftableGrade: Low, Middle, High), and what is lifted asks for one (LiftableParam's
# LiftGrade): a cucco, Ruto and a Bombchu ask for None, and a bomb for Low, the bracelet's. So every seed makes the
# bomb ask for None (bomb_lift), in each pack that has the bomb's file with a grade (BOMB_PACKS). A bomb flower is
# another matter: its own logic names the bracelet (Obj_BombFlower_Fruit.root.ainb: Armor_Child_Gauntlet_Goron), so
# Dodongo's Cavern, whose way in is a bomb flower's, still asks for it (quest_need). NOT SEEN IN PLAY YET.
BOMB_LIFT = "Component/LiftableParam/Item_Bomb.game__component__LiftableParam.bgyml"
# (three packs of bomb flowers hold a copy of the bomb's file too, beside the flower's own, which keeps its grade:
#  another randomizer of this game changes all five, "whichever is loaded first" (github.com/Mozencaz/OotrR,
#  qol_patches.py, MIT). Looked at here: each has the bomb's file with the bracelet's grade)
BOMB_PACKS = ("Item_Bomb", "Npc_Hylia_ImperialSoldier_Bomb", "Obj_BombFlower_A_01", "Obj_BombFlower_A_04",
              "Obj_BombFlower_Fruit_For_Break_Obj_DeathMtTrail_BrokenRock_A_01")
BOMB_GRADE, BOMB_GRADE_WAS = "None", "Low"


def bomb_lift(data):
    """An actor's pack with the bomb asking for no lifting grade: the new bytes (the same bytes when it asks for none
    already). A pack without the bomb's file, or whose grade is not the one this was written for,
    is an error."""
    parts = sarc_read(data)
    if BOMB_LIFT not in parts:
        raise ValueError("the pack has no %s" % BOMB_LIFT)
    tree, version = byml_parse(parts[BOMB_LIFT])
    grade = tree[1].get("LiftGrade")
    free, was = (struct.pack("<I", murmur3(n.encode())) for n in (BOMB_GRADE, BOMB_GRADE_WAS))
    if not grade or grade[1] not in (free, was):
        raise ValueError("the bomb's lifting grade is not the Goron's Bracelet's, as this was written for")
    if grade[1] == free:
        return data
    # (the file written anew by byml_build was 176 bytes longer and the game fell reading it, at its start: seen
    #  without a window, 2026-11-14. So the grade's four bytes are changed where they are: a hash's node, 0xD3)
    raw, node = parts[BOMB_LIFT], bytes((0xD3,)) + was
    if raw.count(node) != 1:
        raise ValueError("the bomb's lifting grade is not once in its file")
    parts[BOMB_LIFT] = raw.replace(node, bytes((0xD3,)) + free)
    return sarc_write(parts)


def chu_limit(data, limit=BOMBCHU_LIMIT):
    """the list of pouch actors with the Bombchus' limit their own: the new bytes (the same bytes back when it is so
    already). A list without their row, or whose row is not as the game's, is an error."""
    tree, version = byml_parse(data)
    rows = [r for r in tree[1] if r[1].get("__RowId", ("", ""))[1] == BOMBCHU]
    if len(rows) != 1:
        raise ValueError("the list of pouch actors has %d rows of %s" % (len(rows), BOMBCHU))
    row = rows[0][1]
    if "FixedMaxNum" in row and "MaxNumGameData" not in row and "SmallBagActor" not in row:
        return data
    if row.get("MaxNumGameData") != ("string", "Bomb") or "SmallBagActor" not in row or "FixedMaxNum" in row:
        raise ValueError("the Bombchus' row is not counted against the Bomb Bag as this was written for")
    kept = [(k, v) for k, v in row.items() if k not in ("MaxNumGameData", "SmallBagActor")] + [("FixedMaxNum", (0xD1, struct.pack("<i", limit)))]
    row.clear()
    row.update(sorted(kept))
    return byml_build(tree, version)


# ---- A shelf that sold its item stays sold ----
# A shelf that sold its one item was for sale again when its map was loaded again (reported from play, 2026-11-14:
# after the Sun's Song; tools/rando/README.md, "A shelf that is for sale again", has what was found). What a shelf
# sold is the shelf's actor's own, and nothing saved. The game has a way to keep a shelf back, which a goods list's
# entry names: Release, a flag the game waits for before it shows the shelf (the Kokiri shop's fuller stock waits
# for Meet_DekuTree_IsAfter_Step02_Exp). So each shelf that sells a shuffled item waits for a flag of its own that
# says "still for sale" (shelf_flags): it starts a new game true (flag_defaults), and the game's side puts it out
# when the tracker marks the shelf collected and keeps it as the tracker's record says (host/hos_main.c
# oot_shelf_flags, by <mod>/shelf_flags.txt: a shelf's name in the checks file, and its flag's hash).
# The flags are ones the game has and a randomizer game has no use for: the two a pouch actor has (the scene of an
# item got was played, HavePlayedGetEvent.<actor>; the item was got, IsGet.<actor>) of actors that are never got:
# SHELF_FLAG_NEVER (the amiibo's masks and the like), and the game's own shelf actors that this seed sells nowhere
# (SHELF_FLAG_SHOP: a shelf's own actor, when no shelf of the seed still sells it). The first kind before the second.
SHELF_FLAGS = "shelf_flags.txt"
SHELF_FLAG_WORDS = ("HavePlayedGetEvent.", "IsGet.")
# (and after those, for the Kakariko shops of their own, SHOP_TOWNS: with every shelf, 64 shelves and 50 flags. Actors
#  never got: Dark Link's sword, two that are only other actors' base, the heads Link wears with no mask and the bow's
#  three kinds of magic arrows in the pouch; their flags false in a save at the end of the logic run, and the arrows'
#  with the Fire Arrows got. After the others: a seed's shelves keep their flags)
SHELF_FLAG_MORE = ("Weapon_Sword_DarkLinkSword", "Obj_Item_Base", "Weapon_Base", "Armor_Child_Default_Head", "Armor_Adult_Default_Head",
                   "Pouch_Range_BowAndArrow_Fire", "Pouch_Range_BowAndArrow_Ice", "Pouch_Range_BowAndArrow_Light")
SHELF_FLAG_NEVER = ("Armor_Child_Mask_Amiibo0", "Armor_Child_Mask_Amiibo1", "Pouch_Amiibo", "Armor_Mask_Base", "Weapon_Shield_DarkLinkShield")
SHELF_FLAG_SHOP = ("Shop_ArrowBundle_01", "Shop_ArrowBundle_02", "Shop_ArrowBundle_03", "Shop_BombBundle_01", "Shop_BombBundle_02", "Shop_BombBundle_03",
                   "Shop_BombBundle_04", "Shop_BombchuBundle_01", "Shop_BombchuBundle_02", "Shop_BombchuBundle_03", "Shop_BombchuBundle_04",
                   "Shop_BombchuBundle_05", "Shop_BombchuBundle_06", "Shop_BombchuBundle_07", "Shop_BombchuBundle_08", "Shop_DekuNutBundle_01",
                   "Shop_DekuNutBundle_02", "Shop_DekuSeedBundle_01", "Shop_DekuSeedBundle_02", "Shop_DekuStickBundle_Medium")


def shelf_flags(count, every=False, shield=False, placement=PLACEMENT):
    """the flags of `count` shelves that sell a shuffled item, in the shelves' order: names of the game's flags that
    this seed has no use for (see above). every and shield: as shop_slots'. ValueError: more shelves than flags."""
    sold = set()   # (the game's own shelf actors that the seed still sells somewhere)
    for shop in shops(placement):
        taken = set(shop_slots(shop, every, shield))
        sold.update(actor for slot in list(shop.slots) + list(shop.rest) + ([SHIELD_SHELF[1:]] if shop.key == SHIELD_SHELF[0] else [])
                    for actor in [slot[1]] if tuple(slot) not in taken)
    actors = list(SHELF_FLAG_NEVER) + [n for n in SHELF_FLAG_SHOP if n not in sold]
    names = [word + actor for word in SHELF_FLAG_WORDS for actor in actors]
    names += [word + actor for word in SHELF_FLAG_WORDS for actor in SHELF_FLAG_MORE]   # (after: the others keep their places)
    if count > len(names):
        raise ValueError("%d shelves and %d flags to keep them sold by" % (count, len(names)))
    return names[:count]


def shop_goods(data, sells, shown=None):
    """A keeper's goods list with the places of `sells` ({place: (the game's own shelf actor there, the new one)})
    selling the new actor, one in stock, from the start (what the game waits for before it shows a shelf, and what
    it takes off its price, are left out). shown: {place: the flag the shelf waits for} (shelf_flags), for the
    places that have one. ValueError: a place whose actor is not the one named."""
    tree, version = byml_parse(data)
    goods = tree[1].get("GoodsList")
    if not goods or goods[0] != "array":
        raise ValueError("no goods list")
    stock = next((g[1]["StockNum"][0] for g in goods[1] if "StockNum" in g[1]), 0xD3)
    for index, (old, new) in sells.items():
        if index >= len(goods[1]) or goods[1][index][1].get("Actor", ("", ""))[1] != ACTOR_REF % old:
            raise ValueError("the goods list's place %d is not %s" % (index, old))
        entry = collections.OrderedDict((k, v) for k, v in goods[1][index][1].items() if k not in ("Release", "PriceOffset", "ConditionalPriceOffsetList"))
        entry["Actor"] = ("string", ACTOR_REF % new)
        entry["StockNum"] = (stock, struct.pack("<I", 1))
        if shown and index in shown:
            entry["Release"] = ("dict", collections.OrderedDict((("IsCheckReleaseGameData", (0xD0, struct.pack("<I", 1))),
                                                                 ("ReleaseGameData", ("string", shown[index])))))
        goods[1][index] = ("dict", collections.OrderedDict(sorted(entry.items())))
    return byml_build(tree, version)


def shelf_actors(data, sells, lifts=None, scales=None, turns=None):
    """A map file with its shelves of `sells` ({(the game's own shelf actor, its place in the row): the new one})
    made the new actor: (the file written anew, or None when it has none of them; how many). lifts: {a new actor:
    how much higher its shelf's actor is put}; scales: {a new actor: how large it is made}, where not its own size.
    The board of how many a bundle holds beside such a shelf is put out of sight (SHELF_BOARD)."""
    tree, version = byml_parse(data)
    actors = tree[1].get("Actors")
    n = 0
    number = lambda node: struct.unpack("<f", node[1])[0] if isinstance(node[1], bytes) and len(node[1]) == 4 else None
    place = lambda actor: ([number(x) for x in actor[1]["Translate"][1]]
                           if actor[1].get("Translate", ("", ()))[0] == "array" and len(actor[1]["Translate"][1]) == 3 else None)
    changed = []   # (where the shelves that sell a shuffled item were, before any lift)
    for actor in actors[1] if actors and actors[0] == "array" else ():
        gyaml = actor[1].get("Gyaml", ("", ""))[1]
        index = actor[1].get("Dynamic", ("dict", {}))[1].get("ShopItemIndex")
        if sells.get((gyaml, struct.unpack("<I", index[1])[0] if index and isinstance(index[1], bytes) and len(index[1]) == 4 else 0)):
            at = place(actor)
            if at and None not in at:
                changed.append(at)
    for actor in actors[1] if actors and actors[0] == "array" else ():
        gyaml = actor[1].get("Gyaml", ("", ""))
        at = place(actor)
        if (gyaml[0] == "string" and gyaml[1].startswith(SHELF_BOARD) and at and None not in at and
                any(abs(at[0] - x) <= SHELF_BOARD_NEAR and abs(at[2] - z) <= SHELF_BOARD_NEAR and abs(at[1] - y) <= SHELF_BOARD_NEAR for x, y, z in changed)):
            node = actor[1]["Translate"][1]
            node[1] = (node[1][0], struct.pack("<f", at[1] - SHELF_BOARD_AWAY))
    for actor in actors[1] if actors and actors[0] == "array" else ():
        gyaml = actor[1].get("Gyaml", ("", ""))[1]
        index = actor[1].get("Dynamic", ("dict", {}))[1].get("ShopItemIndex")
        new = sells.get((gyaml, struct.unpack("<I", index[1])[0] if index and isinstance(index[1], bytes) and len(index[1]) == 4 else 0))
        if new and actor[1].get("Gyaml", ("", ""))[0] == "string":
            actor[1]["Gyaml"] = ("string", new)
            at = actor[1].get("Translate")
            if (lifts or {}).get(new) and at and at[0] == "array" and len(at[1]) == 3 and isinstance(at[1][1][1], bytes) and len(at[1][1][1]) == 4:
                at[1][1] = (at[1][1][0], struct.pack("<f", struct.unpack("<f", at[1][1][1])[0] + lifts[new]))
            size = (scales or {}).get(new)
            if size and size != 1.0:
                actor[1]["Scale"] = ("array", [(0xD2, struct.pack("<f", size))] * 3)
            turn = (turns or {}).get(new)
            if turn:   # (turned on its shelf: added to the shelf's own angles, x, y, z in radians)
                was = actor[1].get("Rotate")
                angles = [number(x) or 0.0 for x in was[1]] if was and was[0] == "array" and len(was[1]) == 3 else [0.0, 0.0, 0.0]
                actor[1]["Rotate"] = ("array", [(0xD2, struct.pack("<f", a + b)) for a, b in zip(angles, turn)])
            n += 1
    return (byml_build(tree, version) if n else None), n


def msbt_hash(label, groups):
    """the group of a text file's labels that a label is in"""
    h = 0
    for ch in label.encode():
        h = (h * 0x492 + ch) & 0xffffffff
    return h % groups


def msbt_add(data, label, text):
    """The text file with another line, `label`, of the bytes `text` (its closing zero byte is added), the last of
    its texts. A label it has is given the text (msbt_set). ValueError: a file with more than labels and texts (a
    line's attributes are not known how to write)."""
    try:
        msbt_text(data, label)
        return msbt_set(data, label, text)
    except ValueError as e:
        if "has no line" not in str(e):
            raise
    out = bytearray(data[:0x20])
    at = 0x20
    for _ in range(struct.unpack_from("<H", data, 0x0e)[0]):
        kind, size = data[at:at + 4], struct.unpack_from("<I", data, at + 4)[0]
        body = at + 0x10
        sec = bytearray(data[body:body + size])
        if kind == b"LBL1":
            groups = struct.unpack_from("<I", sec, 0)[0]
            labels, n = [[] for _ in range(groups)], 0
            for g in range(groups):
                count, off = struct.unpack_from("<II", sec, 4 + 8 * g)
                for _k in range(count):
                    ln = sec[off]
                    labels[g].append(bytes(sec[off:off + 1 + ln + 4]))
                    off += 1 + ln + 4
                    n += 1
            labels[msbt_hash(label, groups)].append(bytes([len(label.encode())]) + label.encode() + struct.pack("<I", n))
            sec = bytearray(struct.pack("<I", groups) + bytes(8 * groups))
            for g in range(groups):
                struct.pack_into("<II", sec, 4 + 8 * g, len(labels[g]), len(sec))
                sec += b"".join(labels[g])
        elif kind == b"TXT2":
            n = struct.unpack_from("<I", sec, 0)[0]
            offs = [struct.unpack_from("<I", sec, 4 + 4 * i)[0] for i in range(n)] + [size]
            texts = [bytes(sec[offs[i]:offs[i + 1]]) for i in range(n)] + [bytes(text) + b"\0"]
            sec = bytearray(struct.pack("<I", n + 1) + bytes(4 * (n + 1)))
            for i, t in enumerate(texts):
                struct.pack_into("<I", sec, 4 + 4 * i, len(sec))
                sec += t
        else:
            raise ValueError("a text file with a section %r: a line cannot be added" % bytes(kind))
        fill = data[body + size:body + (size + 15 & ~15)][:1] or b"\xab"
        out += kind + struct.pack("<I", len(sec)) + data[at + 8:at + 0x10] + sec + fill * (-len(sec) % 16)
        at = body + (size + 15 & ~15)
    struct.pack_into("<I", out, 0x12, len(out))
    return bytes(out)


def shop_caption(data, name):
    """The pouch's text file with the words a shop shows under an item's name, <name>_ShopCaption, for an item that
    has none: its own description (<name>_Caption), or what is said when it is got (<name>_GetCaption). None: it
    has the line, or neither of the other two."""
    try:
        msbt_text(data, name + "_ShopCaption")
        return None
    except ValueError:
        pass
    for other in ("_Caption", "_GetCaption"):
        try:
            a, b = msbt_text(data, name + other)
        except ValueError:
            continue
        return msbt_add(data, name + "_ShopCaption", bytes(data[a:b]).rstrip(b"\0"))
    return None


# A shop keeper's line names the item on the shelf from its <name>_Name line in lowercase ("Lookin' at the
# <Shop_SelectItemName>?"), save each word with a tag before it (group 0xc9, tag 0x0d: "^Deku ^Shield", "Five ^Deku
# Nuts"). An item the game never sells (one with no _ShopCaption of its own: shop_caption) has none, so the keeper said
# "the kokiri sword?", "the saria's song?" (seen in play). Such a name keeps its capitals in English (SHOP_NAME_CAPS):
# each word that starts with a capital is given the tag. The tag is the game's own in its names, so the name looks the
# same where it is shown as it is (the pause menu, a shelf's title). Other languages are left as they are.
NAME_CAP = b"\x0e\xc9\x00\x0d\x00\x00\x00"
SHOP_NAME_CAPS = ("USen", "EUen")


def shop_name_caps(data, name):
    """The pouch's text file with each word of <name>_Name that starts with a capital letter given the tag that keeps
    it so in a keeper's line (NAME_CAP). None: no such line, or nothing to tag."""
    try:
        a, b = msbt_text(data, name + "_Name")
    except ValueError:
        return None
    raw = bytes(data[a:b]).rstrip(b"\0")
    out, i, changed, word_start = bytearray(), 0, False, True
    while i < len(raw):
        if raw[i] == 0x0e:   # (a tag, kept whole: its parameters' size is at +5)
            n = 7 + struct.unpack_from("<H", raw, i + 5)[0]
            out += raw[i:i + n]
            i += n
            continue
        if word_start and 0x41 <= raw[i] <= 0x5a and not out.endswith(NAME_CAP):
            out += NAME_CAP
            changed = True
        word_start = raw[i] in b" -\n"
        out.append(raw[i])
        i += 1
    return msbt_set(data, name + "_Name", bytes(out)) if changed else None


# ---- a scrub's words ----
# A sale's text is the scrub's own, named in the sale's call (SellerMessageId): "This bag will allow you to carry more
# Deku sticks. It's 40 rupees. Wanna buy it?" for a sale that is now a Bomb Bag (seen in play). The texts are in the
# language archives (Mals/<language>.Product.<n>.sarc.zs), a file a subject (EventFlowMsg/Enemy_Event.msbt: UTF-8, a
# line's tags the byte 0x0E, then its group, type and size as 16-bit numbers, then its bytes). No line of the scrubs'
# is without its item, so the words before "It's <price> rupees. Wanna buy it?" of a sale that sells another item are
# made SCRUB_WORDS. The line is shorter then, and the file is written anew with it (msbt_set): it and its archive are
# smaller, never bigger, so the size table's entry still holds them. The price and the question, with their tags, are
# as they were. English only (the two English archives): the other languages keep the scrub's own words. The two
# Pieces of Heart are one line. The stick scrub has two: ..._02 is what he says the first time, two pages ("Do you
# know about Deku sticks? ..." and "And this bag can carry a lot of Deku sticks! It's ..."; seen in play, the first
# of them left as it was), made the one page.
SCRUB_TEXT = "EventFlowMsg/Enemy_Event.msbt"
SCRUB_LANGS = ("USen", "EUen")
SCRUB_WORDS = "I've got something special for you."
SCRUB_LINES = {"scrub_heart_field": ("Enemy_Scrub_Business_Heart_01",), "scrub_heart_secret": ("Enemy_Scrub_Business_Heart_01",),
               "scrub_sticks": ("Enemy_Scrub_Business_DekuStickPouch_01", "Enemy_Scrub_Business_DekuStickPouch_02"),
               "scrub_nuts": ("Enemy_Scrub_Business_DekuNutsPouch_01",)}


def msbt_text(data, label):
    """where a line of a text file (MSBT) is: (its first byte, the byte after its last), by its label. ValueError: not
    such a file, or no such label."""
    if data[:8] != b"MsgStdBn" or data[8:10] != b"\xff\xfe" or data[0x0c] != 0:
        raise ValueError("not a little-endian UTF-8 text file")
    at, index, texts = 0x20, None, None
    for _ in range(struct.unpack_from("<H", data, 0x0e)[0]):
        kind, size = data[at:at + 4], struct.unpack_from("<I", data, at + 4)[0]
        body = at + 0x10
        if kind == b"LBL1":
            for g in range(struct.unpack_from("<I", data, body)[0]):
                n, off = struct.unpack_from("<II", data, body + 4 + 8 * g)
                p = body + off
                for _k in range(n):
                    ln = data[p]
                    if data[p + 1:p + 1 + ln] == label.encode():
                        index = struct.unpack_from("<I", data, p + 1 + ln)[0]
                    p += 1 + ln + 4
        elif kind == b"TXT2":
            texts = (body, size)
        at = body + (size + 15 & ~15)
    if index is None or texts is None:
        raise ValueError("the text file has no line %s" % label)
    body, size = texts
    n = struct.unpack_from("<I", data, body)[0]
    if index >= n:
        raise ValueError("the line %s is past the file's texts" % label)
    start = struct.unpack_from("<I", data, body + 4 + 4 * index)[0]
    end = struct.unpack_from("<I", data, body + 4 + 4 * (index + 1))[0] if index + 1 < n else size
    return body + start, body + end


def msbt_set(data, label, text):
    """The text file with the line `label` made the bytes `text` (its closing zero byte is added): the file written
    anew, the texts after it moved, the sections' and the file's sizes set. The other lines and sections are as they
    were."""
    start, end = msbt_text(data, label)
    out = bytearray(data[:0x20])
    at = 0x20
    for _ in range(struct.unpack_from("<H", data, 0x0e)[0]):
        kind, size = data[at:at + 4], struct.unpack_from("<I", data, at + 4)[0]
        body = at + 0x10
        sec = bytearray(data[body:body + size])
        if kind == b"TXT2":
            n = struct.unpack_from("<I", sec, 0)[0]
            offs = [struct.unpack_from("<I", sec, 4 + 4 * i)[0] for i in range(n)] + [size]
            index = next(i for i in range(n) if body + offs[i] == start)
            texts = [bytes(sec[offs[i]:offs[i + 1]]) for i in range(n)]
            texts[index] = bytes(text) + b"\0"
            sec = bytearray(struct.pack("<I", n) + bytes(4 * n))
            for i, t in enumerate(texts):
                struct.pack_into("<I", sec, 4 + 4 * i, len(sec))
                sec += t
        fill = data[body + size:body + (size + 15 & ~15)][:1] or b"\xab"   # (what the file fills a section's end with)
        out += kind + struct.pack("<I", len(sec)) + data[at + 8:at + 0x10] + sec + fill * (-len(sec) % 16)
        at = body + (size + 15 & ~15)
    struct.pack_into("<I", out, 0x12, len(out))
    return bytes(out)


def scrub_words(data, label, words=SCRUB_WORDS):
    """The text file with the sale line `label` saying `words` before its price ("It's ..."): the new bytes (the
    file is shorter by what the scrub's own words were longer: msbt_set), or None when it says so already. The tags
    at the line's start and everything from "It's" on are as they were; a line of two pages is one."""
    start, end = msbt_text(data, label)
    a = start
    while a + 8 <= end and data[a] == 0x0E:   # (the tags the line starts with)
        a += 7 + struct.unpack_from("<H", data, a + 5)[0]
    b = data.find(b"It's", a, end)
    if b < 0:
        raise ValueError("the line %s names no price" % label)
    last = end
    while last > b and data[last - 1] == 0:   # (its closing zero byte, and what fills the section after the last line)
        last -= 1
    sep = b"\n" if data[b - 1:b] == b"\n" else b" "
    new = bytes(data[start:a]) + words.encode("utf-8") + sep + bytes(data[b:last])
    if len(new) > last - start:
        raise ValueError("the line %s would grow: the words are longer than the scrub's own" % label)
    if new == bytes(data[start:last]):
        return None
    return msbt_set(data, label, new)


def scrubs_swapped():
    """SCRUBS with the two Pieces of Heart's area and name as the game has their scrubs (SCRUB_SWAP_FROM): the "Secret"
    entry's in Hyrule Field's grotto, the pouch entry's in Death Mountain Crater"""
    by = {g.key: g for g in SCRUBS}
    field, secret = by["scrub_heart_field"], by["scrub_heart_secret"]
    swap = {"scrub_heart_field": field._replace(area=secret.area, name="the Business Scrub in the crater: a Piece of Heart"),
            # (the password's: Hyrule Field's note 07 read, an adult's, ADULT; no hammer for the grotto)
            "scrub_heart_secret": secret._replace(area=field.area, name="the Business Scrub with a secret (the password): a Piece of Heart",
                                                  need=ADULT)}
    return tuple(swap.get(g.key, g) for g in SCRUBS)


SCRUB_PLACES_SWAPPED = {"scrub_heart_field": ("C", (-23.0, 119.1, 33.0)), "scrub_heart_secret": ("A", (25.0, 129.9, 22.1))}   # (an adult's: the password is read as one, ADULT)


def gift_hash(key):
    """a gift's place among the chests' hashes: its own, the same in every seed (no chest's is this high)"""
    return 0xF1F7000000000000 | zlib.crc32(key.encode())


def quest_need(need, area, tunics=False, deep=False):
    """what a chest or a Gold Skulltula asks for (by the rules made before Quest rewards) with the gifts' two gating
    items named: the bracelet in Dodongo's Cavern, whose way in is a bomb flower's, and where a rule asks for
    everything; the Silver Scale wherever an adult is. Bombs no longer ask for the bracelet: every seed lets Link
    lift a bomb without it (bomb_lift)."""
    need = set(need)
    if area == "DodongoCavern" or need >= THIRTEEN:
        need.add(BR)
    if need >= ADULT:
        need.add(SSC)
    if tunics:   # (placement 12: an adult's check where heat or deep water hurts, and every rule past the Fire and Water Temples)
        if need >= ADULT and area in TUNIC_AREAS and not (deep and area == "ZoraFountain"):
            need.add(TUNIC_AREAS[area])
        if deep and IRON in need:   # (placement 17: the Iron Boots sink Link into deep water, TUNIC_WATER_FROM)
            need.add(ZT)
        if need >= MEDALS3 or need >= THIRTEEN:
            need |= TUNICS
    return frozenset(need)


class Either(tuple):
    """A rule with alternatives (placement 5): a check is got when any one of them is held, each a frozenset of items
    as a plain rule is. A plain rule stays a frozenset; met() and each() take either."""
    def __new__(cls, ways):
        ways = tuple(dict.fromkeys(frozenset(w) for w in ways))
        if not ways:
            raise ValueError("a rule with no way")
        return tuple.__new__(cls, ways)

    def __repr__(self):
        return "Either(%s)" % " | ".join(sorted("{%s}" % ", ".join(sorted(w)) for w in self))


def met(need, have):
    """whether what Link has (a set) is what a rule asks for: every item of a plain rule, of one of an Either's ways"""
    return any(way <= have for way in need) if isinstance(need, Either) else need <= have


def each(step, need, *args, **kwargs):
    """a rule as step makes it (a function from a frozenset to a frozenset, or to an Either): of each way of an Either
    (one way made two is two ways), or of a plain rule"""
    if not isinstance(need, Either):
        return step(need, *args, **kwargs)
    ways = []
    for way in need:
        made = step(way, *args, **kwargs)
        ways += list(made) if isinstance(made, Either) else [made]
    return either(ways)


def either(ways):
    """a rule from its ways: a plain one when they are one way, nothing when one of them asks for nothing"""
    ways = [frozenset(w) for w in ways]
    if any(not w for w in ways):
        return NONE
    ways = list(dict.fromkeys(ways))
    return Either(ways) if len(ways) > 1 else ways[0]


def hook_need(need, also=None):
    """one way of a rule with the Hookshot asked for (Shuffle Dampe's Hookshot): the Longshot does as well, the game
    keeping them as two items (the race asks for either), and `also` where a check's own rule takes another (HOOK_OR).
    A way that names one of them already is as it was."""
    ways = (HOOK, LONG) + ((also,) if also else ())
    return need if any(w in need for w in ways) else either([need | {w} for w in ways])


def hook_asks(area, event="", key=None, h=None):
    """whether a check's rule asks for the Hookshot (Shuffle Dampe's Hookshot): by its area, its chest's event, its
    gift's key or its Gold Skulltula's hash"""
    return area in HOOK_AREAS or event == DAMPE_EVENT or key in HOOK_GIFTS or h in HOOK_SKULLS


def race_words(gives_now):
    """{what the race's flow names: what it names now} when its Hookshot chest gives another item: both hookshots' names
    (its questions of the pouch and of what was got) become the name of the item's flags (lesson_flag)"""
    if gives_now == HOOK:
        return {}
    return {HOOK: lesson_flag(gives_now), LONG: lesson_flag(gives_now)}


# Zora's Domain for a child (placement 5, the game's owner's word): by Zora's River, which asks for bombs (its boulders)
# and Zelda's Lullaby (the waterfall), or by Lake Hylia, which asks for the Silver Scale (the dive into the Domain)
# and the way out of the forest. A rule of a child's place in Zora's Domain or Jabu-Jabu that asks for the river's
# way (CHILD_BOMBS: the Zoras' diving game, the Zora shop, Jabu-Jabu's chest with Ruto) gets the lake's way beside it:
# what it asks for besides the river's way, with CHILD and the Silver Scale. The songs are named before this (song_need
# adds the Lullaby there), and the lake's way leaves it out.
ZORA_WAY_AREAS = ("ZoraDomain", "InsideJabuJabuBelly")


def zora_ways(need, area):
    """a rule of a place in Zora's Domain or Jabu-Jabu with the lake's way beside the river's (see above)"""
    if area not in ZORA_WAY_AREAS or isinstance(need, Either) or not need >= CHILD_BOMBS or BM in need:
        return need
    lake = (need - CHILD_BOMBS - {ZL}) | CHILD | {SSC}
    return either((need, lake))


# Open forest exit (placement 5): CHILD in a rule is the forest's way out (the sword and the Slingshot, the Deku Tree
# done), which the setting opens from a new game's start: so a rule that asks for it, and not for what it takes to be
# an adult (ADULT: the Boomerang, Jabu-Jabu, among it), asks for it no more. An adult's rules keep it: the three
# stones still ask for the Deku Tree. In Dodongo's Cavern CHILD was also the way in, which bombs open (FOREST_FLOOR):
# its rules keep bombs.
FOREST_FLOOR = {"DodongoCavern": frozenset((BB,))}
# Gifts that the story holds back until the Deku Tree is done, whatever the way out of the forest (placement 6): Zelda
# is met only after the Deku Tree's quest sends Link to the castle (Goto_HyruleCastle), and Impa's lesson follows her.
# Saria's lesson in the meadow waits for the same meeting: its trigger asks for DoorOfTime_IsAfter_Step01_Exp, which
# Goto_HyruleCastle_MeetZelda sets (SacredForestMeadow_Child_Prefab_bbc3; found in play, 2026-11-15: the lesson was
# not there in a new game with Open forest exit). Open forest exit leaves their CHILD (the Deku Tree done) in place.
DEKU_STORY = ("song_zelda", "song_saria", "zelda_letter", "fairy_ocarina")
# The Deku Tree's Slingshot room (room 2) can't be left without the Slingshot in the remake: its way out is a ladder
# that the eye switch drops (Obj_InsideTheDekuTree_FallingLadder_A_01, Obj_EyeSwitch_A_02), and a child has no warp
# song (the owner's word, 2026-11-15). Its two chests, the Slingshot's own and "Chest (Deku Nuts), room 2", ask for the
# Slingshot from elsewhere (placement 7), with Open forest exit too. Nothing stops Link walking in without it; the
# tracker's Return home takes him out. The owner chose this for now over keeping the Slingshot in its chest, and may
# look at it again.
SLINGSHOT_ROOM = (0x0b66198d17d6584e, 0xb4ca60d52ca4d05f)
# The Deku Tree's third floor (room 3, y ~121-126: "Chest (Deku Nuts), room 3" and "Gold Skulltula, room 3") is reached in
# the remake with the Slingshot or the Boomerang, and a weapon for the big Skulltula at its door (the other randomizer's
# logic, OOTRR adf81ae, "Match the Deku Tree ... logic to the remake", 2026-11-18). Ours asked for the sword alone, so
# the Slingshot could be put there. From placement 15 both ask for CHILD (the sword and the Slingshot; the Boomerang's way
# is not counted: too much, never too little). NOT SEEN IN PLAY: which room the remake calls the third floor was matched by
# height only.
DEKU_THIRD_FLOOR = (0x9dc359c40cd5dfe7, 0xbce05898ce61f1c0)
DEKU_THIRD_FROM = 15


def forest_open(need, area=None):
    """a rule with Open forest exit (see above); area: the place's, for FOREST_FLOOR"""
    if not need >= CHILD or BM in need:
        return need
    return frozenset((need - CHILD) | FOREST_FLOOR.get(area, NONE))


def rule(area, event):
    """what a chest of this area with this event asks for; an area the rules do not know: everything"""
    default, by_event = RULES.get(area, (PROGRESSION, {}))
    return by_event.get(event, default)


# Counted tokens (bug 67, placement 12). The Skulltula house's rewards ask for a number of Gold Skulltula tokens: its
# flow asks the pouch (GatheringTokenGold: PouchData.Item_Token_Gold.StockNum at 10, 20, 30, 40 and 50), so a token got
# anywhere counts, from a Skulltula, a chest, a gift or a piece. A rule asks for N of them by a word of its own,
# tokens(N) ("Tokens:N"), held when N places that give a token can be reached: collect and reach count the places of
# placed whose item is TOKEN and whose rule is met, and hold tokens(N) for each N of TOKEN_COUNTS up to that count.
# Every other step that makes a rule (the progressive items, Open forest exit, the Door of Time...) leaves the word as
# it is, and the tracker's file writes it "T<N>" (check_lines), which the Tracker tab reads by the pouch's tokens.
TOKEN_WORD = "Tokens:%d"
TOKEN_COUNTS = (10, 20, 30, 40, 50)


def tokens(n):
    """the word a rule asks for n tokens by"""
    return TOKEN_WORD % n


def token_marks(count):
    """the words of TOKEN_COUNTS that `count` tokens hold"""
    return {tokens(n) for n in TOKEN_COUNTS if n <= count}


def token_count(word):
    """N of the word tokens(N), or None for an item"""
    head, _, n = word.partition(":")
    return int(n) if head == "Tokens" and n.isdigit() else None


def collect(placed):
    """What Link can get from nothing: placed is [(what the chest asks for, its item)]. Returns the spheres: the
    items each round of opening every chest he can reach adds. The tokens of the places reached are counted, for the
    rules that ask for a number of them (tokens): the words they hold are not in the spheres."""
    have, spheres = set(), []
    while True:
        new = sorted({item for need, item in placed if item in PROGRESSION and item not in have and met(need, have)})
        marks = token_marks(sum(1 for need, item in placed if item == TOKEN and met(need, have))) - have
        if not new and not marks:
            return spheres
        have.update(new)
        have.update(marks)
        if new:
            spheres.append(new)


def reach(have, placed):
    """have (any iterable: each token in it counts), and every item that can then be got from the chests of placed,
    with the words of the tokens held (tokens)"""
    have = list(have)
    count = have.count(TOKEN)
    have = set(have) | token_marks(count)
    got = [False] * len(placed)
    grew = True
    while grew:
        grew = False
        for k, (need, item) in enumerate(placed):
            if not got[k] and met(need, have):
                got[k] = True
                count += item == TOKEN
                if item not in have:
                    have.add(item)
                    grew = True
        marks = token_marks(count) - have
        if marks:
            have |= marks
            grew = True
    return have


def stays_why(c, events, placement=PLACEMENT):
    """Why a chest keeps its own item whatever the settings, or None. events: chests that start an event take part too.
    placement: the version of the rules (a seed made by an earlier one is made again as it was)."""
    if placement == 2 and c.event in LOCKED_ROOMS:
        return "its room cannot be left without the item it holds"
    kept = [k for k in KEEP_IF if k in c.params]
    if placement >= 12 and kept == ["Drop__CheckActor", "Drop__DropActor_Substitute"]:
        kept = []   # (SUBSTITUTE_CHESTS: a chest that gives another item when Link has one already takes part)
    if placement >= 12 and c.hash in DAMPE_RACE_CHESTS:
        return None   # (Dampe's race's Piece of Heart chest takes part: DAMPE_RACE_CHESTS)
    if HOOK_SHUFFLED and c.hash == DAMPE_HOOK_CHEST:
        return None   # (Shuffle Dampe's Hookshot: its chest takes part, HOOK)
    if "GetEventName" in kept and (c.event in PLAIN_EVENTS or events and not c.event.startswith("MiniGame")):
        kept.remove("GetEventName")
    if kept == ["GetEventName"]:
        return "starts an event (--event-chests lets them take part)"
    if kept:
        return "a mini-game's, or depends on what Link has"
    if "MiniGame" in c.item:
        return "a mini-game's item"
    return None


def table(d, at):
    n = int.from_bytes(d[at + 1:at + 4], "little")
    out = []
    for k in range(n):
        s = at + struct.unpack_from("<I", d, at + 4 + 4 * k)[0]
        out.append(d[s:d.index(b"\0", s)].decode("utf-8", "replace"))
    return out


def entries(d, at, keys):
    """a dictionary node's (key, type, value, where its value is)"""
    if d[at] != 0xC1:
        return
    for k in range(int.from_bytes(d[at + 1:at + 4], "little")):
        e = at + 4 + 8 * k
        key = int.from_bytes(d[e:e + 3], "little")
        yield keys[key] if key < len(keys) else "", d[e + 3], struct.unpack_from("<I", d, e + 4)[0], e + 4


def chests(d):
    """Every actor with a Dynamic.Drop__DropActor (chests, and pots and the like). And the key and string tables."""
    if d[:2] != b"YB":
        raise ValueError("not a little-endian BYML")
    key_at, str_at, root = struct.unpack_from("<III", d, 4)
    keys, strings = table(d, key_at), table(d, str_at)
    found = []
    for name, kind, value, _ in entries(d, root, keys):
        if name != "Actors" or kind != 0xC0:
            continue
        n = int.from_bytes(d[value + 1:value + 4], "little")
        vals = value + 4 + (n + 3 & ~3)
        for i in range(n):
            if d[value + 4 + i] != 0xC1:
                continue
            actor = struct.unpack_from("<I", d, vals + 4 * i)[0]
            ident, gyaml, dyn, pos = None, "", None, ()
            for k, t, v, where in entries(d, actor, keys):
                if k == "Hash" and t == 0xD5:
                    ident = struct.unpack_from("<Q", d, v)[0]
                elif k == "Hash" and t == 0xD3:
                    ident = v
                elif k == "Gyaml" and t == 0xA0:
                    gyaml = strings[v]
                elif k == "Translate" and t == 0xC0 and int.from_bytes(d[v + 1:v + 4], "little") == 3:
                    pos = tuple(round(x, 1) for x in struct.unpack_from("<3f", d, v + 8))
                elif k == "Dynamic" and t == 0xC1:
                    dyn = (where, v)
            if not dyn:
                continue
            item, event, params = None, "", []
            for dk, dt, dv, _ in entries(d, dyn[1], keys):
                params.append(dk)
                if dk == "Drop__DropActor" and dt == 0xA0:
                    item = strings[dv] if dv < len(strings) else "<%d>" % dv
                elif dk == "GetEventName" and dt == 0xA0:
                    event = strings[dv] if dv < len(strings) else ""
            if item is not None:
                found.append(Chest(ident, gyaml, dyn[0], dyn[1], item, tuple(params), pos, event))
    return found, keys, strings


def string_table(strings):
    """a BYML string table: 0xC2, the count, an offset for each string and one for the end, the strings"""
    head = 4 + 4 * (len(strings) + 1)
    offsets, at, blob = [], head, bytearray()
    for s in strings:
        offsets.append(at)
        raw = s.encode("utf-8") + b"\0"
        blob += raw
        at += len(raw)
    offsets.append(at)
    out = bytes([0xC2]) + len(strings).to_bytes(3, "little") + b"".join(struct.pack("<I", o) for o in offsets) + bytes(blob)
    return out + b"\0" * (-len(out) % 4)


def rewrite(data, gives):
    """data (a BYML map file) with each chest of `gives` ({hash: item}) holding its item: the new bytes, or None when
    nothing in it changes. Read back before it is returned: those chests hold their items, every other actor what it held."""
    found, keys, strings = chests(data)
    todo = [c for c in found if c.hash is not None and gives.get(c.hash, c.item) != c.item]
    if not todo:
        return None
    out = bytearray(data)
    out += b"\0" * (-len(out) % 4)
    names = list(strings)
    for c in todo:
        if gives[c.hash] not in names:
            names.append(gives[c.hash])
    if len(names) > len(strings):   # (after the names it has: every index the file uses stays right)
        at = len(out)
        out += string_table(names)
        struct.pack_into("<I", out, 8, at)
    for c in todo:
        n = int.from_bytes(data[c.dyn_at + 1:c.dyn_at + 4], "little")
        block = bytearray(data[c.dyn_at:c.dyn_at + 4 + 8 * n])
        for k, (dk, dt, dv, _) in enumerate(entries(data, c.dyn_at, keys)):
            if dk in ("Drop__DropActor", "Drop__DropActor_Substitute"):   # (SUBSTITUTE_CHESTS: the same item either way)
                struct.pack_into("<I", block, 4 + 8 * k + 4, names.index(gives[c.hash]))
        at = len(out)
        out += block
        struct.pack_into("<I", out, c.dyn_where, at)
    again, _, _ = chests(bytes(out))
    if len(again) != len(found):
        raise ValueError("did not read back with the same actors")
    for was, now in zip(found, again):
        expect = gives.get(was.hash, was.item) if was.hash is not None else was.item
        if now.item != expect or now.hash != was.hash or now.params != was.params or now.event != was.event:
            raise ValueError("did not read back as written (%r: %s, expected %s)" % (now.hash, now.item, expect))
    return bytes(out)


# ---- Chest size matches contents (rando_chest_size, asked 2026-11-18) ----
# A chest of the shuffle holding a major item is made a big chest, any other a small one: the map actor's Gyaml swapped
# between these pairs (the NoBake twins kept NoBake). Its hash, Dynamic (the item, its flags), place and links stay, and
# the logic files' names follow: a logic module names a chest (Obj_TBox_A_01_435b) only as a label, and the map's
# AiGroups tie each name to the chest by its hash (References: Id, Path, Reference = the actor's Hash; found 2026-11-20 in
# FireTemple_Static, AiGroups[119]). Moves no item. Not swapped: the special kinds (A_03, A_04, A_06, the Lens's, the
# pedestals, memo11), which are their own puzzles.
CHEST_SIZES = {"Obj_TBox_A_01": "Obj_TBox_A_02", "Obj_TBox_A_01_NoBake": "Obj_TBox_A_02_NoBake"}
CHEST_SMALL = {big: small for small, big in CHEST_SIZES.items()}


def chest_major(item):
    """whether a chest holding `item` is made big: a gating item of the seed's rules (PROGRESSION, with what main adds),
    a song, or magic"""
    return item in PROGRESSION or item.startswith("Item_Melody_") or item in ("Item_MagicMeter", "Item_FairyBless_MPDouble")


def chest_kinds(data, gives):
    """data (a BYML map file) with each chest of `gives` ({hash: item}) of a kind of CHEST_SIZES made big for a major item
    and small for any other: the new bytes, or None when none changes. Read back before it is returned."""
    found, keys, strings = chests(data)
    want = {}
    for c in found:
        if c.hash is None or c.hash not in gives:
            continue
        big = chest_major(gives[c.hash])
        kind = CHEST_SIZES.get(c.gyaml, c.gyaml) if big else CHEST_SMALL.get(c.gyaml, c.gyaml)
        if kind != c.gyaml:
            want[c.hash] = kind
    if not want:
        return None
    out = bytearray(data)
    out += b"\0" * (-len(out) % 4)
    names = list(strings)
    for kind in want.values():
        if kind not in names:
            names.append(kind)
    if len(names) > len(strings):
        at = len(out)
        out += string_table(names)
        struct.pack_into("<I", out, 8, at)
    _, _, root = struct.unpack_from("<III", data, 4)
    done = 0
    for name, kind, value, _ in entries(data, root, keys):
        if name != "Actors" or kind != 0xC0:
            continue
        n = int.from_bytes(data[value + 1:value + 4], "little")
        vals = value + 4 + (n + 3 & ~3)
        for i in range(n):
            if data[value + 4 + i] != 0xC1:
                continue
            actor = struct.unpack_from("<I", data, vals + 4 * i)[0]
            ident, gyaml_at = None, None
            for k, ty, v, where in entries(data, actor, keys):
                if k == "Hash" and ty == 0xD5:
                    ident = struct.unpack_from("<Q", data, v)[0]
                elif k == "Hash" and ty == 0xD3:
                    ident = v
                elif k == "Gyaml" and ty == 0xA0:
                    gyaml_at = where
            if ident in want and gyaml_at is not None:
                struct.pack_into("<I", out, gyaml_at, names.index(want[ident]))
                done += 1
    if done != len(want):
        raise ValueError("chest sizes: %d of %d chests found to change" % (done, len(want)))
    again, _, _ = chests(bytes(out))
    if len(again) != len(found):
        raise ValueError("chest sizes: did not read back with the same actors")
    for was, now in zip(found, again):
        if now.item != was.item or now.hash != was.hash or now.params != was.params or now.gyaml != want.get(was.hash, was.gyaml):
            raise ValueError("chest sizes: did not read back as written (%r)" % (now.hash,))
    return bytes(out)


def fix(data, fixes=None):
    """data (a BYML map file) with the truth values of `fixes` ({hash: {Dynamic key: value}}) set: the new bytes, or
    None when the file has none of those actors or they already say so. Each actor gets a Dynamic block of its own
    (an equal block is stored once for several actors). Read back before it is returned."""
    fixes = FIXES if fixes is None else fixes
    if data[:2] != b"YB":
        raise ValueError("not a little-endian BYML")
    key_at, _, root = struct.unpack_from("<III", data, 4)
    keys = table(data, key_at)

    def actors(d):
        """(hash, where the Dynamic block's offset is, the block) of the actors of `fixes`"""
        for name, kind, value, _ in entries(d, root, keys):
            if name != "Actors" or kind != 0xC0:
                continue
            n = int.from_bytes(d[value + 1:value + 4], "little")
            vals = value + 4 + (n + 3 & ~3)
            for i in range(n):
                if d[value + 4 + i] != 0xC1:
                    continue
                ident, dyn = None, None
                for k, t, v, where in entries(d, struct.unpack_from("<I", d, vals + 4 * i)[0], keys):
                    if k == "Hash" and t == 0xD5:
                        ident = struct.unpack_from("<Q", d, v)[0]
                    elif k == "Dynamic" and t == 0xC1:
                        dyn = (where, v)
                if ident in fixes and dyn:
                    yield ident, dyn[0], dyn[1]

    def values(d, block):
        return {k: v != 0 for k, t, v, _ in entries(d, block, keys) if t == 0xD0}

    todo = [(h, where, block) for h, where, block in actors(data)
            if any(values(data, block).get(k) != v for k, v in fixes[h].items())]
    if not todo:
        return None
    before, _, _ = chests(data)
    out = bytearray(data)
    out += b"\0" * (-len(out) % 4)
    for h, where, block in todo:
        n = int.from_bytes(data[block + 1:block + 4], "little")
        new = bytearray(data[block:block + 4 + 8 * n])
        for k, (dk, dt, _, _) in enumerate(entries(data, block, keys)):
            if dk in fixes[h]:
                if dt != 0xD0:
                    raise ValueError("%s of %#x is not a truth value" % (dk, h))
                struct.pack_into("<I", new, 4 + 8 * k + 4, int(fixes[h][dk]))
        at = len(out)
        out += new
        struct.pack_into("<I", out, where, at)
    out = bytes(out)
    for h, _, block in actors(out):
        if any(values(out, block).get(k) != v for k, v in fixes[h].items()):
            raise ValueError("the fix of %#x did not read back as written (has it that key?)" % h)
    after, _, _ = chests(out)
    if [(c.hash, c.item, c.params, c.event) for c in after] != [(c.hash, c.item, c.params, c.event) for c in before]:
        raise ValueError("a fix changed a chest")
    return out


class NotInPlace(ValueError):
    """a drop that add_drop_in_place does not write: the file is written anew for it (add_drop_anew)"""


def add_drop(data, drops, anew=False):
    """data (a BYML map file) with each actor of `drops` ({hash: item}) given that item as what it drops: its Dynamic
    block gets a Drop__DropActor (the key a chest names its item by; an enemy has the same one), or has the one it had
    changed. The new bytes, or None when the file has none of those actors. Written into the file as it is where
    that can be done (add_drop_in_place), and the whole file anew where an actor has no Dynamic block or the file no
    such key (add_drop_anew; anew: that way whatever the file has, for a test)."""
    if not drops or not any(struct.pack("<Q", h) in data for h in drops):
        return None
    if not anew:
        try:
            return add_drop_in_place(data, drops)
        except NotInPlace:
            pass
    return add_drop_anew(data, drops)


def add_drop_anew(data, drops):
    """add_drop by reading the whole file and writing it again (byml_parse, byml_build): an actor without a Dynamic
    block gets one, and the key table gets Drop__DropActor in its place. The file grows: the game's stores equal
    dictionaries once, and this does not. Everything else reads back as it was, or it is an error."""
    tree, version = byml_parse(data)
    actors = tree[1].get("Actors") if tree and tree[0] == "dict" else None
    done = set()
    for actor in actors[1] if actors and actors[0] == "array" else []:
        ident = actor[1].get("Hash") if actor[0] == "dict" else None
        if not ident or ident[0] not in (0xD3, 0xD5):
            continue
        h = int.from_bytes(ident[1], "little")
        if h in drops:
            dyn = actor[1].get("Dynamic")
            if dyn is None or dyn[0] != "dict":
                dyn = actor[1]["Dynamic"] = ("dict", collections.OrderedDict())
            dyn[1]["Drop__DropActor"] = ("string", drops[h])
            done.add(h)
    if not done:
        return None
    out = byml_build(tree, version)

    def plain(node):   # (a dictionary's keys in any order: the file has them in its key table's)
        if node[0] == "dict":
            return {k: plain(v) for k, v in node[1].items()}
        return [plain(v) for v in node[1]] if node[0] == "array" else node
    if plain(byml_parse(out)[0]) != plain(tree):
        raise ValueError("the file written anew does not read back as it was made")
    before, _, _ = chests(data)
    after, _, _ = chests(out)
    got = {c.hash: c.item for c in after}
    if any(got.get(h) != drops[h] for h in done):
        raise ValueError("a drop did not read back as written")
    was = {c.hash: (c.item, c.event, c.gyaml, c.params, c.pos) for c in before}
    now = {c.hash: (c.item, c.event, c.gyaml, c.params, c.pos) for c in after}
    if any(now.get(h) != v for h, v in was.items() if h not in done) or set(now) - set(was) - done:
        raise ValueError("giving a drop changed another actor's")
    return out


def add_drop_in_place(data, drops):
    """add_drop without writing the file anew: the actor gets a Dynamic block of its own at the end of the file, and
    an item name the file does not have goes into a copy of its string table there. An actor without a Dynamic
    block, or a file that has no Drop__DropActor key, is NotInPlace."""
    if not drops:
        return None
    found, keys, strings = chests(data)
    key_at, _, root = struct.unpack_from("<III", data, 4)
    todo = []
    for name, kind, value, _ in entries(data, root, keys):
        if name != "Actors" or kind != 0xC0:
            continue
        n = int.from_bytes(data[value + 1:value + 4], "little")
        vals = value + 4 + (n + 3 & ~3)
        for i in range(n):
            if data[value + 4 + i] != 0xC1:
                continue
            ident, dyn = None, None
            for k, t, v, where in entries(data, struct.unpack_from("<I", data, vals + 4 * i)[0], keys):
                if k == "Hash" and t == 0xD5:
                    ident = struct.unpack_from("<Q", data, v)[0]
                elif k == "Dynamic" and t == 0xC1:
                    dyn = (where, v)
            if ident in drops:
                if not dyn:
                    raise NotInPlace("%#x has no Dynamic block to put a drop in" % ident)
                todo.append((ident, dyn[0], dyn[1]))
    if not todo:
        return None
    if "Drop__DropActor" not in keys:
        raise NotInPlace("the file has no Drop__DropActor key")
    drop_key = keys.index("Drop__DropActor")
    out = bytearray(data)
    out += b"\0" * (-len(out) % 4)
    names = list(strings)
    for h, _, _ in todo:
        if drops[h] not in names:
            names.append(drops[h])
    if len(names) > len(strings):
        at = len(out)
        out += string_table(names)
        struct.pack_into("<I", out, 8, at)
    for h, where, node in todo:
        n = int.from_bytes(data[node + 1:node + 4], "little")
        rows = [bytes(data[node + 4 + 8 * k:node + 12 + 8 * k]) for k in range(n)]
        rows = [r for r in rows if int.from_bytes(r[:3], "little") != drop_key]
        rows.append(drop_key.to_bytes(3, "little") + bytes([0xA0]) + struct.pack("<I", names.index(drops[h])))
        rows.sort(key=lambda r: int.from_bytes(r[:3], "little"))   # (a dictionary's keys are in the key table's order)
        at = len(out)
        out += bytes([0xC1]) + len(rows).to_bytes(3, "little") + b"".join(rows)
        struct.pack_into("<I", out, where, at)
    out = bytes(out)
    again, _, _ = chests(out)
    got = {c.hash: c.item for c in again}
    if any(got.get(h) != drops[h] for h, _, _ in todo):
        raise ValueError("a drop did not read back as written")
    before = {c.hash: (c.item, c.event) for c in found}
    if any(before[c.hash] != (c.item, c.event) for c in again if c.hash in before and c.hash not in drops):
        raise ValueError("giving a drop changed another actor's")
    return out


# ---- an actor's pack (Pack/Actor/<name>.pack.zs): a SARC archive of its parameter files ----
# The Gold Skulltulas setting. A Gold Skulltula drops what its map file names (Drop__DropActor, the key a chest names
# its item by; without one, its token), so its token and a chest's item can change places: the chest gives the token
# as an item (TOKEN), the Skulltula drops the chest's, made a pick-up (pickup_pack).
SKULLTULA = "Enemy_Skulltula_Gold"
TOKEN = "Item_Token_Gold"
# What a Skulltula may be given: what the game can be finished without, and is no loss where a Skulltula cannot be
# reached yet. No gating item and no dungeon's key (the rules know no Skulltula's place: many ask for the Boomerang,
# the Hookshot or the night), and no Heart Piece (it hangs where it is put and is taken with A from beside it: one
# dropped on a wall could not be reached, seen in play).
# A Skulltula is done with when its drop is got as a token is: the drop's get event runs, and the drop is gone. The
# game runs an item's get event the first time it is got and not again, so the second seed of a game was put in the
# pouch and stayed where it was, and its Skulltula was back when the room was entered again, for another seed. With
# the event each time (pickup_pack's each_time) four seeds in a row were each got with their text and their
# Skulltulas stayed dead; so were Deku Nut bundles (seen in play).
# A bundle Link has nothing to carry in is not got at all: a bomb bundle without a Bomb Bag, and a Deku Nut bundle in
# a game that had had no nuts yet, stayed where they were with nothing given, and their Skulltulas were back when
# the room was entered again (seen in play; the nuts were got once some had been bought). It is there for later, as
# a token out of reach is. The stick and Bombchu bundles are given on the strength of the nuts: not seen yet.
# A chest's arrows and magic jar have the pouch file of the world's own (a world arrow bundle's, a jar's), so each is
# given one of its own (PICKUP_OWN_POUCH) with the event each time: two arrow bundles in a line, and two jars, were
# each got with their text (without a window, on a save that had had both before). The large arrow bundle is given on
# the strength of the medium one.
SKULLTULA_ITEMS = ("Item_ScrubBusinessSeed", "Item_BombBundle_Small", "Item_BombchuBundle_Small", "TBox_DekuNutBundle",
                   "Item_DekuStickBundle_Small", "TBox_ArrowBundle_Medium", "TBox_ArrowBundle_Large", "Tbox_MagicJar_Large")
# Kept from the Skulltulas: the rupees. A chest's green rupee made a pick-up was walked through and stayed, with the
# game's own pouch file, with one of its own, and with one of its own that asks for its get event each time (without
# a window, on a save that had picked up rupees before): a rupee's get event is not run a second time whatever its
# pouch file says, and a pick-up made from the token waits for it. What else was tried with them on the way: what a
# world rupee thinks with (AIInfoRef DropItem: it fell); a world rupee (Obj_Rupee_*) dropped in a chest rupee's place
# (it fell into water, and its Skulltula was back each time).
SKULLTULA_ITEMS_NOT_YET = ("TBox_Rupee_Green", "TBox_Rupee_Blue", "TBox_Rupee_Red", "TBox_Rupee_Purple", "TBox_Rupee_Gold")
# Placement 12 (bug 67, the owner's word, 2026-11-17): the Gold Skulltulas and the Pieces of Heart lying in the world
# take part as chests do, in the main placement (place), their token and their piece going into the pool; each holds
# what it can hold of the pool (place's `holds`), and the rest goes to the other places. What a Skulltula may drop
# (skulltula_holds): its token; the supplies above; a gating item as gate_skulltulas let one before (the Boomerang,
# the Megaton Hammer and the small Bomb Bag were seen dropped and got), but not those it never tried (SKULLTULA_NEVER:
# the Silver Scale, the wallets, the songs), nor the tunics (not a chest's item: pickup_pack cannot make one a pick-up,
# found making a seed of 12, "Obj_Armor_Goron is not made from Item_EventObject_Base"); and the one-of-a-kind items of
# the same make as those gating items (SKULLTULA_MORE: the Stone of Agony, the magic arrows and spells, the bigger
# bags, quivers and bullet bags, the shields), which no Skulltula has dropped yet: to be seen in play.
# Not a Skulltula's: the Pieces of Heart and the rupees (above: seen not to work), a dungeon's keys, map and compass
# (counted for the dungeon they are got in, and the rules know no Skulltula's place in a dungeon well enough), the
# songs (none got from a pick-up yet), the bottles, the scales and the wallets (never tried on one), the Heart
# Containers, the dungeons' stones and medallions, and anything else not named: they go to chests, gifts, shelves and
# the pieces.
SHUFFLED_FROM = 12   # (the placement from which they take part so; before, gate_skulltulas and mix_skulltulas)
SKULLTULA_MORE = frozenset(("Item_AgonyStone", "Item_Arrow_Fire", "Item_Arrow_Ice", "Item_Arrow_Light", "Item_DinFire", "Item_FaroreWind",
                            "Item_NayruLove", "Item_BombBag_Medium", "Item_BombBag_Large", "Item_BulletBag_Medium", "Item_BulletBag_Large",
                            "Item_Quiver_Medium", "Item_Quiver_Large", "Item_StickBag_Medium", "Item_StickBag_Large", "Item_NutBag_Medium",
                            "Item_NutBag_Large", "TBox_Shield_Deku", "TBox_Shield_Hylian", "Item_BombchuBundle_Large"))
SKULLTULA_NEVER = frozenset(("Item_Ocarina_Time", "Item_Ocarina_Fairy", "Item_ZeldaLetter", "Item_Scale_Silver", "Item_Scale_Gold", "Item_Wallet_Medium", "Item_Wallet_Large", "Item_Bottle",
                             "Obj_Armor_Goron", "Obj_Armor_Zora", "Obj_Heart_Piece", "Obj_Heart_Container") + SKULLTULA_ITEMS_NOT_YET)


# Gold Skulltulas by day (rando_skulltulas_day, asked for 2026-11-17): 30 of the game's Gold Skulltulas come out only
# at night, by their actor's Dynamic Enemy_Skulltula_Gold_Nocturnal (true in each of theirs, absent in the others').
# With the setting on it is made false in the seed's copies of their map files, in place (a true/false is a whole
# word of its entry: the file keeps its size). The rules never asked for the night (it comes by waiting, or the Sun's
# Song), so no rule changes. NOT SEEN YET: whether the flag alone is what keeps them to the night.
NOCTURNAL = "Enemy_Skulltula_Gold_Nocturnal"


def skulltulas_by_day(data):
    """a map file with its night-only Gold Skulltulas out by day too (NOCTURNAL made false): (the new bytes or None
    when it has none, how many)"""
    if data[:2] != b"YB" or NOCTURNAL.encode() not in data:
        return None, 0
    key_at, _, root = struct.unpack_from("<III", data, 4)
    keys = table(data, key_at)
    out, count, seen = bytearray(data), 0, set()
    for name, kind, value, _ in entries(data, root, keys):
        if name != "Actors" or kind != 0xC0:
            continue
        n = int.from_bytes(data[value + 1:value + 4], "little")
        vals = value + 4 + (n + 3 & ~3)
        for i in range(n):
            if data[value + 4 + i] != 0xC1:
                continue
            fields = {k: (t, v) for k, t, v, _ in entries(data, struct.unpack_from("<I", data, vals + 4 * i)[0], keys)}
            if fields.get("Gyaml", (0, -1))[0] != 0xA0 or fields.get("Dynamic", (0,))[0] != 0xC1:
                continue
            for k, t, v, where in entries(data, fields["Dynamic"][1], keys):
                if k == NOCTURNAL and t == 0xD0 and v and where not in seen:
                    struct.pack_into("<I", out, where, 0)
                    seen.add(where)
                    count += 1
    return (bytes(out), count) if count else (None, 0)


# (bug 82, the owner's run 2026-11-18: with NOCTURNAL false in the maps they still kept to the night: by day only their
#  web showed. Their own utility AI (SKULLTULA_AI in SKULLTULA_PACK) asks QueryTimeDivision and a bool selector takes its
#  IsDayTime output: by day it keeps them hidden. With the setting on, that selector's input is unlinked and false: the
#  AI is never told it is day. Seen without a window on the owner's save by the Bottom of the Well exit: at noon the web
#  alone before, the Skulltula after. Every Gold Skulltula takes the same AI; the day ones are out day and night anyway)
SKULLTULA_PACK = "Pack/Actor/Enemy_Skulltula_Gold.pack.zs"
SKULLTULA_AI = "AI/Enemy_Skulltula_Gold.utility.root.ainb"
# (what in fact keeps them to the night, found the same day: each night Skulltula and its web are an AI group of their
#  map (AiGroups) with one shared logic, NIGHT_SKULLTULA_LOGIC: HoldWmGetTimeDiv's Day output, through an OR, deletes
#  the Skulltula. With the setting on, the input that takes Day is unlinked and false: never deleted by day)
NIGHT_SKULLTULA_LOGIC = "Logic/Gimmick_Nighttime_Skulltula_Gold_Appear_05a9.logic.module.ainb"


def night_skulltula_logic_day(data):
    """The night Skulltulas' logic (NIGHT_SKULLTULA_LOGIC) never told it is day: the bool input that takes
    HoldWmGetTimeDiv's Day output (its output 0) unlinked and false. The new bytes, of the same size. ValueError: not the
    file, or not one such input. (The layout as skulltula_ai_day's; an unlinked bool input's flags 0x01800000)"""
    u32 = lambda at: struct.unpack_from("<I", data, at)[0]
    if data[:4] != b"AIB " or u32(4) != 0x408:
        raise ValueError("not the logic file this was written for")
    pool = u32(0x24)
    name = lambda off: data[pool + (off & 0x3FFFFFFF):].split(bytes(1))[0].decode("utf-8", "replace")
    nodes = 0x74 + 0x18 * u32(0x0C)
    time = [i for i in range(u32(0x10)) if name(u32(nodes + 0x3C * i + 8)) == "HoldWmGetTimeDiv"]
    if len(time) != 1:
        raise ValueError("%d HoldWmGetTimeDiv nodes where one was expected" % len(time))
    io = u32(0x34)
    bool_in, bool_out, bool_out_end = u32(io + 8), u32(io + 12), u32(io + 16)
    outs = [name(u32(at)) for at in range(bool_out, bool_out_end, 4)]
    if "Day" not in outs or outs.index("Night") != outs.index("Day") + 1:
        raise ValueError("no Day and Night outputs")
    hits = [at for at in range(bool_in, bool_out, 16) if u32(at + 4) == time[0]]   # (output 0 of the node: Day)
    if len(hits) != 1:
        raise ValueError("%d inputs take the time's Day where one was expected" % len(hits))
    out = bytearray(data)
    struct.pack_into("<IIII", out, hits[0], u32(hits[0]), 0xFFFF, 0x01800000, 0)
    return bytes(out)


def skulltula_ai_day(data):
    """The Gold Skulltula's utility AI (SKULLTULA_AI) never told it is day: the bool input that takes QueryTimeDivision's
    IsDayTime output unlinked (no node, its own value false). The new bytes, of the same size. An AIB file of version
    0x408: commands of 0x18 bytes at 0x74, then the nodes, 0x3C bytes each (name at +8); its parameters' section (header
    +0x34) begins with twelve offsets, the bool inputs' at +8, of 16 bytes each (name, node | output index << 16, flags,
    value), the bool outputs' at +12, of 4 bytes each. ValueError: not the file, or not one such input."""
    u32 = lambda at: struct.unpack_from("<I", data, at)[0]
    if data[:4] != b"AIB " or u32(4) != 0x408:
        raise ValueError("not the AI file this was written for")
    pool = u32(0x24)
    name = lambda off: data[pool + (off & 0x3FFFFFFF):].split(bytes(1))[0].decode("utf-8", "replace")
    nodes = 0x74 + 0x18 * u32(0x0C)
    query = [i for i in range(u32(0x10)) if name(u32(nodes + 0x3C * i + 8)) == "QueryTimeDivision"]
    if len(query) != 1:
        raise ValueError("%d QueryTimeDivision nodes where one was expected" % len(query))
    io = u32(0x34)
    bool_in, bool_out, bool_out_end = u32(io + 8), u32(io + 12), u32(io + 16)
    outs = [name(u32(at)) for at in range(bool_out, bool_out_end, 4)]
    if "IsDayTime" not in outs:
        raise ValueError("no IsDayTime output")
    hits = [at for at in range(bool_in, bool_out, 16) if u32(at + 4) == query[0]]   # (output 0 of the node: IsDayTime)
    if len(hits) != 1:
        raise ValueError("%d inputs take the time's IsDayTime where one was expected" % len(hits))
    out = bytearray(data)
    struct.pack_into("<IIII", out, hits[0], u32(hits[0]), 0xFFFF, 0x80000000, 0)
    return bytes(out)


def skulltula_holds(item, gating):
    """whether a Gold Skulltula may drop this item (placement 12, see above); gating: the seed's gating items"""
    if item in SKULLTULA_NEVER or item.startswith("Item_Melody_") or item in DUNGEON_ITEMS:
        return False
    return item == TOKEN or item in SKULLTULA_ITEMS or item in SKULLTULA_MORE or item in gating


# What a Piece of Heart lying in the world may give (placement 12): the piece stays in the map and the game's side
# renames the pouch's add of the piece to the item (host/hos_main.c oot_piece_gives), the way the game itself gives
# any item (a gold rupee's add is 200 rupees, the game's side's own fill). Seen in play: the Megaton Hammer of Zora's
# River. Not a piece's (PIECE_NEVER): a dungeon's keys, map and compass (a piece lies in the overworld, and a key is
# counted for the dungeon it is got in), the songs (none given by an add's name yet: a song's scene and flags are the
# lesson's), the tunics (gifts' items whose pouch names are not theirs, Armor_Adult_*), the dungeons' stones and
# medallions and the Heart Containers. A bundle Link has nothing to carry in is given as nothing, the piece taken: a
# supply lost, not a check left (to be seen in play).
PIECE_NEVER = frozenset(("Item_Ocarina_Time", "Item_Ocarina_Fairy", "Item_ZeldaLetter", "Obj_Armor_Goron", "Obj_Armor_Zora", "Obj_Heart_Container"))


def piece_holds(item):
    """whether a Piece of Heart lying in the world may give this item (placement 12, see above)"""
    return not (item in PIECE_NEVER or item.startswith("Item_Melody_") or item in DUNGEON_ITEMS or item in REWARD_ITEMS)


def skulltulas(data):
    """A map file's Gold Skulltulas: [(hash, position, can be given a drop in place, is a dungeon's)]. In place: it has
    a Dynamic block and the file has the Drop__DropActor key (add_drop_in_place; the file is written anew for the
    others). A dungeon's has its room's number there, as a dungeon's chest has."""
    if data[:2] != b"YB":
        raise ValueError("not a little-endian BYML")
    key_at, str_at, root = struct.unpack_from("<III", data, 4)
    keys, strings = table(data, key_at), table(data, str_at)
    out = []
    for name, kind, value, _ in entries(data, root, keys):
        if name != "Actors" or kind != 0xC0:
            continue
        n = int.from_bytes(data[value + 1:value + 4], "little")
        vals = value + 4 + (n + 3 & ~3)
        for i in range(n):
            if data[value + 4 + i] != 0xC1:
                continue
            ident, gyaml, dyn, pos, dungeon = None, "", False, (), False
            for k, t, v, _ in entries(data, struct.unpack_from("<I", data, vals + 4 * i)[0], keys):
                if k == "Hash" and t == 0xD5:
                    ident = struct.unpack_from("<Q", data, v)[0]
                elif k == "Gyaml" and t == 0xA0:
                    gyaml = strings[v] if v < len(strings) else ""
                elif k == "Translate" and t == 0xC0 and int.from_bytes(data[v + 1:v + 4], "little") == 3:
                    pos = tuple(round(x, 1) for x in struct.unpack_from("<3f", data, v + 8))
                elif k == "Dynamic" and t == 0xC1:
                    dyn = True
                    dungeon = any(dk == "DefaultDungeonRoomIndex" for dk, _, _, _ in entries(data, v, keys))
            if gyaml == SKULLTULA and ident is not None:
                out.append((ident, pos, dyn and "Drop__DropActor" in keys, dungeon))
    return out


# ---- the logic for a Gold Skulltula: what Link needs before its drop can be got ----
# Not known Skulltula by Skulltula yet, so each asks for too much: what its area's chests can ask for (RULES), and
# what a Skulltula's place can ask for anywhere: the three stones, the Longshot (the Hookshot's reach and more) and
# the Megaton Hammer. A Skulltula known better than that is in SKULLTULA_RULES, by its hash: what it asks for in
# place of all that. A drop is brought in by the Boomerang and by the Hookshot (both seen in play), so a gating item
# goes to the child's Skulltulas and the adult's alike.
SKULLTULA_ASKS = ADULT | {LONG, HAM}
# (bug 84, the owner's run 2026-11-19: the Tracker had a bean-soil Skulltula in logic with no bottle) A Gold Skulltula in
# bean soil (its map's Enemy_Skulltula_Gold_IsMagicBeanSoil) comes out only for bugs let out of a bottle. The rules counted
# the bugs as free (CHILD: "child, bugs"), from when the bottles stayed where the game has them; with Quest rewards the
# bottles are gifts of the shuffle (the cucco lady's, the Potion Shop keeper's) and none was asked for: a seed could put
# an item it needs on such a Skulltula with every bottle behind it. From placement BOTTLE_FROM, where a bottle is shuffled,
# the bottle is a gating item and such a Skulltula asks for one. (Ruto's Letter, not shuffled, holds bugs only once
# given to King Zora: not counted, the rules meant to ask for too much.) A seed made before keeps its placement.
BOTTLE = "Item_Bottle"
BOTTLE_FROM = 13


# (asked 2026-11-24) The owner: the soil Skulltulas without fetching bugs each time, when Link has a bottle. Each stands in
# its area's child map only while Gimmick_MagicBeanSoil_<area> is set (its Presence), which the bugs let out on the soil set.
# From fixes 89 each of the ten waits for IsGet.Item_Bottle instead (set once Link has had a bottle): it is there whenever a
# bottle was got, no bugs. The rules ask for what they asked before (a bottle, soil_need), so no placement changes. A Quality
# of life setting from 2026-11-24 (the owner): Soil Skulltulas without bugs, rando_soil_bottle, off by default.
SOIL_FILES = tuple("Banc/%s/%s_Child_Static.bcett.byml.zs" % (a, a) for a in (
    "DeathMountainCrater", "DeathMountainTrail", "DesertColossus", "GerudoValley", "Graveyard", "HyruleField", "KokiriForest",
    "LostWood", "ZoraRiver"))
SOIL_PREFIX, SOIL_BOTTLE, SOIL_COUNT = "Gimmick_MagicBeanSoil_", "IsGet." + BOTTLE, 10


def soil_by_bottle(data):
    """A child map file with its bean-soil Gold Skulltulas (Enemy_Skulltula_Gold_IsMagicBeanSoil) there for a bottle got
    (SOIL_BOTTLE) in place of the soil's bugs (a Presence of SOIL_PREFIX): (the file written anew, how many changed)."""
    tree, version = byml_parse(data)
    actors = tree[1].get("Actors")
    if not actors or actors[0] != "array":
        raise ValueError("the map file has no actors")
    n = 0
    for a in actors[1]:
        d = a[1]
        if d.get("Gyaml", ("", ""))[1] != "Enemy_Skulltula_Gold" or d.get("Presence", ("", {}))[0] != "dict":
            continue
        dyn = d.get("Dynamic", ("", {}))[1] if d.get("Dynamic", ("", {}))[0] == "dict" else {}
        soil = dyn.get("Enemy_Skulltula_Gold_IsMagicBeanSoil")
        flag = d["Presence"][1].get("FlagName", ("", ""))
        if soil and soil[1] not in (False, 0, bytes(4)) and str(flag[1]).startswith(SOIL_PREFIX):
            d["Presence"][1]["FlagName"] = ("string", SOIL_BOTTLE)
            n += 1
    return byml_build(tree, version), n


def soil_need(need, soil, bottles):
    """a Skulltula's rule with a bottle asked for where it is in bean soil and the bottles are gating items (each way)"""
    return each(lambda way: way | {BOTTLE}, need) if soil and bottles else need
# (where a child goes: the overworld's maps say it in their name, <area>_Child_..., and a dungeon has one map for both)
SKULLTULA_CHILD_DUNGEONS = ("InsideTheDekuTree", "DodongoCavern", "InsideJabuJabuBelly", "BottomOfTheWell")
# Written from the original game's randomizer logic (track-oot.net's, without tricks), each matched to the map's
# Skulltula by its area, who can get it, night and soft soil, and where two were alike by height or room; the
# remake's new places from the player (<game folder>/rando/skulltulas_to_check.txt has every line and how sure
# it is). In the rules' own words: CHILD is out of the forest (night, a bottle of bugs, a Deku Stick), ADULT is the
# three stones done (the Hookshot, the songs an adult learns). Where the original gives a choice (the Boomerang or
# the Hookshot) the child's is asked for; where two could not be told apart both ask for the most either does.
SKULLTULA_RULES = {
    # Bottom of the Well
    0x6789388e9fb9c92c: ADULT | {LENS},        # boomerang, lens, adult first (Song of Storms)
    0xa8d6182a5c956e16: ADULT | {LENS},        # boomerang, lens, adult first (Song of Storms)
    0x35fb354fac262d36: ADULT | {LENS},        # boomerang, lens, adult first (Song of Storms)
    # DeathMountainCrater
    0xfcd7f04dcf755e8e: CHILD | {BB},          # child, sword, slingshot, bombs (to get up the mountain)
    0x58c75badf059ca54: ADULT | {HAM},         # child, bugs, and adult first with the hammer (the child gets here by B
    # DeathMountainTrail
    0xf5359b24fc86ac22: ADULT | {HAM},         # adult, hammer, night
    0x0b8e43abfa0b5f86: ADULT | {HAM},         # adult, hammer, night
    0x04e03ac27985e328: CHILD | {BB},          # bombs (or the hammer)
    0xf1d32c06612da232: CHILD | {BB},          # child, bugs, bombs
    # DesertColossus
    0xd0f7e5ffa76ba288: DESERT,                # adult, hookshot, night; all it takes to cross the desert (probably)
    0x9ae3d0ac392e6cda: DESERT,                # adult, hookshot or longshot, night; all it takes to cross the desert (probably)
    0x0341f2c03598c861: DESERT,                # child, bugs; adult first with all it takes to cross the desert (the ch
    # Dodongo's Cavern
    0xbdfe13c37f356829: CHILD | {BB},          # bombs (or the hammer) (probably)
    0x758ce7b4868447fb: CHILD | {BB, BM},      # boomerang or hookshot, bombs (probably)
    0x3f5b150f16d84603: CHILD | {BB},          # bombs (probably)
    0x0d53e429a1ef383d: ADULT | {LONG},        # adult, scarecrow or longshot (probably)
    0x10434342a3917ebd: CHILD | {BB},          # sword or slingshot, bombs (probably)
    # Ganon's Castle (outside)
    0x4e13cc311cd04df4: ADULT,                 # adult
    # GerudoValley
    0xbc85efca2b222cd9: ADULT | {LONG},        # adult, hookshot, night, longshot (to cross the valley)
    0xa017ce09904c2dce: ADULT | {LONG},        # adult, hookshot, night, longshot (to cross the valley)
    0x738f5746cc517702: CHILD,                 # child, bugs
    0xd3d86d3d6988ed8c: CHILD | {BM},          # child, boomerang, night
    # GoronCity
    0xfbbc2d490276c68e: ADULT,                 # adult
    0x07e6e21142cc54db: CHILD | {BB},          # child, bombs
    # Graveyard
    0x032f42f523be6425: CHILD | {BM},          # child, boomerang, night
    0xe91f6be796358ffc: CHILD,                 # child, bugs
    # Haunted Wasteland
    0xceed596f17934971: DESERT,                # hookshot or boomerang; all it takes to cross the desert
    # Hyrule Castle
    0x22c0f7dff5ebb86d: CHILD,                 # child, sword or slingshot
    0x7f28485fa5d3688f: ADULT,                 # boomerang or hookshot, bombs, Song of Storms (adult first) (probably)
    # HyruleField
    0x0af4d6f063d3ae9f: ADULT | {LONG},        # adult, longshot, night
    0x6689bdebc95368eb: ADULT | {IRON},        # adult, iron boots, hookshot
    0x7d8ec14bdd1f6341: ADULT,                 # adult, bombs as a child (the rock over the grotto), sword or slingshot
    0x781e0de8eed42373: CHILD,                 # sword or slingshot
    0xa6a4e87da18fa678: CHILD | {BB, BM},      # boomerang or hookshot, bombs (to open the grotto) (probably)
    0x25e6072d4df023b3: CHILD | {BM},          # boomerang or hookshot, night (probably)
    0x04be4a8ff29f2099: CHILD | {BM},          # child, boomerang, night (probably)
    0x1e38e8d23596eecf: CHILD | {BM},          # child, boomerang, night (probably)
    0xc1858a4fcd84a28e: CHILD | {BM},          # child, boomerang, night
    0x61576befd16c499a: CHILD,                 # child, bugs
    0xdc8113831c56b194: CHILD | {BM},          # child, boomerang, night (probably)
    # IceCavern
    0xcdb49f5d0a67fcf6: ADULT,                 # adult, hookshot or boomerang
    0x63701a2cf70b201c: ADULT,                 # adult, hookshot or boomerang
    0x165fc0bc0aca1f6c: ADULT,                 # adult, hookshot or boomerang
    # Inside Jabu-Jabu's Belly
    0x9c95fd41b89c058a: ADULT,                 # child, boomerang, bombs (to get to Jabu-Jabu)
    0xc03f282ff60942b6: ADULT,                 # child, boomerang, bombs (to get to Jabu-Jabu)
    0x9fc92497f014dbd5: ADULT,                 # child, boomerang, bombs (to get to Jabu-Jabu)
    0xddd260afb6f2989a: ADULT,                 # child, boomerang, bombs (to get to Jabu-Jabu)
    # Inside the Deku Tree
    0xf2e27d6a27026acf: CHILD,                 # slingshot or boomerang
    0xbce05898ce61f1c0: frozenset((S,)),       # sword or slingshot
    0xfad8931a0011e1d4: CHILD,                 # slingshot or boomerang (probably)
    0xdf73f3739cef466b: CHILD,                 # slingshot or boomerang (probably)
    # KakarikoVillage
    0x2df265292516bdf0: ADULT,                 # adult, hookshot, night
    0xa1632e322c612b97: CHILD,                 # child, night
    0x6a8d9b2373d08fcb: CHILD,                 # child, night, sword or slingshot
    0xc3c68d0ac4b85831: CHILD,                 # child, night
    0xd1cef51cf294fb86: CHILD,                 # child, night, slingshot (probably)
    0xd4883a16973b1d06: CHILD,                 # child, night
    # KokiriForest
    0x62c340f0b876c195: ADULT,                 # adult, hookshot, night
    0xecdc46b409ed7d38: CHILD,                 # child, sword or slingshot, night (out of the forest, or the Sun's Song
    0x858f5000ad57b2cc: CHILD,                 # child, bugs, sword or slingshot
    # Lost Woods
    0x3c2b585ac5c0443e: ADULT,                 # adult, night, a bean planted as a child (probably)
    0x8186bcb07d6c2cf9: CHILD,                 # child, bugs
    0xf6fa6ef0ca152948: CHILD,                 # child, bugs
    # Market
    0x7c1a05315f83c34d: CHILD,                 # child
    # SacredForestMeadow
    0xc8db3346f78ea31b: ADULT,                 # adult, hookshot, night
    # ZoraDomain
    0x853b892663c0215d: ADULT,                 # adult, night, hookshot or bow
    # ZoraFountain
    0x845ba51dc18c855e: ADULT | {SG},          # adult, hookshot, night, silver gauntlets, bombs (probably)
    0x63446d12663daa83: ADULT,                 # child, boomerang, night, bombs (to get up the river)
    0xf0dac245e2fc448e: CHILD | {BB},          # child, bombs (to get up the river)
    # ZoraRiver
    0x97824c2ffeaa877c: ADULT,                 # adult, hookshot, night
    0x8325fea55edfbe97: ADULT,                 # adult, hookshot, night
    0xabad0e9f0d471156: CHILD | {BB},          # child, bugs, bombs: past the boulders (seen in play)
    0x78ae4fd90b3cfaaa: CHILD | {BB},          # child, night, sword or slingshot, bombs (past the boulders)
    # The adult's temples. A temple's keys may lie behind anything the temple takes (Dungeon keys: Own dungeon), so each
    # asks for what its temple's chests can (RULES) and no less, but for the Forest Temple's first, by the door; and no
    # more: not the Megaton Hammer or the Longshot of SKULLTULA_ASKS where its temple does not take them.
    # FireTemple
    0xcc175a90e0014905: ADULT | {HAM, BOW},            # adult; hammer, bow
    0x7f498ada1c2e9c7a: ADULT | {HAM, BOW},            # adult; hammer, bow
    0x4d1b7e35ca0c6484: ADULT | {HAM, BOW},            # adult; hammer, bow
    0xb0f77b17cfb37458: ADULT | {HAM, BOW},            # adult; hammer, bow
    0x5e3ae6a7cf3ac292: ADULT | {HAM, BOW},            # adult; hammer, bow
    # ForestTemple
    0x984021bc20419ebe: ADULT | {BOW, LONG},           # adult, longshot; bow (probably)
    0x2aa39f00aaa2d331: ADULT | {BOW},                 # adult, hookshot or boomerang; bow
    0xf46b1710ed0620d1: ADULT | {BOW},                 # adult, hookshot or boomerang; bow (probably)
    0x99ca89963485df11: ADULT,                         # adult, hookshot or bow or bombs
    0x1bf5f0176ef03bda: ADULT | {BOW},                 # adult, hookshot; bow (probably)
    # GerudoFortress
    0x81ed4ed76699e3d8: ADULT | {HOVER, LONG, BOW},    # adult, night; hover boots, longshot, bow (what the fortress 
    0xb4ece769e6f3a206: ADULT | {HOVER, LONG, BOW},    # adult, night; hover boots, longshot, bow (what the fortress 
    # ShadowTemple
    0x8e87908cb035e950: MEDALS3 | {LENS, HOVER},       # adult; lens, hover boots, and the three temples before it
    0xd23a7a2c9eced9ce: MEDALS3 | {LENS, HOVER},       # adult; lens, hover boots, and the three temples before it
    0xd7ffbe169189e50d: MEDALS3 | {LENS, HOVER},       # adult; lens, hover boots, and the three temples before it
    0x7a74bc651f9fe024: MEDALS3 | {LENS, HOVER},       # adult; lens, hover boots, and the three temples before it
    0xeafe60e592e9a3fb: MEDALS3 | {LENS, HOVER},       # adult; lens, hover boots, and the three temples before it
    # SpiritTemple
    0x8c8bb95471d20d02: DESERT | {SG, BOW, MS},        # the desert crossed; silver gauntlets, bow, mirror shield
    0x4696b2730de0516c: DESERT | {SG, BOW, MS},        # the desert crossed; silver gauntlets, bow, mirror shield
    0x9222e742b73d3d2c: DESERT | {SG, BOW, MS},        # the desert crossed; silver gauntlets, bow, mirror shield
    0xb3d9f353599eea53: DESERT | {SG, BOW, MS},        # the desert crossed; silver gauntlets, bow, mirror shield
    0x70b0fca66ca4808a: DESERT | {SG, BOW, MS},        # the desert crossed; silver gauntlets, bow, mirror shield
    # WaterTemple
    0xd731ea6a04d0fd01: ADULT | {IRON, LONG, BOW},     # adult, iron boots, longshot, bow
    0xa0973706f6415ecd: ADULT | {IRON, LONG, BOW},     # adult, iron boots, longshot, bow (probably)
    0xe03a2965df9f7b30: ADULT | {IRON, LONG, BOW},     # adult, iron boots, longshot, bow
    0x02974596f92cf377: ADULT | {IRON, LONG, BOW},     # adult, iron boots, longshot, bow
    0x3d0de5adaeb73cc9: ADULT | {IRON, LONG, BOW},     # adult, iron boots, longshot, bow
}
SKULLTULA_GATING_SHARE = 0.35   # (of the gating items, how many are tried on a Skulltula)


def skulltula_rule(h, area):
    """what the Skulltula of this hash, in this area, asks for"""
    return SKULLTULA_RULES.get(h, rule(area, "") | SKULLTULA_ASKS)


def gate_skulltulas(rng, gives, drops, skulls, needs, skull_needs, fixed, share=SKULLTULA_GATING_SHARE, never=(), token=TOKEN, keep=()):
    """Some of the gating items the logic put in chests (gives) moved to Gold Skulltulas that still drop their token
    (skulls: hashes, in a fixed order; drops: the ones that do not), each only if every gating item can still be
    got by the rules. The chest it leaves gives the token. needs and skull_needs: what a chest and a Skulltula ask
    for; fixed: [(what it asks for, the item)] of the gating items in chests that stay.
    never: gating items that are not tried (one not seen dropped by a Skulltula yet).
    keep: chests whose gating item is not tried (a lesson that may hold only some items: a token is not one).
    token: what a Skulltula's own drop is, which the chest left gives (the Pieces of Heart lying in the world are
    placed by this too: theirs is the piece).
    Returns (what the chests give, what the Skulltulas drop, the spheres, how many were moved)."""
    gives, drops = dict(gives), dict(drops)
    where = {i: (False, h) for h, i in gives.items() if i in PROGRESSION}   # item -> (on a Skulltula, the hash)

    def placed():
        return fixed + [((skull_needs if on_skull else needs)[h], i) for i, (on_skull, h) in sorted(where.items())]

    want = {i for _, i in fixed} | set(where)
    free = [h for h in skulls if h not in drops]
    rng.shuffle(free)
    order = sorted(where)
    rng.shuffle(order)
    order = [i for i in order if i not in never and where[i][1] not in keep]   # (after the shuffle: the seeds made before `never` keep theirs)
    moved = 0
    for item in order:
        if not free or rng.random() >= share:
            continue
        chest = where[item][1]
        where[item] = (True, free[-1])
        if {i for sphere in collect(placed()) for i in sphere} >= want:
            drops[free.pop()] = item
            gives[chest] = token
            moved += 1
        else:
            where[item] = (False, chest)
    return gives, drops, collect(placed()), moved


def mix_skulltulas(rng, gives, skulls, token=TOKEN):
    """The tokens of `skulls` (Skulltulas' hashes, in a fixed order) and the chests' items a Skulltula may be given
    (SKULLTULA_ITEMS) shuffled among those chests and those Skulltulas. Returns (what the chests give now, {a
    Skulltula's hash: the item it drops} for the ones that do not drop their token)."""
    if not skulls:
        return dict(gives), {}
    chests_in = [h for h in gives if gives[h] in SKULLTULA_ITEMS]
    items = [gives[h] for h in chests_in] + [token] * len(skulls)
    rng.shuffle(items)
    new, drops = dict(gives), {}
    for h, item in zip(chests_in + list(skulls), items):
        if h in gives:
            new[h] = item
        elif item != token:
            drops[h] = item
    return new, drops


def sarc_hash(name, mult=101):
    h = 0
    for c in name.encode():
        h = (h * mult + (c if c < 128 else c - 256)) & 0xFFFFFFFF
    return h


def sarc_read(data):
    """a SARC archive's files, {name: bytes} (little-endian, as the game's are)"""
    if data[:4] != b"SARC" or struct.unpack_from("<H", data, 6)[0] != 0xFEFF:
        raise ValueError("not a little-endian SARC archive")
    head, _, _, data_at = struct.unpack_from("<HHII", data, 4)
    if data[head:head + 4] != b"SFAT":
        raise ValueError("a SARC archive without its file table")
    n = struct.unpack_from("<H", data, head + 6)[0]
    nodes = head + 12
    names = nodes + 16 * n + 8
    out = collections.OrderedDict()
    for i in range(n):
        _, attr, a, b = struct.unpack_from("<IIII", data, nodes + 16 * i)
        at = names + (attr & 0xFFFFFF) * 4
        out[data[at:data.index(b"\0", at)].decode()] = bytes(data[data_at + a:data_at + b])
    return out


def sarc_write(files, mult=101, align=8):
    """a SARC archive of {name: bytes}, as the game's own packs are laid out (the same bytes for the same files)"""
    names, nodes, blob = bytearray(), [], bytearray()
    for name, data in sorted(files.items(), key=lambda kv: sarc_hash(kv[0], mult)):
        blob += b"\0" * (-len(blob) % align)
        nodes.append((sarc_hash(name, mult), 0x01000000 | len(names) // 4, len(blob), len(blob) + len(data)))
        blob += data
        names += name.encode() + b"\0"
        names += b"\0" * (-len(names) % 4)
    head = 0x14 + 12 + 16 * len(nodes) + 8 + len(names)
    data_at = head + (-head % align)
    out = bytearray(b"SARC" + struct.pack("<HHIIHH", 0x14, 0xFEFF, data_at + len(blob), data_at, 0x0100, 0))
    out += b"SFAT" + struct.pack("<HHI", 12, len(nodes), mult)
    for node in nodes:
        out += struct.pack("<IIII", *node)
    out += b"SFNT" + struct.pack("<HH", 8, 0) + names
    out += b"\0" * (data_at - len(out)) + blob
    return bytes(out)


def set_root_string(data, key, value):
    """a BYML file with the string its root dictionary has under `key` changed: the new bytes. The new string goes
    into a copy of the string table at the end of the file, as an item's name does in a map file."""
    if data[:2] != b"YB":
        raise ValueError("not a little-endian BYML")
    key_at, str_at, root = struct.unpack_from("<III", data, 4)
    keys, strings = table(data, key_at), table(data, str_at)
    where = next((w for k, t, _, w in entries(data, root, keys) if k == key and t == 0xA0), None)
    if where is None:
        raise ValueError("the file's root has no string %s" % key)
    out = bytearray(data)
    out += b"\0" * (-len(out) % 4)
    names = strings if value in strings else strings + [value]
    if len(names) > len(strings):
        at = len(out)
        out += string_table(names)
        struct.pack_into("<I", out, 8, at)
    struct.pack_into("<I", out, where, names.index(value))
    return bytes(out)


def byml_parse(data):
    """A little-endian BYML file as a tree that keeps every value's type, for writing it again changed: a dictionary
    is ("dict", {key: node}), an array ("array", [node]), a string ("string", text), anything else (its type byte,
    its bytes: 4, or the 8 a 64-bit value points at). Returns (the tree, the file's version)."""
    if data[:2] != b"YB":
        raise ValueError("not a little-endian BYML")
    version = struct.unpack_from("<H", data, 2)[0]
    key_at, str_at, root = struct.unpack_from("<III", data, 4)
    keys = table(data, key_at) if key_at else []
    strings = table(data, str_at) if str_at else []

    def value(kind, at):
        raw = struct.unpack_from("<I", data, at)[0]
        if kind == 0xA0:
            return ("string", strings[raw])
        if kind in (0xC0, 0xC1):
            return node(raw)
        if kind in (0xD4, 0xD5, 0xD6):
            return (kind, bytes(data[raw:raw + 8]))
        if kind in (0xD0, 0xD1, 0xD2, 0xD3, 0xFF):
            return (kind, bytes(data[at:at + 4]))
        raise ValueError("a BYML value of a type not written again here (%#x)" % kind)

    def node(at):
        kind, n = data[at], int.from_bytes(data[at + 1:at + 4], "little")
        if kind == 0xC1:
            out = collections.OrderedDict()
            for k in range(n):
                e = at + 4 + 8 * k
                out[keys[int.from_bytes(data[e:e + 3], "little")]] = value(data[e + 3], e + 4)
            return ("dict", out)
        if kind == 0xC0:
            vals = at + 4 + (n + 3 & ~3)
            return ("array", [value(data[at + 4 + k], vals + 4 * k) for k in range(n)])
        raise ValueError("a BYML node of a type not written again here (%#x)" % kind)

    return (node(root) if root else None), version


def byml_build(tree, version):
    """the bytes of a tree of byml_parse: the key and string tables sorted, every container written once"""
    keys, strings = set(), set()

    def gather(nd):
        if nd[0] == "dict":
            keys.update(nd[1])
            for v in nd[1].values():
                gather(v)
        elif nd[0] == "array":
            for v in nd[1]:
                gather(v)
        elif nd[0] == "string":
            strings.add(nd[1])
    gather(tree)
    keys, strings = sorted(keys, key=lambda k: k.encode()), sorted(strings, key=lambda k: k.encode())
    key_index, string_index = {k: i for i, k in enumerate(keys)}, {k: i for i, k in enumerate(strings)}
    out = bytearray(16)
    key_at = len(out)
    out += string_table(keys)
    str_at = len(out)
    out += string_table(strings)

    def emit(nd):
        """(type byte, the 4 bytes that stand for the value where it is held)"""
        if nd[0] == "string":
            return 0xA0, struct.pack("<I", string_index[nd[1]])
        if nd[0] == "dict":
            rows = [(key_index[k], emit(v)) for k, v in nd[1].items()]
            rows.sort(key=lambda r: r[0])
            at = len(out)
            out.extend(bytes([0xC1]) + len(rows).to_bytes(3, "little"))
            for k, (kind, held) in rows:
                out.extend(k.to_bytes(3, "little") + bytes([kind]) + held)
            return 0xC1, struct.pack("<I", at)
        if nd[0] == "array":
            rows = [emit(v) for v in nd[1]]
            at = len(out)
            out.extend(bytes([0xC0]) + len(rows).to_bytes(3, "little") + bytes(k for k, _ in rows))
            out.extend(b"\0" * (-len(out) % 4))
            for _, held in rows:
                out.extend(held)
            return 0xC0, struct.pack("<I", at)
        kind, raw = nd
        if kind in (0xD4, 0xD5, 0xD6):
            out.extend(b"\0" * (-len(out) % 8))
            at = len(out)
            out.extend(raw)
            return kind, struct.pack("<I", at)
        return kind, raw

    _, held = emit(tree)
    out[0:16] = b"YB" + struct.pack("<HII", version, key_at, str_at) + held
    return bytes(out)


# What an item's actor is made a pick-up from. Obj_Item_Base is what a Heart Piece and a rupee are made from: it falls
# to the ground. A gold token is made from it too, with parts of its own: it stays where the Skulltula died, is
# collected by touching it, and the Boomerang and the Hookshot bring it in, which is how every Skulltula's place was
# made to be reached. So an item is made a pick-up from the token.
PICKUP_BASE = "Obj_Token_Gold"
# The token's effects and sounds come with it: a gold skull's outline around the item as it is got, in the item's own
# chest too (seen in play). The item's actor cannot name others: an ELinkRef or SLinkRef of its own, empty or another
# pick-up's or the token's very own, stopped the game as the actor was made, and an item given the token's parts one
# by one without them was not there at all when its Skulltula died (all tried). What the token's two files say is
# changed in the item's pack instead: each holds a name, and they get a plain pick-up's, the Deku Shield as it lies in
# the world.
PICKUP_EFFECTS = "Obj_Shield_Deku"


# (what a chest's item is made from: the model a chest's get scene shows, with nothing to touch)
CHEST_BASE = "Item_EventObject_Base"


def ref_file(ref):
    """the pack's file a parameter file names: "?X.bgyml" is X.bgyml, "Work/X.gyml" is X.bgyml"""
    name = ref.lstrip("?")
    if name.startswith("Work/"):
        name = name[len("Work/"):]
    return name[:-len(".gyml")] + ".bgyml" if name.endswith(".gyml") else name


def actor_chain(item, files):
    """An item's actor and the actors it is made from, as far as its pack has them: [[file, tree, version]], the
    item's own first (a red rupee's: TBox_Rupee_Red, TBox_Rupee_Green, Item_EventObject_Base)."""
    chain, name = [], "Actor/%s.engine__actor__ActorParam.bgyml" % item
    while name in files and name not in [c[0] for c in chain]:
        tree, version = byml_parse(files[name])
        chain.append([name, tree, version])
        parent = tree[1].get("$parent")
        if not parent or parent[0] != "string":
            break
        name = ref_file(parent[1])
    return chain


def pickup_family(item, item_pack):
    """the actors an item is made from that are chests' items themselves, by name, the item's own first: each has a
    pack of its own with a copy of the same file, and is made a pick-up with the item"""
    chest = "Actor/%s.engine__actor__ActorParam.bgyml" % CHEST_BASE
    return [name.split("/")[1].split(".")[0] for name, _, _ in actor_chain(item, sarc_read(item_pack)) if name != chest]


# An item's model is made to be held up over Link's head, seen from close: hanging where a Skulltula died the
# smallest are hard to see (the Lens of Truth and the Goron's Bracelet, seen in play). These are made larger, by
# their ModelInfo's DebugModelScale (the game's own dogs, light balls and a rolling rock have one that is not 1). The
# model is as much larger in its chest's scene: the two are one actor. Not more than this: an item hangs in the
# pose of that scene, about half a metre over the place it is taken at, and its size carries that with it (at 2.5
# the Lens of Truth hung a metre over it; without the pose, its ASRef and ASInfoRef left out, it lay edge-on at
# the right height: both seen without a window).
PICKUP_SCALES = {"Item_GlassTruth": 1.5, "Item_Gauntlet_Goron": 1.5}


# How an item is got, in its pouch file: "Large" is Link holding it up (the hash of the word, as the game's files have it)
GET_LARGE = 1746592023


# An item whose pouch file is another thing's too: a chest's rupee has the world rupee's, a chest's arrows the world's
# arrow bundle's, a chest's magic jar the world's jar's. Changed in place it would change every world rupee (its get
# event each time one is picked up), and of the copies of one name the game uses the first it loaded. These are given
# a pouch file of their own, under a name of its own (OWN_POUCH), with the item's as its parent.
PICKUP_OWN_POUCH = frozenset(("TBox_Rupee_Green", "TBox_Rupee_Blue", "TBox_Rupee_Red", "TBox_Rupee_Purple", "TBox_Rupee_Gold",
                              "TBox_ArrowBundle_Medium", "TBox_ArrowBundle_Large", "Tbox_MagicJar_Large"))
OWN_POUCH = "Component/PouchContentParam/Rando_%s.game__component__PouchContentParam.bgyml"


def pickup_pack(item, item_pack, base_pack, base_name=PICKUP_BASE, effects_name=PICKUP_EFFECTS, each_time=False,
                own_pouch=PICKUP_OWN_POUCH):
    """An item's pack (a SARC archive) made into a pick-up's. Its actor takes the base's as its parent in place of
    Item_EventObject_Base (the model a chest's get scene shows, with nothing to touch), and the pack gets the files
    of the base's that it lacks. An item made from another item (a red rupee from a green one) has that one's
    parent changed: the one whose parent Item_EventObject_Base is. What the item has of its own (its model, its
    animation, what it is in the pouch) stays over the base's, with two changes:
      - its table of game parameters names the base's as its parent. An item's own table took the base's place
        whole and left the pick-up without DropBoundParam and GamePhysicsControllerParam: the game stopped at the
        missing one as the actor was made (a rupee's table has the base's as its parent);
      - what it is in the pouch is got by touching it (DefaultAutoGet, as a token's and a rupee's are), not by
        standing beside it and pressing A. One that says so already, itself or by its parent, is left as it is.
    each_time: its get event runs each time it is got, not only the first (PlayGetEventManyTimes, and how it is got
    where its pouch file does not say: every item of the game's own that is got each time says both). A pick-up made
    from the token is done with by its get event: the second Deku Scrub's seed of a game was put in the pouch and
    stayed where it was, and its Skulltula was back when the room was entered again (seen in play).
    Seen in play with the Boomerang, the Megaton Hammer and the small Bomb Bag: the chest still gives the item with
    its scene, and dropped by a Gold Skulltula it stays there and is collected by touching it, with its text."""
    files, base = sarc_read(item_pack), sarc_read(base_pack)
    own = "Actor/%s.engine__actor__ActorParam.bgyml" % item
    chest_actor = "Actor/%s.engine__actor__ActorParam.bgyml" % CHEST_BASE
    if own not in files:
        raise ValueError("%s: its pack has no actor of that name" % item)
    chain = actor_chain(item, files)

    def pouch_says(key, name=None):
        """what the item's pouch file (or the pouch file `name`) says of `key`, itself or the nearest parent that
        does: True, False or None"""
        seen = []
        for _, tree, _ in chain if name is None else ():
            ref = tree[1].get("Components", ("dict", {}))[1].get("PouchContentRef")
            if ref and ref[0] == "string" and ref[1]:
                name = ref_file(ref[1])
                break
        while name in files and name not in seen:
            seen.append(name)
            sub, _ = byml_parse(files[name])
            if key in sub[1]:
                return any(sub[1][key][1])
            parent = sub[1].get("$parent")
            name = ref_file(parent[1]) if parent and parent[0] == "string" else ""
        return None

    base_actor = "Actor/%s.engine__actor__ActorParam.bgyml" % base_name
    base_table = "GameParameter/GameParameterTable/%s.engine__actor__GameParameterTable.bgyml" % base_name
    if base_actor not in base or base_table not in base:
        raise ValueError("%s: the base's pack has no actor or no table of game parameters of %s" % (item, base_name))
    top = next((k for k, (_, tree, _) in enumerate(chain)
                if tree[1].get("$parent", ("", ""))[0] == "string" and ref_file(tree[1]["$parent"][1]) == chest_actor), None)
    if top is None:
        raise ValueError("%s is not made from %s: not a chest's item" % (item, CHEST_BASE))
    chain = chain[:top + 1]
    name, tree, version = chain[top]
    tree[1]["$parent"] = ("string", "Work/" + base_actor.replace(".bgyml", ".gyml"))
    files[name] = byml_build(tree, version)

    def part(key):
        """the pack's file an entry of the actor's Components names (the item's own, or the nearest it is made
        from), or "" """
        for _, tree, _ in chain:
            ref = tree[1].get("Components", ("dict", {}))[1].get(key)
            if ref and ref[0] == "string" and ref[1]:
                return ref_file(ref[1]) if ref_file(ref[1]) in files else ""
        return ""

    name = part("GameParameterTableRef")
    if name and name != base_table:
        sub, sub_version = byml_parse(files[name])
        if "$parent" not in sub[1]:
            sub[1]["$parent"] = ("string", "Work/" + base_table.replace(".bgyml", ".gyml"))
            files[name] = byml_build(sub, sub_version)
    # (a pouch file of its own for each actor of the item's that names one and is in own_pouch: the item's, and the item
    # it is made from, whose actor this pack has a copy of and whose own pack is changed the same way)
    for name, tree, version in chain:
        actor = name.split("/")[1].split(".")[0]
        ref = tree[1].get("Components", ("dict", {}))[1].get("PouchContentRef")
        if actor not in own_pouch or not ref or ref[0] != "string" or ref_file(ref[1]) not in files:
            continue
        was = ref_file(ref[1])
        was_tree, was_version = byml_parse(files[was])
        new = OWN_POUCH % actor
        # (a copy of the item's, with all it says and its parent: a file that only named the item's as its parent was
        # not taken by touching it, seen without a window. And what the item's own would be given below, given here to
        # each: the same file in every pack that has it)
        own = collections.OrderedDict(was_tree[1])
        own["DefaultAutoGet"] = (0xD0, struct.pack("<I", 1))
        if each_time and not pouch_says("PlayGetEventManyTimes", was):
            own["PlayGetEventManyTimes"] = (0xD0, struct.pack("<I", 1))
            if pouch_says("GetType", was) is None:
                own["GetType"] = (0xD3, struct.pack("<I", GET_LARGE))
        files[new] = byml_build(("dict", own), was_version)
        tree[1]["Components"][1]["PouchContentRef"] = ("string", "?" + new)
        files[name] = byml_build(tree, version)
    first = part("PouchContentRef")
    if first and not pouch_says("DefaultAutoGet"):
        sub, sub_version = byml_parse(files[first])
        sub[1]["DefaultAutoGet"] = (0xD0, struct.pack("<I", 1))
        files[first] = byml_build(sub, sub_version)
    name = part("ModelInfoRef")
    if name and item in PICKUP_SCALES:
        sub, sub_version = byml_parse(files[name])
        sub[1]["DebugModelScale"] = ("dict", collections.OrderedDict((axis, (0xD2, struct.pack("<f", PICKUP_SCALES[item]))) for axis in "XYZ"))
        files[name] = byml_build(sub, sub_version)
    if first and each_time and not pouch_says("PlayGetEventManyTimes"):
        sub, sub_version = byml_parse(files[first])
        sub[1]["PlayGetEventManyTimes"] = (0xD0, struct.pack("<I", 1))
        if pouch_says("GetType") is None:
            sub[1]["GetType"] = (0xD3, struct.pack("<I", GET_LARGE))
        files[first] = byml_build(sub, sub_version)
    for name, data in base.items():
        files.setdefault(name, data)
    for kind in ("ELink", "SLink"):   # (the base's effects and sounds: another's, PICKUP_EFFECTS above)
        name = "Component/%s/%s.engine__component__%sParam.bgyml" % (kind, base_name, kind)
        if effects_name and name in files:
            sub, sub_version = byml_parse(files[name])
            if sub[1].get("UserName", ("", ""))[0] == "string":
                sub[1]["UserName"] = ("string", effects_name)
                files[name] = byml_build(sub, sub_version)
    return sarc_write(files)


def murmur3(data, seed=0):
    """MurmurHash3, 32 bits: the game's list of flags names each by this hash of its name"""
    c1, c2, h = 0xcc9e2d51, 0x1b873593, seed
    whole = len(data) & ~3
    for i in range(0, whole, 4):
        k = int.from_bytes(data[i:i + 4], "little") * c1 & 0xffffffff
        k = (k << 15 | k >> 17) * c2 & 0xffffffff
        h ^= k
        h = ((h << 13 | h >> 19) & 0xffffffff) * 5 + 0xe6546b64 & 0xffffffff
    if len(data) > whole:
        k = int.from_bytes(data[whole:], "little") * c1 & 0xffffffff
        h ^= (k << 15 | k >> 17) * c2 & 0xffffffff
    h ^= len(data)
    h = (h ^ h >> 16) * 0x85ebca6b & 0xffffffff
    h = (h ^ h >> 13) * 0xc2b2ae35 & 0xffffffff
    return h ^ h >> 16


def flag_hash(name):
    """A flag's hash: its name's MurmurHash3, or, for a flag whose name is not known, "#<the hash in hex>"."""
    return int(name[1:], 16) if name.startswith("#") else murmur3(name.encode())


def flag_defaults(data, flags, kind="Bool"):
    """The game's list of flags (GameDataList: a BYML as the map files are, but big-endian, "BY") with the value each
    flag of `flags` ({name: truth value}) starts a new game with: the new bytes, or None when they already start so.
    A flag is a dictionary of Data.Bool, {DefaultValue, Hash (of its name), ...}; the value is in the dictionary
    itself, so the file keeps its size. A name the list does not have as a truth value is an error.
    kind "Int": the list's whole numbers (Data.Int: PlayerStatus.CurrentRupee, the rupees Link has), `flags` then
    {name: a number from 0 to 2147483647}."""
    whole = kind == "Int"
    if whole and any(not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 0x7fffffff for v in flags.values()):
        raise ValueError("a number to start with is not a whole number the list can hold")
    if data[:2] != b"BY":
        raise ValueError("not a big-endian BYML (%r)" % data[:4])
    key_at, _, root = struct.unpack_from(">III", data, 4)
    count = lambda at: int.from_bytes(data[at + 1:at + 4], "big")
    keys = []
    for k in range(count(key_at)):
        at = key_at + struct.unpack_from(">I", data, key_at + 4 + 4 * k)[0]
        keys.append(data[at:data.index(b"\0", at)].decode("utf-8", "replace"))

    def fields(at):
        """a dictionary node's {key: (type, value, where its value is)}"""
        if data[at] != 0xC1:
            raise ValueError("no dictionary at %#x" % at)
        out = {}
        for k in range(count(at)):
            e = at + 4 + 8 * k
            key = int.from_bytes(data[e:e + 3], "big")
            out[keys[key] if key < len(keys) else ""] = (data[e + 3], struct.unpack_from(">I", data, e + 4)[0], e + 4)
        return out

    node, at, _ = fields(root).get("Data", (0, 0, 0))
    node, bools, _ = fields(at).get(kind, (0, 0, 0)) if node == 0xC1 else (0, 0, 0)
    if node != 0xC0 or data[bools] != 0xC0:
        raise ValueError("the list has no Data.%s" % kind)
    want = {flag_hash(name): name for name in flags}
    if len(want) != len(flags):
        raise ValueError("two of the flags have one hash")
    n = count(bools)
    values = bools + 4 + (n + 3 & ~3)
    found = {}
    for i in range(n):
        if data[bools + 4 + i] != 0xC1:
            continue
        f = fields(struct.unpack_from(">I", data, values + 4 * i)[0])
        h = f.get("Hash")
        if not h or h[0] not in (0xD1, 0xD3) or h[1] not in want:
            continue
        v = f.get("DefaultValue")
        if not v or v[0] != (0xD1 if whole else 0xD0):
            raise ValueError("%s has no %s to start with" % (want[h[1]], "whole number" if whole else "truth value"))
        found[want[h[1]]] = (v[1] if whole else v[1] != 0, v[2])
    missing = sorted(set(flags) - set(found))
    if missing:
        raise ValueError("the game's list has no flag " + ", ".join(missing))
    if all(found[name][0] == (v if whole else bool(v)) for name, v in flags.items()):
        return None
    out = bytearray(data)
    for name, v in flags.items():
        struct.pack_into(">I", out, found[name][1], v if whole else int(bool(v)))
    return bytes(out)


def opening_skip(data):
    """OpeningEvent (a BFEVFL file) with its two cutscenes passed over: the new bytes, of the same size. Every step
    it relies on is checked first (see OPENING, above): a flow that is not the one this was written for is an error."""
    u16 = lambda at: struct.unpack_from("<H", data, at)[0]
    u64 = lambda at: struct.unpack_from("<Q", data, at)[0]
    if data[:6] != b"BFEVFL" or u16(0x20) != 1:
        raise ValueError("not an event flow file of one flowchart")
    chart = u64(u64(0x28))
    if data[chart:chart + 4] != b"EVFL" or u16(chart + 0x16) != 29 or u16(chart + 0x18) != 2:
        raise ValueError("the opening's flowchart is not the one of 29 events and 2 entry points")
    events, entries = u64(chart + 0x30), u64(chart + 0x40)
    event = lambda i: events + 0x30 * i

    def text(ptr):
        return bytes(data[ptr + 2:ptr + 2 + u16(ptr)]).decode("utf-8", "replace") if ptr else ""

    def plays(i):
        """the cutscene an EventTransition step plays: the first string of its parameters that names a Dm_ flow"""
        at = u64(event(i) + 0x10)
        for k in range(u16(at + 2) if at else 0):
            item = u64(at + 0x10 + 8 * k)
            if data[item] in (0, 5) and u16(item + 2) == 1 and text(u64(item + 0x10)).startswith("Dm_"):
                return text(u64(item + 0x10))
        return ""

    step = lambda i: (data[event(i) + 8], u16(event(i) + 0x0a))   # (its kind: 0 an action, 1 a switch; its next step)
    if (u16(entries + 0x1c) != 7 or step(7) != (0, 14) or plays(7) != "Dm_Kokiri_0000" or data[event(14) + 8] != 1 or
            step(23) != (0, 0) or step(0) != (0, 17) or plays(0) != "Dm_Kokiri_0030" or data[event(17) + 8] != 1 or step(19) != (0, 10)):
        raise ValueError("the opening's steps are not the ones this was written for")
    out = bytearray(data)
    struct.pack_into("<H", out, entries + 0x1c, 14)        # (the first entry point starts after the narration)
    struct.pack_into("<H", out, event(23) + 0x0a, 19)      # (the wait goes on to what follows Navi's cutscene)
    return bytes(out)


def bombchu_presence(data):
    """A map file of the child's Market with the Bombchu Shop's keeper and music there from the start and its "Closed"
    sign gone (BOMBCHU_ACTORS, BOMBCHU_SIGN, above): (the file written anew, or None when it has none of them; how
    many actors were changed or taken out)."""
    tree, version = byml_parse(data)
    actors = tree[1].get("Actors")
    if not actors or actors[0] != "array":
        return None, 0
    keep, done = [], 0
    for actor in actors[1]:
        rows = actor[1]
        name = rows.get("Gyaml", ("", ""))[1]
        presence = rows.get("Presence")
        quest = presence and presence[0] == "dict" and presence[1].get("FlagName", ("", ""))[1] == BOMBCHU_QUEST
        if quest and name == BOMBCHU_SIGN:
            done += 1
            continue   # (the sign: out)
        if quest and name in BOMBCHU_ACTORS:
            del rows["Presence"]
            done += 1
        keep.append(actor)
    if not done:
        return None, 0
    tree[1]["Actors"] = ("array", keep)
    return byml_build(tree, version), done


# Three red rupees on Hyrule Castle's drawbridge (asked for by the owner, 2026-11-15): the original game had three at
# the top of the drawbridge's chains, which the remake's bridge cannot be climbed to. They are loose rupees of the
# kind the game lays about elsewhere (Obj_Rupee_Red, as in Death Mountain Crater: a name, its two hashes and a place,
# nothing else), put in the child's Hyrule Field down the middle of the lowered bridge's deck (Land_HrlField_DrawBridge
# at z 34.0 by the gate, over the moat, whose floor is at z 36 to 45, to the field at about z 47; the Market's side is
# below z 34, its loading zone an Area at z 28.1). A loose rupee is not kept as taken: it should be there again after
# a loading zone. Their hashes are new ones of our own (DRAWBRIDGE_HASH + 1..3), not in the file before.
DRAWBRIDGE_FILE = "Banc/HyruleField/HyruleField_Child_Dynamic.bcett.byml.zs"
DRAWBRIDGE_RUPEES = ((0.0, 151.2, 37.5), (0.0, 151.2, 40.5), (0.0, 151.2, 43.5))   # (the deck: from the gate, z 34, out over the moat to the field at about z 47)
DRAWBRIDGE_HASH = 0x5241_4E44_0B21_D000   # (+1, +2, +3; SRTHash: the low 32 bits)


def drawbridge_rupees(data):
    """The child's Hyrule Field map file with the drawbridge's three red rupees (DRAWBRIDGE_RUPEES) added: (the file
    written anew, how many were added). ValueError: the file has no actors, or a hash of ours already."""
    tree, version = byml_parse(data)
    actors = tree[1].get("Actors")
    if not actors or actors[0] != "array":
        raise ValueError("the field's map file has no actors")
    have = {rows[1]["Hash"][1] for rows in actors[1] if "Hash" in rows[1]}
    added = []
    for i, (x, y, z) in enumerate(DRAWBRIDGE_RUPEES, 1):
        h = struct.pack("<Q", DRAWBRIDGE_HASH + i)
        if h in have:
            raise ValueError("the field's map file has a rupee of ours already")
        added.append(("dict", collections.OrderedDict((
            ("Gyaml", ("string", "Obj_Rupee_Red")),
            ("Hash", (0xD5, h)),
            ("Phive", ("dict", collections.OrderedDict((("Placement", ("dict", collections.OrderedDict((("ID", (0xD5, h)),)))),)))),
            ("SRTHash", (0xD3, struct.pack("<I", (DRAWBRIDGE_HASH + i) & 0xFFFFFFFF))),
            ("Translate", ("array", [(0xD2, struct.pack("<f", v)) for v in (x, y, z)]))))))
    tree[1]["Actors"] = ("array", actors[1] + added)
    return byml_build(tree, version), len(added)


def bombchu_door_open(data):
    """The Bombchu Shop's door logic (BOMBCHU_DOOR_LOGIC, above) with its two AND nodes made OR nodes: the new bytes,
    of the same size. ValueError: the file is not the one this was written for."""
    u16 = lambda at: struct.unpack_from("<H", data, at)[0]
    u32 = lambda at: struct.unpack_from("<I", data, at)[0]
    if data[:4] != b"AIB " or u32(4) != 0x408 or u32(0x10) != 8:
        raise ValueError("not the AI file of 8 nodes this was written for")
    pool = u32(0x24)
    name = lambda i: data[pool + u32(0x74 + 0x3C * i + 8):].split(bytes(1))[0]
    if [name(i) for i in (0, 4, 5)] != [b"OperateAND", b"OperateAND", b"OperateOR"] or b"Get_StoneOfFire_IsCompleted_Exp" not in data:
        raise ValueError("the door's nodes are not the ones this was written for")
    out = bytearray(data)
    for i in (0, 4):
        out[0x74 + 0x3C * i + 8:0x74 + 0x3C * i + 16] = data[0x74 + 0x3C * 5 + 8:0x74 + 0x3C * 5 + 16]   # (the name's place and its hash)
    return bytes(out)


# Bombchu Bowling and the Bombchu Shop open from the start, the shop by day too (asked 2026-11-20, every seed from
# fixes 59; OOTRR v0.8.0 did the first, 525dace, and was the lead). What kept them shut is the Goron's Ruby's quest done,
# Get_StoneOfFire_IsCompleted_Exp (BOMBCHU_QUEST), read in three AI files (CHU_LOGIC: the shop's door, the bowling's
# attendant and the bowling game), two talk flows (CHU_FLOWS: a question of it, the bowling's and the Bazaar man's) and
# the Market's map (BOMBCHU_ACTORS, BOMBCHU_SIGN, above). The flows' question is sent to its "done" answer either way
# (flow_switch_yes); the AI files read ALWAYS_EXP instead, a formula of the game's list of flags that nothing in the
# game reads (looked for in every AI, flow, map and pack file) made always true: "ALWAYS_FLAG or not ALWAYS_FLAG"
# (always_exp). The shop's door, already made "the quest OR the night" (bombchu_door_open), is then open day and night.
ALWAYS_EXP = "Get_StoneOfFire_IsAfter_Ready_Exp"
ALWAYS_FLAG = "Market_Child_TimeTempleDoor_Opened"   # (any truth value would do: one some formula already reads)
CHU_LOGIC = ("Logic/Market_Child_Prefab_0c76.logic.module.ainb", "Logic/Market_Child_Prefab_d0eb.logic.module.ainb",
             "Logic/MiniGame_BombchuBowling_e64e.logic.module.ainb")
CHU_FLOWS = (("Event/EventFlow/MiniGame_BombchuBowling.bfevfl.zs", "Event137"),
             ("Event/EventFlow/Npc_Hylia_018_Shop_Child.bfevfl.zs", "Event14"))   # (the Bazaar man's: his talk of the Gorons back)
# The Water Temple's gate switch by Lake Hylia without the Ice Cavern (asked 2026-11-20, every seed from fixes 59; OOTRR
# v0.8.0, 224e19c, the lead): an invisible wall (FldObj_AirWall_All) stands over the switch and the gate in the adult's
# Hyrule Field map until the Water Sage's quest is past Step03, at the Ice Cavern's end. It is taken out of the map
# (water_wall_out). The rules never asked for the Ice Cavern there (AREAS' WaterTemple), so they are as they were.
WATER_WALL_FILE = "Banc/HyruleField/HyruleField_Adult_Dynamic.bcett.byml.zs"
WATER_WALL = ("FldObj_AirWall_All", "SageOfWater_IsAfter_Step03_Exp")
# (bug 119, the owner's run 2026-11-23: the Longshot did not catch the vines of Lake Hylia's dead tree, its Gold
# Skulltula's way, "LH GS Tree" by the Longshot in the rules.) A thin FldObj_AirWall_Hookshot lies along the vines in both
# Links' Hyrule Field maps, there while WaterTemple_Room07_00 is not set (walking into the Water Temple's room 7). Fixes
# 73 took it out, read as a wall that stops the Hookshot: the owner then saw the reticle red on the vines (in reach,
# nothing to catch) and no catch, with the Water Temple done too. Its shape (0.87 x 1.21 x 0.29, tilted as the trunk, at
# the vines' height) and the other such walls (Water Temple, Fire Temple, Kakariko: small boards where the Hookshot
# catches) say it is what the Hookshot catches. Fixes 79 kept it there always (water_wall_out's keep), but the owner then saw no marker at all on the vines: its
# own physics is HitOnlyHookshot (it stops the Hookshot, not catches it), so from fixes 82 it is taken out again. What the
# Longshot catches is the tree's climbable shape (AirwallForClimb), its boxes about 143-152 high: the top of the vines.
TREE_WALL_FILES = ("Banc/HyruleField/HyruleField_Adult_Dynamic.bcett.byml.zs", "Banc/HyruleField/HyruleField_Child_Dynamic.bcett.byml.zs")
TREE_WALL = ("FldObj_AirWall_Hookshot", "WaterTemple_Room07_00")
# Without the wall the Longshot reached the tree (red marker) but did not pull (the owner, 2026-11-24). A surface is a
# catch by its collision's StickHookshot shape tag (PhiveConfig's UserShapeTagMask). The tree is placed "Bakeable": its
# collision, and that of the two invisible climbing boxes over its vine sheet (Land_LakeHrl_Tree_A_01__AirwallForClimb,
# preset AirWallForClimb: an AirWall with no tags), is the copy baked into Hyrule Field's static compound
# (HyruleField_<age>_X7_Z10); edits to the tree's own pack and mesh (83, 84) are never read. The Longshot at the vines
# hits those boxes, in front of them: an AirWall makes no sound (the owner's lead: the vines silent after a load, then the
# last sound again) and has no StickHookshot. Found with the owner over seven tries of that file's material table
# (16 bytes each: u32 material, u32 sub-material, u64 shape tags, from the u32 at +0x20 to the one at +0x24): every
# entry tagged caught everything, the AirWalls alone the vines, entries 1 and 6 alone the vines. Entry 1 is the
# untagged AirWall (Undefined sub-material) the climbing preset makes; 6 has a sub-material of its own. From fixes 87
# entry 1 of both ages' tables carries StickHookshot (86's tag on the tree's Wood, the trunk a catch, is out).
BAKED_TREE_FILES = tuple("Phive/StaticCompoundBody/HyruleField/HyruleField_%s_X7_Z10.Nin_Ounce_NVN2.bphsc.zs" % age for age in ("Adult", "Child"))
MATERIAL_AIRWALL, CLIMB_WALL_ENTRY, TAG_STICK_HOOKSHOT = 27, 1, 1 << 44
# That was not enough (seen in play, 2026-11-20: the switch hookshotted, the gate stayed shut, no cutscene). So the gate
# is open from a new game's start (fixes 60): the state the game leaves it in once the switch is hit, its cutscene
# marked played and the gate's pillars risen (the lake's logic, HyruleField_LakeHylia_Common_Prefab_6a9d, opens the
# gate, SwitchShutter, by the first; the cutscene sets the second, which lights the two pillars by the door: seen without
# a window, set on a save before the Ice Cavern). The game's side sets them for a save made before (host/hos_main.c).
# Since 2026-11-22 (fixes 67) the gate is a setting, Water Temple gate (rando_water_gate: Open, Shut), now that the switch
# works (bug 91). It is the game's side's alone: a new game no longer starts with the two flags; the game sets them in a
# new game's first second at Open and leaves them at Shut (host/hos_main.c, host/oot_rando.c hos_rando_water_gate_shut),
# so the setting can be changed on a seed being played without the seed written again. WATER_GATE names the two flags.
WATER_GATE = {"HavePlayedEvent.Dm_WaterTemple_0000": True, "WaterTemple_EmitGatePillar": True}


def always_exp(data):
    """The game's list of flags (GameDataList, a big-endian BYML) with ALWAYS_EXP made "ALWAYS_FLAG or not ALWAYS_FLAG":
    the new bytes, 24 longer. A formula (Data.BoolExp) is {Hash, Values: an array of steps}, a step an array of an
    operation (a 64-bit number: 0 a truth value's flag, 4 OR, 5 NOT, 12 an enum after a value, 2 that value) and its
    flag's or value's hash; the steps are shared among formulas, so the formula is given a new array of its own (put
    at the file's end) of steps the file already has. ValueError: not the file, or the formula not the game's."""
    if data[:2] != b"BY":
        raise ValueError("not a big-endian BYML (%r)" % data[:4])
    key_at, _, root = struct.unpack_from(">III", data, 4)
    count = lambda at: int.from_bytes(data[at + 1:at + 4], "big")
    u32 = lambda at: struct.unpack_from(">I", data, at)[0]
    keys = [data[key_at + u32(key_at + 4 + 4 * k):data.index(b"\0", key_at + u32(key_at + 4 + 4 * k))].decode("utf-8", "replace")
            for k in range(count(key_at))]

    def fields(at):   # (a dictionary: {key: (type, value, where the value is)})
        if data[at] != 0xC1:
            raise ValueError("no dictionary at %#x" % at)
        return {keys[int.from_bytes(data[at + 4 + 8 * k:at + 7 + 8 * k], "big")]: (data[at + 7 + 8 * k], u32(at + 8 + 8 * k), at + 8 + 8 * k)
                for k in range(count(at))}

    def items(at):   # (an array: [(type, value)])
        if data[at] != 0xC0:
            raise ValueError("no array at %#x" % at)
        n = count(at)
        return [(data[at + 4 + i], u32(at + 4 + (n + 3 & ~3) + 4 * i)) for i in range(n)]

    def step(at):   # (a step: its numbers, each a 64-bit one)
        parts = items(at)
        return tuple(struct.unpack_from(">Q", data, v)[0] if t == 0xD5 else None for t, v in parts)

    data_at = fields(root).get("Data", (0, 0, 0))[1]
    exps = items(fields(data_at)["BoolExp"][1])
    bools = {fields(v).get("Hash", (0, None))[1] for t, v in items(fields(data_at)["Bool"][1]) if t == 0xC1}
    want, flag = murmur3(ALWAYS_EXP.encode()), murmur3(ALWAYS_FLAG.encode())
    if flag not in bools:
        raise ValueError("the list has no truth value %s" % ALWAYS_FLAG)
    target, done, steps = None, None, {}
    for t, at in exps:
        f = fields(at)
        if f.get("Hash", (0, None))[1] == want:
            target = f
        if f.get("Hash", (0, None))[1] == murmur3(BOMBCHU_QUEST.encode()):
            done = f
        for t2, s in items(f["Values"][1]):
            steps.setdefault(step(s), s)
    if target is None or done is None:
        raise ValueError("the list has no formula %s or %s" % (ALWAYS_EXP, BOMBCHU_QUEST))
    quest = step(items(done["Values"][1])[0][1])   # (the quest done: (1, the quest's enum), (2, Complete))
    if [step(s) for _, s in items(target["Values"][1])] != [(12, quest[1]), (2, murmur3(b"Ready"))]:
        raise ValueError("%s is not the formula this was written for (or is made already)" % ALWAYS_EXP)
    use = [(0, flag), (0, flag), (5,), (4,)]
    missing = [s for s in use if s not in steps]
    if missing:
        raise ValueError("no formula has the step %r to share" % (missing[0],))
    out = bytearray(data) + bytes(-len(data) & 3)
    at = len(out)
    out += bytes((0xC0, 0, 0, len(use))) + bytes((0xC0,)) * len(use) + b"".join(struct.pack(">I", steps[s]) for s in use)
    struct.pack_into(">I", out, target["Values"][2], at)
    return bytes(out)


# Every mask from the Happy Mask Shop from the start (bug 120, the owner's word 2026-11-23: the Forest Stage's two checks
# ask for a young Link wearing the Skull Mask or the Mask of Truth, and the masks came only by the mask salesman's trade).
# The shop's goods list shows each mask by a formula of its own (HappyMaskShop_HasMask_<mask>): the trade's step (or, for
# the Keaton Mask, the gate guard's Npc_Hylia_Soldier_003_GateOpen) AND the rest (no mask held from the shop just now,
# and the mask's own). The first part is made always true ("ALWAYS_FLAG or not ALWAYS_FLAG", as always_exp), the rest
# kept: one mask lent at a time, as the game has it. The salesman is there once the gate is open (his actor waits for
# GateOpen: Zelda's Letter shown, or Kakariko's gate Open). Every seed (fixes 74); the rules from MASKS_FROM.
MASK_EXPS = tuple("HappyMaskShop_HasMask_" + m for m in ("Keaton", "Skull", "Spooky", "Bunny", "Zora", "Goron", "Gerudo", "Truth"))
MASKS_FROM = 26
MASK_GIFTS = ("forest_stage_skull", "forest_stage_truth")


def masks_open(data, names=MASK_EXPS):
    """The game's list of flags with each formula of `names` made true in its first part (MASK_EXPS, above): the new
    bytes, longer by the formulas' new arrays. ValueError: not the file, or a formula not as the game has it."""
    if data[:2] != b"BY":
        raise ValueError("not a big-endian BYML (%r)" % data[:4])
    key_at, _, root = struct.unpack_from(">III", data, 4)
    count = lambda at: int.from_bytes(data[at + 1:at + 4], "big")
    u32 = lambda at: struct.unpack_from(">I", data, at)[0]
    keys = [data[key_at + u32(key_at + 4 + 4 * k):data.index(b"\0", key_at + u32(key_at + 4 + 4 * k))].decode("utf-8", "replace")
            for k in range(count(key_at))]

    def fields(at):
        if data[at] != 0xC1:
            raise ValueError("no dictionary at %#x" % at)
        return {keys[int.from_bytes(data[at + 4 + 8 * k:at + 7 + 8 * k], "big")]: (data[at + 7 + 8 * k], u32(at + 8 + 8 * k), at + 8 + 8 * k)
                for k in range(count(at))}

    def items(at):
        if data[at] != 0xC0:
            raise ValueError("no array at %#x" % at)
        n = count(at)
        return [(data[at + 4 + i], u32(at + 4 + (n + 3 & ~3) + 4 * i)) for i in range(n)]

    def step(at):
        return tuple(struct.unpack_from(">Q", data, v)[0] if t == 0xD5 else None for t, v in items(at))

    data_at = fields(root).get("Data", (0, 0, 0))[1]
    exps = items(fields(data_at)["BoolExp"][1])
    bools = {fields(v).get("Hash", (0, None))[1] for t, v in items(fields(data_at)["Bool"][1]) if t == 0xC1}
    flag = murmur3(ALWAYS_FLAG.encode())
    if flag not in bools:
        raise ValueError("the list has no truth value %s" % ALWAYS_FLAG)
    want = {murmur3(n.encode()): n for n in names}
    found, steps = {}, {}
    for t, at in exps:
        f = fields(at)
        if f.get("Hash", (0, None))[1] in want:
            found[f["Hash"][1]] = f
        for t2, st in items(f["Values"][1]):
            steps.setdefault(step(st), st)
    if len(found) != len(want):
        raise ValueError("the list has no formula %s" % ", ".join(n for h, n in want.items() if h not in found))
    use = [(0, flag), (0, flag), (5,), (4,)]
    if any(u not in steps for u in use):
        raise ValueError("no formula has the steps of an always true to share")
    out = bytearray(data) + bytes(-len(data) & 3)
    for h, f in sorted(found.items()):
        own = items(f["Values"][1])
        first = step(own[0][1])
        if not (first[0] == 10 or first == (0, murmur3(b"Npc_Hylia_Soldier_003_GateOpen"))) or len(own) < 5:
            raise ValueError("%s is not the formula this was written for (or is made already)" % want[h])
        offsets = [steps[u] for u in use] + [v for _, v in own[1:]]
        out += bytes(-len(out) & 3)
        at = len(out)
        out += bytes((0xC0, 0, 0, len(offsets))) + bytes((0xC0,)) * len(offsets) + bytes(-len(offsets) & 3) + b"".join(struct.pack(">I", o) for o in offsets)
        struct.pack_into(">I", out, f["Values"][2], at)
    return bytes(out)


# The mask salesman's trade done from a new game's start (bug 133, the owner's run 2026-11-23: with masks_open alone,
# borrowing the Bunny Hood started the trade, and no other mask could be had until it was sold). The trade's step is an
# enum of the game's list (Data.Enum, its name's hash 0xea010310 as the save keeps it: the name itself not found; seen in
# the owner's save at UntilRentMaskOfKeaton): NotReady, Ready, UntilRentMaskOfKeaton ... Step08, Complete. Started at
# Complete, every mask is the shop's to swap freely, as the game has it once the trade is done
# (HappyMaskShop_RentalAnyMask reads SubEvent_MaskSalesman_IsCompleted_Exp). Every seed (fixes 78); a save made before
# keeps its trade's step.
MASK_TRADE = 0xea010310
MASK_TRADE_WAS, MASK_TRADE_NOW = "NotReady", "Complete"


def enum_default(data, key=MASK_TRADE, was=MASK_TRADE_WAS, now=MASK_TRADE_NOW):
    """The game's list of flags with the enum of hash `key` starting a new game at `now` (one of its values) in place of
    `was`: the new bytes (the same size). ValueError: not the file, no such enum, `now` not one of its values, or it
    does not start at `was` (made already, or not the list this was written for)."""
    if data[:2] != b"BY":
        raise ValueError("not a big-endian BYML (%r)" % data[:4])
    key_at, str_at, root = struct.unpack_from(">III", data, 4)
    count = lambda at: int.from_bytes(data[at + 1:at + 4], "big")
    u32 = lambda at: struct.unpack_from(">I", data, at)[0]
    keys = [data[key_at + u32(key_at + 4 + 4 * k):data.index(b"\0", key_at + u32(key_at + 4 + 4 * k))].decode("utf-8", "replace")
            for k in range(count(key_at))]

    def fields(at):
        if data[at] != 0xC1:
            raise ValueError("no dictionary at %#x" % at)
        return {keys[int.from_bytes(data[at + 4 + 8 * k:at + 7 + 8 * k], "big")]: (data[at + 7 + 8 * k], u32(at + 8 + 8 * k), at + 8 + 8 * k)
                for k in range(count(at))}

    def items(at):
        if data[at] != 0xC0:
            raise ValueError("no array at %#x" % at)
        n = count(at)
        return [(data[at + 4 + i], u32(at + 4 + (n + 3 & ~3) + 4 * i)) for i in range(n)]
    enums = items(fields(fields(root)["Data"][1])["Enum"][1])
    mine = [f for f in (fields(at) for t, at in enums if t == 0xC1) if f.get("Hash", (0, None))[1] == key]
    if len(mine) != 1:
        raise ValueError("the list has %d enums of hash %#x" % (len(mine), key))
    f = mine[0]
    values = [struct.unpack_from(">Q", data, v)[0] if t == 0xD5 else None for t, v in items(f["Values"][1])]
    if murmur3(now.encode()) not in values:
        raise ValueError("%s is not a value of the enum %#x" % (now, key))
    kind, value, where = f["DefaultValue"]
    if kind != 0xD3 or value != murmur3(was.encode()):
        raise ValueError("the enum %#x does not start at %s (made already?)" % (key, was))
    out = bytearray(data)
    struct.pack_into(">I", out, where, murmur3(now.encode()))
    return bytes(out)


def ainb_exp_swap(data, old=BOMBCHU_QUEST, new=ALWAYS_EXP):
    """An AI file (AIB, version 0x408) whose one reading of the flag `old` reads `new`: the new name put at the end of
    its strings (the file's last part: a string is its place there) and the reading's place of the name changed. The new
    bytes. ValueError: not such a file, or the name not there once, or read in more than one place."""
    u32 = lambda at: struct.unpack_from("<I", data, at)[0]
    if data[:4] != b"AIB " or u32(4) != 0x408:
        raise ValueError("not an AI file of the version this was written for")
    pool = u32(0x24)
    name = old.encode() + b"\0"
    places = [i for i in range(pool, len(data)) if data.startswith(name, i) and (i == pool or data[i - 1] == 0)]
    if len(places) != 1 or new.encode() + b"\0" in data:
        raise ValueError("the file has %s %d times (or %s already)" % (old, len(places), new))
    off = places[0] - pool
    refs = [at for at in range(0x74, pool - 3, 4) if u32(at) == off]
    if len(refs) != 1:
        raise ValueError("%s is read in %d places, not one" % (old, len(refs)))
    out = bytearray(data)
    struct.pack_into("<I", out, refs[0], len(data) - pool)
    return bytes(out + new.encode() + b"\0")


def flow_switch_yes(data, event, query="EventQueryIsGameDataBoolExp", flag=BOMBCHU_QUEST):
    """A talk flow (BFEVFL) whose question `event` (a `query` of `flag`, its answers 0 and 1) goes on to its "yes" (0:
    a true/false question's answer 0 is its true one, seen in the Bazaar man's lines here) either way: the new bytes,
    of the same size. ValueError: not such a file, or the step not the one written for."""
    steps = scene_steps(data)[0]
    u16 = lambda at: struct.unpack_from("<H", data, at)[0]
    u64 = lambda at: struct.unpack_from("<Q", data, at)[0]
    named = [s for s in steps if data[u64(s["at"]) + 2:u64(s["at"]) + 2 + u16(u64(s["at"]))] == event.encode()]
    if len(named) != 1 or named[0]["kind"] != 1 or named[0]["what"] != query or data.count(flag.encode()) != 1:
        raise ValueError("%s is not the question of %s this was written for" % (event, flag))
    e = named[0]["at"]
    cases = u64(e + 0x18)
    if u16(e + 0x0a) != 2 or [struct.unpack_from("<I", data, cases + 8 * k)[0] for k in (0, 1)] != [0, 1]:
        raise ValueError("%s does not have the answers 0 and 1" % event)
    out = bytearray(data)
    out[cases + 12:cases + 14] = data[cases + 4:cases + 6]   # (answer 1's next step: answer 0's)
    return bytes(out)


def baked_climb_hook(data):
    """A static compound (.bphsc, unpacked) whose untagged AirWall (CLIMB_WALL_ENTRY of its material table: 16 bytes each,
    u32 material, u32 sub-material, u64 shape tags, from the u32 at +0x20 to the one at +0x24) carries StickHookshot
    (BAKED_TREE_FILES): the bytes changed in place. ValueError: not a Phive file, or that entry not an untagged AirWall."""
    if data[:6] != b"Phive" + bytes(1):
        raise ValueError("not a Phive file")
    at, end = struct.unpack_from("<II", data, 0x20)
    if (end - at) % 16 or end > len(data) or at + 16 * (CLIMB_WALL_ENTRY + 1) > end:
        raise ValueError("its material table is not whole")
    e = at + 16 * CLIMB_WALL_ENTRY
    if struct.unpack_from("<IIQ", data, e) != (MATERIAL_AIRWALL, 0, 0):
        raise ValueError("its entry %d is %r, not an untagged AirWall" % (CLIMB_WALL_ENTRY, struct.unpack_from("<IIQ", data, e)))
    out = bytearray(data)
    struct.pack_into("<Q", out, e + 8, TAG_STICK_HOOKSHOT)
    return bytes(out)


def water_wall_out(data, wall=WATER_WALL, keep=False):
    """The adult's Hyrule Field map file without the invisible wall over the Water Temple's gate switch (WATER_WALL), or
    another wall (its Gyaml, the flag its Presence waits for): the file written anew. keep: the wall stays, there always
    (its Presence taken away: TREE_WALL). ValueError: not one such wall in it."""
    tree, version = byml_parse(data)
    actors = tree[1].get("Actors")
    if not actors or actors[0] != "array":
        raise ValueError("the map file has no actors")
    walls = [a for a in actors[1] if a[1].get("Gyaml", ("", ""))[1] == wall[0] and a[1].get("Presence", ("", {}))[0] == "dict"
             and a[1]["Presence"][1].get("FlagName", ("", ""))[1] == wall[1]]
    if len(walls) != 1:
        raise ValueError("%d walls %s by %s in it, not 1" % (len(walls), wall[0], wall[1]))
    if keep:
        del walls[0][1]["Presence"]
    else:
        tree[1]["Actors"] = ("array", [a for a in actors[1] if a is not walls[0]])
    return byml_build(tree, version)



# With Skip cutscenes, the Fire Temple's jailed Gorons are gone (the other randomizer's change, OOTRR 97e343a, always on
# there). Eight of the nine sit in front of a small key's chest that stays locked until Link talks to the Goron and
# watches him leave (Dm_FireTemple_0020). Each Goron's room logic deletes him and the invisible wall before him by one
# OR (his "_FireTemple_Delete" flag or the Fire quest done): both those Logic_Delete inputs are made a fixed true. Each
# chest's logic unlocks it by the Goron's "_Delete" flag: its Unlock is made a fixed true. The cells still open by their
# own switches, so the rules do not change. No flag: it works on any save.
FIRE_GORONS = tuple("Logic/FireTemple_Level_Room_%s.logic.module.ainb" % r for r in (
    "02_Prefab_f1d5", "04_Prefab_c7fa", "05_Prefab_812f", "10_Prefab_1fcc", "11_Prefab_6c9c", "17_Prefab_68e8",
    "20_Prefab_4850", "22_Prefab_f820", "23_Prefab_612a"))
# The Forest Temple's Bow room (its room 17, logic prefab Room_06 6b8c; the other randomizer's fix, OOTRR 7146d21, read
# again in our file 2026-11-22). Entering from the Red Poe room locks the barred door behind Link (the shutter's
# LockMinusZ, from an OR) until the eye switch above it is shot, and the eye answers only once the Stalfos are dead and
# the chest has appeared; only arrows hit it. With the Bow shuffled out of that chest, Link was shut in (FIXES only let
# him warp out). The lock's OR reads the eye switch's focus (Gimmick_FocusOnGimmick_Basic_ff0d), which starts from an AND
# of the eye and "the Stalfos cleared": the OR now reads that second input itself, as the Lower Stalfos room opens its
# door. The eye switch still works. Every seed (bow_room_fix)
BOW_ROOM_LOGIC = "Logic/ForestTemple_Level_Room_06_Prefab_6b8c.logic.module.ainb"
BOW_ROOM_NAMES = ("Gimmick_FocusOnGimmick_Basic_ff0d.logic.module", "ActorLogicBootUpActorIsFirstOnEventTrigger")


def bow_room_fix(data):
    """The Bow room's logic (BOW_ROOM_LOGIC) with the lock's multi-input entry that reads the eye switch's focus made to
    read the focus's other condition, the Stalfos cleared: the new bytes, of the same size. A two-input gate's inputs are a
    pair of 8-byte entries (the node | its output << 16, flags) in the multi-input table (the header's +0x38 to +0x30), as
    in water_switch_no_boots. ValueError: not the file known (one entry reads the focus, one the eye, the eye's partner
    neither of them)."""
    u32 = lambda at: struct.unpack_from("<I", data, at)[0]
    if data[:4] != b"AIB " or u32(4) != 0x408:
        raise ValueError("not an AI file of version 0x408")
    pool = u32(0x24)
    name = lambda at: data[pool + at:data.index(b"\0", pool + at)]
    nodes = u32(0x10)
    named = lambda what: [i for i in range(nodes) if name(u32(0x74 + 0x3C * i + 8)) == what.encode()]
    focus, eye = named(BOW_ROOM_NAMES[0]), named(BOW_ROOM_NAMES[1])
    if len(focus) != 1 or len(eye) != 1:
        raise ValueError("%d eye switch focuses and %d eye switches in the Bow room, not 1 each" % (len(focus), len(eye)))
    start, end = u32(0x38), u32(0x30)
    entries = [(k, u32(start + 8 * k) & 0xffff) for k in range((end - start) // 8)]
    to_focus = [k for k, node in entries if node == focus[0]]
    to_eye = [k for k, node in entries if node == eye[0]]
    if len(to_focus) != 1 or len(to_eye) != 1:
        raise ValueError("the focus is read %d times and the eye %d times, not once each" % (len(to_focus), len(to_eye)))
    partner = to_eye[0] ^ 1
    if partner * 8 >= end - start or entries[partner][1] in (focus[0], eye[0]):
        raise ValueError("the eye's gate does not pair it with another condition")
    out = bytearray(data)
    at, frm = start + 8 * to_focus[0], start + 8 * partner
    out[at:at + 4] = data[frm:frm + 4]
    return bytes(out)


# Goron City's sign-order grotto (bug 127, the owner's run 2026-11-23: one wrong try, and the right order after gave no
# chest). Its logic (SIGN_GROTTO_LOGIC: six signboards, two chests that appear) lets the right chest appear when the right
# signs are cut AND node 31 is false, node 31 being OR(node 28, the saved _clear): node 28 is OR(clear_InLocalScene,
# faild_InLocalScene). A wrong try sets faild_InLocalScene, which is not saved but lasts while Link is in Goron City (the
# grotto is part of its scene), so the right chest could not come until he left. (The saved _OutOfService the wrong chest
# sets is read by nothing that gates a chest.) sign_grotto_fix makes node 31's first input node 26's output 0 (the
# clear_InLocalScene reader) instead of node 28's: a wrong try no longer holds the right chest back; the wrong chest's
# own gate is as it was. Found by the agent's reading of the file, 2026-11-23. Every seed (fixes 80).
SIGN_GROTTO_LOGIC = "Logic/HidingHole_Level_Hole_17_Prefab_e58a.logic.module.ainb"


def sign_grotto_fix(data):
    """The sign-order grotto's logic (SIGN_GROTTO_LOGIC) with node 31's first input (multi-input entry 28) reading node
    26's output 0 in place of node 28's output 1: the new bytes, of the same size. ValueError: not the file known."""
    u32 = lambda at: struct.unpack_from("<I", data, at)[0]
    if data[:4] != b"AIB " or u32(4) != 0x408:
        raise ValueError("not an AI file of version 0x408")
    pool = u32(0x24)
    kind = lambda i: data[pool + u32(0x74 + 0x3C * i + 8):data.index(b"\0", pool + u32(0x74 + 0x3C * i + 8))]
    if u32(0x10) <= 31 or [kind(i) for i in (10, 26, 27, 28, 31)] != [b"HoldGameDataGetBoolSimple"] * 3 + [b"OperateOR"] * 2:
        raise ValueError("not the nodes this was written for")
    start, end = u32(0x38), u32(0x30)
    if end - start < 8 * 30 or u32(start + 8 * 28) != 28 | 1 << 16 or u32(start + 8 * 29) != 10:
        raise ValueError("node 31's inputs are not node 28's and node 10's (made already?)")
    out = bytearray(data)
    struct.pack_into("<I", out, start + 8 * 28, 26)
    return bytes(out)


FIRE_CHESTS = tuple("Logic/FireTemple_Level_Room_%s.logic.module.ainb" % r for r in (
    "02_Prefab_3004", "04_Prefab_d826", "05_Prefab_5b8f", "10_Prefab_b3bc", "11_Prefab_c20f", "20_Prefab_7421",
    "22_Prefab_e0c9", "23_Prefab_efdf",
    # (and Room 17's big chest, the Boss Key's (Obj_TBox_A_03_30dc): its Unlock is an AND of its Goron's
    #  Npc_Goron_010_Delete and Link in its area, so with the Goron gone it stayed locked and the temple could not be
    #  finished. The other randomizer found it, OOTRR 7146d21, 2026-11-22)
    "17_Prefab_a4ce"))


def ainb_fix_inputs(data, input_name, node_class, count, value=1):
    """A logic file (AIB, version 0x408) whose `count` linked inputs named `input_name` (all from one node's same output,
    and the file with one node of `node_class`) are made the fixed `value`, as the file's own unlinked inputs are (node
    0xffff, flags 0x01800000): the new bytes, of the same size. An input is 16 bytes in the inputs' part (from the
    header's +0x34 to the strings): its name's place, the node | its output << 16, flags, its value. ValueError: not
    such a file."""
    u32 = lambda at: struct.unpack_from("<I", data, at)[0]
    if data[:4] != b"AIB " or u32(4) != 0x408:
        raise ValueError("not an AI file of version 0x408")
    pool = u32(0x24)
    name = lambda off: data[pool + off:data.index(b"\0", pool + off)] if 0 < off < len(data) - pool else b""
    if [name(u32(0x74 + 0x3C * i + 8)) for i in range(u32(0x10))].count(node_class.encode()) != 1:
        raise ValueError("not one %s in it" % node_class)
    hits = [at for at in range(u32(0x34), pool - 16, 4) if name(u32(at)) == input_name.encode() and u32(at + 4) & 0xFFFF != 0xFFFF]
    if len(hits) != count or len({u32(at + 4) for at in hits}) != 1:
        raise ValueError("%d linked %s inputs (from %d places), not %d from one" % (len(hits), input_name, len({u32(at + 4) for at in hits}), count))
    out = bytearray(data)
    for at in hits:
        struct.pack_into("<III", out, at + 4, 0xFFFF, 0x01800000, value)
    return bytes(out)

# The cucco lady's game wants one cucco (asked 2026-11-17, every seed from fixes 43). Her pen's logic
# (CUCCO_LOGIC) compares the count in the pen with a fixed 7 (an OperateCompareInt's unlinked Int_A, its one fixed
# number), and her flow (CUCCO_FLOW) counts "how many are left" from 7 for her lines (Captured_Npc_Hylia_CalcRemainCount
# sets Npc_Hylia_049_Child_HowManyCuccos to 7 and takes the pen's count from it; a question asks whether it is still 7,
# none caught). All three 7s are made 1. Not seen in play yet.
CUCCO_LOGIC = "Logic/MiniGame_CatchCucco_c69b.logic.module.ainb"
CUCCO_FLOW = "Event/EventFlow/Minigame_CatchCucco.bfevfl.zs"
CUCCO_COUNT = "Npc_Hylia_049_Child_HowManyCuccos"
CUCCOS = 1


def cucco_logic_one(data, want=CUCCOS):
    """The cucco pen's logic (CUCCO_LOGIC) with its fixed 7 made `want`: the new bytes, of the same size. An input
    is 16 bytes (its name's place, the node it takes (0xffff: none), flags, its value). ValueError: not the file."""
    u32 = lambda at: struct.unpack_from("<I", data, at)[0]
    if data[:4] != b"AIB " or u32(4) != 0x408 or b"MiniGame_CatchCucco_InFenceCount" not in data:
        raise ValueError("not the cucco pen's AI file this was written for")
    pool = u32(0x24)
    name = lambda off: data[pool + off:].split(bytes(1))[0] if 0 < off < len(data) - pool else b""
    hits = [at for at in range(0x74, pool - 16, 4) if name(u32(at)) == b"Int_A" and u32(at + 4) & 0xFFFF == 0xFFFF and
            u32(at + 8) == 0x01800000 and u32(at + 12) == 7]
    if len(hits) != 1:
        raise ValueError("%d fixed 7s where one was expected" % len(hits))
    out = bytearray(data)
    struct.pack_into("<i", out, hits[0] + 12, want)
    return bytes(out)


# ---- Deku Scrubs, On, 10 rupees each (rando_scrubs 2, asked for 2026-11-17 with the scrubs' menus) ----
# Each of the four one-time sales (SCRUBS) is a call of SimpleShopSub_Scrub_Business_OneTime with its item and its
# Price, a number the scrub's line says by a tag ("It's <price> rupees"): so the price is set in the call, in place,
# for every call of the sale's entry point that names its item (both sizes of an upgrade). It moves no item: the
# stamp's second line (QOL_STAMP). NOT SEEN IN PLAY.
SCRUB_CHEAP = 10


def scrub_prices(data, sales, price=SCRUB_CHEAP):
    """The Business Scrubs' flow (SCRUB_FLOW) with the Price of each call that is one of `sales` ({(entry point, the
    item it names)}) made `price`: (the new bytes, of the same size; the sales found). ValueError: not a flow file."""
    u16 = lambda at: struct.unpack_from("<H", data, at)[0]
    u64 = lambda at: struct.unpack_from("<Q", data, at)[0]
    if data[:6] != b"BFEVFL" or u16(0x20) != 1:
        raise ValueError("not an event flow file of one flowchart")
    chart = u64(u64(0x28))
    count, events = u16(chart + 0x16), u64(chart + 0x30)
    text = lambda ptr: bytes(data[ptr + 2:ptr + 2 + u16(ptr)]).decode("utf-8", "replace") if 0 < ptr < len(data) - 2 else ""
    reach = {entry: flow_reach(data, entry) for entry in {entry for entry, _ in sales}}
    out, found = bytearray(data), set()
    for i in range(count):
        e = events + 0x30 * i
        params = u64(e + 0x10)
        if data[e + 8] != 4 or not params or data[params] != 1:
            continue
        keys = u64(params + 8)
        got = {text(u64(keys + 8 + 16 * (k + 1) + 8)): u64(params + 0x10 + 8 * k) for k in range(u16(params + 2))} if keys else {}
        name, cost = got.get("ActorName"), got.get("Price")
        if name is None or cost is None or data[name] != 5 or data[cost] != 2:
            continue
        for entry, item in sales:
            if i in reach[entry] and text(u64(name + 0x10)) == item:
                struct.pack_into("<i", out, cost + 0x10, price)
                found.add((entry, item))
    return bytes(out), found


# ---- Items of our own (custom items), first the magic meter (asked for 2026-11-19) ----
# A new item is an actor of its own name whose actor file has an item of the game's as its parent ($parent: every part
# inherited) and names only what differs, as the shops' shelf actors are made (shop_pack): a copy of a whole actor file
# under another name stopped the game as it was made (the Pieces of Heart's try, 2026-11-19). Its pack is its parent's
# pack with that file added; it has a row in each of the game's three lists of actors (custom_rows), its parent's with
# its own name and the fields given; and its words (CUSTOM_WORDS' labels in ActorMsg/PouchContent).
def custom_pack(name, parent, parent_pack, components=None):
    """The pack of an item of our own: (its bytes, the files no other pack has). parent: the game's item it is made
    from (its pack: parent_pack's bytes); components: {a part's name: its file reference} that differ from the parent's."""
    files = collections.OrderedDict(sarc_read(parent_pack))
    if ACTOR_FILE % parent not in files:
        raise ValueError("%s: its pack has no actor of that name" % parent)
    _, version = byml_parse(files[ACTOR_FILE % parent])
    comps = collections.OrderedDict(sorted((k, ("string", v)) for k, v in (components or {}).items()))
    files[ACTOR_FILE % name] = byml_build(("dict", collections.OrderedDict((("$parent", ("string", ACTOR_REF % parent)),
                                                                           ("Components", ("dict", comps))))), version)
    return sarc_write(files), [ACTOR_FILE % name]


def custom_rows(data, kind, name, parent, fields=None):
    """One of the game's three lists of actors (kind: SHOP_TABLES) with a row for an item of our own: its parent's,
    its id its own name, and `fields` ({field: a BYML value}, None to take one out) changed"""
    tree, version = byml_parse(data)
    by = {r[1]["__RowId"][1]: r for r in tree[1]}
    if parent not in by:
        raise ValueError("the game's %s has no row of %s" % (kind, parent))
    row = collections.OrderedDict(by[parent][1])
    for k, v in (fields or {}).items():
        if v is None:
            row.pop(k, None)
        else:
            row[k] = v
    row["__RowId"] = ("string", name)
    row = ("dict", collections.OrderedDict(sorted(row.items())))
    rows = [r for r in tree[1] if r[1]["__RowId"][1] != name] + [row]
    rows.sort(key=lambda r: r[1]["__RowId"][1])
    return byml_build((tree[0], rows), version)


CUSTOM_WORDS = ("_Name", "_Caption", "_GetMessage", "_GetCaption")
CUSTOM_TEXT = SHOP_TEXT   # (in each language's archive, Mals/*.sarc.zs: SHOP_TEXT)
MAGIC_ITEM = "Item_MagicMeter"   # (the first magic meter: the doubled magic's gift as its parent, 24 magic)
MAGIC_PARENT = "Item_FairyBless_MPDouble"
MAGIC_WORDS = {"_Name": "Magic Power", "_Caption": "Proof of a Great Fairy's blessing, this gift grants you magic power.",
               "_GetMessage": "You got magic power!", "_GetCaption": "You can now use magic!"}


# ---- Magic and the fairies' gifts (rando_magic, asked for 2026-11-19) ----
# In the remake the magic meter is no fairy's: every item that uses magic (the Lens of Truth, the spells, the magic arrows,
# even the Bow with its arrows) and the spin attack's gift raise PlayerStatus.MPMax to 24 as they are got (the list of
# pouch actors' ExpansionAvility MPMaxUP, MPMax 24), the doubled magic's gift to 48. With the setting:
# - those marks are taken out of every row but the doubled magic's (MAGIC_FREE): no item gives magic by itself;
# - magic is the doubled magic's gift twice in the pool (a blue rupee's chest the second's): found with no meter, the
#   game's side gives it as MAGIC_ITEM, an item of our own (custom_pack: its parent the doubled magic's gift, its own
#   words), and sets the meter to 24 (host/hos_main.c oot_magic_give); found with the meter, it is the gift: 48;
# - the Great Fairies of the improved spin (Hyrule Castle, A_01), the doubled magic (the crater, A_04) and the halved
#   damage (outside Ganon's Castle, A_06) are gifts of the shuffle as the spells' are (MAGIC_GIFTS, FAIRY_GIFTS' way);
# - the rules ask for magic wherever they ask for the Lens of Truth, and Ganon's Castle asks for everything.
# Needs Quest rewards (the fairies' way). NOT SEEN IN PLAY as a whole.
MAGIC_DOUBLE, MAGIC_SPIN, MAGIC_DEFENSE = "Item_FairyBless_MPDouble", "Item_FairyBless_MP", "Item_FairyBless_DefenseDouble"
MAGIC_KEEP = ("Item_FairyBless_MPDouble", "Pouch_FairyBless_MPDouble")
MAGIC_JUNK = "TBox_Rupee_Blue"   # (the chest item the second magic takes the place of)
# (the owner's run 2026-11-23: the Great Fairy outside Ganon's Castle asked for everything, the Zora Tunic among it; her
#  fountain is behind a pillar the Golden Gauntlets lift, an adult's.) From COURAGE_FROM she asks for that alone.
COURAGE_FROM = 26

# A check that is there only for a while (bug 131, the owner's word 2026-11-23: "put junk in them since its only
# available for a limited time and sometimes never available if you complete shadow temple before getting nocturne
# check"): the chest on Kakariko's windmill in the rainy village (KakarikoVillage_Adult_Alternative, from the Nocturne
# scene until the Shadow Temple is done), the one check in that map's files alone, holds junk only (rupees and ammo,
# junk_holds); the normal village's copy (#2) takes part as any chest.
RAINY_FROM = 27
RAINY_ONLY = (0xb588e3f93990af69,)
# (and a check that can't be reached at all, junk only the same way: Gerudo Valley's Song of Storms grotto has a child's
#  copy of its invisible chest (red rupee #2), and a child can't come there, the owner's word 2026-11-23: a slip of the
#  remake's makers)
JUNK_ONLY = RAINY_ONLY + (0x561cbe4b374f3739,)


def junk_holds(item):
    """whether a check there only for a while may hold this item (RAINY_FROM): rupees and ammo, nothing the logic needs"""
    return item not in PROGRESSION and item != TOKEN and (item.startswith("TBox_Rupee_") or "Bundle" in item)
COURAGE_NEED = ADULT | {GG}
MAGIC_GIFTS = (
    Gift("fairy_power", "Dm_FairyFountain_Power", (MAGIC_SPIN,), MAGIC_SPIN, "HyruleCastle",
         "the Great Fairy of Hyrule Castle", CHILD | {BB}, "magic"),
    Gift("fairy_wisdom", "Dm_FairyFountain_Wisdom", (MAGIC_DOUBLE,), MAGIC_DOUBLE, "DeathMountainCrater",
         "the Great Fairy of Death Mountain Crater", GROWN | {HAM}, "magic"),
    Gift("fairy_courage", "Dm_FairyFountain_Courage", (MAGIC_DEFENSE,), MAGIC_DEFENSE, "GanonCastle",
         "the Great Fairy outside Ganon's Castle", EVERYTHING, "magic"),
)


def magic_free(data):
    """The list of pouch actors (PouchActorInfo) with the magic mark (ExpansionAvility MPMaxUP, MPMax) taken out of
    every row but MAGIC_KEEP's: (the new bytes, how many rows were changed)"""
    tree, version = byml_parse(data)
    done = 0
    for row in tree[1]:
        fields = row[1]
        if fields["__RowId"][1] in MAGIC_KEEP:
            continue
        if fields.get("ExpansionAvility", ("", ""))[1] == "MPMaxUP" or "MPMax" in fields:
            fields.pop("ExpansionAvility", None)
            fields.pop("MPMax", None)
            done += 1
    return byml_build(tree, version), done


def magic_need(need):
    """a rule with magic named where it names the Lens of Truth (rando_magic)"""
    return frozenset(need | {MAGIC_DOUBLE}) if LENS in need else need


def cucco_flow_one(data, want=CUCCOS):
    """The cucco lady's flow (CUCCO_FLOW) with its count of 7 cuccos made `want` (the set and the question of
    CUCCO_COUNT): the new bytes, of the same size. ValueError: not the file, or not two such steps."""
    u16 = lambda at: struct.unpack_from("<H", data, at)[0]
    u64 = lambda at: struct.unpack_from("<Q", data, at)[0]
    if data[:6] != b"BFEVFL" or u16(0x20) != 1:
        raise ValueError("not an event flow file of one flowchart")
    chart = u64(u64(0x28))
    count, events = u16(chart + 0x16), u64(chart + 0x30)
    text = lambda ptr: bytes(data[ptr + 2:ptr + 2 + u16(ptr)]).decode("utf-8", "replace") if 0 < ptr < len(data) - 2 else ""

    def items(at):   # (a step's parameters: {name: the place of its value's record})
        keys = u64(at + 8) if at else 0
        return {text(u64(keys + 8 + 16 * (k + 1) + 8)): u64(at + 0x10 + 8 * k) for k in range(u16(at + 2) if at and keys else 0)}
    out, done = bytearray(data), 0
    for i in range(count):
        e = events + 0x30 * i
        if data[e + 8] not in (0, 1):
            continue
        got = items(u64(e + 0x10))
        name, value = got.get("GameDataName"), got.get("Value")
        if name is None or value is None or data[name] not in (0, 5) or text(u64(name + 0x10)) != CUCCO_COUNT or data[value] != 2:
            continue
        if struct.unpack_from("<i", data, value + 0x10)[0] != 7:
            raise ValueError("a step of %s whose value is not 7" % CUCCO_COUNT)
        struct.pack_into("<i", out, value + 0x10, want)
        done += 1
    if done != 2:
        raise ValueError("%d steps of %s where two were expected" % (done, CUCCO_COUNT))
    return bytes(out)


# ---- Epona by Epona's Song (rando_epona_song, asked 2026-11-21, bugs.md 98) ----
# Owning a horse is not a flag: only EventCopyAndRegisterOwnedHorse on an Epona actor writes it (Get_Epona's ranch
# escape, its _Warp entries), and Epona's Song (EPONA_SONG_FLOW) only calls an owned horse: an adult without one is
# answered by the ranch's horses inside its fence and by nothing elsewhere. With this setting the song's question
# "does Link own a horse?" sends "no", where riding is allowed, to a step that starts an event of our own (EPONA_OWN,
# as the ocarina event starts Pierre's: EventSystemActor.EventTransition) and then on to the song's own "yes" (it calls
# the horse). The event makes an Epona (EventMemberCreateMethod 1: no flow of the game makes a horse, NPCs and props
# are made this way), registers her as the escape does, takes her off stage, moves the Epona quest to Complete and sets
# the escape's Skullchild_JustAfterGetEpona, as the escape does: Ingo then talks as after the escape, and Talon leaves
# Kakariko (the adult trade's Pocket Cucco waits on him). Always, the lesson had or not: Malon's lesson (a check) still
# plays for young Link with the quest Complete (the owner's test, bugs.md 52); holding the quest back until the lesson
# left Ingo and Talon as before the races (the owner's run, 2026-11-21). The event is listed in
# the event tables (EVENT_TABLES) from Pierre's rows, and among the ocarina event's child events as his is.
# The idea is REALAZK's OOTRR (randomizer/core/src/open_world/skips.rs, GPL-3.0-or-later, untested there); the steps
# and their settings are the game's own (Get_Epona's escape, Dm_SY_Ocarina's Pierre). Flow files are written with
# evfl (tools/rando/evfl, leoetlino, GPL-2.0-or-later). Moves no item. SEEN IN PLAY 2026-11-21 (the owner: Epona, Ingo, the trade, the lesson); it took Skip Ingo's races' place.
EPONA_SONG_FLOW = "Event/EventFlow/Dm_SY_Ocarina_EponaSong.bfevfl.zs"
EPONA_OWN = "WillowEponaOwn"
EPONA_OWN_FLOW = "Event/EventFlow/%s.bfevfl.zs" % EPONA_OWN
EVENT_TABLES = ("RSDB/EventSetting.Product.111.rstbl.byml.zs", "RSDB/GameAnalyzedEventInfo.Product.111.rstbl.byml.zs")
EPONA_TEMPLATE = "AppearPierre_ByScarecrowSong"   # (the rows copied: a flowchart event the ocarina event starts)


def evfl_module():
    """the evfl library kept beside this file (tools/rando/evfl; -I leaves this folder off the path)"""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import evfl
    return evfl


def epona_song_flows(song_raw):
    """(Epona's Song's flow with the unowned answer sent to EPONA_OWN, the new event's flow) as bytes, from the game's
    EPONA_SONG_FLOW unpacked. ValueError: the song's flow is not the one this was written for."""
    import copy
    import io
    evfl = evfl_module()

    def holder(actor, name, kind="actions"):
        got = [h for h in getattr(actor, kind) if h.v == name]
        if got:
            return got[0]
        h = evfl.common.StringHolder(name)
        getattr(actor, kind).append(h)
        return h

    def container(**items):
        c = evfl.Container()
        c.data.update(items)
        return c

    def action(name, actor, act, params, nxt=None):
        e = evfl.Event()
        e.name = name
        e.data = evfl.ActionEvent()
        e.data.actor.v, e.data.actor_action.v, e.data.params = actor, holder(actor, act), params
        e.data.nxt.v = nxt
        return e

    def switch(name, actor, query, params, cases):
        e = evfl.Event()
        e.name = name
        e.data = evfl.SwitchEvent()
        e.data.actor.v, e.data.actor_query.v, e.data.params = actor, holder(actor, query, "queries"), params
        for value, to in cases.items():
            e.data.cases[value] = evfl.util.RequiredIndex()
            e.data.cases[value].v = to
        return e

    song = evfl.EventFlow()
    song.read(song_raw)
    fc = song.flowchart
    if fc is None or fc.name != "Dm_SY_Ocarina_EponaSong" or any(e.name.startswith("WillowEpona") for e in fc.events):
        raise ValueError("not the game's Epona's Song flow, or already changed")
    asks = [e for e in fc.events if isinstance(e.data, evfl.SwitchEvent) and e.data.actor_query.v.v == "EventQueryHasOwnedHorse"
            and set(e.data.cases) == {0, 1}]
    if len(asks) != 1:
        raise ValueError("not one question of an owned horse with both answers")
    ask = asks[0]
    owned, unowned = ask.data.cases[0].v, ask.data.cases[1].v
    if not isinstance(owned.data, evfl.SwitchEvent) or owned.data.actor_query.v.v != "EventQueryIsCurrentSceneEnableRide":
        raise ValueError("the owned horse's way does not start by asking whether riding is allowed here")
    base = fc.actors[0].params
    mover = [a for a in fc.actors if a.identifier.name == "EventSystemActor" and not a.identifier.sub_name]
    if not mover:
        a = evfl.Actor()
        a.identifier = evfl.ActorIdentifier("EventSystemActor")
        a.params = copy.deepcopy(base)
        a.params.data["EventMemberCreateMethod"] = 0
        a.concurrent_clips = fc.actors[0].concurrent_clips
        fc.actors.append(a)
        mover = [a]
    start = action("WillowEpona1", mover[0], "EventTransition",
                   container(EventName=EPONA_OWN, IsWaitEnd=True, SpecialEventActionType=1, FadeInTypeEventEnd=0), owned)
    ride = switch("WillowEpona0", owned.data.actor.v, "EventQueryIsCurrentSceneEnableRide", copy.deepcopy(owned.data.params),
                  {0: start, 1: unowned})
    # (and each time she is called: the quest to Complete, a quest done already left as it is. A save that had her by
    #  the song before this event finished the quest (the lesson first, 2026-11-21) is put right by the next call)
    gd = [a for a in fc.actors if a.identifier.name == "GameDataActor" and not a.identifier.sub_name]
    if not gd:
        raise ValueError("the song's flow has no GameDataActor to copy")
    quest = evfl.Actor()
    quest.identifier = evfl.ActorIdentifier("ChallengeSystemActor")
    quest.params = copy.deepcopy(gd[0].params)
    quest.params.data["EventMemberCreateMethod"] = 0
    quest.concurrent_clips = gd[0].concurrent_clips
    fc.actors.append(quest)
    finish = action("WillowEpona2", quest, "EventExecuteProgressChallengeStep",
                    container(ChallengeName="Get_Epona", IsWaitEnd=True, IsIgnoreCompletedChallenge=True, StepName="Complete",
                              IsIgnoreChallengeProgressUI=True), owned)
    fc.events += [ride, start, finish]
    ask.data.cases[1].v = ride
    ask.data.cases[0].v = finish
    start.data.nxt.v = finish
    out = io.BytesIO()
    song.write(out)
    song_new = out.getvalue()

    # ---- the new event: its own flowchart in a copy of the song's file ----
    own = evfl.EventFlow()
    own.read(song_raw)
    own.name = EPONA_OWN
    f = own.flowchart
    f.name = EPONA_OWN
    like = {a.identifier.name: a for a in f.actors if not a.identifier.sub_name}
    if "GameDataActor" not in like:
        raise ValueError("the song's flow has no GameDataActor to copy")
    plain = copy.deepcopy(like["GameDataActor"].params)

    def member(name, **extra):
        a = evfl.Actor()
        a.identifier = evfl.ActorIdentifier(name)
        a.params = copy.deepcopy(plain)
        a.params.data.update(extra)
        a.concurrent_clips = like["GameDataActor"].concurrent_clips
        return a
    # (an Epona the event makes: the member settings Get_Epona gives the ranch's Epona, made by the event)
    epona = member("Animal_Epona_Adult", EventMemberCreateMethod=1)
    for slot in ("Weapon", "SubWeapon", "Shield", "Bow"):
        epona.params.data["EquipmentUser_%s" % slot] = ""
        epona.params.data["EquipmentUser_%s_EquipmentState" % slot] = 0
    for slot in ("Tool", "SubTool", "Accessory1", "Accessory2", "Accessory3", "Accessory4"):
        epona.params.data["EquipmentUser_%s" % slot] = ""
    data, quest = member("GameDataActor", EventMemberCreateMethod=0), member("ChallengeSystemActor", EventMemberCreateMethod=0)
    f.actors = [epona, data, quest]
    flag = action("WillowEponaOwn4", data, "EventTriggerSetGameDataBool",
                  container(Value=True, Index=-1, GameDataName="Skullchild_JustAfterGetEpona"))
    done = action("WillowEponaOwn3", quest, "EventExecuteProgressChallengeStep",
                  container(ChallengeName="Get_Epona", IsWaitEnd=True, IsIgnoreCompletedChallenge=False, StepName="Complete",
                            IsIgnoreChallengeProgressUI=False), flag)
    off = action("WillowEponaOwn1", epona, "EventGoOffstageForUser",
                 container(IsWaitEnd=True, IsSleepXLink=True, ExecuteSetSpeedZeroEveryFrame=False, IsRidingTargetGoOffstage=False), done)
    reg = action("WillowEponaOwn0", epona, "EventCopyAndRegisterOwnedHorse", container(IsWaitEnd=True), off)
    f.events = [reg, off, done, flag]
    entry = evfl.EntryPoint(EPONA_OWN)
    entry.main_event.v = reg
    f.entry_points = [entry]
    out = io.BytesIO()
    own.write(out)
    return song_new, out.getvalue()


# ---- Gifts kept when a quest is moved on first (the other randomizer's quest order, OOTRR 92dbffd, 2026-11-22 survey) ----
# Two shuffled gifts are given only while their quest sits on one step, and a seed lets Link move the quest on first:
# - the rolling Goron, as an adult (goron_tunic): his gift talk (SageOfFire's Step02_Npc_Goron_DaruniaJr_Adult_Talk) runs
#   only while the Fire quest is at TalkDaruniaJr. Entering the Crater (the Bolero), the temple or the quest's end moves it
#   on, and he then talks through his own flow (Npc_Goron_DaruniaJr_Adult: Talk, Npc_Goron_DaruniaJr_Step3_on,
#   SageOfFire_IsCompleted_Exp_Talk) with no gift. His gift talk sets SageOfFire_Step02_DoorOpen;
# - King Zora thawed (zora_tunic): after the Water Temple he talks through Npc_Zora_KingZora_adult's Talk with no gift;
#   SageOfWater's Safety_Entry is the gift part, which sets SageOfWater_KingZora_adult_Talk_Event198.
# In front of those talks (QUEST_LATE): an adult whose gift is still owed gets the gift part instead (a sub-call into the
# quest's flow, where the seed's item is). A gift part also asks for its quest's step, and the game moves a quest BACK when
# asked for an earlier step (Fire Temple progress undone): each Fire step request (QUEST_ORDER) runs only while the quest
# is not past that step. And Goron City entered from the Crater plays no intro, so the Goron's creation flag is never set
# there: the Crater's exit to the city sets it for an adult (QUEST_MAKE). Read in our files 2026-11-22: every entry,
# flag and step as the other randomizer has them.
QUEST_LATE = (   # (flow, its entries, a further condition (an expression) or None, the gift's done flag, (sub flow, entry), name)
    ("Npc_Goron_DaruniaJr_Adult", ("Talk", "Npc_Goron_DaruniaJr_Step3_on", "SageOfFire_IsCompleted_Exp_Talk"), None,
     "SageOfFire_Step02_DoorOpen", ("SageOfFire", "Step02_Npc_Goron_DaruniaJr_Adult_Talk"), "WillowLateGoron"),
    ("Npc_Zora_KingZora_adult", ("Talk",), "SageOfWater_IsCompleted_Exp",
     "SageOfWater_KingZora_adult_Talk_Event198", ("SageOfWater", "Safety_Entry"), "WillowLateZora"),
)
QUEST_ORDER = ("SageOfFire", "SageOfFire", ("StopDaruniaJr", "TalkDaruniaJr", "MoveStatue"), "WillowOrder")
# Darunia's gift after Dodongo's Cavern (bug 128, the owner's run 2026-11-23: Saria's Song to Darunia after the cavern was
# done gave a talk, no gift). Saria's Song at his ocarina point runs Get_StoneOfFire's Get_StoneOfFire_PlayOcarina, which
# asks Get_StoneOfFire_IsAfter_SariaMelodyPlay_Exp: false, the gift's scene (EventTransition Dm_Goron_0030); true, a
# talk. Finishing the cavern takes the quest past that step. Darunia's gift is owed while HavePlayedEvent.Dm_Goron_0030
# is not set (the scene sets it; seen 1 in every save copy that had the gift): in front of the talk, a switch on it sends
# a Link still owed the gift to the scene (DARUNIA_LATE). The scene asks for the quest's step DodongoCavernOpne, which
# would move the quest back (QUEST_ORDER's note): that step is asked only while the quest is not past it
# (DARUNIA_ORDER). Found by the agent's reading, 2026-11-23. With Quest rewards, placement aside (fixes 81).
DARUNIA_LATE = ("Get_StoneOfFire", "Get_StoneOfFire_IsAfter_SariaMelodyPlay_Exp", "Dm_Goron_0030", "HavePlayedEvent.Dm_Goron_0030", "WillowDaruniaLate")
DARUNIA_ORDER = ("Dm_Goron_0030", "Get_StoneOfFire", "DodongoCavernOpne", "WillowDaruniaOrder")


def darunia_late_flow(raw, name):
    """Get_StoneOfFire (DARUNIA_LATE) or Dm_Goron_0030 (DARUNIA_ORDER) with Darunia's late gift: the new bytes.
    ValueError: not the flow this was written for, or changed already."""
    import io
    evfl = evfl_module()
    flow = evfl.EventFlow()
    flow.read(raw)
    fc = flow.flowchart
    if fc is None or fc.name != name or any(e.name.startswith("WillowDarunia") for e in fc.events):
        raise ValueError("not the game's %s flow, or already changed" % name)
    import copy
    data_actor = [a for a in fc.actors if a.identifier.name == "GameDataActor" and not a.identifier.sub_name]
    if data_actor:
        data_actor = data_actor[0]
    else:   # (the scene has none: one made as quest_order_flow's actor_of does)
        data_actor = evfl.Actor()
        data_actor.identifier = evfl.ActorIdentifier("GameDataActor")
        data_actor.params = copy.deepcopy(fc.actors[0].params)
        data_actor.params.data["EventMemberCreateMethod"] = 0
        data_actor.concurrent_clips = fc.actors[0].concurrent_clips
        fc.actors.append(data_actor)

    def ask(label, query, flag, yes, no):
        got = [h for h in data_actor.queries if h.v == query]
        if got:
            q = got[0]
        else:
            q = evfl.common.StringHolder(query)
            data_actor.queries.append(q)
        e = evfl.Event()
        e.name = label
        e.data = evfl.SwitchEvent()
        c = evfl.Container()
        c.data.update(dict(Index=-1, GameDataName=flag) if query == "EventQueryIsGameDataBool" else dict(GameDataName=flag))
        e.data.actor.v, e.data.actor_query.v, e.data.params = data_actor, q, c
        for value, to in ((0, yes), (1, no)):
            e.data.cases[value] = evfl.util.RequiredIndex()
            e.data.cases[value].v = to
        fc.events.append(e)
        return e
    param = lambda e, k: e.data.params.data.get(k) if getattr(e.data, "params", None) is not None else None
    if name == DARUNIA_LATE[0]:
        _, exp, scene, done, label = DARUNIA_LATE
        hits = [e for e in fc.events if isinstance(e.data, evfl.SwitchEvent) and param(e, "GameDataName") == exp
                and 1 in e.data.cases and isinstance(e.data.cases[1].v.data, evfl.ActionEvent)
                and param(e.data.cases[1].v, "EventName") == scene and 0 in e.data.cases]
        if len(hits) != 1:
            raise ValueError("%d switches of %s lead to %s, not 1" % (len(hits), exp, scene))
        sw = hits[0]
        owed = ask(label, "EventQueryIsGameDataBool", done, sw.data.cases[0].v, sw.data.cases[1].v)
        sw.data.cases[0].v = owed
    elif name == DARUNIA_ORDER[0]:
        _, quest, step, label = DARUNIA_ORDER
        hits = [e for e in fc.events if isinstance(e.data, evfl.ActionEvent) and e.data.actor_action.v.v == "EventExecuteProgressChallengeStep"
                and param(e, "ChallengeName") == quest and param(e, "StepName") == step]
        if len(hits) != 1:
            raise ValueError("%s asks for %s's %s %d times, not once" % (name, quest, step, len(hits)))
        t = hits[0]
        holders = []
        for e in fc.events:
            d = e.data
            holders += [getattr(d, a) for a in ("nxt", "join") if hasattr(d, a)] + list(getattr(d, "forks", [])) + list(getattr(d, "cases", {}).values())
        holders += [p.main_event for p in fc.entry_points]
        holders = [h for h in holders if h.v is t]
        guard = ask(label, "EventQueryIsGameDataBoolExp", "%s_IsAfter_%s_Exp" % (quest, step), t.data.nxt.v, t)
        for h in holders:
            h.v = guard
    else:
        raise ValueError("not a flow of Darunia's late gift: %s" % name)
    out = io.BytesIO()
    flow.write(out)
    return out.getvalue()
QUEST_MAKE = ("Dm_SY_BancChangeGo", "DeathMountainCrater_ToGoronCity", "SageOfFire_GenerateDaruniaJr", "WillowLateGoronMake")


def quest_order_flow(raw, name):
    """the flow `name` (one of QUEST_LATE's, QUEST_ORDER's or QUEST_MAKE's) with its quest-order change: the new bytes.
    ValueError: not the flow this was written for, or changed already."""
    import copy
    import io
    evfl = evfl_module()
    flow = evfl.EventFlow()
    flow.read(raw)
    fc = flow.flowchart
    if fc is None or fc.name != name or any(e.name.startswith("Willow") for e in fc.events):
        raise ValueError("not the game's %s flow, or already changed" % name)

    def actor_of(kind):
        got = [a for a in fc.actors if a.identifier.name == kind and not a.identifier.sub_name]
        if got:
            return got[0]
        a = evfl.Actor()
        a.identifier = evfl.ActorIdentifier(kind)
        a.params = copy.deepcopy(fc.actors[0].params)
        a.params.data["EventMemberCreateMethod"] = 0
        a.concurrent_clips = fc.actors[0].concurrent_clips
        fc.actors.append(a)
        return a

    def holder(actor, what, kind):
        got = [h for h in getattr(actor, kind) if h.v == what]
        if got:
            return got[0]
        h = evfl.common.StringHolder(what)
        getattr(actor, kind).append(h)
        return h

    def container(**items):
        c = evfl.Container()
        c.data.update(items)
        return c

    def ask(label, query, flag, yes, no):
        """a switch on a flag (EventQueryIsGameDataBool) or an expression (...BoolExp): case 0 (true) yes, 1 (false) no"""
        e = evfl.Event()
        e.name = label
        e.data = evfl.SwitchEvent()
        data = actor_of("GameDataActor")
        params = container(Index=-1, GameDataName=flag) if query == "EventQueryIsGameDataBool" else container(GameDataName=flag)
        e.data.actor.v, e.data.actor_query.v, e.data.params = data, holder(data, query, "queries"), params
        for value, to in ((0, yes), (1, no)):
            if to is not None:
                e.data.cases[value] = evfl.util.RequiredIndex()
                e.data.cases[value].v = to
        fc.events.append(e)
        return e

    def entry(n):
        got = [p for p in fc.entry_points if p.name == n]
        if len(got) != 1:
            raise ValueError("%s has no entry %s" % (name, n))
        return got[0]

    def refs():
        """every place that names an event: (an Index holder, how to set it)"""
        for e in fc.events:
            d = e.data
            for attr in ("nxt", "join"):
                if hasattr(d, attr):
                    yield getattr(d, attr)
            for f in getattr(d, "forks", []):
                yield f
            for c in getattr(d, "cases", {}).values():
                yield c
        for p in fc.entry_points:
            yield p.main_event

    late = [l for l in QUEST_LATE if l[0] == name]
    if late:
        _, entries, when, done, (sub_flow, sub_entry), label = late[0]
        mains = []
        for n in entries:
            m = entry(n).main_event.v
            if m is None:
                raise ValueError("%s's entry %s starts nowhere" % (name, n))
            if m not in mains:
                mains.append(m)
        for k, old in enumerate(mains):
            give = evfl.Event()
            give.name = "%s%dGive" % (label, k)
            give.data = evfl.SubFlowEvent()
            give.data.res_flowchart_name, give.data.entry_point_name = sub_flow, sub_entry
            fc.events.append(give)
            owed = ask("%s%dDone" % (label, k), "EventQueryIsGameDataBool", done, old, give)
            then = ask("%s%dWhen" % (label, k), "EventQueryIsGameDataBoolExp", when, owed, old) if when else owed
            top = ask("%s%dAdult" % (label, k), "EventQueryIsGameDataBool", "Sequence_IsChildhood", old, then)
            at = fc.events.index(give)
            for n in entries:
                p = entry(n)
                if p.main_event.v is old:
                    p.main_event.v = top
                    p._sub_flow_event_indices.append(at)
    if name == QUEST_ORDER[0]:
        _, quest, steps, label = QUEST_ORDER
        targets = [e for e in fc.events if isinstance(e.data, evfl.ActionEvent)
                   and e.data.actor_action.v.v == "EventExecuteProgressChallengeStep" and e.data.params is not None
                   and e.data.params.data.get("ChallengeName") == quest and e.data.params.data.get("StepName") in steps]
        if sorted(t.data.params.data["StepName"] for t in targets) != sorted(steps):
            raise ValueError("%s does not ask for each of %s once" % (name, ", ".join(steps)))
        for k, t in enumerate(targets):
            after = t.data.nxt.v
            holders = [h for h in refs() if h.v is t]
            guard = ask("%s%d" % (label, k), "EventQueryIsGameDataBoolExp", "%s_IsAfter_%s_Exp" % (quest, t.data.params.data["StepName"]),
                        after, t)
            for h in holders:
                h.v = guard
    if name == QUEST_MAKE[0]:
        _, n, flag, label = QUEST_MAKE
        p = entry(n)
        old = p.main_event.v
        e = evfl.Event()
        e.name = label + "Set"
        e.data = evfl.ActionEvent()
        data = actor_of("GameDataActor")
        e.data.actor.v, e.data.actor_action.v = data, holder(data, "EventTriggerSetGameDataBool", "actions")
        e.data.params = container(Index=-1, Value=True, GameDataName=flag)
        e.data.nxt.v = old
        fc.events.append(e)
        p.main_event.v = ask(label + "Adult", "EventQueryIsGameDataBool", "Sequence_IsChildhood", old, e)
    out = io.BytesIO()
    flow.write(out)
    return out.getvalue()


# ---- Time savers from the other randomizer (asked 2026-11-22; OOTRR's qol/fishing.rs, skull_kid_session.rs,
# tower_escape.rs, read again in our files). Each a setting, off by default; none moves an item ----
# Any fish wins (rando_any_fish): MiniGame_Fishing's size checks at 40, 50 and 60 (EventQueryIsGameDataInt on
# MiniGame_Fishing_KeepFishSize) compare with 0, and the sinking lure's and the loach's questions go the prize way.
# Faster Skull Kid game (rando_skull_kid_fast): Npc_SkullKid_Child_02's session is one turn of 6 notes: SessionStart sets
# CurrentGradeSoundNumForSession 6 and MaxRallyCount 1 (both of its MaxRallyCount sets 1), the example's 6-note case
# plays the 8-note way's preparation, and a win under 8 notes goes on to the Heart Piece's question (Event68), where the
# seed's item is. Skip the tower escape (rando_skip_tower): Defeat_Ganon's banc change to the collapsing tower loads the
# field below it at its entrance with the escape's end event (InsideGanonCaslte_Dungeon_Escape, the game's spelling);
# the tower's preloading anchor (InsideGanonCastle_Dynamic) preloads that field. The tower skip SEEN IN PLAY by the owner,
# 2026-11-23 (turned on for a seed already made: Ganondorf beaten, straight to the field); any fish and the Skull Kid seen
# before.
FISH_FLOW = "Event/EventFlow/MiniGame_Fishing.bfevfl.zs"
SKULL_KID_FLOW = "Event/EventFlow/Npc_SkullKid_Child_02.bfevfl.zs"
GANON_FLOW = "Event/EventFlow/Defeat_Ganon.bfevfl.zs"
TOWER_ANCHOR_FILE = "Banc/InsideGanonCastle/InsideGanonCastle_Dynamic.bcett.byml.zs"
# Archery games won whatever the score (rando_archery_wins, asked 2026-11-23, share/todo.md). The shooting galleries
# (MiniGame_HitTarget, the Market's young Link's and Kakariko's adult's) end a round in a talk chosen by MiniGame_Score
# (EventQueryGameDataIntBranch, cases 0 to 10: under 8 the "try again", 8 and 9 the "so close", 10 the prize's way through
# RewardTalk): every case goes the prize's way. The horseback archery (Minigame_HorsebackArchery) asks "MiniGame_Score
# at least 1400" (ARCHERY_TOP, the remake's top prize's score; at least 750 its first) at a round's end: its "no" goes
# the "yes" way, which gives the Piece of Heart first if not had (with the quiver after it, HourseBackArchery_
# MakeQuiverLarger_DoubleGet), else the quiver's prize: both checks, the 1000 and 1500 points ones, on the first round.
# Bombchu Bowling: the first two wins give the two checks (asked 2026-11-23, share/todo.md; every seed with the gifts
# shuffled, from fixes 88). MiniGame_BombchuBowling's prize (its entry MiniGame_BombchuBowling_GetPrise) is not drawn at
# random: three questions in a row, "won once before?" (MiniGame_BombchuBowling_ClearFirstTime), "twice?" (..._ClearSecond
# Time), "three times?" (..._ClearThirdTime), give the 1st win 10 Bombchus, the 2nd the bag (bowling_bag, by a question of
# the bag Link has), the 3rd the Piece of Heart (bowling_heart), then a red rupee each time (the owner's run 2026-11-23:
# 10 Bombchus, then the bag's check). bowling_order_flow makes it the bag, the Piece of Heart, then the Bombchus.
BOWLING_FLOW = "Event/EventFlow/MiniGame_BombchuBowling.bfevfl.zs"


def bowling_order_flow(raw):
    """MiniGame_BombchuBowling with the bag's prize for the 1st win, the Piece of Heart's for the 2nd and the 10 Bombchus
    for the 3rd: the new bytes. ValueError: not the flow known (or changed already)"""
    import io
    evfl = evfl_module()
    flow = evfl.EventFlow()
    flow.read(raw)
    fc = flow.flowchart
    if fc is None or fc.name != "MiniGame_BombchuBowling":
        raise ValueError("no flowchart, or not MiniGame_BombchuBowling")
    flag = lambda e: (e.data.params.data.get("GameDataName") if isinstance(e.data, evfl.SwitchEvent) and e.data.params is not None
                      and e.data.actor_query.v.v == "EventQueryIsGameDataBool" else None)
    # (a true/false question's case 0 is its TRUE answer: "won before" goes on to the next question, 1 to the prize)
    nxt = lambda e, f: e.data.cases[0].v if 0 in e.data.cases and 1 in e.data.cases and flag(e.data.cases[0].v) == f else None
    firsts = [e for e in fc.events if flag(e) == "MiniGame_BombchuBowling_ClearFirstTime" and
              nxt(e, "MiniGame_BombchuBowling_ClearSecondTime") is not None and
              nxt(nxt(e, "MiniGame_BombchuBowling_ClearSecondTime"), "MiniGame_BombchuBowling_ClearThirdTime") is not None]
    if len(firsts) != 1:
        raise ValueError("%d prize questions (won once, twice, three times before), not 1" % len(firsts))
    first = firsts[0]
    second = nxt(first, "MiniGame_BombchuBowling_ClearSecondTime")
    third = nxt(second, "MiniGame_BombchuBowling_ClearThirdTime")
    chus, bag, heart = first.data.cases[1].v, second.data.cases[1].v, third.data.cases[1].v
    if not (isinstance(chus.data, evfl.SubFlowEvent) and isinstance(bag.data, evfl.SwitchEvent) and isinstance(heart.data, evfl.SubFlowEvent)):
        raise ValueError("the prizes are not a hand-over, the bag's question and a hand-over (changed already?)")
    first.data.cases[1].v, second.data.cases[1].v, third.data.cases[1].v = bag, heart, chus
    out = io.BytesIO()
    flow.write(out)
    return out.getvalue()


# Faster block pushing (rando_fast_push, asked 2026-11-23, share/todo.md; a Quality of life setting, off by default, moves
# no item). How a pushed or pulled block moves is its GrabMoveActorParam's MoveSpeed: a curve (Hermit2DSplit: groups of
# x, y and the slopes on either side) of how far along one push it is (y, 0 to 1) by the frames since it started (x, to
# MaxX: 44 for the common block, Obj_MovableBox_A_01). Every x and MaxX are divided by FAST_PUSH (the slopes multiplied by
# it): the same push in half the frames. The blocks of the Forest Temple, Dodongo's Cavern, the Fire, Shadow and Spirit
# Temples and the like (FAST_PUSH_PARAMS: the boxes, the Armos and Goron statues, the Shadow Temple's statue, the
# graveyard's tombstones), in every actor pack that carries a copy (a block's pack carries the file of the block it is
# made from). Not the pivoting floors nor the Spirit Temple's mirror (turned, not pushed). NOT SEEN IN PLAY: whether Link's
# push animation keeps with the block is for the owner to see (share/verify-list.md).
FAST_PUSH = 2.0
FAST_PUSH_PARAMS = ("Obj_MovableBox_A_01", "Obj_MovableBox_A_04", "Obj_MovableBox_A_05", "Obj_AmosStatue_A_01",
                    "Obj_ShadowTemple_Statue_A_01", "Obj_Tombstone_A_01")
FAST_PUSH_PART = "GameParameter/GrabMoveActorParam/%s.game__object__GrabMoveActorParam.bgyml"


def fast_push_param(data, factor=FAST_PUSH):
    """a GrabMoveActorParam file with its MoveSpeed curve run `factor` times as fast: the new bytes, or None when it has
    no curve of its own (it takes its parent's). ValueError: a curve not as known"""
    tree, version = byml_parse(data)
    if tree[0] != "dict" or "MoveSpeed" not in tree[1]:
        return None
    curve = tree[1]["MoveSpeed"]
    if curve[0] != "dict" or curve[1].get("Type") != ("string", "Hermit2DSplit") or "Data" not in curve[1] or "MaxX" not in curve[1]:
        raise ValueError("a MoveSpeed that is not a Hermit2DSplit curve with its Data and MaxX")
    points = curve[1]["Data"][1]
    if len(points) % 4 or any(p[0] != 210 for p in points) or curve[1]["MaxX"][0] != 210:
        raise ValueError("a MoveSpeed curve not of groups of four floats")
    f = lambda node: struct.unpack("<f", node[1])[0]
    pack = lambda v: (210, struct.pack("<f", v))
    for k in range(0, len(points), 4):
        points[k] = pack(f(points[k]) / factor)
        points[k + 2], points[k + 3] = pack(f(points[k + 2]) * factor), pack(f(points[k + 3]) * factor)
    curve[1]["MaxX"] = pack(f(curve[1]["MaxX"]) / factor)
    return byml_build(tree, version)


GALLERY_FLOW = "Event/EventFlow/MiniGame_HitTarget.bfevfl.zs"
HORSE_ARCHERY_FLOW = "Event/EventFlow/Minigame_HorsebackArchery.bfevfl.zs"
ARCHERY_TOP = 1400


def qol_flow(raw, which):
    """a time saver's flow change (which: "fish", "skull kid", "tower"): the new bytes. ValueError: not the flow known"""
    import io
    evfl = evfl_module()
    flow = evfl.EventFlow()
    flow.read(raw)
    fc = flow.flowchart
    if fc is None or any(e.name.startswith("Willow") for e in fc.events):
        raise ValueError("no flowchart, or changed already")
    p = lambda e, k: e.data.params.data.get(k) if getattr(e.data, "params", None) is not None else None
    call = lambda e: ((e.data.actor.v.identifier.name + "." + (e.data.actor_query.v.v if isinstance(e.data, evfl.SwitchEvent) else
                       e.data.actor_action.v.v)) if isinstance(e.data, (evfl.SwitchEvent, evfl.ActionEvent)) else None)

    def named(n):
        got = [e for e in fc.events if e.name == n]
        if len(got) != 1:
            raise ValueError("%d events named %s, not 1" % (len(got), n))
        return got[0]

    def case(e, v):
        return e.data.cases[v].v if v in e.data.cases else None

    def set_case(e, v, to):
        if v not in e.data.cases:
            e.data.cases[v] = evfl.util.RequiredIndex()
        e.data.cases[v].v = to

    if which == "fish":
        if fc.name != "MiniGame_Fishing":
            raise ValueError("not MiniGame_Fishing")
        first = None
        for limit in (40, 50, 60):
            hits = [e for e in fc.events if call(e) == "GameDataActor.EventQueryIsGameDataInt" and
                    p(e, "GameDataName") == "MiniGame_Fishing_KeepFishSize" and p(e, "Value") == limit]
            if len(hits) != 1:
                raise ValueError("%d fish size checks at %d, not 1" % (len(hits), limit))
            hits[0].data.params.data["Value"] = 0
            first = first or hits[0]
        talks = lambda e: e is not None and call(e) == "Npc_EventStarter.EventTalk" and p(e, "MessageId") == "EventFlowMsg/MiniGame_Fishing:Talk_145"
        lures = [e for e in fc.events if call(e) == "GameDataActor.EventQueryIsGameDataBool" and
                 p(e, "GameDataName") == "MiniGame_Fishing_UseSinkingLure" and talks(case(e, 1))]
        if len(lures) != 2:
            raise ValueError("%d sinking lure checks before the prizes, not 2" % len(lures))
        for e in lures:
            set_case(e, 0, case(e, 1))
        loach = [e for e in fc.events if call(e) == "GameDataActor.EventQueryIsGameDataBool" and
                 p(e, "GameDataName") == "MiniGame_Fishing_KeepLoach" and case(e, 1) is first]
        if len(loach) != 1:
            raise ValueError("%d loach checks before the size checks, not 1" % len(loach))
        set_case(loach[0], 0, first)
    elif which == "skull kid":
        if fc.name != "Npc_SkullKid_Child_02":
            raise ValueError("not Npc_SkullKid_Child_02")
        grade, rally = "Minigame_SkullKidSession_CurrentGradeSoundNumForSession", "Minigame_SkullKidSession_MaxRallyCount"
        ask = named("Event64")
        if call(ask) != "GameDataActor.EventQueryIsGameDataBool" or p(ask, "GameDataName") != "Minigame_SkullKidSession_IsGetHeartPiece":
            raise ValueError("Event64 no longer asks for the Heart Piece's flag")
        way = named("Event68")
        nxt = way.data.nxt.v if isinstance(way.data, evfl.ActionEvent) else None
        if not (nxt is not None and isinstance(nxt.data, evfl.ActionEvent) and nxt.data.nxt.v is ask):
            raise ValueError("Event68 no longer leads to the Heart Piece's question")
        eight = named("Event10")
        if call(eight) != "GameDataActor.EventQueryIsGameDataInt" or p(eight, "GameDataName") != grade or p(eight, "Value") != 8 or 0 not in eight.data.cases:
            raise ValueError("Event10 no longer asks for the 8-note game with a case below it")
        set_case(eight, 0, way)
        prep = named("Event143")
        if not isinstance(prep.data, evfl.SwitchEvent) or 8 not in prep.data.cases or 6 not in prep.data.cases:
            raise ValueError("Event143 no longer branches on the 6- and 8-note games")
        set_case(prep, 6, case(prep, 8))
        sets = [e for e in fc.events if p(e, "GameDataName") == rally and isinstance(e.data, evfl.ActionEvent)]
        if len(sets) != 2:
            raise ValueError("%d MaxRallyCount sets, not 2" % len(sets))
        for e in sets:
            e.data.params.data["Value"] = 1
        entry = [x for x in fc.entry_points if x.name == "SessionStart"]
        if len(entry) != 1:
            raise ValueError("no SessionStart entry")
        holder = sets[0].data.actor.v
        act = [h for h in holder.actions if h.v == "EventTriggerSetGameDataInt"]
        if not act:
            raise ValueError("the flow's GameDataActor sets no ints")

        def set_int(n, name, value, to):
            e = evfl.Event()
            e.name = n
            e.data = evfl.ActionEvent()
            e.data.actor.v, e.data.actor_action.v = holder, act[0]
            c = evfl.Container()
            c.data.update(GameDataName=name, Index=-1, Value=value)
            e.data.params = c
            e.data.nxt.v = to
            fc.events.append(e)
            return e
        turn = set_int("WillowSkullKidOneTurn", rally, 1, entry[0].main_event.v)
        entry[0].main_event.v = set_int("WillowSkullKidSixNotes", grade, 6, turn)
    elif which == "tower":
        if fc.name != "Defeat_Ganon":
            raise ValueError("not Defeat_Ganon")
        hits = [e for e in fc.events if call(e) == "GameSystemActor.EventReserveBancChange" and
                p(e, "NextBanc") == "CrumblingGanonCastle" and p(e, "BootEventName") == "CrumblingGanonCastle_Arrive"]
        if len(hits) != 1:
            raise ValueError("%d banc changes to the collapsing tower, not 1" % len(hits))
        d = hits[0].data.params.data
        for k, v in (("NextBanc", "FinalBattleField"), ("NextStartPos", "FinalBattleField_Entrance"),
                     ("BootEventName", "InsideGanonCaslte_Dungeon_Escape"), ("EventStarterName", "FinalBattleField_Entrance")):
            if k in d:
                d[k] = v
    elif which == "gallery":   # (ARCHERY_WINS: the Market's and Kakariko's shooting galleries, one flow)
        if fc.name != "MiniGame_HitTarget":
            raise ValueError("not MiniGame_HitTarget")
        hits = [e for e in fc.events if call(e) == "GameDataActor.EventQueryGameDataIntBranch" and p(e, "GameDataName") == "MiniGame_Score"
                and all(k in e.data.cases for k in range(11)) and len({id(case(e, k)) for k in range(11)}) == 3]
        if len(hits) != 1:
            raise ValueError("%d result talks by the score (lose, almost, win), not 1" % len(hits))
        win = case(hits[0], 10)
        for k in range(10):
            set_case(hits[0], k, win)
    elif which == "horse":     # (ARCHERY_WINS: the Gerudo horseback archery)
        if fc.name != "Minigame_HorsebackArchery":
            raise ValueError("not Minigame_HorsebackArchery")
        hits = [e for e in fc.events if call(e) == "GameDataActor.EventQueryIsGameDataInt" and p(e, "GameDataName") == "MiniGame_Score"
                and p(e, "Value") == ARCHERY_TOP and 1 in e.data.cases and 0 in e.data.cases]
        if len(hits) != 1:
            raise ValueError("%d checks of the score at %d, not 1" % (len(hits), ARCHERY_TOP))
        set_case(hits[0], 0, case(hits[0], 1))
    else:
        raise ValueError("no time saver " + which)
    out = io.BytesIO()
    flow.write(out)
    return out.getvalue()



# (bug 113, the owner's run 2026-11-23: the Goron shop would not sell the Empty Bottle on its shelf without an empty
# bottle) The shops' shared flow, DisplayShop, sorts the item picked by its pouch name (EventQueryCheckShopSelectItemName):
# its kind 5 is a bottle's contents (a potion, a bug, a fish), and the flow asks for an empty bottle to put it in before
# the sale (SelectItem_CheckAvailable), then sells it by the bottle's own way. The Empty Bottle, Item_Bottle, is of that
# kind too. So both questions of the kind get a step before their kind 5: is the item picked Item_Bottle
# (Shop_SelectItemName, the flow's own way of naming one)? Then it goes the way of every other item (the question's
# answer 0); a potion still asks for its bottle. Written with Shops on.
SHOP_FLOW = "Event/EventFlow/DisplayShop.bfevfl.zs"
SHOP_BOTTLE = "Item_Bottle"


def shop_bottle_flow(raw):
    """DisplayShop with the Empty Bottle sold as any other item (SHOP_BOTTLE, above): the new bytes. ValueError: not
    the flow known"""
    import io
    evfl = evfl_module()
    flow = evfl.EventFlow()
    flow.read(raw)
    fc = flow.flowchart
    if fc is None or fc.name != "DisplayShop" or any(e.name.startswith("Willow") for e in fc.events):
        raise ValueError("not DisplayShop, or changed already")
    query = lambda e: e.data.actor.v.identifier.name + "." + e.data.actor_query.v.v if isinstance(e.data, evfl.SwitchEvent) else None
    kind = [e for e in fc.events if query(e) == "Npc_EventStarter.EventQueryCheckShopSelectItemName" and 0 in e.data.cases and 5 in e.data.cases]
    asks = {"available": ("PouchSystemActor.EventQueryIsAnyBottleEmpty", None),
            "sold": ("Npc_EventStarter.EventQueryHavePlayedGetEventAtShop", "PouchSystemActor.EventQueryCanAddToPorchByGameData")}
    names = [e for e in fc.events if query(e) == "GameDataActor.EventQueryIsGameDataString64" and
             e.data.params.data.get("GameDataName") == "Shop_SelectItemName"]
    if not names:
        raise ValueError("no question of Shop_SelectItemName to copy")
    for what, (five, zero) in asks.items():
        hits = [e for e in kind if query(e.data.cases[5].v) == five and (zero is None or query(e.data.cases[0].v) == zero)]
        if len(hits) != 1:
            raise ValueError("%d questions of the item's kind before %s, not 1" % (len(hits), five))
        e = evfl.Event()
        e.name = "WillowShopBottle_" + what
        e.data = evfl.SwitchEvent()
        e.data.actor.v, e.data.actor_query.v = names[0].data.actor.v, names[0].data.actor_query.v
        c = evfl.Container()
        c.data.update(GameDataName="Shop_SelectItemName", Index=-1, Value=SHOP_BOTTLE)
        e.data.params = c
        for value, to in ((0, hits[0].data.cases[0].v), (1, hits[0].data.cases[5].v)):   # (0: it is the Empty Bottle)
            e.data.cases[value] = evfl.util.RequiredIndex()
            e.data.cases[value].v = to
        fc.events.append(e)
        hits[0].data.cases[5].v = e
    out = io.BytesIO()
    flow.write(out)
    return out.getvalue()

def tower_anchor(data):
    """Ganon's tower's map with its preloading anchor (ChangeBancBeforehandAnchor, to CrumblingGanonCastle) preloading
    the field instead: the new bytes. ValueError: not one such anchor"""
    tree, version = byml_parse(data)
    actors = tree[1].get("Actors")
    if not actors or actors[0] != "array":
        raise ValueError("the map file has no actors")
    hit = 0
    for a in actors[1]:
        if a[1].get("Gyaml", ("", ""))[1] != "ChangeBancBeforehandAnchor":
            continue
        dyn = a[1].get("Dynamic")
        if dyn and dyn[0] == "dict" and dyn[1].get("NextBancParamName", ("", ""))[1] == "CrumblingGanonCastle":
            dyn[1]["NextBancParamName"] = (dyn[1]["NextBancParamName"][0], "FinalBattleField")
            hit += 1
    if hit != 1:
        raise ValueError("%d anchors preloading the collapsing tower, not 1" % hit)
    return byml_build(tree, version)


def epona_event_rows(data, analyzed):
    """An event table (EVENT_TABLES: analyzed False the settings', True the analyzed one's) with a row for EPONA_OWN
    copied from EPONA_TEMPLATE's, and (the analyzed one) EPONA_OWN among the ocarina event's child events: the new bytes.
    ValueError: no such rows, or EPONA_OWN there already."""
    tree, version = byml_parse(data)
    if tree is None or tree[0] != "array":
        raise ValueError("an event table that is not a list of rows")
    by = {r[1]["__RowId"][1]: r for r in tree[1] if r[0] == "dict" and "__RowId" in r[1]}
    if EPONA_TEMPLATE not in by or EPONA_OWN in by:
        raise ValueError("the table has no row of %s, or one of %s already" % (EPONA_TEMPLATE, EPONA_OWN))
    row = collections.OrderedDict(by[EPONA_TEMPLATE][1])
    row["__RowId"] = ("string", EPONA_OWN)
    if analyzed:
        if "SubFlowList" in row:
            row["SubFlowList"] = ("array", [])
        ocarina = by.get("Dm_SY_Ocarina")
        kids = ocarina[1].get("ChildEventList") if ocarina else None
        if not kids or kids[0] != "array":
            raise ValueError("the ocarina event has no list of child events")
        names = sorted([k[1] for k in kids[1]] + [EPONA_OWN])
        ocarina[1]["ChildEventList"] = ("array", [("string", n) for n in names])
    else:
        row["FlowchartFileName"] = ("string", "Work/Event/EventFlow/%s.evfc" % EPONA_OWN)
        row["EntryPointName"] = ("string", EPONA_OWN)
        if "Dm_SY_Ocarina" in by and "EventBaseSetting" in by["Dm_SY_Ocarina"][1]:   # (at Link, as the ocarina event)
            row["EventBaseSetting"] = by["Dm_SY_Ocarina"][1]["EventBaseSetting"]
    rows = list(tree[1]) + [("dict", row)]
    rows.sort(key=lambda r: r[1]["__RowId"][1])
    return byml_build(("array", rows), version)


# ---- Every Great Fairy from the start (asked for 2026-11-19) ----
# Zelda's Lullaby on a fountain's Triforce mark plays TriForcePoint (FOUNTAIN_FLOW). For every fountain but one it then
# asks IsGet.Item_DinFire and sends one answer to Navi's lines ("It doesn't seem like anything happened... Let's come
# back later", Dm_FairyFountain_Power:Talk_00 to _02, by the Fire quest's step) and the other on to the fairy, so the
# fountains wait for the first one. Both answers are made to go on to the fairy. NOT SEEN IN PLAY.
FOUNTAIN_FLOW = "Event/EventFlow/TriForcePoint.bfevfl.zs"


def fountains_open(data):
    """The fountains' flow (FOUNTAIN_FLOW) with the question the fountain's choice (EventQueryFairyFountainSelectSpecialAbility)
    leads to, a yes-or-no one (IsGet of the Din fairy's gift: its name is the seed's item there, FAIRY_WORDS), sending
    both answers where its "no" goes: the new bytes, of the same size. ValueError: not the file, or not one such question."""
    u16 = lambda at: struct.unpack_from("<H", data, at)[0]
    u32 = lambda at: struct.unpack_from("<I", data, at)[0]
    u64 = lambda at: struct.unpack_from("<Q", data, at)[0]
    if data[:6] != b"BFEVFL" or u16(0x20) != 1:
        raise ValueError("not an event flow file of one flowchart")
    chart = u64(u64(0x28))
    actors, count, events = u64(chart + 0x28), u16(chart + 0x16), u64(chart + 0x30)
    text = lambda ptr: bytes(data[ptr + 2:ptr + 2 + u16(ptr)]).decode("utf-8", "replace") if 0 < ptr < len(data) - 2 else ""
    query = lambda e: text(u64(u64(actors + 0x38 * u16(e + 0x0c) + 0x20) + 8 * u16(e + 0x0e)))
    cases = lambda e: {u32(u64(e + 0x18) + 8 * c): u64(e + 0x18) + 8 * c + 4 for c in range(u16(e + 0x0a))}
    hits = set()
    for i in range(count):
        e = events + 0x30 * i
        if data[e + 8] != 1 or query(e) != "EventQueryFairyFountainSelectSpecialAbility":
            continue
        for place in cases(e).values():
            g = events + 0x30 * u16(place)
            if data[g + 8] == 1 and query(g) == "EventQueryIsGameDataBool" and set(cases(g)) == {0, 1}:
                hits.add(g)
    if len(hits) != 1:
        raise ValueError("%d yes-or-no questions after the fountain's choice where one was expected" % len(hits))
    pairs = cases(hits.pop())
    out = bytearray(data)
    struct.pack_into("<H", out, pairs[1], u16(pairs[0]))
    return bytes(out)


def sword_prompt_open(data):
    """The adult's Master Sword logic (SWORD_PROMPT_LOGIC) with its attention's Logic_Delete input unlinked: the new
    bytes, of the same size. The input (name, node, its output, flags, default) took node 1, InvBool of the Forest
    Temple's expression; unlinked as the file's other unlinked inputs are (node 0xffff, flags 0x01800000, default 0),
    the prompt is never deleted. ValueError: the file is not the one this was written for."""
    u32 = lambda at: struct.unpack_from("<I", data, at)[0]
    if data[:4] != b"AIB " or u32(4) != 0x408 or u32(0x10) != 4 or b"SageOfForest_IsCompleted_Exp" not in data:
        raise ValueError("not the AI file of 4 nodes this was written for")
    pool = u32(0x24)
    name = lambda off: data[pool + off:].split(bytes(1))[0]
    at = SWORD_PROMPT_INPUT
    if name(u32(at)) != b"Logic_Delete" or data[at + 4:at + 16] != struct.pack("<HHII", 1, 0, 0, 0):
        raise ValueError("the prompt's Logic_Delete is not linked as this was written for")
    out = bytearray(data)
    out[at + 4:at + 16] = struct.pack("<HHII", 0xFFFF, 0, 0x01800000, 0)
    return bytes(out)


def scene_steps(data):
    """A scene's flowchart (a BFEVFL file of one flowchart) read for quiet_scene: (its steps, its entry points'
    first steps with where each is kept, what its steps use). A step is a dict: kind (0 an action, 1 a switch, 2 a
    fork, 3 a join, 4 a sub-flow call), at (where it is), what (an action's or a question's name, a sub-flow's flow),
    and the places of its ways on: "next" (an action's, a join's, a call's), "cases" and "forks" (lists of places).
    ValueError: not such a file."""
    u16 = lambda at: struct.unpack_from("<H", data, at)[0]
    u64 = lambda at: struct.unpack_from("<Q", data, at)[0]
    if data[:6] != b"BFEVFL" or u16(0x20) != 1:
        raise ValueError("not an event flow file of one flowchart")
    chart = u64(u64(0x28))
    if data[chart:chart + 4] != b"EVFL":
        raise ValueError("the flowchart is not where the file says")
    actors, count, entries_n = u64(chart + 0x28), u16(chart + 0x16), u16(chart + 0x18)
    events, entries = u64(chart + 0x30), u64(chart + 0x40)

    def text(ptr):
        return bytes(data[ptr + 2:ptr + 2 + u16(ptr)]).decode("utf-8", "replace") if 0 < ptr < len(data) - 2 else ""

    def param(at, key):   # (a step's parameter: a whole number or a string; None when it has none)
        keys = u64(at + 8) if at else 0
        for k in range(u16(at + 2) if at else 0):
            if keys and text(u64(keys + 8 + 16 * (k + 1) + 8)) == key:
                item = u64(at + 0x10 + 8 * k)
                if data[item] == 2:
                    return struct.unpack_from("<i", data, item + 0x10)[0]
                if data[item] in (0, 5) and u16(item + 2) == 1:
                    return text(u64(item + 0x10))
        return None

    choices = lambda at: param(at, "ChoiceNumber") or 0   # (a talk's ChoiceNumber: 0 when it asks nothing)

    steps = []
    for i in range(count):
        e = events + 0x30 * i
        kind = data[e + 8]
        s = {"kind": kind, "at": e, "what": "", "choices": 0}
        if kind in (0, 1):
            actor = actors + 0x38 * u16(e + 0x0c)
            names = u64(actor + (0x18 if kind == 0 else 0x20))
            s["what"] = text(u64(names + 8 * u16(e + 0x0e)))
        if kind == 0:
            s["next"] = e + 0x0a
            s["name"] = param(u64(e + 0x10), "GameDataName")   # (what a game-data step sets, or None)
            if s["what"] == "EventTriggerSetGameDataString64":
                s["value"] = param(u64(e + 0x10), "Value")   # (the text it sets)
            if s["what"] == "EventTalk":
                s["choices"] = choices(u64(e + 0x10))
            elif s["what"] == "EventTransition":
                s["event"] = param(u64(e + 0x10), "EventName") or ""
            elif s["what"] == "EventPlayAS":   # (who plays it and what: SCENE_MOVES)
                s["as"] = (text(u64(actor)), param(u64(e + 0x10), "ASName") or "")
            elif s["what"] == "EventTriggerStartBgmSimple":   # (how long its music lasts: SCENE_MUSIC)
                s["life"] = param(u64(e + 0x10), "CommandLife")
        elif kind in (1, 5):   # (5: a switch of another kind, its cases as a switch's: seen in Goto_HyruleCastle)
            cases = u64(e + 0x18)
            s["cases"] = [cases + 8 * c + 4 for c in range(u16(e + 0x0a))]
        elif kind == 2:
            forks = u64(e + 0x10)
            s["forks"] = [forks + 2 * c for c in range(u16(e + 0x0a))]
            s["join"] = e + 0x0c
        elif kind == 3:
            s["next"] = e + 0x0a
        elif kind == 4:
            s["next"] = e + 0x0a
            s["what"] = text(u64(e + 0x18))
            s["entry"] = text(u64(e + 0x20))
        elif kind == 6:   # (a step that names where to go by a hash, not by a step's place: AllSage's)
            pass
        else:
            raise ValueError("a step of an unknown kind (%d)" % kind)
        steps.append(s)
    firsts = [entries + 0x20 * k + 0x1c for k in range(entries_n)]
    used = {s["what"] for s in steps if s["what"]}
    return steps, firsts, used


# The Potion Shop's keeper (the Market's, as a child) sells nothing until his errand is done: at the first talk he gives
# an empty bottle (a gift scene, Item_Bottle), says to catch the bug in his shop, and marks the errand started; the bug
# caught, he puts a Red Potion in the bottle and marks it cleared, and the shop is open (the owner's account, 2026-11-16;
# the flow Npc_Hylia_020_Shop_Child). With the randomizer the bug is passed over: after the gift the two talks about
# the bug are skipped, and from the mark of the errand started the flow goes on to the mark of it cleared and the
# challenge's last step, by the step that takes the bug away (its own, from the scene of it caught). The bottle is a gift of the
# shuffle (GIFTS, "potion_bottle"); the Red Potion is not given.
POTION_FLOW = SCENE_FLOWS + "/Npc_Hylia_020_Shop_Child.bfevfl.zs"
POTION_STARTED, POTION_CLEARED = "Market_Item_Bottle_TutorialEvent_Started", "Market_Item_Bottle_TutorialEvent_Cleared"
# (the bug is made by the map's logic once the errand is started, Market_Child_Prefab_f039, and goes when this is set: left there,
#  it kept Link in the shop, the keeper asking for it again as he walked away; seen in play, 2026-11-16)
POTION_BUG_GONE = "Market_Item_Bottle_TutorialEvent_Insect_Delete"
# (and the keeper keeps his panicked schedule, whose talk and nearness run the errand's entries, until this is set: his
#  AIScheduleParam's ConditionFlag. Without it he asked for the bug again as Link walked away; seen in play, 2026-11-16)
POTION_CALM = "Market_Item_Bottle_TutorialEvent_Shop_Bottle_Insect_Appeared"


def potion_errand_skip(data):
    """The Potion Shop keeper's flow (POTION_FLOW) with the bug passed over: the steps that led into the talks before the
    errand's start mark lead to the mark itself, and the step after the mark goes on to the bug's mark, the keeper's
    calm schedule's mark and the cleared mark. The new bytes,
    of the same size. ValueError: not the flow this was written for."""
    steps, _, _ = scene_steps(data)
    u16 = lambda at: struct.unpack_from("<H", data, at)[0]
    sets = lambda name: [i for i, s in enumerate(steps) if s["kind"] == 0 and s["what"] == "EventTriggerSetGameDataBool" and s.get("name") == name]
    started, cleared, gone, calm = sets(POTION_STARTED), sets(POTION_CLEARED), sets(POTION_BUG_GONE), sets(POTION_CALM)
    if len(started) != 1 or len(cleared) != 1 or len(gone) != 1 or len(calm) != 1:
        raise ValueError("the keeper's flow does not set the errand's marks and the bug's once each")
    started, cleared, gone, calm = started[0], cleared[0], gone[0], calm[0]
    after = u16(steps[started]["next"])   # (the keeper's schedule set back, then the challenge's "playing" step)
    if after >= len(steps) or steps[after]["kind"] != 0 or u16(steps[after]["next"]) >= len(steps):
        raise ValueError("the keeper's flow has no step after the errand's start mark")
    talks = set()   # (the talks that come just before the start mark, one after another)
    head = started
    while True:
        before = [i for i, s in enumerate(steps) if s["kind"] == 0 and s["what"] == "EventTalk" and u16(s["next"]) == head]
        if len(before) != 1:
            break
        head = before[0]
        talks.add(head)
    if len(talks) != 2:
        raise ValueError("the keeper's flow does not have two talks before the errand's start mark (%d)" % len(talks))
    out = bytearray(data)
    into = 0
    for i, s in enumerate(steps):
        if i in talks:
            continue
        for place in ([s["next"]] if "next" in s else []) + s.get("cases", []):
            if u16(place) == head:
                struct.pack_into("<H", out, place, started)
                into += 1
    if into != 1:
        raise ValueError("the keeper's talks about the bug are come to from %d steps, not one" % into)
    struct.pack_into("<H", out, steps[after]["next"], gone)   # (the bug gone, the keeper calm, then the errand cleared)
    struct.pack_into("<H", out, steps[gone]["next"], calm)
    struct.pack_into("<H", out, steps[calm]["next"], cleared)
    return bytes(out)


# Bug 68 (the owner, 2026-11-17): back to a child, Link held a usable sword he never got. The game's swap of the two
# ages' gear, the flow ReplaceEquipmentForEraChange (called by the Temple of Time's AdultToChild and ChildToAdult), puts
# the Kokiri Sword in the child's slot whenever that slot is empty on the way back (its step: an adult, and
# PlayerStatus.AnotherEraEquipWeapon empty -> set it to Weapon_Sword_Kokiri), with no question of the pouch: the
# original game's child always had it. Read in the game's file, not taken from elsewhere. With that step passed over the
# slot stays empty: a child who had the Kokiri Sword in hand when he went gets it back as before (the slot is not
# empty), one who never had it comes back with no sword, and one who owned it but held none equips it from the menu.
ERA_FLOW = SCENE_FLOWS + "/ReplaceEquipmentForEraChange.bfevfl.zs"


# The same flow on the way to an adult sets an empty adult's slot to the Master Sword (the owner's test of Shuffle the
# Master Sword, 2026-11-21: adult Link held the sword with none in the Equipment screen, and young Link too with Swords
# for either age). With the sword shuffled (master) that step is passed over too: the adult has no sword until he finds it.
def era_sword_fix(data, master=False):
    """ReplaceEquipmentForEraChange with the step that gives an empty child's slot the Kokiri Sword passed over
    (lead_past), and with master the one that gives an empty adult's slot the Master Sword: the new bytes, of the same
    size. ValueError: not the flow this was written for (no such step, or more than one)."""
    steps, firsts, _ = scene_steps(data)
    kokiri = [i for i, s in enumerate(steps) if s["kind"] == 0 and s["what"] == "EventTriggerSetGameDataString64" and
              s.get("name") == "PlayerStatus.AnotherEraEquipWeapon" and s.get("value") == "Weapon_Sword_Kokiri"]
    if len(kokiri) != 1:
        raise ValueError("the swap of the ages' gear does not set the child's slot to the Kokiri Sword once (%d)" % len(kokiri))
    sword = [i for i, s in enumerate(steps) if s["kind"] == 0 and s["what"] == "EventTriggerSetGameDataString64" and
             s.get("name") == "PlayerStatus.AnotherEraEquipWeapon" and s.get("value") == "Weapon_Sword_Master"]
    if master and len(sword) != 1:
        raise ValueError("the swap of the ages' gear does not set the adult's slot to the Master Sword once (%d)" % len(sword))
    return lead_past(data, steps, firsts, set(kokiri) | (set(sword) if master else set()), {})


# Bug 64 (the owner, 2026-11-17): an adult's first visit to Goron City had no rolling Goron; he came at the next visit.
# The first-visit arrival (Dm_SY_BancChangeArrive, GoronCity_InitDemo_Arrive: the city's intro, then the quest's
# ArriveCity step) ends there; the ordinary one (GoronCity_Arrive) asks whether Link is a child and, for an adult who has
# not seen it, plays his scene (SageOfFire_CityIn). The first-visit arrival is made to go on to that same question
# after its quest step: a child then ends as an ordinary arrival does, an adult gets his scene.
ARRIVE_FLOW = SCENE_FLOWS + "/Dm_SY_BancChangeArrive.bfevfl.zs"


def goron_arrival_fix(data):
    """Dm_SY_BancChangeArrive with the Goron City first-visit arrival's last step (the call of Get_StoneOfFire's
    ArriveCity) going on to the ordinary arrival's child-or-adult question: the new bytes, of the same size.
    ValueError: not the flow this was written for."""
    steps, _, _ = scene_steps(data)
    u16 = lambda at: struct.unpack_from("<H", data, at)[0]
    scene = [i for i, s in enumerate(steps) if s["kind"] == 0 and s.get("event") == "SageOfFire_CityIn"]
    seen = [i for i, s in enumerate(steps) if s["kind"] == 1 and any(u16(c) in scene for c in s.get("cases", []))]
    child = [i for i, s in enumerate(steps) if s["kind"] == 1 and s["what"] == "EventQueryPlayerIsChild" and
             any(u16(c) in seen for c in s.get("cases", []))]
    call = [i for i, s in enumerate(steps) if s["kind"] == 4 and s["what"] == "Get_StoneOfFire" and s.get("entry") == "Get_StoneOfFire_ArriveCity"]
    if len(scene) != 1 or len(seen) != 1 or len(child) != 1 or len(call) != 1:
        raise ValueError("not the arrivals this was written for (%d, %d, %d, %d)" % (len(scene), len(seen), len(child), len(call)))
    if u16(steps[call[0]]["next"]) != 0xFFFF:
        raise ValueError("the first-visit arrival's quest step does not end the arrival")
    out = bytearray(data)
    struct.pack_into("<H", out, steps[call[0]]["next"], child[0])
    return bytes(out)


def quiet_scene(data, entries=None, silent=False):
    """A scene (a BFEVFL file of one flowchart: a Dm_ flow the game plays as a flowchart) with what only shows
    something passed over (SCENE_SHOWS, above): the new bytes, of the same size, and how many talks were taken out;
    (None, 0) when nothing is to be taken out. What the scene does to the game is left. entries: the names of entry
    points, and only what they come to is looked at (the story's flows a lesson calls). ValueError: a branch or an
    entry point would be left with nothing and the scene has no step that does nothing (SCENE_NOTHING), or an entry
    point of `entries` is not the flow's. silent: a scene with no talk and no gift taken all the same (SCENE_SILENT)."""
    steps, firsts, _ = scene_steps(data)
    u16 = lambda at: struct.unpack_from("<H", data, at)[0]
    END = 0xFFFF
    nexts = lambda s: ([u16(s["next"])] if "next" in s else []) + [u16(c) for c in s.get("cases", []) + s.get("forks", [])] + (
        [u16(s["join"])] if "join" in s else [])

    def comes_to(start, goals):   # (whether a way from start comes to one of goals)
        seen, stack = set(), [start]
        while stack:
            i = stack.pop()
            if i in goals:
                return True
            if i == END or i >= len(steps) or i in seen:
                continue
            seen.add(i)
            stack += nexts(steps[i])
        return False

    # (the steps passed over: what only shows; a fork left with nothing in any branch, to its join; a question, with its
    #  switch, whose answers but one come back to it, or whose answers all come to the same step once what only shows
    #  is passed over (Zelda's "You came from the forest...": "Yes" and "No" each have a line, then the scene goes on))
    shows = lambda s: (s["kind"] == 0 and s["what"] in SCENE_SHOWS and not s["choices"] and s.get("as") not in SCENE_MOVES) or (
        s["kind"] == 0 and (s["what"], s.get("life")) == SCENE_MUSIC) or (
        s["kind"] == 4 and (s["what"] in SCENE_SHOWS_SUB or (s["what"], s["entry"]) in SCENE_LESSON))
    passed, answer = set(i for i, s in enumerate(steps) if shows(s)), {}
    if entries is not None:   # (only what these entry points come to: a story's flow a lesson calls, SCENE_LESSON_CALLS)
        u64 = lambda at: struct.unpack_from("<Q", data, at)[0]
        chart = u64(u64(0x28))
        names = u64(chart + 0x38)
        text = lambda ptr: bytes(data[ptr + 2:ptr + 2 + u16(ptr)]).decode("utf-8", "replace") if 0 < ptr < len(data) - 2 else ""
        stack = [u16(place) for k, place in enumerate(firsts) if names and text(u64(names + 8 + 16 * (k + 1) + 8)) in entries]
        if len(stack) != len(set(entries)):
            raise ValueError("the flow has not every entry point of %s" % ", ".join(sorted(entries)))
        reach = set()
        while stack:
            i = stack.pop()
            if i == END or i >= len(steps) or i in reach:
                continue
            reach.add(i)
            stack += nexts(steps[i])
        passed &= reach
    joined = {}   # (a step in a branch of a fork -> the fork's join: where a branch that ends goes on)
    for f, s in enumerate(steps):
        if s["kind"] == 2:
            for b in s.get("forks", []):
                seen, stack = set(), [u16(b)]
                while stack:
                    i = stack.pop()
                    if i == END or i >= len(steps) or i in seen:
                        continue
                    seen.add(i)
                    joined.setdefault(i, u16(s["join"]))
                    stack += nexts(steps[i])

    def after(i):   # (where a question's talk goes on: its next, or what follows its branch's join)
        j = u16(steps[i]["next"])
        if j == END and i in joined:
            k = joined[i]
            j = u16(steps[k]["next"]) if "next" in steps[k] else END
        return j

    def onward(i):
        seen = set()
        while i != END and i < len(steps) and i in passed and i not in seen:
            seen.add(i)
            i = answer[i] if i in answer else u16(steps[i]["next"])
        return i

    questions = [(i, after(i)) for i, s in enumerate(steps) if s["kind"] == 0 and s["what"] == "EventTalk" and s["choices"]]
    questions = [(i, j) for i, j in questions if j != END and steps[j]["kind"] == 1 and steps[j]["what"] in SCENE_CHOICE]
    nothing = {i for i, s in enumerate(steps) if s["kind"] == 0 and s["what"] in SCENE_NOTHING and u16(s["next"]) == END}
    changed = True
    while changed:
        changed = False
        for f, s in enumerate(steps):
            if s["kind"] == 2 and f not in passed and all(onward(u16(b)) == END or onward(u16(b)) in nothing for b in s["forks"]):
                passed |= {f, u16(s["join"])}
                answer[f] = u16(s["join"])
                changed = True
        for i, j in questions:
            if i in passed:
                continue
            cases = [u16(c) for c in steps[j]["cases"]]
            ends = {onward(c) for c in cases}
            if len(ends) == 1:
                to = ends.pop()
            else:
                leads = [c for c in cases if not comes_to(c, (i, j))]   # (back to the question, or to its answers)
                if len(leads) != 1:
                    continue
                to = leads[0]
            passed |= {i, j}
            answer[j] = to
            changed = True
    talks = sum(1 for i in passed if steps[i]["what"].startswith("EventTalk"))
    if not talks and not (entries is None and passed and (silent or any(s["kind"] == 4 and s["what"] in SCENE_GIFTS for s in steps))):
        return None, 0

    return lead_past(data, steps, firsts, passed, answer), talks


def lead_past(data, steps, firsts, passed, answer):
    """A flow (scene_steps') with the steps of `passed` passed over: every way into one leads to what follows it (a
    question of `answer`, its switch's place -> the answer taken, to that answer). A branch of a fork or an entry point
    left with nothing goes to a step of the flow's own that does nothing (SCENE_NOTHING), or else to one of the steps
    passed over that does not wait, made to end there. A fork keeps the branches left with something, first, and its
    count is made theirs: one step in two branches running at once kept a join from ever going on (seen in play: Impa's
    lesson ended before its gift, its fork 107's branches all one comment). The new bytes, of the same size.
    ValueError: there is neither."""
    u16 = lambda at: struct.unpack_from("<H", data, at)[0]
    END = 0xFFFF

    def onward(i):   # (the first step from i that is not passed over)
        seen = set()
        while i != END and i < len(steps) and i in passed and i not in seen:
            seen.add(i)
            i = answer[i] if i in answer else u16(steps[i]["next"])
        return i

    nothing = [i for i, s in enumerate(steps) if s["kind"] == 0 and s["what"] in SCENE_NOTHING and u16(s["next"]) == END]
    out = bytearray(data)
    if not nothing:   # (else one of the steps passed over that does not wait, an EventTrigger..., made to end there)
        nothing = [i for i in sorted(passed) if steps[i]["kind"] == 0 and steps[i]["what"].startswith("EventTrigger")][:1]
        if nothing:
            struct.pack_into("<H", out, steps[nothing[0]]["next"], END)
    for i, s in enumerate(steps):
        for place in ([s["next"]] if "next" in s else []) + s.get("cases", []):
            struct.pack_into("<H", out, place, onward(u16(place)))
        if "join" in s:
            struct.pack_into("<H", out, s["join"], onward(u16(s["join"])))
        if s.get("forks"):   # (a fork keeps the branches that are left, first, and counts them: no step in two branches)
            ways = [onward(u16(place)) for place in s["forks"]]
            left = [to for to in ways if to != END]
            if not left:
                if not nothing:
                    raise ValueError("a fork would be left with nothing, and the scene has no step that does nothing")
                left = nothing[:1]
            for place, to in zip(s["forks"], left + [END] * (len(ways) - len(left))):
                struct.pack_into("<H", out, place, to)
            struct.pack_into("<H", out, s["at"] + 0x0a, len(left))
    for place in firsts:
        to = onward(u16(place))
        if to == END:
            if not nothing:
                raise ValueError("an entry point would be left with nothing, and the scene has no step that does nothing")
            to = nothing[0]
        struct.pack_into("<H", out, place, to)
    return bytes(out)


def pass_videos(data, videos):
    """A flow (a BFEVFL file of one flowchart) with each step that plays one of `videos` (an EventTransition to it)
    passed over (lead_past): the new bytes, of the same size, and the videos so passed; (None, []) when it plays
    none of them."""
    steps, firsts, _ = scene_steps(data)
    passed = {i for i, s in enumerate(steps) if s.get("event") in videos}
    if not passed:
        return None, []
    return lead_past(data, steps, firsts, passed, {}), sorted({steps[i]["event"] for i in passed})


def sword_chest_plain(data):
    """Get_StoneOfForest (a BFEVFL file) with the Kokiri Sword's chest's own cutscene passed over: the new bytes, of the
    same size. Every step it relies on is checked first (see SWORD_EVENT, above): a flow that is not the one this
    was written for is an error."""
    u16 = lambda at: struct.unpack_from("<H", data, at)[0]
    u64 = lambda at: struct.unpack_from("<Q", data, at)[0]
    if data[:6] != b"BFEVFL" or u16(0x20) != 1:
        raise ValueError("not an event flow file of one flowchart")
    chart = u64(u64(0x28))
    if data[chart:chart + 4] != b"EVFL" or u16(chart + 0x16) != 227 or u16(chart + 0x18) != 27:
        raise ValueError("the flowchart is not the one of 227 events and 27 entry points")
    events, entries = u64(chart + 0x30), u64(chart + 0x40)
    event = lambda i: events + 0x30 * i

    def text(ptr):
        return bytes(data[ptr + 2:ptr + 2 + u16(ptr)]).decode("utf-8", "replace") if ptr else ""

    def plays(i):
        """the cutscene an EventTransition step plays: the string of its parameters that names a Dm_ flow"""
        at = u64(event(i) + 0x10)
        for k in range(u16(at + 2) if at else 0):
            item = u64(at + 0x10 + 8 * k)
            if data[item] in (0, 5) and u16(item + 2) == 1 and text(u64(item + 0x10)).startswith("Dm_"):
                return text(u64(item + 0x10))
        return ""

    step = lambda i: (data[event(i) + 8], u16(event(i) + 0x0a))   # (its kind: 0 an action, 1 a switch; its next step)
    if (u16(entries + 0x20 * 7 + 0x1c) != 48 or step(48) != (0, 47) or step(47) != (0, 88) or plays(47) != "Dm_SY_Treasurebox" or
            step(88) != (0, 211) or plays(88) != "Dm_Kokiri_0063" or data[event(211) + 8] != 1):
        raise ValueError("the sword chest's steps are not the ones this was written for")
    out = bytearray(data)
    struct.pack_into("<H", out, event(47) + 0x0a, 211)     # (the chest's opening goes on to what follows the sword's cutscene)
    return bytes(out)


# ---- a gift: what a character hands Link ----
# Nearly every item given by a character, a fairy or a scene goes through one flow of the game's, Dm_SY_GetInEvent (and
# GetPouchContent): the scene's own flow calls it as a sub-flow and names the item in the call's parameters, a string
# (Darunia's, Dm_Goron_0030: GetInEvent_Goron with ActorName "Item_Gauntlet_Goron"). 209 such calls were counted.
# So a gift is changed by changing that string. The item's name is the scene's actor's name too (the bracelet Darunia
# holds out), from the same file's strings, so the string itself is left: the new name is put at the file's end and
# the parameter made to point at it. The scene is as it was: Darunia still holds out a bracelet.
GIFT_FLOWS = "Event/EventFlow"
FLOW_EXTRA = 288   # (a flow's entry in the size table: its size rounded up to 32 and 272 or 280 in the three looked at)


def gift_item(data, old, new):
    """An event flow (a BFEVFL file) with every sub-flow call's parameter that is the string `old` made the string
    `new`: the new bytes (longer by the new string, the file's size in its header raised), or None when no call has
    it. The other strings and every other pointer are as they were."""
    return gift_items(data, {old: new})[0]


def flow_reach(data, entry):
    """The events of a flow's flowchart that its entry point `entry` can come to (their indices), by every branch:
    an action's and a sub-flow call's next, a switch's cases, a fork's branches and its join. ValueError: no such
    entry point."""
    u16 = lambda at: struct.unpack_from("<H", data, at)[0]
    u64 = lambda at: struct.unpack_from("<Q", data, at)[0]
    chart = u64(u64(0x28))
    count, entries_n = u16(chart + 0x16), u16(chart + 0x18)
    events, names, entries = u64(chart + 0x30), u64(chart + 0x38), u64(chart + 0x40)

    def text(ptr):
        return bytes(data[ptr + 2:ptr + 2 + u16(ptr)]).decode("utf-8", "replace") if 0 < ptr < len(data) - 2 else ""

    first = [u16(entries + 0x20 * k + 0x1c) for k in range(entries_n) if names and text(u64(names + 8 + 16 * (k + 1) + 8)) == entry]
    if not first:
        raise ValueError("the flow has no entry point %s" % entry)
    seen, stack = set(), list(first)
    while stack:
        i = stack.pop()
        if i == 0xFFFF or i >= count or i in seen:
            continue
        seen.add(i)
        e = events + 0x30 * i
        kind = data[e + 8]
        if kind in (0, 3, 4):
            stack.append(u16(e + 0x0a))
        elif kind == 1:
            cases = u64(e + 0x18)
            stack += [u16(cases + 8 * c + 4) for c in range(u16(e + 0x0a))]
        elif kind == 2:
            forks = u64(e + 0x10)
            stack += [u16(forks + 2 * c) for c in range(u16(e + 0x0a))] + [u16(e + 0x0c)]
    return seen


def gift_items(data, swaps, kinds=(4,)):
    """gift_item for several items of one flow at once: swaps is {old: new}. kinds: the steps looked at (4 a call of a
    sub-flow, the gifts'; 0 an action and 1 a question too, for a name the flow sets or asks about: the songs'). All are found before any is changed, so
    that one gift's new item is not taken for another's old one (a flow with two gifts whose items changed places).
    A key (entry, old) in place of old is only that entry point's calls (flow_reach): two sales of one flow that
    name the same item. Such a key comes before a plain one for the same name.
    Returns (the new bytes, or None when no call has any of them; the keys that were found)."""
    scoped = {}   # an entry point -> the events it comes to
    for key in swaps:
        if isinstance(key, tuple) and key[0] not in scoped:
            scoped[key[0]] = flow_reach(data, key[0])
    u16 = lambda at: struct.unpack_from("<H", data, at)[0]
    u64 = lambda at: struct.unpack_from("<Q", data, at)[0]
    if data[:6] != b"BFEVFL" or u16(0x20) != 1 or struct.unpack_from("<I", data, 0x1c)[0] != len(data):
        raise ValueError("not an event flow file of one flowchart")
    chart = u64(u64(0x28))
    if data[chart:chart + 4] != b"EVFL":
        raise ValueError("the flowchart is not where the file says")
    events, count = u64(chart + 0x30), u16(chart + 0x16)

    def text(ptr):
        return bytes(data[ptr + 2:ptr + 2 + u16(ptr)]).decode("utf-8", "replace") if 0 < ptr < len(data) - 2 else ""

    where = []
    for i in range(count):
        e = events + 0x30 * i
        if data[e + 8] not in kinds:   # (4: a call of a sub-flow)
            continue
        params = u64(e + 0x10)
        if not params or data[params] != 1:   # (1: a container of named parameters)
            continue
        for k in range(u16(params + 2)):
            item = u64(params + 0x10 + 8 * k)
            if data[item] != 5 or u16(item + 2) != 1:   # (5: a string of its own, not a name passed on)
                continue
            name = text(u64(item + 0x10))
            key = next(((entry, name) for entry, reach in scoped.items() if i in reach and (entry, name) in swaps), name)
            if key in swaps:
                where.append((item + 0x10, swaps[key], key))
    if not where:
        return None, set()
    out = bytearray(data)
    at = {}
    for pointer, new, _ in where:
        if new not in at:   # (each new name once, at the file's end)
            out += b"\0" * (-len(out) % 8)
            at[new] = len(out)
            name = new.encode("utf-8")
            out += struct.pack("<H", len(name)) + name + b"\0"
        struct.pack_into("<Q", out, pointer, at[new])
    out += b"\0" * (-len(out) % 8)
    struct.pack_into("<I", out, 0x1c, len(out))
    return bytes(out), {old for _, _, old in where}


def size_entry(size, extra=264):
    """what the game's size table holds for a file of `size` bytes unpacked: the size rounded up to 32, and 264 for a
    map file (every one looked at had exactly that), 312 for an actor's pack (PACK_EXTRA: six looked at)"""
    return (size + 31 & ~31) + extra


PACK_EXTRA = 312
SHOP_EXTRA = 65536   # (for a list of the game's actors and a language's archive, whose entries follow no rule looked for: far more than either grows)


def size_table_update(tbl, sizes, extra=264):
    """The size table ("RESTBL": a header of 22 bytes, then a path's CRC32 and a size for each file, sorted by the
    CRC32) with the entries of `sizes` ({path without .zs: bytes unpacked}) raised to fit."""
    if tbl[:6] != b"RESTBL":
        raise ValueError("not a size table (%r)" % tbl[:6])
    count = struct.unpack_from("<I", tbl, 14)[0]
    if 22 + count * 8 > len(tbl):
        raise ValueError("the size table's entry count does not fit the file")
    out = bytearray(tbl)
    for path, size in sizes.items():
        crc = zlib.crc32(path.encode()) & 0xffffffff
        lo, hi = 0, count
        while lo < hi:
            mid = (lo + hi) // 2
            if struct.unpack_from("<I", tbl, 22 + mid * 8)[0] < crc:
                lo = mid + 1
            else:
                hi = mid
        at = 22 + lo * 8
        if lo >= count or struct.unpack_from("<I", tbl, at)[0] != crc:
            raise ValueError("%s is not in the size table" % path)
        struct.pack_into("<I", out, at + 4, max(struct.unpack_from("<I", tbl, at + 4)[0], size_entry(size, extra)))
    return bytes(out)


# The size table has an entry for each parameter file inside a pack too, by the file's own name, and the game takes
# the memory for the file as it is read from it: the Bomb Bag's table of game parameters, given a parent, no longer
# fitted its entry and the game stopped there as the pack was read (the Boomerang's, changed the same way, still
# fitted its own). The game's entries follow no rule found (252 bytes: 5432; 568 bytes: 5896; 152 bytes: 5288), so a
# changed file's entry is raised by this much, far more than any of them grows.
PART_GROWTH = 4096


def size_table_raise(tbl, paths, by=PART_GROWTH):
    """the size table with the entries of `paths` raised by `by`; a path with no entry is left out"""
    count = struct.unpack_from("<I", tbl, 14)[0]
    index = {struct.unpack_from("<I", tbl, 22 + k * 8)[0]: 22 + k * 8 for k in range(count)}
    out = bytearray(tbl)
    for path in set(paths):
        at = index.get(zlib.crc32(path.encode()) & 0xffffffff)
        if at is not None:
            struct.pack_into("<I", out, at + 4, struct.unpack_from("<I", tbl, at + 4)[0] + by)
    return bytes(out)


# What a new parameter file's entry is given: more than any of the game's own of its kind has (5288 to 5984 for a pouch
# file, of 152 to 740 bytes).
PART_NEW = 8192


def size_table_add(tbl, paths, size=PART_NEW):
    """the size table with an entry of `size` for each of `paths` that it does not have: put in its place among the
    CRC32s, which are sorted, and the count raised. A path whose CRC32 the table has is left as it is."""
    count = struct.unpack_from("<I", tbl, 14)[0]
    end = 22 + count * 8
    have = {struct.unpack_from("<I", tbl, 22 + k * 8)[0] for k in range(count)}
    new = sorted({zlib.crc32(path.encode()) & 0xffffffff for path in paths} - have)
    if not new:
        return tbl
    rows = [bytes(tbl[22 + k * 8:30 + k * 8]) for k in range(count)] + [struct.pack("<II", crc, size) for crc in new]
    rows.sort(key=lambda r: struct.unpack_from("<I", r)[0])
    return bytes(tbl[:14]) + struct.pack("<I", len(rows)) + bytes(tbl[18:22]) + b"".join(rows) + bytes(tbl[end:])


def unpack(data, zs, dicts):
    if data[:4] != ZSTD:
        return data
    try:
        return zs.ZstdDecompressor().decompress(data, max_output_size=1 << 28)
    except Exception:
        pass
    for d in dicts:
        try:
            return zs.ZstdDecompressor(dict_data=d).decompress(data, max_output_size=1 << 28)
        except Exception:
            pass
    raise ValueError("could not be decompressed")


def dictionaries(romfs, zs):
    try:
        raw = zs.ZstdDecompressor().decompress(open(os.path.join(romfs, "Pack", "ZsDic.pack.zs"), "rb").read(), max_output_size=1 << 28)
        start = struct.unpack_from("<I", raw, 0x0c)[0]
        return [zs.ZstdCompressionDict(raw[start + st:start + end], dict_type=zs.DICT_TYPE_FULLDICT)
                for _, _, st, end in (struct.unpack_from("<IIII", raw, 0x20 + k * 16) for k in range(struct.unpack_from("<H", raw, 0x1a)[0]))]
    except Exception:
        return []


# ---- Starting items (rando_start_items, asked 2026-11-21) ----
# A new game starts with the items chosen in the launcher's New seed window: the options file's line
# "rando_start_items=KS,SL,ZL" (START_ITEMS' codes; a line of its own, which the game's menu keeps as it keeps every line
# it does not know). The game has no list of a new game's pouch to change, so the game's side gives them: each one Link
# does not hold yet, with its first ammo when it is given (host/hos_main.c oot_start_items, from START_FILE beside the
# seed). The rules take them as held from the start (start_need: each way without them), and one of each that is not a
# song leaves the pool (its place gives START_JUNK); a song stays (a lesson can hold few other items), found again it
# is the same song. On the stamp's first line: another choice is another seed. NOT SEEN IN PLAY.
START_FILE = "start_items.txt"
START_JUNK = "TBox_Rupee_Blue"
# code: (the seed's item, the game's names to give it by (host: oot_item_names), the ammo it comes with (name, count))
START_ITEMS = {
    "KS": (S, ("Weapon_Sword_Kokiri",), None), "DS": (DS, ("Weapon_Shield_Deku",), None),
    "DK": ("Item_DekuStickBundle_Small", ("Item_StickBag_Small",), ("Item_DekuStick", 10)),
    "DN": ("TBox_DekuNutBundle", ("Item_NutBag_Small",), ("Item_DekuNut", 20)),
    "HY": ("TBox_Shield_Hylian", ("Weapon_Shield_Hylian",), None),
    "SL": (SL, ("Weapon_Range_SlingShot", "Item_BulletBag_Small"), ("Item_DekuSeed", 30)),
    "BM": (BM, ("Item_Boomerang",), None), "BB": (BB, ("Item_BombBag_Small",), ("Item_Bomb", 20)),
    "BW": (BOW, ("Weapon_Range_Bow", "Item_Quiver_Small"), ("Item_Arrow_Normal", 30)),
    "HS": ("Item_Hookshot", ("Item_Hookshot",), None), "LS": (LONG, ("Item_Hookshot", "Item_Longshot"), None),
    "HM": (HAM, ("Item_Hammer",), None), "LT": (LENS, ("Item_GlassTruth",), None),
    "IB": (IRON, ("Armor_Adult_HeavyBoot",), None), "HB": (HOVER, ("Armor_Adult_HoverBoot",), None),
    "GB": ("Item_Gauntlet_Goron", ("Item_Gauntlet_Goron",), None), "SS": ("Item_Scale_Silver", ("Item_Scale_Silver",), None),
    "FO": ("Item_Ocarina_Fairy", ("Item_Ocarina_Fairy",), None), "AW": ("Item_Wallet_Medium", ("Item_Wallet_Medium",), None),
    "DF": ("Item_DinFire", ("Item_DinFire",), None),
    "ZL": ("Item_Melody_ZeldaLullaby", ("Item_Melody_ZeldaLullaby",), None), "EP": ("Item_Melody_EponaSong", ("Item_Melody_EponaSong",), None),
    "SR": ("Item_Melody_SariaSong", ("Item_Melody_SariaSong",), None), "SU": ("Item_Melody_SunSong", ("Item_Melody_SunSong",), None),
    "ST": ("Item_Melody_TimeSong", ("Item_Melody_TimeSong",), None), "SO": ("Item_Melody_StormSong", ("Item_Melody_StormSong",), None),
    "MI": ("Item_Melody_ForestMinuet", ("Item_Melody_ForestMinuet",), None), "BF": ("Item_Melody_FireBolero", ("Item_Melody_FireBolero",), None),
    "SE": ("Item_Melody_WaterSerenade", ("Item_Melody_WaterSerenade",), None), "NC": ("Item_Melody_ShadowNocturne", ("Item_Melody_ShadowNocturne",), None),
    "RQ": ("Item_Melody_SpiritRequiem", ("Item_Melody_SpiritRequiem",), None), "PR": ("Item_Melody_LightPrelude", ("Item_Melody_LightPrelude",), None),
}
# ---- Test pins (asked 2026-11-21, for testing only) ----
# While PIN_FILE lies beside this script, every seed made puts the items it names in the spots it names (place's
# `bound`: that item there, that spot nothing else), the rest shuffled as ever. A line "<area>|<the spot's position as
# the spoiler says it, or its start>|<item>"; # starts a note. The file's text is on the stamp: another file, another seed.
PIN_FILE = "test_pins.txt"


def read_pins():
    """[(area, where, item)] from PIN_FILE beside this script ([] when it is not there)"""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), PIN_FILE), encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []
    pins = []
    for line in text.splitlines():
        parts = [x.strip() for x in line.split("|")]
        if line.strip() and not line.lstrip().startswith("#") and len(parts) == 3:
            pins.append(tuple(parts))
    return pins


def pin_groups(spots, pins):
    """place's bound groups for the pins: ({item}, {the spot's hash}); a pin whose spot is not found stops the seed"""
    groups = []
    for area, where, item in pins:
        found = [h for h in sorted(spots) if spots[h][0] == area and str(spots[h][5]).startswith(where)]
        if len(found) != 1:
            sys.exit("test pin %s | %s: %d spots match (one is needed)" % (area, where, len(found)))
        groups.append((frozenset({item}), frozenset(found)))
        print("test pin: %s at %s %s" % (item, area, spots[found[0]][5]))
    return groups


START_ALSO = {"LS": ("Item_Hookshot",)}   # (the Longshot held: the Hookshot too, as the rules count the family)
# (Deku Sticks and Deku Nuts, asked 2026-11-21: the bag with 10 sticks or 20 nuts. Supplies, not one of a kind: none
#  leaves the pool, and the rules ask for neither)
START_SUPPLIES = frozenset({"DK", "DN"})


def start_codes(text):
    """the starting items' codes of an options line's value ("KS,SL"), known ones only, in START_ITEMS' order"""
    want = {c.strip().upper() for c in (text or "").split(",")}
    return [c for c in START_ITEMS if c in want]


def start_option(game):
    """the options file's rando_start_items value ("" none)"""
    try:
        with open(os.path.join(game, "hookshot_options.ini"), encoding="utf-8", errors="replace") as f:
            for line in f:
                key, eq, value = line.partition("=")
                if eq and key.strip() == "rando_start_items":
                    return value.strip()
    except OSError:
        pass
    return ""


def start_held(codes):
    """the seed's items the starting items make held (the Longshot's Hookshot too)"""
    return frozenset(START_ITEMS[c][0] for c in codes) | frozenset(i for c in codes for i in START_ALSO.get(c, ()))


def start_need(need, held):
    """a rule with the starting items held: each way without them (a way left with nothing: the check asks for nothing)"""
    return each(lambda way: frozenset(way) - held, need) if held else need


def start_lines(codes):
    """START_FILE's lines: "<a name the game gives it by> [<its ammo> <count>]", each a line, the ammo on its item's first"""
    out = []
    for c in codes:
        names, ammo = START_ITEMS[c][1], START_ITEMS[c][2]
        for k, name in enumerate(names):
            out.append(name + (" %s %d" % ammo if ammo and k == 0 else ""))
    return out


def settings(game):
    """the randomizer's lines of the options file (0 where it does not say)"""
    got = {"rando_on": 0, "rando_seed": 0, "rando_chests": 0, "rando_keys": 0, "rando_major": 0, "rando_open_deku": 0, "rando_open_forest": 0,
           "rando_skip_intro": 0, "rando_skip_cutscenes": 0, "rando_skulltulas": 0, "rando_quests": 0, "rando_frogs": 0, "rando_light_arrows": 0,
           "rando_start_rupees": 0, "rando_scrubs": 0, "rando_shops": 0, "rando_progressive": 0, "rando_songs": 0, "rando_heart_pieces": 0,
           "rando_shop_shelves": 0, "rando_sword_shield": 0, "rando_dungeon_rewards": 0, "rando_open_door": 0,
           "rando_ammo_pickups": 0, "rando_rupee_fill": 0, "rando_skulltulas_day": 0,
           "rando_ganon_bridge": 0, "rando_hints": 0, "rando_ageless": 0, "rando_letter": 0, "rando_magic": 0, "rando_ageless_items": 0, "rando_ageless_tunics": 0, "rando_chest_size": 0, "rando_bridge_medallions": 0, "rando_master_sword": 0, "rando_dampe_hookshot": 0, "rando_epona_song": 0, "rando_ocarinas": 0, "rando_castle_guards": 0, "rando_free_scarecrow": 0, "rando_any_fish": 0, "rando_skull_kid_fast": 0, "rando_skip_tower": 0, "rando_fairy_prices": 0, "rando_archery_wins": 0, "rando_fast_push": 0, "rando_soil_bottle": 0, "rando_gerudo_guards": 0, "rando_house_hints": 0, "rando_maps": 0, "rando_boss_keys": 0, "rando_pots": 0}   # (ammo, rupees and the bridge: the game's side's alone, host/hos_main.c oot_pickup_qol and oot_ganon_bridge)
    try:
        with open(os.path.join(game, "hookshot_options.ini"), encoding="utf-8", errors="replace") as f:
            for line in f:
                key, eq, value = line.partition("=")
                if eq and key.strip() in got:
                    try:
                        got[key.strip()] = int(value.strip())
                    except ValueError:
                        pass
    except OSError:
        pass
    return got


def set_option(game, key, value):
    """one line of the options file set (the others kept as they are)"""
    path = os.path.join(game, "hookshot_options.ini")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    lines = [x for x in lines if x.partition("=")[0].strip() != key] + ["%s=%d" % (key, value)]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


# ---- the tracker: the checks the seed has in each area, for the game's menu ----
# The Insert menu's Tracker tab (gpu/vk/vk_menu.cpp: tracker_load) shows <game folder>\mods\rando-seed\tracker.txt as
# it is: a row for each line "<name>|<what>", TRACKER_ROWS of them at most, a name of up to 47 characters and a
# value of up to 71. Lines that start with # are not rows.
TRACKER = "tracker.txt"
TRACKER_ROWS = 48
AREA_NAMES = {
    "KokiriForest": "Kokiri Forest", "LostWood": "Lost Woods", "SacredForestMeadow": "Sacred Forest Meadow", "HyruleField": "Hyrule Field",
    "Market": "Market", "HyruleCastle": "Hyrule Castle", "GanonCastle": "Ganon's Castle (outside)", "KakarikoVillage": "Kakariko Village",
    "Graveyard": "Graveyard", "DeathMountainTrail": "Death Mountain Trail", "DeathMountainCrater": "Death Mountain Crater",
    "GoronCity": "Goron City", "ZoraRiver": "Zora's River", "ZoraDomain": "Zora's Domain", "ZoraFountain": "Zora's Fountain",
    "GerudoValley": "Gerudo Valley", "GerudoFortress": "Gerudo's Fortress", "HountedWasteland": "Haunted Wasteland",
    "DesertColossus": "Desert Colossus", "InsideTheDekuTree": "Inside the Deku Tree", "DodongoCavern": "Dodongo's Cavern",
    "InsideJabuJabuBelly": "Inside Jabu-Jabu's Belly", "BottomOfTheWell": "Bottom of the Well", "ForestTemple": "Forest Temple",
    "FireTemple": "Fire Temple", "IceCavern": "Ice Cavern", "WaterTemple": "Water Temple", "ShadowTemple": "Shadow Temple",
    "SpiritTemple": "Spirit Temple", "GerudoTrainingGround": "Gerudo Training Ground", "InsideGanonCastle": "Inside Ganon's Castle",
    "DreamWorld": "Dream World",
}


def tracker_lines(chests, skulls, gifts=None, hearts=None):
    """The tracker file's lines. chests, skulls, gifts and hearts: {area (the Banc folder): how many of them take part}.
    A line for the whole game, then one for each area that has any, by its name; no more than the menu has rows for.
    (hearts: the Pieces of Heart lying in the world and the bosses' Heart Containers, counted with the Gold Skulltulas
    before: 122 "Gold Skulltulas" for 100 and 22 hearts, the owner's question 2026-11-19)"""
    gifts, hearts = gifts or {}, hearts or {}

    def what(c, k, g, h=0):
        parts = (["%d chest%s" % (c, "" if c == 1 else "s")] if c else []) + (["%d Gold Skulltula%s" % (k, "" if k == 1 else "s")] if k else [])
        parts += ["%d heart%s" % (h, "" if h == 1 else "s")] if h else []
        parts += ["%d gift%s" % (g, "" if g == 1 else "s")] if g else []
        return ", ".join(parts) or "nothing"

    areas = sorted(set(chests) | set(skulls) | set(gifts) | set(hearts), key=lambda a: AREA_NAMES.get(a, a).lower())
    areas = [a for a in areas if chests.get(a, 0) or skulls.get(a, 0) or gifts.get(a, 0) or hearts.get(a, 0)]
    rows = [("The whole game", what(sum(chests.values()), sum(skulls.values()), sum(gifts.values()), sum(hearts.values())))]
    rows += [(AREA_NAMES.get(a, a), what(chests.get(a, 0), skulls.get(a, 0), gifts.get(a, 0), hearts.get(a, 0))) for a in areas]
    if len(rows) > TRACKER_ROWS:   # (more areas than rows: the last row says so)
        rows = rows[:TRACKER_ROWS - 1] + [("And %d more areas" % (len(rows) - TRACKER_ROWS + 1), "see the spoiler")]
    return ["# The checks of this seed in each area, for the menu's Tracker tab: <name>|<what>"] + [
        "%s|%s" % (name.replace("|", "/")[:47], value[:71]) for name, value in rows]


# ---- the checks, one by one: for the Tracker tab's "Go there" ----
# <game folder>\mods\rando-seed\checks.txt, a line for each chest and Gold Skulltula that takes part:
# "<the area's name, as its tracker row>|<Chest or Gold Skulltula>|<the Banc folder>|<C, A or CA: the ages whose map has
# it>|<x> <y> <z>|<what the rules ask for>". The menu steps through an area's lines and has the game take Link to one
# (the debug tools: the teleport to the folder's map, then the place). What a check holds is not in the file. A gift
# or a Business Scrub's sale has a line too, its kind the gift's name and its place from GIFT_PLACES. CHECK_ROWS: as
# many as the menu keeps (kTrackerChecks).
# What the rules ask for: the gating items of the check's rule, each by its two letters (CHECK_CODES, the menu's
# kLogicItems), with commas; "-" when it asks for nothing. The menu says a check is in logic when Link carries them
# all. The rules ask for too much, never too little (see RULES): a check not in logic may be within reach.
CHECKS = "checks.txt"
# The way to a check, for the Tracker tab (asked for by the game's owner, 2026-11-16): <game folder>\mods\rando-seed\
# check_ways.txt, "<the check's actor hash, as checks.txt has it>|<words>", for the Gold Skulltulas, Pieces of Heart and
# Heart Containers that Ocarina Atlas describes (atlas_ways.json beside this script, taken from it under its MIT licence:
# ATLAS_NOTICE.txt). Its words are the original game's way there, its name for the place, and whether it is there at
# night only. No json beside the script: an empty file, and the tab says nothing more.
CHECK_WAYS = "check_ways.txt"
ATLAS_WAYS = "atlas_ways.json"


def check_ways(checks_path):
    """[(hash, words)] for the lines of checks_path whose actor hash ATLAS_WAYS describes, in the file's order"""
    import json
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ATLAS_WAYS), encoding="utf-8") as f:
            ways = json.load(f)["ways"]
        with open(checks_path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except (OSError, ValueError, KeyError):
        return []
    out, seen = [], set()
    for line in lines:
        parts = line.split("|")
        if line.startswith("#") or len(parts) < 7 or parts[6] in seen or parts[6] not in ways:
            continue
        seen.add(parts[6])
        w = ways[parts[6]]
        words = "%s. %s" % (w["name"].rstrip("."), w["way"])
        if w.get("night") and "night" not in w["way"].lower():
            words += " It comes out at night only."
        out.append((parts[6], words.replace("|", "/").replace("\r", " ").replace("\n", " ")))
    return out


# ---- What a check waits for in the story (the owner's to-do, 2026-11-23: the Nocturne's lesson and Zelda's Light Arrows
# showed "in logic" before the Water, Shadow and Spirit Temples were done) ----
# The rules count items only: MEDALS3 and the like stand for "those temples done" by the items they take. The game holds
# some checks back until temples are really done (each temple's awakening scene played: HavePlayedEvent.Dm_Awake_<X>,
# what AllSage's SageRoom_AllSage_LastSage asks of the Shadow and Spirit Temples before Zelda's Light Arrows). The seed
# writes those checks to CHECK_AFTER, "<the check's hash, as checks.txt has it>|<the temples' folders, by commas>"; the
# game's side tells the Tracker which temples are done (host/hos_main.c oot_tracker_refresh, OOT_TRACKER_TEMPLES) and the
# Tracker says "in logic after ..." until they are (gpu/vk/vk_menu.cpp tracker_after). tests/test_rando_story_waits.py
CHECK_AFTER = "check_after.txt"
STORY_TEMPLES = ("ForestTemple", "FireTemple", "WaterTemple", "ShadowTemple", "SpiritTemple")   # (the menu's bits, in order)
# (the gifts by key: the Nocturne's lesson as the original game, after the Forest, Fire and Water medallions (its rule
#  MEDALS3); the Prelude's after the Forest's (its rule the Forest Temple's Bow); the Light Arrows after both sages' scenes)
STORY_GIFTS = {"song_nocturne": ("ForestTemple", "FireTemple", "WaterTemple"), "song_prelude": ("ForestTemple",),
               "light_arrows": ("ShadowTemple", "SpiritTemple")}
# (checks by their actor's hash: Lake Hylia's chest there once the Water Temple is done, AFTER_WATER, and the sun's shot,
#  whose rule is the Water Temple's ending's: the lake filled. Made in check_after: SUN_ARROWS is set below)
STORY_HASH_TEMPLES = ("WaterTemple",)


def check_after(lines):
    """[(hash, (temple folders))] for the lines of a checks file (checks.txt's text, by lines) whose check the game holds
    back until temples are done, in the file's order. Those of STORY_GIFTS (by name) and of AFTER_WATER and SUN_ARROWS; the Shadow Temple's
    own checks, when no check gives the Nocturne (its lesson is then the only way in: DUNGEON_ENTRY's MEDALS3); and a
    check every way of whose rule asks for an item that only checks that wait give, which waits for theirs too."""
    names = {(g.name[:1].upper() + g.name[1:]).replace("|", "/")[:CHECK_NAME]: STORY_GIFTS[g.key]
             for g in SONGS + GIFTS if g.key in STORY_GIFTS}
    rows = [line.split("|") for line in lines if not line.startswith("#") and len(line.split("|")) >= 6]
    hashes = {"%016x" % h: STORY_HASH_TEMPLES for h in AFTER_WATER + (SUN_ARROWS,)}
    waits = {}
    for i, r in enumerate(rows):
        hash_ = r[6] if len(r) > 6 else "-"
        wait = set(names.get(r[1], ())) | set(hashes.get(hash_, ()))
        if wait:
            waits[i] = wait
    if not any(len(r) > 7 and r[7] == NOCTURNE for r in rows):
        for i, r in enumerate(rows):
            if r[2] == "ShadowTemple":
                waits.setdefault(i, set()).update(STORY_GIFTS["song_nocturne"])
    codes = dict(CHECK_CODES)
    while True:   # (an item given only where the story waits: the checks that cannot be had without it wait as well)
        givers = collections.defaultdict(list)
        for i, r in enumerate(rows):
            if len(r) > 7 and r[7] in codes:
                givers[codes[r[7]]].append(waits.get(i, set()))
        held = {code: set.intersection(*map(set, w)) for code, w in givers.items() if all(w)}
        grew = False
        for i, r in enumerate(rows):
            ways = [set(way.split(",")) for way in r[5].split("/")]
            if not ways or any(not way & set(held) for way in ways):
                continue
            more = set.intersection(*(set().union(*(held[c] for c in way & set(held))) for way in ways))
            if not more <= waits.get(i, set()):
                waits.setdefault(i, set()).update(more)
                grew = True
        if not grew:
            break
    return [(rows[i][6], tuple(t for t in STORY_TEMPLES if t in waits[i])) for i in sorted(waits)
            if len(rows[i]) > 6 and rows[i][6] != "-"]


CHECK_ROWS = 512   # (was 320: a seed with the shops and every gift on had 337, bug 85, the last areas cut off)
CHECK_NAME = 79   # (a check's name: as many characters as the menu keeps of it)
CHECK_CODES = collections.OrderedDict((
    ("Item_Sword_Kokiri", "KS"), ("Item_Range_SlingShot", "SL"), ("Item_BombBag_Small", "BB"), ("Item_Boomerang", "BM"),
    ("Item_GlassTruth", "LT"), ("Item_Range_Bow", "BW"), ("Item_Hammer", "HM"), ("Item_HeavyBoot", "IB"), ("Item_HoverBoot", "HB"),
    ("Item_Longshot", "LS"), ("Item_Gauntlet_Silver", "SG"), ("Item_Shield_Mirror", "MS"), ("Item_Gauntlet_Gold", "GG"),
    ("Item_Gauntlet_Goron", "GB"), ("Item_Scale_Silver", "SS"), ("Item_Wallet_Medium", "AW"), ("Item_Wallet_Large", "GW"),
    ("Item_Melody_ZeldaLullaby", "ZL"), ("Item_Melody_EponaSong", "EP"), ("Item_Melody_SariaSong", "SR"), ("Item_Melody_TimeSong", "ST"),
    ("Item_Melody_StormSong", "SO"), ("Item_Melody_SpiritRequiem", "RQ"), ("Item_Melody_ShadowNocturne", "NC"),
    ("Obj_Armor_Goron", "GT"), ("Obj_Armor_Zora", "ZT"), (BOTTLE, "BO"), ("Item_ZeldaLetter", "LE"), ("Item_Ocarina_Fairy", "FO"),
    ("Item_FairyBless_MPDouble", "MG"), ("Weapon_Sword_Master", "MW"), (HOOK, "HS"), ("Item_DinFire", "DF"), ("Item_Scale_Gold", "GS")))   # (the tunics, placement 12: TUNICS; MW: Shuffle the Master Sword, MASTER; HS: Shuffle Dampe's Hookshot, HOOK)


def token_codes(way):
    """the tracker's letters of the tokens a way of a rule asks for (tokens): "T<N>", which the Tracker tab holds when
    the pouch has N Gold Skulltula tokens (gpu/vk/vk_menu.cpp tracker_way_held)"""
    return ["T%d" % n for n in sorted(token_count(word) or 0 for word in way) if n]


def check_ages(names):
    """C, A or CA: the ages whose map files (names) have a check. A map without an age in its name is both's."""
    child = any("_Child" in n or "_Adult" not in n for n in names)
    adult = any("_Adult" in n or "_Child" not in n for n in names)
    return ("C" if child else "") + ("A" if adult else "")


# A gift or a Business Scrub's sale is a scene, not an actor with a hash: where Link stands for it is written here, by
# the gift's key, from the map files of its area (GIFTS' and SCRUBS' area): the giver, or the game's own place for
# Link there (a mini-game's StartPos, a scene's anchor). (the ages whose map has it, the place). Its line's kind is the
# gift's name. Read from the map files, not walked to: the four tried unattended are named in the README.
GIFT_PLACES = {
    "master_sword": ("C", (137.6, 106.6, -34.0)),          # (Obj_TimeTemple_MasterSword_A_01: the game's side finds the check by it)
    "darunia": ("C", (-0.2, 98.6, -38.5)),                 # (Npc_Goron_Darunia_Child at z -41.8, the door at -29.2)
    "lostwood_target": ("C", (41.1, 102.6, -4.9)),         # (HitTargetOfDekuScrub)
    "skulltula_house_10": ("CA", (-26.5, 109.9, 74.5)),    # (Npc_SkullDad at z 72.5)
    "skulltula_house_20": ("CA", (-26.5, 109.9, 74.5)),
    "skulltula_house_30": ("CA", (-26.5, 109.9, 74.5)),
    "skulltula_house_40": ("CA", (-26.5, 109.9, 74.5)),
    "skulltula_house_50": ("CA", (-26.5, 109.9, 74.5)),
    "forest_stage_skull": ("C", (-10.0, 83.2, -52.0)),     # (ScrubForestStageElder at z -54.5)
    "forest_stage_truth": ("C", (-10.0, 83.2, -52.0)),
    "bowling_bag": ("C", (-25.1, 100.0, 9.5)),             # (BombchuBowlingStartPos)
    "bowling_heart": ("C", (-25.1, 100.0, 9.5)),
    "diving": ("C", (25.4, 113.2, -5.3)),                  # (MiniGame_Diving_PlayerStart)
    "fishing_child": ("C", (-97.6, 134.1, 489.7)),         # (MiniGame_Fishing_PlayerStart)
    "fishing_adult": ("A", (-97.6, 134.1, 489.7)),
    "frogs": ("C", (9.2, 101.9, -54.8)),                   # (OcarinaPoint_MiniGame_FrogTenors)
    "frogs_game": ("C", (9.2, 101.9, -54.8)),
    "gallery_market": ("C", (-14.2, 100.1, -12.4)),        # (HitTargetStartPos)
    "gallery_kakariko": ("A", (-58.5, 91.4, 62.6)),        # (HitTargetStartPos)
    "cucco_lady": ("C", (-73.9, 99.5, 82.9)),              # (CatchCucco_GoalPoint)
    "archery_heart": ("A", (69.5, 115.0, 36.3)),           # (HorsebackArcheryPlayerPos)
    "archery_quiver": ("A", (69.5, 115.0, 36.3)),
    "rolling_goron": ("C", (-10.3, 109.6, -16.5)),         # (Npc_Goron_006_Child)
    "goron_tunic": ("A", (5.8, 109.9, -12.1)),             # (Npc_Goron_DaruniaJr_Adult, where he waits in the city's ring)
    "zora_tunic": ("A", (66.1, 119.5, 12.5)),              # (Npc_Zora_KingZora_adult, on his throne)
    "roof_man": ("CA", (-36.1, 107.5, 29.0)),              # (his HeartPieceAnchor)
    "skull_kid_song": ("C", (-28.6, 101.0, 1.6)),          # (On_Center_Npc_SkullKid_Child)
    "skull_kid_game": ("C", (48.4, 97.8, 15.8)),           # (OcarinaPoint_SkullKidSession)
    "dog_lady": ("C", (-0.3, 100.1, 26.9)),                # (SubEvent_FindRichard_Link_Stay)
    "lab_dive": ("CA", (-172.5, 137.8, 422.2)),            # (beside Npc_Hylia_045, the scientist in Lake Hylia's lab, at x -174.5)
    "potion_bottle": ("C", (20.6, 100.1, 6.0)),            # (the Potion Shop, as its shelves: SHOPS "medicine")
    "light_arrows": ("A", (108.0, 103.9, -34.0)),          # (the Temple of Time, before the Spirit Stones' base at x 110.4)
    "scrub_heart_field": ("CA", (25.0, 129.9, 22.1)),      # (the scrubs: where the map has them)
    "scrub_heart_secret": ("C", (-23.0, 119.1, 33.0)),
    "scrub_sticks": ("CA", (-45.2, 95.2, 72.6)),
    "scrub_nuts": ("CA", (7.3, 82.9, -85.6)),
    "ocarina_time": ("C", (0.2, 150.2, 56.8)),             # (as the Song of Time's lesson: before the Market's bridge)
    "fairy_ocarina": ("C", (-115.0, 114.5, -38.2)),       # (Npc_Kokiri_Saria_Child, KokiriForest_ArriveLostWood, at x -117.1)
    "zelda_letter": ("C", (5.1, 126.8, -236.4)),           # (as Impa's lesson: the meeting's end, in the courtyard)
    "fairy_din": ("CA", (-34.0, 211.2, -189.2)),          # (the fountains' marks, Obj_TriForcePoint_A_02, _03, _05:
    "fairy_farore": ("CA", (62.5, 104.3, 99.2)),          #  where the Lullaby is played)
    "fairy_nayru": ("A", (-49.1, 101.5, -77.9)),
    "fairy_power": ("C", (118.5, 108.8, -76.8)),          # (Obj_TriForcePoint_A_01, A_04, A_06: Magic and the fairies'
    "fairy_wisdom": ("A", (-76.6, 122.2, 46.6)),          #  gifts, MAGIC_GIFTS)
    "fairy_courage": ("A", (139.2, 85.2, 312.5)),
    "song_zelda": ("C", (5.1, 126.8, -236.4)),             # (DoorOfTime_MeetImpa_StartPos: before Impa, in the castle's courtyard)
    "song_epona": ("C", (-91.9, 150.6, 247.0)),            # (Npc_Hylia_Malon_Child at z 245.4, Lon Lon Ranch)
    "song_saria": ("C", (-6.9, 114.4, -85.2)),             # (Dm_MelodyGet_Saria_Start)
    "song_sun": ("CA", (149.5, 98.7, 2.7)),                # (Dm_MelodyGet_Sun_Child: in the royal tomb)
    "song_time": ("C", (0.2, 150.2, 56.8)),                # (GetOcarinaOfTime_AreaOut_Destination: before the Market's bridge)
    "song_storms": ("A", (1.2, 105.1, 49.5)),              # (Npc_Hylia_009_Adult at z 51.3, in the windmill)
    "song_minuet": ("A", (-7.0, 114.4, -84.3)),            # (Dm_MelodyGet_Forest_Position)
    "song_bolero": ("A", (-17.5, 114.0, -10.2)),           # (Dm_MelodyGet_Fire_LinkPosition)
    "song_serenade": ("A", (-45.1, 109.7, 41.8)),          # (before the chest whose opening starts the lesson, SageOfWater_MelodyGet_Water)
    "song_requiem": ("A", (-156.0, 95.4, 10.3)),           # (Dm_MelodyGet_Spilit_Player_pos)
    "song_nocturne": ("A", (-119.8, 96.6, 58.7)),          # (KakarikoVillage_Entrance: the lesson starts as Link comes in)
    "song_prelude": ("A", (134.0, 106.4, -34.0)),          # (before Npc_Hylia_Sheik_Adult at x 139.0, past the Door of Time)
}


# ---- a chest's and a Gold Skulltula's name, made from the map files ----
# The game names neither. What its map files do say is put together (check_name): what the chest held before the
# shuffle (known to who knows the game, and nothing about what it holds now), whether it is the big kind, a Gold
# Skulltula's night and its bean soil, and where: a dungeon's room by its number, a part of the map that has a name
# of its own (Lake Hylia, Lon Lon Ranch, the Temple of Time: a LocationArea not the map's own), or the way out it
# is near (a MapIconEntranceAnchor within EXIT_NEAR metres). "Chest (red rupee), room 10", "Big chest (Kokiri Sword)",
# "Gold Skulltula, night, by the Lost Woods exit". Two of an area that come out the same are numbered, by place.
# Nobody has gone through them: they tell one check from the next, and are not the names a player would give.
ITEM_WORDS = {
    # (the owner's run 2026-11-23: the Bottom of the Well's "Chest (Fairy Bless MPDouble)": the magic gifts by the game's own names)
    "Item_FairyBless_MPDouble": "Doubled Magic", "Item_FairyBless_MP": "Improved Spin", "Item_FairyBless_DefenseDouble": "Halved Damage",
    "Item_Arrow_Fire": "Fire Arrows", "Item_Arrow_Ice": "Ice Arrows", "Item_Arrow_Light": "Light Arrows",
    "TBox_Rupee_Green": "green rupee", "TBox_Rupee_Blue": "blue rupee", "TBox_Rupee_Red": "red rupee", "TBox_Rupee_Purple": "purple rupee",
    "TBox_Shield_Deku": "Deku Shield", "TBox_Shield_Hylian": "Hylian Shield",
    "TBox_Rupee_Silver": "silver rupee", "TBox_Rupee_Gold": "gold rupee", "Item_ScrubBusinessSeed": "Deku Seeds", "Obj_Heart_Piece": "Piece of Heart",
    "Item_Token_Gold": "Skulltula token", "TBox_DekuNutBundle": "Deku Nuts", "TBox_ArrowBundle_Small": "arrows", "TBox_ArrowBundle_Medium": "arrows",
    "TBox_ArrowBundle_Large": "arrows", "Item_BombchuBundle_Small": "Bombchus", "Item_BombBundle_Small": "bombs", "Tbox_MagicJar_Large": "magic jar",
    "Item_StickBag_Large": "Deku Stick bag", "Item_NutBag_Large": "Deku Nut bag", "Item_DekuStickBundle_Small": "Deku Sticks",
    "Item_Sword_Kokiri": "Kokiri Sword", "Item_Range_SlingShot": "Slingshot", "Item_BombBag_Small": "Bomb Bag", "Item_Boomerang": "Boomerang",
    "Item_GlassTruth": "Lens of Truth", "Item_Range_Bow": "Bow", "Item_Hammer": "Megaton Hammer", "Item_HeavyBoot": "Iron Boots",
    "Item_HoverBoot": "Hover Boots", "Item_Longshot": "Longshot", "Item_Gauntlet_Silver": "Silver Gauntlets", "Item_Shield_Mirror": "Mirror Shield",
    "Item_Gauntlet_Gold": "Golden Gauntlets", "Item_Gauntlet_Goron": "Goron's Bracelet", "Item_Dungeon_SmallKey": "small key", "Item_Dungeon_BossKey": "boss key", "Item_Dungeon_Map": "map",
    "Item_Dungeon_Compass": "compass", "Item_ZeldaLetter": "Zelda's Letter", "Item_Ocarina_Fairy": "Fairy Ocarina", "Item_Ocarina_Time": "Ocarina of Time",
    "Weapon_Sword_Master": "Master Sword",   # (Shuffle the Master Sword: a chest's name and a hint's, MASTER)
}
EXIT_NEAR = 40.0
MARKS = ("LocationArea", "MapIconEntranceAnchor")


def spaced(name):
    """an actor's or a place's name in words: "LonLonRanch" -> "Lon Lon Ranch", "Item_Arrow_Fire" -> "Arrow Fire" """
    name = name.split("_", 1)[1] if name.split("_", 1)[0] in ("Item", "TBox", "Tbox", "Obj", "Weapon", "Armor") and "_" in name else name
    out = ""
    for k, ch in enumerate(name.replace("_", " ")):
        out += (" " if k and ch.isupper() and out[-1:].islower() else "") + ch
    return out


def marks(data):
    """What a map file has to name its checks by: [(hash, Gyaml, place, scale, {a Dynamic's name: its text, or its
    number as it is written})] for its chests, Gold Skulltulas, Pieces of Heart, Heart Containers, LocationAreas and
    MapIconEntranceAnchors."""
    if data[:2] != b"YB":
        raise ValueError("not a little-endian BYML")
    key_at, str_at, root = struct.unpack_from("<III", data, 4)
    keys, strings = table(data, key_at), table(data, str_at)
    out = []
    for name, kind, value, _ in entries(data, root, keys):
        if name != "Actors" or kind != 0xC0:
            continue
        n = int.from_bytes(data[value + 1:value + 4], "little")
        vals = value + 4 + (n + 3 & ~3)
        for i in range(n):
            if data[value + 4 + i] != 0xC1:
                continue
            ident, gyaml, pos, scale, dyn, turned = None, "", (), (), None, (0.0, 0.0, 0.0)
            for k, t, v, _ in entries(data, struct.unpack_from("<I", data, vals + 4 * i)[0], keys):
                if k == "Hash" and t == 0xD5:
                    ident = struct.unpack_from("<Q", data, v)[0]
                elif k == "Hash" and t == 0xD3:
                    ident = v
                elif k == "Gyaml" and t == 0xA0:
                    gyaml = strings[v] if v < len(strings) else ""
                elif k in ("Translate", "Scale") and t == 0xC0 and int.from_bytes(data[v + 1:v + 4], "little") == 3:
                    three = tuple(round(x, 1) for x in struct.unpack_from("<3f", data, v + 8))
                    pos, scale = (three, scale) if k == "Translate" else (pos, three)
                elif k == "Rotate" and t == 0xC0 and int.from_bytes(data[v + 1:v + 4], "little") == 3:
                    turned = struct.unpack_from("<3f", data, v + 8)
                elif k == "Dynamic" and t == 0xC1:
                    dyn = v
            if gyaml in MARKS or gyaml == SKULLTULA or gyaml.startswith("Obj_TBox") or gyaml in HEART_ACTORS or gyaml == CONTAINER or gyaml == SUN_ACTOR or gyaml.startswith("Obj_Pot"):
                words = {}
                for dk, dt, dv, _ in entries(data, dyn, keys) if dyn is not None else ():
                    words[dk] = (strings[dv] if dv < len(strings) else "") if dt == 0xA0 else dv
                words["Rotate"] = turned   # (not a Dynamic's name: how the actor is turned, in radians about X, Y and Z)
                out.append((ident, gyaml, pos, scale, words))
    return out


# Where Link is put to go to a chest: not on it. Above a chest he came down on it or behind it, and behind one of Mido's
# house's he was between the chest and the wall, where a wall he could not see kept him (seen in play). A chest's
# front is its own +Z turned as the chest is (about X, then Y, then Z: the four of Mido's house, turned 0.83 to -0.78
# about Y, face the room's middle so); he is put CHEST_FRONT metres before it, at its height.
CHEST_FRONT = 1.3

# Chests whose front is not where Link can be put. Kokiri Forest's chest in a hollow stump by the bridge to Hyrule
# Field (seen in play, 2026-11-15) is reached on a Magic Bean's leaf: a bean planted there as a child grows the
# four-coloured leaf (Obj_Plant_MagicBeanLeaf_A_03, at -116.1 119.3 -56.4) that carries an adult to the stump. Put by
# the stump, or at the leaf, Link fell out at once (DmF_SY_FallDown; tried without a window); he is put at the forest
# end of that bridge instead (DestinationAnchor ArriveLostWood_LinkWarpPosition), where he stood, a short way from it.
CHEST_GO = {0x3c5bb811b4cf54dd: (-120.5, 114.5, -38.2)}
# The ages a chest is for, where its map files say both and play says one (only the Tracker tab's line: the logic
# asks the same of it). The stump chest is an adult's: only an adult rides the bean's leaf (seen in play, 2026-11-15).
CHEST_AGES = {0x3c5bb811b4cf54dd: "A", 0x292e3ed6acacbe44: "C"}
# A chest's own rule, from placement 10, in place of its area's (RULES asks each overworld chest for what its area's
# hardest did). Hyrule Field's Piece of Heart chest, by the Gerudo Valley exit (the owner's word, 2026-11-16, and Ocarina
# Atlas's "Paradox of the chest from the past"): opened as a child once Link has been an adult (as an adult it is open and
# empty), so it asks for ADULT and the way back to a child: the Forest Temple done (Sheik keeps an adult from going back
# until then: DOOR_SHEIK), which is its own rule, ADULT | {BOW}. With Open Door of Time the way back is free (chest_need).
# Not the Megaton Hammer its area asked for. A child's chest on the Tracker tab (CHEST_AGES).
CHEST_NEEDS = {0x292e3ed6acacbe44: ("adult and back", ADULT, frozenset((BOW,)))}


def chest_need(h, need, open_door):
    """a chest's rule by CHEST_NEEDS (its own, what it asks for always and what only without Open Door of Time), else need"""
    if h not in CHEST_NEEDS:
        return need
    _, always, without_door = CHEST_NEEDS[h]
    return frozenset(always) if open_door else frozenset(always | without_door)


def chest_front(pos, turned, far=CHEST_FRONT):
    """the place `far` metres before a chest: its place and how it is turned (radians about X, Y, Z)"""
    x, y, z = 0.0, 0.0, 1.0
    rx, ry, rz = turned
    y, z = y * math.cos(rx) - z * math.sin(rx), y * math.sin(rx) + z * math.cos(rx)
    x, z = x * math.cos(ry) + z * math.sin(ry), -x * math.sin(ry) + z * math.cos(ry)
    x, y = x * math.cos(rz) - y * math.sin(rz), x * math.sin(rz) + y * math.cos(rz)
    flat = math.hypot(x, z) or 1.0
    return (round(pos[0] + far * x / flat, 1), pos[1], round(pos[2] + far * z / flat, 1))


# ---- Songs: the twelve songs, shuffled among the twelve places that teach one ----
# Each lesson gives its song as a character gives a gift: its flow (Dm_MelodyGet_...) calls the game's
# GetPouchContent with the song's name. So a lesson is a gift whose item is a song (SONGS), and the song it gives is
# changed as a gift's is. The lesson's scene is as it was: its teacher plays the notes of the song the game has there,
# and the scene of the song got names the one the shuffle put there.
# A song is not only named where it is given. The game asks "has Link this song" to know whether a lesson is done
# (the windmill man, Sheik, the Kokiri: IsGet.Item_Melody_..., EventQueryCheckIsGet), the Bolero's lesson sets its
# flag itself before the gift, and the royal tomb's two stones talk as after the lesson once Link has the Sun's Song
# (their AIScheduleParam's ConditionFlag). With the songs shuffled each of these means the lesson, not the song, so
# each is made to name the song its lesson gives now (SONG_FLOWS, SONG_STONES): a song found elsewhere does not shut
# the place that taught it. The flows that play a song (Dm_SY_Ocarina...) are left: there the song is the song.
# Left as the game has them, not looked into: Kakariko's adult logic (Logic/KakarikoVillage_Adult_Common_*, which
# names the Song of Storms' flag and cannot be changed in place), Navi's hints, the Scarecrow's Song.
# The rules: a song that gates the game is a gating item (SONG_GATES), placed by the logic with the others, and only
# in a lesson (place's `bound`). What the rules had folded in is named (song_need): an adult has Zelda's Lullaby (the
# Zoras' and Darunia's doors), Saria's Song (Darunia), the Song of Time (the Door of Time) and, asked for too much
# rather than too little, the Song of Storms (the well, the grottos); the Zoras' places ask for the Lullaby; the
# Shadow Temple for the Nocturne (the only way in), the Spirit Temple and the Colossus for the Requiem (a child's only
# way there); Ganon's Castle for all of them. Epona's Song gates the horseback archery only. The other five gate
# nothing. A lesson asks for what its line says, the songs named: none asks for the song the game teaches there.
ZL, EPONA, SARIA, SUN, TIME, STORMS, MINUET, BOLERO, SERENADE, REQUIEM, NOCTURNE, PRELUDE = SONG_ITEMS = tuple(
    "Item_Melody_" + n for n in ("ZeldaLullaby", "EponaSong", "SariaSong", "SunSong", "TimeSong", "StormSong", "ForestMinuet", "FireBolero",
                                 "WaterSerenade", "SpiritRequiem", "ShadowNocturne", "LightPrelude"))
SONG_GATES = frozenset((ZL, EPONA, SARIA, TIME, STORMS, REQUIEM, NOCTURNE))
SONG_GROWN = frozenset((ZL, SARIA, TIME, STORMS))   # (what an adult's check asks for)
SONG_ADULT = ADULT | {ZL, SARIA, TIME}              # (what an adult's lesson asks for: an adult, without the Song of Storms)
SONG_AREAS = {"ZoraDomain": {ZL}, "ZoraFountain": {ZL}, "InsideJabuJabuBelly": {ZL}, "BottomOfTheWell": {STORMS}, "ShadowTemple": {NOCTURNE},
              "SpiritTemple": {REQUIEM}, "DesertColossus": {REQUIEM}, "InsideGanonCastle": set(SONG_GATES)}
SONG_GIFTS = {"darunia": {ZL, SARIA}, "skull_kid_song": {SARIA}, "archery_heart": {EPONA}, "archery_quiver": {EPONA},
              "fairy_din": {ZL}, "fairy_farore": {ZL}, "fairy_nayru": {ZL}, "fairy_power": {ZL}, "fairy_wisdom": {ZL},
              "fairy_courage": {ZL}}
# Malon's lesson (child, Epona's Song) is shut for good once the Epona quest has moved past its step
# ReadyForGetEponaSong: the ranch's logic (LonLonRanch_Child_NoTerrain_Prefab_5286, Area_9a63) clears the lesson's block
# only at that very step (the other randomizer's finding, OOTRR 856b011, 2026-11-19). With Songs: Anywhere, Epona's Song can
# come from another check, an adult can then call Epona, win her from Ingo and finish the quest before the child ever
# learns from Malon: what her lesson holds is then out of reach. So from placement 15 it asks for everything, as the frogs
# do: it only ever holds what the game can be finished without. (Their fix opens the lesson by a spare flag instead, a
# logic module edit that adds nodes: not built here.)
# SEEN IN PLAY 2026-11-21 (the owner, a new seed, Debug's Add all and adult): Epona won from Ingo in both races and the
# fence jumped (the quest done), then back as a child, Talon woken at the castle, and at the ranch Malon taught and gave the
# seed's item as usual. So the lesson is not shut once the quest is done, and from placement 18 (MALON_FREE_FROM) it asks
# for its own rule again; placements 15-17 keep asking for everything, as their seeds were made.
MALON_HARD = ("song_epona",)
MALON_HARD_FROM = 15
MALON_FREE_FROM = 18
SONGS_HARD = ("frogs",)   # (the frogs ask for six songs: with the songs shuffled, for everything, so no gating item is theirs)
# The frogs' two prizes (bug 132, the owner's run 2026-11-23: the Song of Storms gave the check's item and the ocarina game
# gave it again): MiniGame_FrogTenors gives a Piece of Heart for the Song of Storms (its PlayOcarinaForFrogMiniGame_Melody
# entry: GetInEvent_NotTurn_NotNpc) and another for their game of the five other songs (FrogMiniGame_Insectrepellent and
# FrogMiniGame_RetryFlow: MushiToriGame), the other logic's "ZR Frogs in the Rain" and "ZR Frogs Ocarina Game". Before 27
# one gift made both its item. From FROGS_SPLIT_FROM, "frogs" is the Song of Storms' alone (its entry, and its name) and
# "frogs_game" the game's; with the songs shuffled, the Song of Storms' asks as an adult's check does (the Song of Storms
# with the others, song_need) and the game's for everything (SONGS_HARD_SPLIT).
FROGS_SPLIT_FROM = 27
FROG_STORMS_ENTRY = "PlayOcarinaForFrogMiniGame_Melody"
FROG_STORMS_NAME = "the frogs of Zora's River: the Song of Storms"
SONGS_HARD_SPLIT = ("frogs_game",)
SONGS = (
    Gift("song_zelda", "Dm_MelodyGet_Zelda", (ZL,), ZL, "HyruleCastle", "Impa's lesson: Zelda's Lullaby", CHILD, "songs"),
    Gift("song_epona", "Dm_MelodyGet_Epona", (EPONA,), EPONA, "HyruleField", "Malon's lesson: Epona's Song", CHILD, "songs"),
    Gift("song_saria", "Dm_MelodyGet_Saria", (SARIA,), SARIA, "SacredForestMeadow", "Saria's lesson: Saria's Song", CHILD, "songs"),
    Gift("song_sun", "Dm_MelodyGet_Sun_03", (SUN,), SUN, "Graveyard", "the royal tomb: the Sun's Song", CHILD | {ZL}, "songs"),
    Gift("song_time", "Dm_MelodyGet_Time", (TIME,), TIME, "HyruleField", "the Ocarina of Time: the Song of Time", ADULT | {ZL, SARIA}, "songs"),
    Gift("song_storms", "Dm_MelodyGet_Storm", (STORMS,), STORMS, "KakarikoVillage", "the windmill man: the Song of Storms", SONG_ADULT, "songs"),
    Gift("song_minuet", "Dm_MelodyGet_Forest", (MINUET,), MINUET, "SacredForestMeadow", "Sheik, the meadow: the Minuet of Forest", SONG_ADULT, "songs"),
    Gift("song_bolero", "Dm_MelodyGet_Fire", (BOLERO,), BOLERO, "DeathMountainCrater", "Sheik, the crater: the Bolero of Fire", SONG_ADULT | {HAM}, "songs"),
    Gift("song_serenade", "Dm_MelodyGet_Water", (SERENADE,), SERENADE, "IceCavern", "Sheik, the Ice Cavern: the Serenade of Water", SONG_ADULT, "songs"),
    Gift("song_requiem", "Dm_MelodyGet_Spilit", (REQUIEM,), REQUIEM, "DesertColossus", "Sheik, the Colossus: the Requiem of Spirit", SONG_ADULT | DESERT, "songs"),
    Gift("song_nocturne", "Dm_MelodyGet_Shadow", (NOCTURNE,), NOCTURNE, "KakarikoVillage", "Sheik, Kakariko: the Nocturne of Shadow", SONG_ADULT | MEDALS3, "songs"),
    Gift("song_prelude", "Dm_MelodyGet_Shine", (PRELUDE,), PRELUDE, "Market", "Sheik, the Temple of Time: the Prelude of Light", SONG_ADULT | {BOW}, "songs"),
)
# ---- Songs: how a song looks where it is got (every seed) ----
# A song has an actor of its own (Item_Melody_...), whose model the game left as a green rupee's (Obj_Rupee, in its
# ModelInfo and its row of the list of actors): the original never shows a song as a thing. Got from a chest, bought
# from a shelf or given as a gift, a song was a green rupee (the owner's pictures, 2026-11-15). The owner wants a song
# to look like none of the other items, and not like an ocarina, which is to be shuffled too: so a song looks like
# Sheik's harp (Item_Harp_Sheik, of Dm_Item_Sheik_Harp, the harp of Sheik's lessons). The ModelInfo of each song is
# changed in its pack and in every shelf pack that has a copy of it (the game keeps the first copy it loads), and the
# rows of the songs and of their shelves in the list of actors take the harp's model, size and heaps.
SONG_LOOK = "Item_Harp_Sheik"
# On a shelf the harp lay tipped back and sunk in, only its top bar showing (the owner's picture, 2026-11-15): the
# shelf's fit was the rupee's (its box, read before the songs took the harp's), the rupee standing on its base and the
# harp's model turning about its middle. A quarter turn about X (as the Mirror Shield's) only spun it in its own
# plane (seen without a window, the owner's save in the Bombchu Shop); a quarter turn about the upright stands it up,
# facing out, and it is raised.
# A quarter turn about the upright left it edge-on to Link (the owner's picture, 2026-11-16, the Potion Shop's Bolero of Fire):
# it faces out with no turn, raised as before.
SHELF_TURN.update({song: (0.0, 0.0, 0.0) for song in SONG_ITEMS})
SHELF_LIFT.update({song: 0.3 for song in SONG_ITEMS})
SONG_LOOK_ROW = "Dm_Item_Sheik_Harp"
SONG_LOOK_FILE = "Component/ModelInfo/%s.engine__component__ModelInfo.bgyml"


def song_look_pack(data):
    """A pack with each song's ModelInfo naming the harp (SONG_LOOK): (the new bytes, how many files were changed);
    the same bytes and 0 when it has none. ValueError: a song's ModelInfo that does not name the rupee's model."""
    files = sarc_read(data)
    done = 0
    for song in SONG_ITEMS:
        name = SONG_LOOK_FILE % song
        if name not in files:
            continue
        tree, version = byml_parse(files[name])
        rows = tree[1]
        if tree[0] != "dict" or rows.get("ModelProjectName") not in (("string", "Obj_Rupee"), ("string", SONG_LOOK)):
            raise ValueError("%s's model is not the rupee's as this was written for" % song)
        rows["FmdbName"] = rows["ModelProjectName"] = ("string", SONG_LOOK)
        files[name] = byml_build(tree, version)
        done += 1
    return (sarc_write(files), done) if done else (data, 0)


def song_look_rows(data, names):
    """The list of actors (ActorInfo) with the rows named (the songs', their shelves') taking the harp's model, its
    box and the larger of the two heaps: (the new bytes, how many rows were changed)."""
    tree, version = byml_parse(data)
    by = {r[1]["__RowId"][1]: r for r in tree[1]}
    if SONG_LOOK_ROW not in by:
        raise ValueError("the list of actors has no row of %s" % SONG_LOOK_ROW)
    harp = by[SONG_LOOK_ROW][1]
    done = 0
    for name in names:
        row = by.get(name)
        if not row:
            continue
        rows = row[1]
        for k in ("FmdbName", "ModelProjectName", "ModelAabbMax", "ModelAabbMin"):
            if k in harp:
                rows[k] = harp[k]
        for k in ("InstanceHeapSize", "PreActorRenderInfoHeapSize"):
            if k in rows and k in harp:
                rows[k] = (rows[k][0], struct.pack("<I", max(struct.unpack("<I", rows[k][1])[0], struct.unpack("<I", harp[k][1])[0])))
        done += 1
    return byml_build(tree, version), done


# ---- Songs: Anywhere (rando_songs 2, --songs 2) ----
# A song is an item as any other: bought from a shop's shelf in a test seed, the Sun's Song and Saria's Song had the
# scene of a song learnt and were played after, and worked (seen in play, 2026-11-14). So with Anywhere the twelve
# songs are in the pool with the chests' items, the gifts' and the shelves', and a lesson is a place as a gift is.
# What a lesson may hold is the one thing that is not free. Eight lessons are asked about by name (SONG_ASKED): the
# game knows such a lesson is done by its song's flag (IsGet.<song>: the windmill man, Sheik in the meadow, the royal
# tomb's stones, the sages' scenes, Fado; the Bolero's sets it itself), and those words are made to name what the
# lesson gives now, as in Song spots. So what it gives must be got nowhere else and have that flag under its own
# name: a song, or one of LESSON_ITEMS, when the seed has it once (lesson_items). An upgrade of a family
# (LESSON_FAMILIES) only without Progressive items: with them what is found is not what is put in the pouch, and the
# flag asked about would be another's. The other four (Zelda's Lullaby, Epona's Song, the Song of Time, the Prelude)
# are named by no flow that asks whether they are done, by no logic module and no actor's pack (every file of the
# game was read for the songs' names): the story's own steps keep them, and they hold anything. The list of flags has
# one expression more that reads the Lullaby's flag, by its hash; it reads the song, as it does in Song spots.
# The eight are given the items they may hold that are not songs first, so that as many songs as can be are out in
# the world; when the seed has fewer such items than lessons left, a gating song or item is put in a lesson by the
# logic (place's `only`), and the rest of them hold songs.
# The ocarina's own flow adds the lesson's song when the notes are played back (SONG_PLAY_FLOW). A lesson that gives
# a song adds that song there, as in Song spots; one that gives anything else adds a green rupee there
# (SONG_PLAY_OTHER), so that its item is got once, by the scene, whatever it is.
# NOT SEEN IN PLAY: a lesson that gives something that is not a song; a song from a chest or a character.
# SONGS_ANYWHERE: False holds the choice off (it is then as Song spots, and the launcher does not offer it: its
# RandoNotYet, checked against this by tests/test_rando_settings.py), as REWARDS_READY does the dungeons' rewards.
SONGS_ANYWHERE = True
SONG_ASKED = ("song_saria", "song_sun", "song_storms", "song_minuet", "song_bolero", "song_serenade", "song_requiem", "song_nocturne")
LESSON_ITEMS = ("Item_AgonyStone", "Item_Arrow_Fire", "Item_Arrow_Ice", "Item_Arrow_Light", "Item_Boomerang", "Item_Hammer",
                "Item_DinFire", "Item_FaroreWind", "Item_NayruLove")
LESSON_FAMILIES = ("Item_Hookshot", "Item_Longshot", "Item_BombBag_Small", "Item_BombBag_Medium", "Item_BombBag_Large", "Item_BulletBag_Medium",
                   "Item_BulletBag_Large", "Item_NutBag_Medium", "Item_NutBag_Large", "Item_StickBag_Medium", "Item_StickBag_Large",
                   "Item_Quiver_Medium", "Item_Quiver_Large", "Item_Scale_Silver", "Item_Scale_Gold", "Item_Wallet_Medium", "Item_Wallet_Large")
SONG_PLAY_OTHER = "Obj_Rupee_Green"
# More of them (asked for: "make all songs randomized with progressive items on"; with them a seed had too few items a
# lesson may hold, and about half the songs stayed in lessons). Five items of no family are got once and have the two
# flags, under the name the pouch has them by, not their own (LESSON_NAMED: the item, the name its flags have):
# the Lens of Truth, the two boots, the Mirror Shield and the Kokiri Sword. With them a seed has nine or so items for
# its eight lessons, and every song can be out in the world. A lesson that gives one asks about the flags of that
# name (lesson_flag, song_words).
# LESSON_NAMED_READY: False held them off until it was seen that the game sets those flags when the item is given by
# its own name (a lesson whose flag is never set is taught again and again). Seen without a window, 2026-11-14
# (HOS_OOT_GIVE, HOS_OOT_WATCHFLAG): the Megaton Hammer, the Iron Boots, the Hover Boots, the Lens of Truth, the
# Mirror Shield, the Stone of Agony, the Ice Arrows and the Boomerang, given one by one, each set its IsGet flag at
# once (the boots', the lens's and the shield's by the pouch's names); the Kokiri Sword's was set already, the save
# having one. The flags of the scene, HavePlayedGetEvent, were not set by that giving: a scene sets them.
LESSON_NAMED = {"Item_GlassTruth": "Armor_GlassTruth", "Item_HeavyBoot": "Armor_Adult_HeavyBoot", "Item_HoverBoot": "Armor_Adult_HoverBoot",
                "Item_Shield_Mirror": "Weapon_Shield_Mirror", "Item_Sword_Kokiri": "Weapon_Sword_Kokiri"}
LESSON_NAMED_READY = True


def lesson_flag(item):
    """the name an item's flags have (IsGet.<name>, HavePlayedGetEvent.<name>): its own, or the pouch's for it"""
    return LESSON_NAMED.get(item, item)


def lesson_items(counts, progressive, flagged=None, named=None):
    """the items a lesson that is asked about by name may hold, the songs apart: LESSON_ITEMS, LESSON_NAMED's (named:
    in place of LESSON_NAMED_READY), and LESSON_FAMILIES without Progressive items, that the seed has once (counts:
    {item: how many}) and that `flagged` says yes to (the game's list has the flags of that name; None: not asked)"""
    named = LESSON_NAMED_READY if named is None else named
    names = LESSON_ITEMS + (tuple(LESSON_NAMED) if named else ()) + (() if progressive else LESSON_FAMILIES)
    return frozenset(i for i in names if counts.get(i, 0) == 1 and (flagged is None or flagged(lesson_flag(i))))


# ---- The Great Fairies of the spells (Quest rewards, placement 14; asked for 2026-11-15, "not in the shuffle yet") ----
# Six fountains, each a mark (Obj_TriForcePoint_A_01.._06) where Zelda's Lullaby is played; the mark's flow
# (TriForcePoint) sends Link to its fountain's scene (Dm_FairyFountain_<name>), which gives its item through
# Dm_SY_GetInEvent's call with ActorName, as Darunia's scene does (gift_items). Read 2026-11-19: Death Mountain Trail's
# mark (A_02) plays Din's scene (seen without a window, the Lullaby played on the ocarina: D-pad left, then Y X A Y X A),
# so A_01 Hyrule Castle is the magic's (Power), A_03 Zora's Fountain Farore's, A_04 the crater the double magic's
# (Wisdom), A_05 the Colossus Nayru's, A_06 Ganon's Castle the double defence's (Courage).
# A fountain knows it gave its gift by its item's flag: Din's scene asks IsGet.Item_DinFire, and the mark's flow and
# every fountain's ask each other's (which scene plays, what the fairy says). So a fountain is a lesson asked about by
# name: it may hold only what a lesson may (lesson_items: got nowhere else, with its own flag; a song with Songs:
# Anywhere), and the words IsGet.<its item> and HavePlayedGetEvent.<its item> in the six fountains' flows and the
# mark's are made to name what it gives now (fairy_words), all at once. The other flows that ask whether Link has a
# spell (the owl and the Gorons on the trail, the Business Scrubs, a Gerudo) still ask for the spell itself: they only
# choose what is said. The fountains of the magic and of the double defence stay: magic is no item of the rules'.
# NOT SEEN IN PLAY: a fountain giving another item.
FAIRY_GIFTS = ("fairy_din", "fairy_farore", "fairy_nayru")
FAIRY_FLOWS = ("Dm_FairyFountain_Power", "Dm_FairyFountain_Wisdom", "Dm_FairyFountain_Courage", "Dm_FairyFountain_Din",
               "Dm_FairyFountain_Frore", "Dm_FairyFountain_Nayru", "TriForcePoint")
FAIRY_WORDS = ("IsGet.", "HavePlayedGetEvent.")


def fairy_words(now):
    """{what a fountain's flow names: what it names now} for the fountains whose item changed: now is {a fountain's own
    item: the item it gives}. Each item's flag and its scene's flag, by the name its flags have (lesson_flag)."""
    return {word + old: word + lesson_flag(new) for old, new in now.items() if old != new for word in FAIRY_WORDS}


# ---- Dungeon rewards: the Spiritual Stones and the Medallions (rando_dungeon_rewards, --dungeon-rewards) ----
# Each of eight dungeons ends in a scene that gives its stone or medallion, by the flow the other gifts go through
# (GetPouchContentByActorName, the item's name a string of the scene's flow): the Deku Tree's last words, Darunia on
# the trail, Ruto at the fountain, and the five sages' awakenings (Dm_Awake_*_Get). The Light Medallion is Rauru's, at
# the Temple of Time, and stays: no dungeon ends in it.
# What the game does with them, looked for in every flow, every logic module, every actor's pack and the list of
# flags: nothing asks whether Link holds one. The story's doors go by each dungeon's own quest, an enum of steps that
# ends in Complete (Get_StoneOfForest, _Fire and _Water; SageOfForest, _Fire, _Water, _Shadow and _Spirit: each has an
# expression <its name>_IsCompleted_Exp, and the Bombchu Shop's door is one that asks it). The flag IsGet.<item> of
# each is in the list and no expression reads it. Their names are otherwise in the scenes that show them (the Door
# of Time's three stones, the bridge to Ganon's Castle) and in their own packs and the menu's. So which stone or
# medallion a dungeon gives changes what the Quest screen shows and nothing the rules ask for: none is a gating item.
# 1, Dungeons: the eight are shuffled among the eight endings (bound to them, as the songs are to the lessons).
# 2, Anywhere, is not made yet: as 1.
# An ending asks for what its dungeon asks for (meant to ask for too much). Not in the tracker yet: no place is
# written for them (GIFT_PLACES). Not seen in play yet.
# REWARDS_READY: the setting is held off until its endings are seen in play (its owner's word, 2026-11-13: off in what
# is pushed, on in the work at hand). Off, the script takes the setting as 0 whatever the options file says, and the
# launcher's row says "Not available yet" (RandoNotYet: 1; on: 2, Dungeons offered and Anywhere not). The two are
# kept in step by tests/test_rando_rewards.py.
REWARDS_READY = True
REWARD_ITEMS = ("Item_Stone_Forest", "Item_Stone_Fire", "Item_Stone_Water",
                "Item_Medal_Forest", "Item_Medal_Fire", "Item_Medal_Water", "Item_Medal_Shadow", "Item_Medal_Spirit")
REWARDS = (
    Gift("reward_deku", "Dm_Kokiri_0130", (REWARD_ITEMS[0],), REWARD_ITEMS[0], "KokiriForest", "the Great Deku Tree's ending", CHILD, "rewards"),
    Gift("reward_dodongo", "Dm_DeathMtTrail_0025", (REWARD_ITEMS[1],), REWARD_ITEMS[1], "DeathMountainTrail", "Dodongo's Cavern's ending: Darunia", CHILD | {BB}, "rewards"),
    Gift("reward_jabu", "Dm_ZoraFountain_0030", (REWARD_ITEMS[2],), REWARD_ITEMS[2], "ZoraFountain", "Jabu-Jabu's ending: Ruto", ADULT, "rewards"),
    Gift("reward_forest", "Dm_Awake_Forest_Get", (REWARD_ITEMS[3],), REWARD_ITEMS[3], "ForestTemple", "the Forest Temple's ending: Saria", ADULT | {BOW}, "rewards"),
    Gift("reward_fire", "Dm_Awake_Fire_Get", (REWARD_ITEMS[4],), REWARD_ITEMS[4], "FireTemple", "the Fire Temple's ending: Darunia", ADULT | {HAM, BOW}, "rewards"),
    Gift("reward_water", "Dm_Awake_Water_Get", (REWARD_ITEMS[5],), REWARD_ITEMS[5], "WaterTemple", "the Water Temple's ending: Ruto", ADULT | {IRON, LONG, BOW}, "rewards"),
    Gift("reward_shadow", "Dm_Awake_Shadow_Get", (REWARD_ITEMS[6],), REWARD_ITEMS[6], "ShadowTemple", "the Shadow Temple's ending: Impa", MEDALS3 | {LENS, HOVER}, "rewards"),
    Gift("reward_spirit", "Dm_Awake_Spirit_Get", (REWARD_ITEMS[7],), REWARD_ITEMS[7], "SpiritTemple", "the Spirit Temple's ending: Nabooru", DESERT | {SG, BOW, MS}, "rewards"),
)
# A flow of the game can have a second file, <name>.110.bfevfl.zs, the one a later version of the game added (the five
# awakenings have one each): both are written with the same change (FLOW_TWIN).
FLOW_TWIN = ".110"
# (the flows that name a song where the lesson is meant: the lessons, and who asks whether one is done)
SONG_FLOWS = tuple(g.flow for g in SONGS) + (
    "AllSage", "BottomOfTheWell", "SageOfWater", "Npc_Hylia_007_Adult", "Npc_Hylia_009_Adult", "Npc_Hylia_009_Child", "Npc_Hylia_051_Adult",
    "Npc_Hylia_Sheik_Adult", "Npc_Kokiri_009_Child", "Npc_Kokiri_011_Child", "Npc_Kokiri_012_Child", "Npc_Kokiri_013_Child",
    "Npc_Kokiri_Fado_Child", "Npc_Kokiri_Mido_Child")
# The ocarina's own flow gives a lesson's song too, before the lesson's scene of the song got: when the notes have
# been played back, its two learning entry points add the song of the lesson's kind to the pouch
# (EventTriggerAddOrRemovePouchContent, one step for each song). Found in play: Malon's lesson, shuffled to the Song of
# Storms, gave that and Epona's Song. So those steps are made to add the song the lesson gives now, and only those:
# the rest of that flow is where a song is played, and names the song that is meant.
SONG_PLAY_FLOW = "Dm_SY_Ocarina"
SONG_PLAY_ENTRIES = ("LearningOcarinaPlayAuto", "LearningOcarinaPlayAutoForSeek")
SONG_WORDS = ("", "IsGet.", "HavePlayedGetEvent.")   # (a song's name, its flag, and the flag of its scene)
SONG_STONES = tuple("Component/AIScheduleParam/Obj_Graveyard_Tombstone_A_0%d.game__component__AIScheduleParam.bgyml" % k for k in (1, 2))


def song_need(need, area, key=None):
    """what a check asks for with the songs named (see above). key: a gift's, for the ones that ask for a song of
    their own. A lesson's own line is not put through this: it names its songs itself."""
    need = set(need)
    if need >= ADULT:
        need |= SONG_GROWN
    return frozenset(need | SONG_AREAS.get(area, set()) | SONG_GIFTS.get(key, set()))


def song_words(now):
    """{what a flow names: what it names now} for the songs that changed places: now is {a lesson's own song: the
    song it gives}. Each song's name, its flag and its scene's flag."""
    return {word + old: word + lesson_flag(new) for old, new in now.items() if old != new for word in SONG_WORDS}


def song_stone(data, now):
    """A royal tomb's stone (an AIScheduleParam file) asking for the song its lesson gives now, or None when it does
    not ask for the Sun's Song's flag. now: as song_words'."""
    words = song_words(now)
    tree, version = byml_parse(data)
    found = []

    def walk(node):
        kind, value = node if isinstance(node, tuple) and len(node) == 2 else (None, None)
        if kind == "dict":
            for k, v in list(value.items()):
                if k == "ConditionFlag" and v[0] == "string" and v[1] in words:
                    value[k] = ("string", words[v[1]])
                    found.append(k)
                else:
                    walk(v)
        elif kind == "array":
            for v in value:
                walk(v)

    walk(tree)
    return byml_build(tree, version) if found else None


# ---- Heart Pieces: the Pieces of Heart lying in the world ----
# A Piece of Heart that lies in the world is an actor of its map file, Obj_Heart_Piece (one, in Gerudo Valley, is
# Obj_GerudoValley_Heart_Piece: the same without being lifted). With the setting on some gating items are moved to
# the pieces, where the rules still let the game be finished (gate_skulltulas, as for the Skulltulas), and the chest
# such an item leaves gives a Piece of Heart, as some of the game's do. A piece holds its own piece or a gating
# item, nothing else, and nothing moves without the logic. So until placement 11: from 12 (bug 67) a piece takes part
# as a chest does, its piece in the pool, and gives any item of the pool it may (piece_holds).
# The map is left as it is: the piece lies there, is taken as a piece and stays taken as every piece does. What it
# gives is said in its check's line, and the game's side puts that item in the pouch in the piece's place
# (host/hos_main.c oot_piece_gives). The scene is the piece's: it shows a Piece of Heart and says so.
# Tried first, and left: the item itself lying there, made a pick-up. From the token (as a Skulltula's drop is) it
# was there again each time its map was entered; from the piece too, seen in play (the Megaton Hammer of Zora's
# River); and with the saved truth value of the piece's hash set by the game's own setter, there again all the same.
# The pieces a character gives or a chest holds are not these: they are gifts and chests.
# What a piece asks for: its area's rule, which asks for an adult and more everywhere a piece lies. The one of Lon Lon
# Ranch (HEART_RULES) asks for what a child out of the forest has. None has been walked to.
# RANDO_TEST_HEARTS="<a piece's hash>=<an item> ..." makes that piece that item, for a test.
HEART = "Obj_Heart_Piece"
HEART_ACTORS = (HEART, "Obj_GerudoValley_Heart_Piece")
HEART_RULES = {0x88358af5b5300aa9: CHILD}   # (Lon Lon Ranch, behind the crates)
# (asked 2026-11-23, share/todo.md "Soon": a piece in a stone room gave a purple rupee and looked like a piece.) From fixes
# 93 a piece that gives another item shows that item: an actor of its own for each item (PIECE_LOOK % k), the piece's
# pack with the item's model (piece_variant_pack), the piece's rows of the three lists of actors (its IsRespawn: taken
# once, as a piece is) with the item's model fields (piece_rows), and the piece's map files naming it. Its name for the
# game stays the piece's (ActorNameRef), so the pouch's add is the piece's and the game's side gives the seed's item as
# before. The Gerudo Valley's piece (another actor) keeps its look.
PIECE_LOOK = "Obj_Heart_Piece_R%02d"
# (and a boss's Heart Container that gives another item, the same way from the container's actor: CONTAINER_LOOK)
CONTAINER_LOOK = "Obj_Heart_Container_R%02d"


def piece_variant_pack(item, piece_pack, item_pack, name, base=None):
    """A Piece of Heart's pack made an actor of its own (name) with an item's model: the piece's files and the item's
    (its model's and pose's), the actor the piece's but its model the item's; the item's own pose only where its shelf
    keeps one (SHELF_OWN_POSE), else none (the piece's spin is its own model's). (the pack, the files only it has)"""
    base = base or HEART   # (the piece's actor, or a boss's Heart Container's: CONTAINER)
    piece, own = sarc_read(piece_pack), sarc_read(item_pack)
    if ACTOR_FILE % base not in piece:
        raise ValueError("the piece's pack has no actor of its name")
    chain = actor_chain(item, own)
    if not chain:
        raise ValueError("%s: its pack has no actor of that name" % item)

    def part(key):
        for _, tree, _ in chain:
            ref = tree[1].get("Components", ("dict", {}))[1].get(key)
            if ref and ref[0] == "string" and ref[1]:
                return ref
        return None
    model = part("ModelInfoRef")
    if not model:
        raise ValueError("%s has no model" % item)
    files = collections.OrderedDict(piece)
    for k, v in own.items():
        files.setdefault(k, v)
    tree, version = byml_parse(piece[ACTOR_FILE % base])
    comps = tree[1]["Components"][1]
    comps["ModelInfoRef"] = model
    for key in ("ASInfoRef", "ASRef", "AnimationRef"):
        comps.pop(key, None)
        if item in SHELF_OWN_POSE and part(key):
            comps[key] = part(key)
    files[ACTOR_FILE % name] = byml_build(tree, version)
    return sarc_write(files), [ACTOR_FILE % name]


def piece_rows(data, kind, item, name, base=None):
    """one of the three lists of actors (SHOP_TABLES) with a row for a piece's actor of its own (name): the piece's row,
    its model's fields (ActorInfo) the item's"""
    base = base or HEART
    tree, version = byml_parse(data)
    by = {r[1]["__RowId"][1]: r for r in tree[1]}
    if base not in by or (kind == "ActorInfo" and item not in by):
        raise ValueError("the game's %s has no row of %s" % (kind, base if base not in by else item))
    row = ("dict", collections.OrderedDict(by[base][1]))
    if kind == "ActorInfo":
        row[1].update((k, v) for k, v in by[item][1].items() if k in SHELF_MODEL_FIELDS)
        for k in ("InstanceHeapSize", "PreActorRenderInfoHeapSize"):   # (the larger of the two, as a shelf's)
            if k in row[1] and k in by[item][1]:
                row[1][k] = (row[1][k][0], struct.pack("<I", max(struct.unpack("<I", row[1][k][1])[0],
                                                                  struct.unpack("<I", by[item][1][k][1])[0]) + 32768))
    row[1]["__RowId"] = ("string", name)
    rows = [r for r in tree[1] if r[1]["__RowId"][1] != name] + [row]
    rows.sort(key=lambda r: r[1]["__RowId"][1])
    return byml_build((tree[0], rows), version)


def piece_named(data, renamed, base=None):
    """a map file with the Pieces of Heart of these hashes ({hash: name}) naming their actor of their own: (the file, how many)"""
    tree, version = byml_parse(data)
    n = 0
    for a in tree[1].get("Actors", ("array", []))[1]:
        d = a[1]
        h = d.get("Hash")
        h = h[1] if h else None
        h = struct.unpack("<Q", h)[0] if isinstance(h, bytes) and len(h) == 8 else h
        if d.get("Gyaml", ("", ""))[1] == (base or HEART) and h in renamed:
            d["Gyaml"] = ("string", renamed[h])
            n += 1
    return byml_build(tree, version), n


def heart_rule(h, area):
    """what the Piece of Heart of this hash, lying in this area, asks for"""
    return HEART_RULES.get(h, rule(area, ""))


def hearts(data):
    """The Pieces of Heart lying in a map file: [(hash, place)]."""
    return [(h, pos) for h, gyaml, pos, _, _ in marks(data) if gyaml in HEART_ACTORS and h is not None]


# ---- the bosses' Heart Containers (bug 31, placement 12, with Heart Pieces on) ----
# A boss's Heart Container is an actor of its dungeon's map, Obj_Heart_Container, made when the boss falls; eight, one
# a dungeon (Ganon leaves none). With the Heart Pieces setting on they take part as the lying pieces do: their
# container in the pool, each giving what a piece may give or a container, and asking for what its dungeon's reward
# asks for (REWARDS: the boss beaten). The add of a container gives its heart by itself and the pouch keeps none, so
# the game's side renames that add to the seed's item (host/hos_main.c oot_piece_gives, by the check's name "Heart
# Container, ..."): no heart then, and nothing to take back. Their checks are named by the boss.
CONTAINER = "Obj_Heart_Container"
BOSS_HEARTS = {"InsideTheDekuTree": ("reward_deku", "Gohma"), "DodongoCavern": ("reward_dodongo", "King Dodongo"),
               "InsideJabuJabuBelly": ("reward_jabu", "Barinade"), "ForestTemple": ("reward_forest", "Phantom Ganon"),
               "FireTemple": ("reward_fire", "Volvagia"), "WaterTemple": ("reward_water", "Morpha"),
               "ShadowTemple": ("reward_shadow", "Bongo Bongo"), "SpiritTemple": ("reward_spirit", "Twinrova")}
CONTAINERS_FROM = 12


def boss_hearts(data):
    """The bosses' Heart Containers in a map file: [(hash, place)]."""
    return [(h, pos) for h, gyaml, pos, _, _ in marks(data) if gyaml == CONTAINER and h is not None]


# ---- Lake Hylia's Fire Arrows (asked 2026-11-23, share/todo.md: the other randomizer's "LH Sun") ----
# Shot at the sun from the lake's island, the Fire Arrows come down there (Dm_LakeHrl_0030) and lie on the island, an
# actor of the adult's Hyrule Field map (Obj_Arrow_Fire, SUN_ARROWS). From placement SUN_FROM they take part as a lying
# Piece of Heart does (whatever the Heart Pieces setting): their Fire Arrows in the pool, the spot giving what a piece
# may give, the game's side giving the seed's item when they are picked up (host/hos_main.c, the check's name "Fire
# Arrows, ..."). They keep their own look (the scene binds the actor by its name). Their rule is the other logic's,
# asking for more: an adult with the Bow, the Water Temple done (its boss's rule; the distant Scarecrow's way left out).
SUN_ARROWS = 0x3fd1b7093f47892e
SUN_ACTOR = "Obj_Arrow_Fire"
SUN_ITEM = "Item_Arrow_Fire"
SUN_FOLDER = "HyruleField"
SUN_NAME = "Fire Arrows, the sun's shot from the lake's island"
SUN_FROM = 28


def sun_arrows(data):
    """Lake Hylia's Fire Arrows in a map file: [(hash, place)]"""
    return [(h, pos) for h, gyaml, pos, _, _ in marks(data) if gyaml == SUN_ACTOR and h == SUN_ARROWS]


def boss_need(folder):
    """what the Heart Container of this dungeon asks for: its reward's rule (the boss beaten)"""
    return next(g.need for g in REWARDS if g.key == BOSS_HEARTS[folder][0])


def check_name(kind, item, about, pos, exits=(), parts=()):
    """A check's name. kind: "Chest" or "Gold Skulltula". item: what a chest held. about: what its actor says
    ({"big", "room", "night", "soil"}). exits: [(place, where it leads)] and parts: [(place, how far it reaches, its
    name)] of its area's maps."""
    if kind == "Chest":
        name = ("Big chest" if about.get("big") else "Chest") + (" (%s)" % (ITEM_WORDS.get(item) or spaced(item)) if item else "")
    else:
        name = kind + (", night" if about.get("night") else "") + (", bean soil" if about.get("soil") else "")
    if isinstance(about.get("room"), int):
        return name + ", room %d" % about["room"]
    if len(pos) != 3:
        return name
    inside = sorted((math.hypot(pos[0] - p[0], pos[2] - p[2]), words) for p, reach, words in parts if math.hypot(pos[0] - p[0], pos[2] - p[2]) < reach)
    if inside:
        return name + ", " + AREA_NAMES.get(inside[0][1], spaced(inside[0][1]))
    near = sorted((math.dist(pos, p), words) for p, words in exits if math.dist(pos, p) < EXIT_NEAR)
    return name + (", by the %s exit" % AREA_NAMES.get(near[0][1], spaced(near[0][1])) if near else "")


# A character's gift has no actor of a map, and so no truth value of its own in a save for the tracker's mark
# (host/hos_main.c: a check with an actor's hash is marked by the value the game keeps for that hash). The game keeps
# a second value for every actor that drops something, by its hash ^ 2 (a chest has one), and was not seen to set a
# chest's: without a window, a chest of Mido's house opened, its second value stayed false, and a chest with it set
# stood shut as before. So each gift borrows the second value of a chest (gift_keys), and its line of the checks
# file has that in the hash's place: the game's side marks it there as it does a chest.
GIFT_KEY = 2


def gift_keys(gifts, chests):
    """{a gift's hash: the key its mark is kept by}: the chests' hashes ^ GIFT_KEY, in order, for the gifts in order.
    ValueError: more gifts than chests."""
    gifts, chests = sorted(gifts), sorted(chests)
    if len(gifts) > len(chests):
        raise ValueError("%d gifts and %d chests to keep their marks by" % (len(gifts), len(chests)))
    return {g: c ^ GIFT_KEY for g, c in zip(gifts, chests)}


CHECK_NEED = 191   # (a check's rule in the tracker's file: the menu's needs[192] and the game's side's)


def key_codes(way):
    """the tracker's letters of the keys a way of a rule asks for (Small keys and Boss Keys: Anywhere, 2026-11-24):
    "K<n>" all the moving small keys of DUNGEON_FOLDERS[n], "B<n>" its Boss Key. The Tracker tab holds one when every
    check of dungeon_items.txt giving that dungeon's key is collected (gpu/vk/vk_menu.cpp tracker_key_held)"""
    out = set()
    for word in way:
        if isinstance(word, str) and "@" in word:
            item, owner = word.split("@")[0], word.split("@")[1].split("#")[0]
            if owner in DUNGEON_FOLDERS and item in (SMALL_KEY, BOSS_KEY):
                out.add(("K" if item == SMALL_KEY else "B") + str(DUNGEON_FOLDERS.index(owner)))
    return sorted(out)


def rule_text(way):
    """one way of a rule as the tracker's file writes it"""
    return ",".join([code for item, code in CHECK_CODES.items() if item in way] + token_codes(way) + key_codes(way)) or "-"


def fit_rule(need):
    """a rule with no more ways than the tracker reads (CHECK_NEED letters): the fewest-item ways kept first. A way left
    out only asks for more, never less (placement 21, where a dungeon's ways and its ways in multiply)"""
    if not isinstance(need, Either):
        return need
    kept, size = [], -1
    for way in sorted(need, key=lambda w: (len(w), sorted(w))):
        text = len(rule_text(way)) + 1
        if kept and size + text > CHECK_NEED:
            continue
        kept.append(way)
        size += text
    return either(kept)


# Where the Tracker's maps put a check, when its own place is not where it is gone to (asked 2026-11-24): a grotto's chest
# lies at the grotto's own place, under the ground, so its dot is put at the grotto's way in, where the owner found it.
# The line's last field (where Go there puts Link) keeps the chest's own place; the game marks a chest by its opened flag,
# not by its place, so it is still marked when opened. Kokiri Forest's Song of Storms grotto: the owner's screenshot,
# Link at its soft soil, measured on the minimap (Kokiri Forest's fit).
CHECK_PLACE = {0xcda7447b91ab4dba: (-49.5, 103.6, -59.5)}
# Where Go there puts Link for a Gold Skulltula whose own place is on a wall he can't be put in (bug 117, the owner's run
# 2026-11-23: Link stuck behind a wall, or fallen out of the world). Each is a floor spot found without a window, Link put
# at eight points 2.5 from the Skulltula and logged where he came to rest (2026-11-24): Dodongo's Cavern's room 2
# (the Scarecrow's ledge: he stood at 103.5-104.1 on each side but one; the picture: on the floor, the web before him),
# Zora's Fountain's night #2 (it hangs above a cave's mouth: the points that stayed at its height were in the rock above
# the cave, dark pictures and a "Let Go"; those in front came down 8 to the open snow before the cave, both ages, where
# the pictures show him standing), and the grotto by Lon Lon Ranch (its Skulltula is high on the grotto's wall: every
# point came down to the floor at about 123.5).
SKULL_GO = {0x0d53e429a1ef383d: (56.5, 104.0, -18.2), 0x845ba51dc18c855e: (82.7, 126.5, 9.5),
            0xa6a4e87da18fa678: (-147.9, 124.0, 324.9)}


def check_lines(chests, skulls, gifts=()):
    """The checks file's lines. chests, skulls and gifts: [(area (the Banc folder), position, ages, what its rule asks
    for, its name, its actor's hash)]; a chest or a Gold Skulltula without a name is "Chest" or "Gold Skulltula". The
    name is the line's kind; those of an area that are the same are numbered, by place. By the area's name, the
    chests first, then the Gold Skulltulas, then the gifts, each by name; no more than the menu keeps. After what the
    rules ask for a line may have two more fields: its actor's hash, 16 hexadecimal digits ("-" without one), and
    the item it gives (a seventh of a tuple): the game's side marks a check collected when its item is given near it.
    A line with neither ends after what the rules ask for. An eighth of a tuple is where Link is put to go to the
    check, when that is not the check's own place (a chest's front): a field more, "x y z"."""
    rows = []
    for order, plain, those in ((0, "Chest", chests), (1, "Gold Skulltula", skulls), (2, "", gifts)):
        for area, pos, ages, need, *more in those:
            if len(pos) != 3 or not ages:
                continue
            name = more[0] if more else plain
            if len(more) > 1 and more[1] in CHECK_PLACE:   # (its dot at the way in; Go there to its own place: CHECK_PLACE)
                more = list(more) + [None] * (4 - len(more))
                more[3] = more[3] or tuple(pos)
                pos = CHECK_PLACE[more[1]]
            rows.append([AREA_NAMES.get(area, area).replace("|", "/")[:47], (name[:1].upper() + name[1:]).replace("|", "/"), area, ages, pos,
                         "/".join(rule_text(way) for way in (need if isinstance(need, Either) else (need,))),
                         order, more[1] if len(more) > 1 else None,
                         more[2] if len(more) > 2 else "", more[3] if len(more) > 3 else None])
    too_long = [r for r in rows if len(r[5]) > CHECK_NEED]
    if too_long:   # (the menu's and the game's side read a rule of CHECK_NEED letters, commas and slashes at most)
        raise ValueError("a rule of %s is %d letters long, more than the %d the tracker reads" % (too_long[0][1], len(too_long[0][5]), CHECK_NEED))
    rows.sort(key=lambda r: (r[0].lower(), r[6], r[1], r[4]))
    if len(rows) > CHECK_ROWS:   # (the last areas' checks would be cut off without a word, as Zora's were, bug 85)
        print("warning: %d checks, more than the %d the Tracker keeps: %s and after are left out of it" % (len(rows), CHECK_ROWS, rows[CHECK_ROWS][0]),
              file=sys.stderr)
    same = collections.Counter((r[0], r[1]) for r in rows if r[1] not in ("Chest", "Gold Skulltula"))
    count = collections.Counter()
    for r in rows:
        if same[(r[0], r[1])] > 1 and r[6] < 2:   # (gifts of one place are told apart by their names already)
            count[(r[0], r[1])] += 1
            r[1] = r[1][:CHECK_NAME - 4] + " #%d" % count[(r[0], r[1])]
        r[1] = r[1][:CHECK_NAME]
    return ["# The checks of this seed, one by one, for the Tracker tab: <area>|<kind>|<folder>|<ages>|<x> <y> <z>|<the rules ask for>[|<the actor's hash>[|<the item it gives>[|<where Link is put>]]]"] + [
        "%s|%s|%s|%s|%.1f %.1f %.1f|%s%s%s%s" % (name, kind, area, ages, pos[0], pos[1], pos[2], need,
                                                 "" if key is None and not given and not stand else "|-" if key is None else "|%016x" % key,
                                                 "|" + given if given else "|-" if stand else "", "|%.1f %.1f %.1f" % tuple(stand) if stand else "")
        for name, kind, area, ages, pos, need, _, key, given, stand in rows[:CHECK_ROWS]]


# ---- Hints from the Gossip Stones (rando_hints, asked for 2026-11-18) ----
# A stone says the line of its own name (GossipStone's flow: EventTalkWithInstanceNameLabel), GOSSIP_<AREA>_<N> of
# EventFlowMsg/GossipStone.msbt; 40 such names stand in the maps (the Lost Woods' second is in Kokiri Forest too, and a
# few stand in the area next to their name's: Lake Hylia's three are in Hyrule Field). No Mask of Truth is asked for:
# without it worn the stone's talk goes to its line. Each hint is said by HINT_STONES stones. Three kinds (the owner's
# list): where a gating item is; an area "on the way of the hero" (it holds an item the seed's logic gates the game
# with); an area that is "foolish" (it holds none, nor a Skulltula token). HINT_FOOLISH and HINT_WAY of those two, the
# rest of the item kind. Chosen by a random of their own (HINT_RANDOM): the items' places are not touched, and a seed
# made before the hints keeps its shuffle (the hints are on the stamp's second line, the fixes').
HINT_TEXT = "EventFlowMsg/GossipStone.msbt"
HINT_PREFIX = "GOSSIP_"
HINT_NOT = ("GOSSIP_RumorCommon_",)   # (the closing words every stone says after its line)
HINT_STONES, HINT_FOOLISH, HINT_WAY = 2, 4, 5
HINT_WIDTH = 56          # (characters a line of the stone's box holds, as its own lines: about 60)
HINT_RANDOM = "hints:%d"
HINTS_FILE = "rando_hints.txt"
HINTS_VERSION = 1   # (on the stamp: a change of what the hints say writes a seed's stones again)
HINT_WORDS = {
    "Item_Melody_ZeldaLullaby": "Zelda's Lullaby", "Item_Melody_EponaSong": "Epona's Song", "Item_Melody_SariaSong": "Saria's Song",
    "Item_Melody_SunSong": "the Sun's Song", "Item_Melody_TimeSong": "the Song of Time", "Item_Melody_StormSong": "the Song of Storms",
    "Item_Melody_ForestMinuet": "the Minuet of Forest", "Item_Melody_FireBolero": "the Bolero of Fire",
    "Item_Melody_WaterSerenade": "the Serenade of Water", "Item_Melody_SpiritRequiem": "the Requiem of Spirit",
    "Item_Melody_ShadowNocturne": "the Nocturne of Shadow", "Item_Melody_LightPrelude": "the Prelude of Light",
    "Obj_Armor_Goron": "the Goron Tunic", "Obj_Armor_Zora": "the Zora Tunic", "Item_Bottle": "a bottle",
    "Item_Scale_Silver": "the Silver Scale", "Item_Scale_Gold": "the Golden Scale", "Item_Wallet_Medium": "the Adult's Wallet",
    "Item_Wallet_Large": "the Giant's Wallet", "Item_Gauntlet_Goron": "the Goron's Bracelet",
    "Item_BombBag_Small": "a Bomb Bag", "Item_Range_Bow": "the Fairy Bow", "Item_Range_SlingShot": "the Fairy Slingshot",
    # (bug 116, the owner's seed 2026-11-23: "the Fairy Bless MPDouble". The rest by the game's own names, PouchContent's
    #  <item>_Name, where the item's file name was said in their place)
    "Item_FairyBless_MPDouble": "the gift of doubled magic", "Item_FairyBless_MP": "the gift of improved spin",
    "Item_FairyBless_DefenseDouble": "the gift of halved damage", "Item_MagicMeter": "magic power",
    "Item_DinFire": "Din's Fire", "Item_FaroreWind": "Farore's Wind", "Item_NayruLove": "Nayru's Love",
    "Item_Arrow_Fire": "the Fire Arrows", "Item_Arrow_Ice": "the Ice Arrows", "Item_Arrow_Light": "the Light Arrows", "Item_AgonyStone": "the Echo Gem",
    "Item_Hookshot": "the Hookshot", "Obj_Heart_Container": "a Heart Container",
    "Item_BombBag_Medium": "a Bigger Bomb Bag", "Item_BombBag_Large": "the Biggest Bomb Bag",
    "Item_BulletBag_Medium": "a Bigger Deku-Seed Bag", "Item_BulletBag_Large": "the Biggest Deku-Seed Bag",
    "Item_Quiver_Medium": "a Bigger Quiver", "Item_Quiver_Large": "the Biggest Quiver",
    "Item_NutBag_Medium": "a Bigger Deku-Nut Bag", "Item_StickBag_Medium": "a Bigger Deku-Stick Bag",
    "Item_BombchuBundle_Large": "20 Bombchus", "Item_Bombchu": "Bombchus", "Obj_Token_Gold": "a Skulltula token",
    "Obj_Rupee_Green": "a green rupee", "Obj_Shield_Deku": "a Deku Shield",
    "Item_Stone_Forest": "the Kokiri Emerald", "Item_Stone_Fire": "the Goron Ruby", "Item_Stone_Water": "the Zora Sapphire",
    "Item_Medal_Forest": "the Forest Medallion", "Item_Medal_Fire": "the Fire Medallion", "Item_Medal_Water": "the Water Medallion",
    "Item_Medal_Shadow": "the Shadow Medallion", "Item_Medal_Spirit": "the Spirit Medallion",
}


def msbt_labels(data):
    """the labels of a text file (MSBT), in no order"""
    out, at = [], 0x20
    for _ in range(struct.unpack_from("<H", data, 0x0e)[0]):
        kind, size = data[at:at + 4], struct.unpack_from("<I", data, at + 4)[0]
        body = at + 0x10
        if kind == b"LBL1":
            for g in range(struct.unpack_from("<I", data, body)[0]):
                n, off = struct.unpack_from("<II", data, body + 4 + 8 * g)
                p = body + off
                for _k in range(n):
                    ln = data[p]
                    out.append(bytes(data[p + 1:p + 1 + ln]).decode("utf-8", "replace"))
                    p += 1 + ln + 4
        at = body + (size + 15 & ~15)
    return out


def hint_item(item):
    """an item's name in a hint"""
    if item in HINT_WORDS:
        return HINT_WORDS[item]
    if item in ITEM_WORDS:
        words = ITEM_WORDS[item]
        return words if words[:1].islower() else "the " + words
    return "the " + spaced(item)


HINT_THE = frozenset(("LostWood", "Market", "Graveyard", "HountedWasteland", "InsideTheDekuTree", "BottomOfTheWell", "ForestTemple",
                      "FireTemple", "IceCavern", "WaterTemple", "ShadowTemple", "SpiritTemple", "GerudoTrainingGround", "DesertColossus"))
HINT_NEVER = frozenset(("DreamWorld",))   # (the boss-rematch area: nothing there is kept, the owner, 2026-11-12)


def hint_area(area):
    """an area's name in a hint, with "the" where it is said so"""
    return ("the " if area in HINT_THE else "") + AREA_NAMES.get(area, spaced(area))


def hint_wrap(words, width=HINT_WIDTH):
    """the words broken into lines of at most `width` characters (a word longer stays whole)"""
    lines = [""]
    for w in words.split():
        if lines[-1] and len(lines[-1]) + 1 + len(w) > width:
            lines.append(w)
        else:
            lines[-1] = (lines[-1] + " " + w).strip()
    return "\n".join(lines)


def choose_hints(rng, held, gating, labels, foolish=HINT_FOOLISH, way=HINT_WAY, each=HINT_STONES):
    """[(label, words)]: each hint said by `each` of the stones' labels. held: [(area, item, moved)] of every check of
    the seed (moved: the shuffle put the item there); gating: the items the logic gates the game with. The item hints
    name a moved gating item, each once; way areas hold a gating item; foolish areas hold none and no token."""
    labels = sorted(labels)
    count = len(labels) // each
    held = [(area, item, moved) for area, item, moved in held if area not in HINT_NEVER]
    areas = sorted({area for area, _, _ in held})
    gated = sorted({area for area, item, _ in held if item in gating})
    empty = [area for area in areas if area not in gated and not any(a == area and item == TOKEN for a, item, _ in held)]
    ways = rng.sample(gated, min(way, len(gated), count))
    fools = rng.sample(empty, min(foolish, len(empty), count - len(ways)))
    items = sorted({(item, area) for area, item, moved in held if moved and item in gating})
    rng.shuffle(items)
    named, picked = set(), []
    for item, area in items:
        if item not in named and len(picked) < count - len(ways) - len(fools):
            named.add(item)
            picked.append((item, area))
    hints = (["They say that %s can be found in %s." % (hint_item(i), hint_area(area)) for i, area in picked] +
             ["They say that %s is on the way of the hero." % hint_area(area) for area in ways] +
             ["They say that it is foolish to look in %s." % hint_area(area) for area in fools])
    rng.shuffle(labels)
    return [(label, hints[k // each]) for k, label in enumerate(labels[:len(hints) * each])]


HINT_FLOW = "Event/EventFlow/GossipStone.bfevfl.zs"
HINT_TALK, HINT_RUMOR = "Talk", "InitTalk_GossipStone"


def stone_talk_open(data):
    """GossipStone's flow (HINT_FLOW) with its Talk's first question, the Mask of Truth in the pouch (worn or not), made
    to lead to the stone's line whatever the answer: every case of that switch to the subflow HINT_RUMOR, the way to
    the line said by the stone's name. Without it a stone talked to without the mask has only Navi's words (seen
    without a window, 2026-11-19). The new bytes, of the same size; ValueError: not the flow known."""
    u16 = lambda at: struct.unpack_from("<H", data, at)[0]
    u64 = lambda at: struct.unpack_from("<Q", data, at)[0]
    if data[:6] != b"BFEVFL" or u16(0x20) != 1:
        raise ValueError("not an event flow file of one flowchart")
    chart = u64(u64(0x28))
    count, events, nent = u16(chart + 0x16), u64(chart + 0x30), u16(chart + 0x18)
    names, entries = u64(chart + 0x38), u64(chart + 0x40)
    text = lambda ptr: bytes(data[ptr + 2:ptr + 2 + u16(ptr)]).decode("utf-8", "replace") if 0 < ptr < len(data) - 2 else ""
    start = next((u16(entries + 0x20 * k + 0x1C) for k in range(nent) if text(u64(names + 8 + 16 * (k + 1) + 8)) == HINT_TALK), None)
    rumor = [i for i in range(count) if data[events + 0x30 * i + 8] == 4 and text(u64(events + 0x30 * i + 0x20)) == HINT_RUMOR]
    if start is None or len(rumor) != 1:
        raise ValueError("no entry %s, or not one subflow %s" % (HINT_TALK, HINT_RUMOR))
    e = events + 0x30 * start
    if data[e + 8] not in (1, 5):
        raise ValueError("the entry %s does not start with a question" % HINT_TALK)
    out, cases = bytearray(data), u64(e + 0x18)
    for c in range(u16(e + 0x0A)):
        struct.pack_into("<H", out, cases + 8 * c + 4, rumor[0])
    return bytes(out)


HINT_HEARD_FLAG = "GossipStone_NaviTalk_Temporary"   # (the game's own, set by its Navi talk: passed over with the hints on)
HINT_SAY = "EventTalkWithInstanceNameLabel"
HINT_STONE_ACTOR = "Obj_GossipStone"


def stone_heard_flow(data):
    """GossipStone's flow (after stone_talk_open) with the stone's line said after HINT_HEARD_FLAG is set (a copy of the
    flow's own step that sets it), for the Tracker's row of the hints heard: the game's side sees the flag, puts it out
    and keeps the stone nearest Link (host/hos_main.c oot_stone_heard). The new bytes; ValueError: not the flow known."""
    import copy
    import io
    evfl = evfl_module()
    flow = evfl.EventFlow()
    flow.read(data)
    fc = flow.flowchart
    says = [e for e in fc.events if isinstance(e.data, evfl.ActionEvent) and e.data.actor_action.v.v == HINT_SAY]
    sets = [e for e in fc.events if isinstance(e.data, evfl.ActionEvent) and e.data.actor_action.v.v == "EventTriggerSetGameDataBool"
            and e.data.params and e.data.params.data.get("GameDataName") == HINT_HEARD_FLAG]
    if len(says) != 1 or not sets or any(e.name == "WillowStoneHeard" for e in fc.events):
        raise ValueError("not one step that says the stone's line and one that sets %s, or changed already" % HINT_HEARD_FLAG)
    say = says[0]
    mark = evfl.Event()
    mark.name = "WillowStoneHeard"
    mark.data = evfl.ActionEvent()
    mark.data.actor.v, mark.data.actor_action.v = sets[0].data.actor.v, sets[0].data.actor_action.v
    mark.data.params = copy.deepcopy(sets[0].data.params)
    mark.data.params.data["Value"] = True
    mark.data.nxt.v = say
    for e in fc.events:   # (every way to the line goes through the mark first)
        d = e.data
        if hasattr(d, "nxt") and d.nxt.v is say:
            d.nxt.v = mark
        for case in getattr(d, "cases", {}).values():
            if case.v is say:
                case.v = mark
        for fork in getattr(d, "forks", []):
            if fork.v is say:
                fork.v = mark
    for entry in fc.entry_points:
        if entry.main_event.v is say:
            entry.main_event.v = mark
    fc.events.append(mark)
    out = io.BytesIO()
    flow.write(out)
    return out.getvalue()


def stone_places(romfs, zs, dicts, read=None):
    """{(a Gossip Stone's name (its line's label), its map folder): (x, y, z)} from the maps (Banc/<folder>/*.bcett.byml.zs;
    a stone in a child's and an adult's map is the same stone; a few stand in two folders). read: the seed's changed
    files, by path, first."""
    out = {}
    root = os.path.join(romfs, "Banc")

    def walk(node, folder):
        kind, value = node if isinstance(node, tuple) and len(node) == 2 else (None, None)
        if kind == "dict":
            gy, name, at = value.get("Gyaml"), value.get("Name"), value.get("Translate")
            if gy and gy[0] == "string" and gy[1].startswith(HINT_STONE_ACTOR) and name and name[0] == "string" and at and at[0] == "array":
                pos = tuple(struct.unpack("<f", v[1][:4])[0] if isinstance(v[1], (bytes, bytearray)) else float(v[1]) for v in at[1][:3])
                out.setdefault((name[1], folder), pos)
            for v in value.values():
                walk(v, folder)
        elif kind == "array":
            for v in value:
                walk(v, folder)
    for folder in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        here = os.path.join(root, folder)
        for n in sorted(os.listdir(here)) if os.path.isdir(here) else []:
            if not n.endswith(".bcett.byml.zs"):
                continue
            rel = "Banc/%s/%s" % (folder, n)
            raw = (read or {}).get(rel) or unpack(open(os.path.join(here, n), "rb").read(), zs, dicts)
            if HINT_STONE_ACTOR.encode() not in raw:
                continue
            walk(byml_parse(raw)[0], folder)
    return out


def hint_line(data, label, words):
    """the text file with the stone's line `label` saying `words`: its opening tags (the box, the voice, the colour)
    kept, the rest of the line made the words (msbt_set)"""
    start, end = msbt_text(data, label)
    old, at = data[start:end], 0
    while at + 7 <= len(old) and old[at] == 0x0e:
        at += 7 + struct.unpack_from("<H", old, at + 5)[0]
    return msbt_set(data, label, bytes(old[:at]) + hint_wrap(words).encode("utf-8"))


# ---- Skulltula House hints (rando_house_hints, asked 2026-11-23) ----
# The cursed man of Kakariko's House of Skulltula says what the next reward asks for ("If you collect a total of 20
# tokens...", GatheringTokenGold's NextGoal: Talk_28 for 10, Talk_23 to _26 for 20 to 50; he says it at almost every
# talk). With the setting each of those lines goes on, after a page of its own, with what each reward of 10 to 50
# tokens gives in this seed (the rewards are gifts of Quest rewards: their items as the Gossip Stones name them,
# hint_item; without Quest rewards the game's own). The 100 tokens' line (Talk_27, every reward had) is left: the list
# is no use then. English in every language, as the stones' hints. Moves no item. NOT SEEN IN PLAY.
HOUSE_HINT_TEXT = "EventFlowMsg/Npc_SkullDad.msbt"
HOUSE_HINT_LABELS = ("Talk_28", "Talk_23", "Talk_24", "Talk_25", "Talk_26")
HOUSE_HINT_PAGE = b"\x0e\x00\x00\x04\x00\x00\x00"   # (a new page of the box: the tag the man's own lines have between pages)
HOUSE_HINT_ROWS, HOUSE_HINT_WIDTH = 3, 50   # (lines in a page of his box, characters in a line: as his own lines)
HOUSE_HINT_HEAD = "My children will reward you so:"


def house_hint_pages(rewards):
    """the pages of the list, from {tokens: item}: the head and one line a reward ("10 tokens: the Giant's Wallet"),
    no reward's line split between pages"""
    def name(item):
        w = hint_item(item)
        return "a " + w if w.endswith(" rupee") and not w.startswith(("a ", "an ", "the ")) else w   # ("a purple rupee")
    entries = [HOUSE_HINT_HEAD] + ["%d tokens: %s" % (n, name(rewards[n])) for n in sorted(rewards)]
    pages = [[]]
    for words in entries:
        lines = hint_wrap(words, HOUSE_HINT_WIDTH).split("\n")
        if pages[-1] and len(pages[-1]) + len(lines) > HOUSE_HINT_ROWS:
            pages.append([])
        pages[-1] += lines
    return ["\n".join(p) for p in pages]


def house_hint_line(data, label, pages):
    """the text file with the line `label` going on with `pages` (house_hint_pages), each after a new page. ValueError:
    no such line, or it has a list already"""
    start, end = msbt_text(data, label)
    old = bytes(data[start:end])
    if old.endswith(b"\0"):
        old = old[:-1]
    if HOUSE_HINT_HEAD.encode() in old:
        raise ValueError("%s has the rewards' list already" % label)
    return msbt_set(data, label, old + b"".join(HOUSE_HINT_PAGE + p.encode("utf-8") for p in pages))


# ---- Either age's items (rando_ageless, asked for 2026-11-18) ----
# The menu's rule of which age may equip or set an item is the pouch table's (UI/Pouch/PouchTable): each item of its
# Equipment and Item arrays is marked IsUsableAdult and IsUsableChild (a mark left out is false). 1, the swords: the
# Kokiri Sword and the Master Sword for both ages (seen by the owner: a sword kept through a Debug age change is drawn and
# swings as it should). 2, also the age-only items: the shields, the boots, the Biggoron's sword, the Slingshot, the
# Boomerang, Deku Sticks, the Hammer, the Hookshots, the Bow and its arrows. Moves no item; the logic does not count on
# it (a child's way to an adult's check is not asked about).
AGELESS_TABLE = "UI/Pouch/PouchTable/PouchTable.game__ui__PouchTable.bgyml"
AGELESS_SWORDS = ("Weapon_Sword_Master", "Weapon_Sword_Kokiri")
# (the owner's tests 2026-11-20 took out what a child can set and not use: the Biggoron's Sword (no swing: its clips are
# in files not lent), the boots (the d-pad's boots did nothing: his model has no boots' parts, the adult's
# EquipmentUserParam hides G_Boots for them), and the magic arrows (fire arrows crashed in the Deku Tree: his Bow shoots
# Deku Seeds, EquipmentUserParam's ArrowActorName, which have no ShootableArrow_ArrowType to make fire of). These were
# the adult's alone, so taking them out changes nothing for him)
AGELESS_NOT_CHILD = ()
# (the two-handed swords back for the child, asked 2026-11-20: their swings are the LSword clips of Player_Adult_02 (53
# attacks) and _03 (the charged and jump attacks), lent to him with the others, AGELESS_ANIMS)
AGELESS_BIGGORON = ("Weapon_Sword_Biggoron", "Weapon_Sword_Giant", "Weapon_Sword_BrokenGiant")
# (the boots back for the child, 2026-11-20: set from the Equipment page, their effects are to be tried without his
# model's boots (the d-pad's change did nothing: the game's own player code, f_805dbde0 and around, not his files))
AGELESS_BOOTS = ("Armor_Adult_HoverBoot", "Armor_Adult_HeavyBoot")
# (the tunics for the child, asked 2026-11-20: the game's side lets their kind (8, EquipArmor) through the same four IsChild
# stops as the boots', host/oot_rando.c hos_oot_boots_child; their effect is the tunic slot's actor, f_80c225d0, no age asked.
# A setting of their own since 2026-11-21, rando_ageless_tunics (the owner: a child may want them without the other
# age's items): a.ageless's bit 4, not among AGELESS_ITEMS)
AGELESS_TUNICS = ("Armor_Adult_Goron", "Armor_Adult_Zora")
AGELESS_ITEMS = AGELESS_SWORDS + (
    "Weapon_Shield_Mirror", "Weapon_Shield_Deku", "Item_DekuStick", "Weapon_Range_SlingShot", "Item_Boomerang", "Item_Hammer",
    "Item_Longshot", "Item_Hookshot", "Item_Arrow_Normal", "Weapon_Range_Bow", "Item_Arrow_Fire", "Pouch_Range_BowAndArrow_Fire",
    "Item_Arrow_Ice", "Pouch_Range_BowAndArrow_Ice", "Item_Arrow_Light", "Pouch_Range_BowAndArrow_Light") + AGELESS_BOOTS + \
    AGELESS_BIGGORON
# (the child's arrows: his EquipmentUserParam names Shootable_DekuSeed as ArrowActorName, what every shot of his is,
# whichever weapon; the adult's names none, and each weapon's BowParam names its own: the Bow's NormalArrow, the
# Slingshot's Shootable_DekuSeed. Without the child's, his Bow shoots arrows (fire arrows need one: a Deku Seed has no
# ShootableArrow_ArrowType, the crash on a spider web, bug 90) and his Slingshot seeds)
AGELESS_ARROWS = ("Component/EquipmentUserParam/Player_Child.game__component__EquipmentUserParam.bgyml", "ArrowActorName")


def ageless_arrows(pack):
    """the child's pack with his EquipmentUserParam's ArrowActorName taken out: (the new pack, 1 if it was there)"""
    rel, key = AGELESS_ARROWS
    parts = sarc_read(pack)
    tree, version = byml_parse(parts[rel])
    if tree[0] != "dict":
        raise ValueError("%s is not a dictionary" % rel)
    if key not in tree[1]:
        return pack, 0
    del tree[1][key]
    parts[rel] = byml_build(tree, version)
    return sarc_write(parts), 1
AGELESS_ARRAYS = ("EquipmentArray", "ItemArray")


# Each Link's moves are clips of his own animation files (Model/Player_<age>_NN_Animation): the child's hold no Bow, Hammer,
# Hookshot, two-handed sword or boots clips, the adult's no Slingshot, Boomerang or Deku Stick ones (counted 2026-11-20;
# the owner saw it too: young Link holds the Biggoron's Sword and the attack button does nothing). Both Links play one
# animation graph (AS/Player_*.root.asb: the same) on skeletons of the same bone names, so with the age-only items each is
# lent the other's files that hold those clips, after his own (his own clips found first): Adult 01 the Bow, 02_H the
# Hammer, the Hookshots and the boots; Child 01 the Boomerang and Deku Sticks, 03 the Slingshot.
AGELESS_ANIMS = {
    "Player_Child": ("Component/AnimationParam/Player_Child.engine__component__AnimationParam.bgyml",
                     ("Player_Adult_01_Animation", "Player_Adult_02_H_Animation", "Player_Adult_02_Animation",
                      "Player_Adult_03_Animation")),
    "Player_Adult": ("Component/AnimationParam/Player.engine__component__AnimationParam.bgyml",
                     ("Player_Child_01_Animation", "Player_Child_03_Animation")),
}


# (the owner's test 2026-11-20: with the clips lent, and loaded (a run's log: the adult opened Player_Child_01 and _03), the
# other age's items still did nothing. Each Link also lists the item actors he holds (ActorHolderParam: the child the Deku
# Stick and the Slingshot, the adult the Hammer, the Hookshots and the Bow); lent alone before the clips (2026-11-19) it did
# nothing either. So both are lent: each Link holds the other's too)
AGELESS_HOLDERS = {
    "Player_Child": "Component/ActorHolderParam/Player_Child.game__component__ActorHolderParam.bgyml",
    "Player_Adult": "Component/ActorHolderParam/Player_Adult.game__component__ActorHolderParam.bgyml",
}


# (the owner's test 2026-11-20: with the clips and the holders lent, the child's Bow and Hammer and the adult's Deku
# Sticks worked; the child's Hookshot crashed (the game looked for "Shootable_HookLong" and found nothing: x6/x7 of the
# crash) and the adult's Boomerang did nothing. What a Link shoots is his ShooterParam's list: the adult's arrows, nuts and
# the two hookshots' tips, the child's nuts, seeds and the Boomerang. So each is lent the other's too)
AGELESS_SHOOTERS = {
    "Player_Child": "Component/ShooterParam/Player_Child.game__component__ShooterParam.bgyml",
    "Player_Adult": "Component/ShooterParam/Player.game__component__ShooterParam.bgyml",
}


def ageless_shooters(packs):
    """{Link's pack name: pack bytes} with each one's ShooterParam listing the other's shootable actors too: (the new
    packs, how many entries were added)"""
    trees, added = {}, 0
    for who, rel in AGELESS_SHOOTERS.items():
        trees[who] = byml_parse(sarc_read(packs[who])[rel])
        if trees[who][0][1].get("ShootableActorSettings", ("",))[0] != "array":
            raise ValueError("%s has no ShootableActorSettings" % rel)
    actor = lambda row: row[1]["Actor"][1] if row[0] == "dict" and "Actor" in row[1] else None
    own = {who: list(trees[who][0][1]["ShootableActorSettings"][1]) for who in trees}
    out = {}
    for who, rel in AGELESS_SHOOTERS.items():
        other = "Player_Adult" if who == "Player_Child" else "Player_Child"
        rows = trees[who][0][1]["ShootableActorSettings"][1]
        have = {actor(r) for r in rows}
        for row in own[other]:
            if actor(row) not in have:
                rows.append(row)
                added += 1
        parts = sarc_read(packs[who])
        parts[rel] = byml_build(*trees[who])
        out[who] = sarc_write(parts)
    return out, added


def ageless_holders(packs):
    """{Link's pack name: pack bytes} with each one's ActorHolderParam holding the other's actors too: (the new packs,
    how many entries were added)"""
    trees, added = {}, 0
    for who, rel in AGELESS_HOLDERS.items():
        trees[who] = byml_parse(sarc_read(packs[who])[rel])
        if trees[who][0][1].get("ActorHoldSettings", ("",))[0] != "dict":
            raise ValueError("%s has no ActorHoldSettings" % rel)
    own = {who: dict(trees[who][0][1]["ActorHoldSettings"][1]) for who in trees}
    out = {}
    for who, rel in AGELESS_HOLDERS.items():
        other = "Player_Adult" if who == "Player_Child" else "Player_Child"
        held = trees[who][0][1]["ActorHoldSettings"][1]
        for name, node in own[other].items():
            if name not in held:
                held[name] = node
                added += 1
        parts = sarc_read(packs[who])
        parts[rel] = byml_build(*trees[who])
        out[who] = sarc_write(parts)
    return out, added


def ageless_anims(pack, param, lent):
    """a Link's pack (bytes) with `lent` animation files listed after his own in his AnimationParam `param`: (the new pack,
    how many were added). ValueError: the file is not the list known."""
    parts = sarc_read(pack)
    tree, version = byml_parse(parts[param])
    if tree[0] != "dict" or tree[1].get("AnimationResources", ("",))[0] != "array":
        raise ValueError("%s has no AnimationResources list" % param)
    rows = tree[1]["AnimationResources"][1]
    have = {r[1]["ModelProjectName"][1] for r in rows if r[0] == "dict" and "ModelProjectName" in r[1]}
    added = 0
    for name in lent:
        if name not in have:
            rows.append(("dict", collections.OrderedDict([("ModelProjectName", ("string", name))])))
            added += 1
    parts[param] = byml_build(tree, version)
    return sarc_write(parts), added


def ageless_actors(which):
    """the actors made usable by both ages: which's bit 1 the swords, bit 2 the age-only items (AGELESS_ITEMS but the swords),
    bit 4 the tunics (AGELESS_TUNICS)"""
    return ((AGELESS_SWORDS if which & 1 else ()) + (tuple(x for x in AGELESS_ITEMS if x not in AGELESS_SWORDS) if which & 2 else ()) +
            (AGELESS_TUNICS if which & 4 else ()))
AGELESS_TRUE = (208, b"\x01\x00\x00\x00")


# ---- Zelda's Letter in a slot of its own (the owner, 2026-11-21) ----
# The menu's trade slot (the pouch table's ItemArray, Pa_ItemIcon_23) lists every trade item, the adult's and then the
# child's: Zelda's Letter, the Chicken (Item_AlarmCucco), the Weird Egg; it shows the first one Link holds that his age
# may use. The original's sequence never let a child hold two, but the randomizer does (the letter shuffled, or the
# Debug tab's Add all): with the letter the egg and its chicken can't be chosen again (the chicken is never taken: after
# Talon wakes it stays, under the letter as in the game). So the letter moves to the amiibo slot (Pa_ItemIcon_24, which
# does nothing here), before the amiibo: the egg and the chicken keep the trade slot, the letter is shown beside it.
LETTER_SLOT = ("ItemArray", 22, 23, "Item_ZeldaLetter")


def pouch_letter_slot(data, slots=LETTER_SLOT):
    """the pouch table with an item moved from one slot's list to the front of another's (LETTER_SLOT): (the new bytes).
    As pouch_ageless: the game's bytes are kept, the two new lists written after the file's end and the two slots
    pointed at them. ValueError: not the table known, or the item not in the first slot's list."""
    array_key, src, dst, name = slots
    if data[:2] != b"YB":
        raise ValueError("not a little-endian BYML")
    key_at, str_at, root = struct.unpack_from("<III", data, 4)
    keys, strings = table(data, key_at), table(data, str_at)
    u32 = lambda at: struct.unpack_from("<I", data, at)[0]

    def entries_of(at):   # a dict: [(key, type, value, the value's place)]
        if data[at] != 0xC1:
            raise ValueError("not a dictionary at %#x" % at)
        n = int.from_bytes(data[at + 1:at + 4], "little")
        return [(keys[int.from_bytes(data[at + 4 + 8 * k:at + 7 + 8 * k], "little")], data[at + 7 + 8 * k], u32(at + 8 + 8 * k),
                 at + 8 + 8 * k) for k in range(n)]

    def items_of(at):   # an array: [(type, value)]
        if data[at] != 0xC0:
            raise ValueError("not an array at %#x" % at)
        n = int.from_bytes(data[at + 1:at + 4], "little")
        base = at + 4 + ((n + 3) & ~3)
        return [(data[at + 4 + k], u32(base + 4 * k)) for k in range(n)]

    def field(at, key):
        hit = [e for e in entries_of(at) if e[0] == key]
        if len(hit) != 1:
            raise ValueError("no %s" % key)
        return hit[0]

    slots_at = field(root, array_key)[2]
    rows = items_of(slots_at)
    src_list, dst_list = field(rows[src][1], "Actor"), field(rows[dst][1], "Actor")
    src_items, dst_items = items_of(src_list[2]), items_of(dst_list[2])
    mine = [(t, v) for t, v in src_items if strings[field(v, "ActorShort")[2]] == name]
    if len(mine) != 1:
        raise ValueError("slot %d holds %d of %s" % (src, len(mine), name))
    if any(strings[field(v, "ActorShort")[2]] == name for _, v in dst_items):
        raise ValueError("slot %d holds %s already" % (dst, name))
    out = bytearray(data)

    def array(items):
        out.extend(bytes(-len(out) % 4))
        at = len(out)
        out.extend(bytes((0xC0,)) + len(items).to_bytes(3, "little") + bytes(t for t, _ in items))
        out.extend(bytes(-len(out) % 4))
        out.extend(b"".join(struct.pack("<I", v) for _, v in items))
        return at

    struct.pack_into("<I", out, src_list[3], array([i for i in src_items if i != mine[0]]))
    struct.pack_into("<I", out, dst_list[3], array(mine + dst_items))
    return bytes(out)


def pouch_ageless(data, actors):
    """the pouch table (AGELESS_TABLE) with these actors usable by both ages: (the new bytes, how many marks were set).
    Every byte of the game's file is kept: each actor's entry is written again after the file's end with both marks
    true, and what pointed at the old entry points at the new one. (Written anew whole by byml_build, unchanged even,
    the game fell as it read the table: seen without a window 2026-11-19; the game's own bytes there load.) ValueError:
    not the table known, or an actor of `actors` not in it."""
    if data[:2] != b"YB":
        raise ValueError("not a little-endian BYML")
    key_at, str_at, root = struct.unpack_from("<III", data, 4)
    keys, strings = table(data, key_at), table(data, str_at)
    key_index = {k: i for i, k in enumerate(keys)}
    if not all(k in key_index for k in ("ActorShort", "IsUsableAdult", "IsUsableChild")):
        raise ValueError("not the pouch table: its keys lack the age marks")
    marks = (key_index["IsUsableAdult"], key_index["IsUsableChild"])
    out, moved, seen, count = bytearray(data), {}, set(), 0
    holders = []   # (the place of a value that points at a dict or an array)

    def walk(at, done=set()):
        nonlocal count
        if at in done:
            return
        done.add(at)
        kind, n = data[at], int.from_bytes(data[at + 1:at + 4], "little")
        if kind == 0xC1:
            rows = [(int.from_bytes(data[at + 4 + 8 * k:at + 7 + 8 * k], "little"), data[at + 7 + 8 * k], bytes(data[at + 8 + 8 * k:at + 12 + 8 * k]))
                    for k in range(n)]
            for k, (_, typ, val) in enumerate(rows):
                if typ in (0xC0, 0xC1):
                    holders.append(at + 8 + 8 * k)
                    walk(struct.unpack("<I", val)[0])
            name = next((strings[struct.unpack("<I", val)[0]] for key, typ, val in rows if key == key_index["ActorShort"] and typ == 0xA0), None)
            if name in actors:
                seen.add(name)
                new = {key: (typ, val) for key, typ, val in rows}
                for mark in marks:
                    if new.get(mark) != (0xD0, struct.pack("<I", 1)):
                        new[mark] = (0xD0, struct.pack("<I", 1))
                        count += 1
                out.extend(bytes(-len(out) % 4))
                moved[at] = len(out)
                out.extend(bytes([0xC1]) + len(new).to_bytes(3, "little"))
                for key in sorted(new):
                    out.extend(key.to_bytes(3, "little") + bytes([new[key][0]]) + new[key][1])
        elif kind == 0xC0:
            vals = at + 4 + (n + 3 & ~3)
            for k in range(n):
                if data[at + 4 + k] in (0xC0, 0xC1):
                    holders.append(vals + 4 * k)
                    walk(struct.unpack_from("<I", data, vals + 4 * k)[0])
        else:
            raise ValueError("a BYML node of a type not read here (%#x)" % kind)

    walk(root, set())
    missing = sorted(set(actors) - seen)
    if missing:
        raise ValueError("the pouch table has no %s" % ", ".join(missing))
    for at in holders:
        old = struct.unpack_from("<I", data, at)[0]
        if old in moved:
            struct.pack_into("<I", out, at, moved[old])
    return bytes(out), count


# ---- Zelda's Letter shuffled (rando_letter, asked for 2026-11-15) ----
# Zelda gives her letter at the end of the castle courtyard's meeting (Dm_HrlCastle_0050, through Dm_SY_GetInEvent's
# GetInEvent_Zeldaletter with ActorName Item_ZeldaLetter): with the setting the letter is an item of the shuffle and the
# meeting gives what the seed put there (gift_items, as Darunia's). Kakariko's gate to Death Mountain opens for a child
# who shows the letter to its guard (Npc_Hylia_Soldier_003); the owner's word on the other ways up (2026-11-15): bombs,
# by the Lost Woods' way to Goron City (its boulder), or the Bolero of Fire, a warp to the crater. So a child's check
# on Death Mountain (LETTER_AREAS) asks for the letter, or bombs, or the Bolero (when the songs are shuffled: otherwise
# the Bolero is an adult's lesson's): letter_need. An adult passes the gate; his rules ask for bombs already (ADULT).
LETTER = "Item_ZeldaLetter"
LETTER_GIFT = Gift("zelda_letter", "Dm_HrlCastle_0050", (LETTER,), LETTER, "HyruleCastle", "Zelda's letter, in the courtyard", CHILD, "letter")
LETTER_AREAS = frozenset(("DeathMountainTrail", "GoronCity", "DodongoCavern", "DeathMountainCrater", "FireTemple"))
LETTER_BOLERO = "Item_Melody_FireBolero"


# ---- Deku Sticks in the Kokiri Sword's place (placement 20, the owner's ask 2026-11-21) ----
# With the Deku Tree and the forest's way out both open, nothing asks a child for the Kokiri Sword itself (Mido checks
# for it only at the Deku Tree's path): where a rule names it, it stands for a weapon, and Deku Sticks do as well (the
# Deku Tree's Gohma, Dodongo's Cavern, Jabu-Jabu, a Skulltula "sword or slingshot"). Where sticks come from without a
# weapon (bug 96): pots, which Link lifts and throws: child Goron City's two (one drops a stick, one a stick table at
# 100%), Zora's Domain's and Zora's River's; they come back after about a day and night. The game gives no first bag
# (the first stick makes room for itself). So a way that asks for the sword may instead ask for the way to Goron City,
# a child's way up the mountain (letter_need: the letter, bombs, or the Bolero), or nothing more when the letter isn't
# shuffled (Zelda gives it) or the gate is open. Grass and Deku Babas need a weapon first; the Kokiri shop's sticks may
# be shuffled away: not counted. NOT SEEN IN PLAY as a seed's logic.
STICKS_FROM = 20


# ---- Each dungeon check by its own rule (placement 21, the owner's ask 2026-11-21) ----
# Before, every check of a dungeon asked for what the whole dungeon could (RULES), written from the original game. From
# placement 21 each chest, Gold Skulltula and boss's Heart Container of the twelve dungeons that the table knows asks for
# its dungeon's way in (DUNGEON_ENTRY: what RULES asked, the dungeon's inner items taken out) and any one of its own
# ways, worked out by tools/rando/dungeon_logic.py from the other randomizers' logic of the remake (OotrR's engine and
# world, ootrr 0.8.2's dungeons rewritten for the remake's layout and its pins of each remake actor to its N64 location;
# tools/rando/ootrr/README.md) into DUNGEON_RULES_FILE, which is installed beside this script (without it the rules are
# as before, and the seed says so). An actor pinned only as one of a pool of equal items asks for every candidate's.
# The ways name the other randomizers' items: DUNGEON_AP_ITEMS turns them into ours. One the seed doesn't shuffle is held
# (the rules counted on it before too); Din's Fire and the Fire Arrows, shuffled but no gating items, are asked for only
# where no other way is: the Shadow Temple's first hall wants Din's Fire for its torches (ootrr 0.8.2, not seen in play
# yet), so with the Great Fairies' gifts shuffled Din's Fire is a gating item (DUNGEON_GATES). Every other step (the
# Door of Time, the songs, the tunics, the Hookshot, the sticks...) then works on these rules as on the old ones.
DUNGEON_RULES_FROM = 21
DUNGEON_RULES_FILE = "dungeon_rules.json"
# (placement 25, 2026-11-22: the same tool on the other randomizer's newer dungeons, ootrr a253c9a "checked against
# remake actors": 102 rules changed, the Spirit Temple and Gerudo Training Ground rewritten, Ganon's trials and three of
# Dodongo's Cavern's. A new seed reads DUNGEON_RULES2_FILE; a seed made before keeps DUNGEON_RULES_FILE, its items where
# they were. dungeon_table_for sets which, before the first dungeon_table)
DUNGEON_RULES2_FROM = 25
DUNGEON_RULES2_FILE = "dungeon_rules_25.json"
_DUNGEON_FILE = [DUNGEON_RULES_FILE]
# (the owner's ask 2026-11-23: with Shuffle the Master Sword, adult checks asked for the sword everywhere, door_need's
#  blanket rule, where bombs, the Bow or the Hammer do.) From placement SWORD_FROM, with the sword shuffled, a check that
#  has a rule of its own (the dungeons' table, the overworld's, our own: worked out by dungeon_logic.py and
#  overworld_logic.py with the engine's shuffle_master_sword, so a way asks for the sword only where nothing else will
#  fight) is not given the sword by door_need. The bosses (their hearts and rewards) and the gifts keep it. The tables:
#  DUNGEON_RULES2_FILE's "ms_by_actor", OVERWORLD_RULES_FILE's ",ms" variants.
SWORD_FROM = 26
_DUNGEON_SWORD = [False]


def dungeon_table_for(placement, master=False):
    """the dungeon rules' file for a seed of this placement (DUNGEON_RULES2_FILE from DUNGEON_RULES2_FROM), the table read
    again if it was another; master: the sword shuffled, its own table from SWORD_FROM"""
    want = DUNGEON_RULES2_FILE if placement >= DUNGEON_RULES2_FROM else DUNGEON_RULES_FILE
    sword = bool(master) and placement >= SWORD_FROM
    if _DUNGEON_FILE[0] != want or _DUNGEON_SWORD[0] != sword:
        _DUNGEON_FILE[0] = want
        _DUNGEON_SWORD[0] = sword
        del _DUNGEON_TABLE[:]
    return want
DIN = "Item_DinFire"
DUNGEON_GATES = frozenset((DIN,))
DUNGEON_AP_ITEMS = {("Kokiri Sword", 1): S, ("Master Sword", 1): "Weapon_Sword_Master", ("Slingshot", 1): SL, ("Boomerang", 1): BM,
                 ("Bomb Bag", 1): BB, ("Bombchus", 1): BB, ("Lens of Truth", 1): LENS, ("Bow", 1): BOW, ("Megaton Hammer", 1): HAM,
                 ("Iron Boots", 1): IRON, ("Hover Boots", 1): HOVER, ("Progressive Hookshot", 1): "Item_Hookshot",
                 ("Progressive Hookshot", 2): LONG, ("Progressive Strength Upgrade", 1): "Item_Gauntlet_Goron",
                 ("Progressive Strength Upgrade", 2): SG, ("Progressive Strength Upgrade", 3): GG,
                 ("Progressive Scale", 1): "Item_Scale_Silver", ("Progressive Scale", 2): "Item_Scale_Gold", ("Mirror Shield", 1): MS,
                 ("Goron Tunic", 1): "Obj_Armor_Goron", ("Zora Tunic", 1): "Obj_Armor_Zora", ("Magic Meter", 1): "Item_FairyBless_MPDouble",
                 ("Dins Fire", 1): DIN, ("Fire Arrows", 1): "Item_Arrow_Fire", ("Ocarina", 1): "Item_Ocarina_Fairy",
                 ("Bottle", 1): "Item_Bottle", ("Deku Shield", 1): "TBox_Shield_Deku",
                 ("Zeldas Lullaby", 1): "Item_Melody_ZeldaLullaby", ("Eponas Song", 1): "Item_Melody_EponaSong",
                 ("Sarias Song", 1): "Item_Melody_SariaSong", ("Suns Song", 1): "Item_Melody_SunSong",
                 ("Song of Time", 1): "Item_Melody_TimeSong", ("Song of Storms", 1): "Item_Melody_StormSong",
                 ("Minuet of Forest", 1): "Item_Melody_ForestMinuet", ("Bolero of Fire", 1): "Item_Melody_FireBolero",
                 ("Serenade of Water", 1): "Item_Melody_WaterSerenade", ("Requiem of Spirit", 1): "Item_Melody_SpiritRequiem",
                 ("Nocturne of Shadow", 1): "Item_Melody_ShadowNocturne", ("Prelude of Light", 1): "Item_Melody_LightPrelude"}
DUNGEON_SHUFFLED_ONLY = frozenset(("Item_Arrow_Fire", DIN))   # (shuffled, no gating items: asked for where no other way is)
DUNGEON_ENTRY = {"InsideTheDekuTree": frozenset((S,)), "DodongoCavern": CHILD | {BB}, "InsideJabuJabuBelly": ADULT,
                 "BottomOfTheWell": ADULT, "ForestTemple": ADULT, "FireTemple": ADULT, "IceCavern": ADULT,
                 "WaterTemple": ADULT | {IRON}, "ShadowTemple": MEDALS3, "SpiritTemple": DESERT,
                 "GerudoTrainingGround": ADULT | {HOVER, LONG, BOW}, "InsideGanonCastle": None}   # (None: everything, as RULES)
# (with the songs shuffled, the Nocturne and the Requiem are items: the Shadow Temple's way in is an adult and the
#  Nocturne, which song_need names; the Spirit Temple's the desert crossed or the Requiem with an adult's (the rules
#  don't tell the child's side from the adult's: too much, never too little). Without, the lessons wait on the three
#  temples (MEDALS3) and the desert is the way)
DUNGEON_ENTRY_SONGS = {"ShadowTemple": ADULT}
# (bug 121, the owner's run 2026-11-23: every Bottom of the Well check asked for Zelda's Lullaby.) Its way in was ADULT
# (too much: before the songs were shuffled, the Song of Storms came from the windmill man, an adult's lesson). The well is
# a young Link's, drained by the Song of Storms at the windmill. From placement WELL_FROM, with the songs shuffled, its way
# in is a young Link out of the forest (CHILD), the Song of Storms and the ocarina where they are shuffled; each check's
# own ways (the table's) ask for the rest, Zelda's Lullaby only where it is needed.
WELL_FROM = 26
BOTTLE_ENTRY_FROM = 26   # (dungeon_rule's no_bottle: Ganon's Castle's way in without a bottle)
WELL = "BottomOfTheWell"
DUNGEON_REQUIEM = "SpiritTemple"
DUNGEON_AGES_FROM = 22
# The Spirit Temple by age (dungeon_logic.py AGE_SPLIT: its checks worked out for the child alone, the adult alone and
# both, its door from the Colossus closed in that logic). Each way of an age asks for that age's way in: the child's the
# Requiem (with the songs shuffled; else the adult learns it at the Colossus first: the desert crossed), out of the
# forest; the adult's the desert crossed or the Requiem as an adult; a way of both, both.


def dungeon_age_entry(requiem, open_door=False):
    """{"child"/"adult"/"both": [the ways in]} for the Spirit Temple (requiem: the Requiem of Spirit is a gating item;
    open_door: with Open Door of Time being an adult asks for nothing (and for the Master Sword when it's shuffled), as
    door_need takes it off an adult's own places)"""
    grown = (frozenset((MASTER,)) if MASTER_SHUFFLED else NONE) if open_door else ADULT
    child = [CHILD | {"Item_Melody_SpiritRequiem"}] if requiem else [DESERT]
    adult = [grown | (DESERT - ADULT)] + ([grown | {"Item_Melody_SpiritRequiem"}] if requiem else [])
    return {"child": child, "adult": adult, "both": [c | d for c in child for d in adult]}
_DUNGEON_TABLE = []


def dungeon_table():
    """the table of DUNGEON_RULES_FILE beside this script: {an actor's hash: [way, ...]}, each way {item: tier}; {} without it"""
    if not _DUNGEON_TABLE:
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), _DUNGEON_FILE[0]), encoding="utf-8") as f:
                whole = json.load(f)
            table = whole["ms_by_actor"] if _DUNGEON_SWORD[0] and "ms_by_actor" in whole else whole["by_actor"]
            _DUNGEON_TABLE.append({int(h): (e["ways"], e.get("age_ways")) for h, e in table.items()})
        except (OSError, ValueError, KeyError):
            _DUNGEON_TABLE.append({})
    return _DUNGEON_TABLE[0]


def dungeon_rule(h, area, progression, pool=frozenset(), open_door=False, ages=True, well_child=False, no_bottle=False):
    """a dungeon check's own rule (see above), or None where the table doesn't know it: its dungeon's way in and any of
    its ways, in our items (progression: the seed's gating items; pool: what the seed shuffles. The others are held)"""
    found = dungeon_table().get(h)
    if not found or area not in DUNGEON_ENTRY:
        return None
    ways, age_ways = found
    songs = "Item_Melody_ShadowNocturne" in progression
    # (no_bottle, placement BOTTLE_ENTRY_FROM: the owner's run 2026-11-23, every check of Ganon's Castle asked for a bottle,
    #  its way in being every gating item; a bottle is no way in, and a check that needs one says so in its own ways)
    everything = frozenset(progression) - ({BOTTLE} if no_bottle else set())
    entries = [everything if DUNGEON_ENTRY[area] is None else DUNGEON_ENTRY_SONGS.get(area, DUNGEON_ENTRY[area]) if songs
               else DUNGEON_ENTRY[area]]
    if area == WELL and songs and well_child:   # (a young Link's, by the Song of Storms: WELL_FROM)
        entries = [CHILD | (frozenset((STORMS, OCARINA)) & frozenset(progression))]
    if area == DUNGEON_REQUIEM and "Item_Melody_SpiritRequiem" in progression:
        entries.append(ADULT | {"Item_Melody_SpiritRequiem"})
    tagged = [(way, entries) for way in ways]
    if age_ways and area == DUNGEON_REQUIEM and ages:   # (each age's ways with its own way in: DUNGEON_AGE_ENTRY)
        by_age = dungeon_age_entry("Item_Melody_SpiritRequiem" in progression, open_door)
        tagged = [(way, by_age[mode]) for mode in ("child", "adult", "both") for way in age_ways.get(mode) or ()]
    plain, other = [], []
    for way, entries in tagged:
        mine = frozenset(DUNGEON_AP_ITEMS[(name, level)] for name, level in way.items()
                         if DUNGEON_AP_ITEMS.get((name, level)) in progression or DUNGEON_AP_ITEMS.get((name, level)) in DUNGEON_SHUFFLED_ONLY & pool)
        (other if mine & DUNGEON_SHUFFLED_ONLY - progression else plain).extend(base | mine for base in entries)
    return either(plain or other)


# ---- Each overworld check by its own rule (placement 23, the owner's ask 2026-11-21) ----
# Before, every overworld check asked for its area's hardest (RULES: Kakariko's child Gold Skulltulas the Slingshot and
# the sword, the out-of-the-forest CHILD, though a weapon and the night are all they take; most of a young Link's checks
# out of logic at a new game's start with the forest and Kakariko's gate open). From placement 23 each chest, Gold
# Skulltula and Piece of Heart lying in the world that the table knows asks for any one of its own ways from a new
# game's start, worked out by tools/rando/overworld_logic.py from the same logic as the dungeons' (OVERWORLD_RULES_FILE,
# beside this script, one table for each OVERWORLD_VARIANT of the seed's settings). Its ways are the whole of its rule:
# the old steps that folded the story into CHILD and ADULT (the forest's way out, the Door of Time, Kakariko's gate, the
# songs' and the gifts' areas, Zora's Domain's two ways) are the table's already and are not done again; the items'
# own steps are (progressive items, magic, the ocarina, sticks for the sword, the Hookshot's audit). Its items:
# DUNGEON_AP_ITEMS and OVERWORLD_AP_ITEMS (sticks bought are the Kokiri Sword, which the sticks step widens); a song
# the seed doesn't shuffle asks for its lesson's rule (SONGS), any other item it doesn't shuffle is held, as in the
# dungeons'. A Gold Skulltula only a child reaches asks for a weapon as well (OVERWORLD_KILL: the logic takes the child to
# have one). Gifts and shelves keep their own rules (GIFTS, shop_need): the table has no actor of theirs.
# NOT SEEN IN PLAY.
OVERWORLD_FROM = 23
OVERWORLD_RULES_FILE = "overworld_rules.json"
OVERWORLD_AP_ITEMS = {("Buy Deku Stick (1)", 1): S, ("Zeldas Letter", 1): "Item_ZeldaLetter"}
OVERWORLD_KILL = frozenset((S, SL, BM, BB))
# Bombchu Bowling has been open from the start in every seed since fixes 59 (ALWAYS_EXP, CHU_LOGIC: no longer after
# Dodongo's Cavern), and the game lends its Bombchus: its two prizes ask for a child out of the forest alone, not bombs
# (the owner, 2026-11-21: they asked for the Bomb Bag).
BOWLING_FREE = ("bowling_bag", "bowling_heart")   # (any one: the sword (or sticks), the Slingshot, the Boomerang, bombs)
_OVERWORLD_TABLE = {}
# Ways the other logic doesn't have, found in play (placement 24, OVERWORLD_MORE_FROM): {an actor's hash: [a way, ...]}
# added to its table ways. Kakariko's watchtower Gold Skulltula (child, night): the Slingshot, bombchus (the Bomb Bag,
# which stands for them: no bombchu item of its own), or the Boomerang (the owner, 2026-11-21).
OVERWORLD_MORE_FROM = 24
# (bug 118, the owner's run 2026-11-23: Hyrule Field's tree Gold Skulltulas and the remake's own chests out of logic
# when they were easy.) The remake's checks the other logic doesn't have took a pool's hardest rule, or the old
# whole-area one. From placement OWN_FROM each has a rule of its own (tools/rando/overworld_own.json, worked out from a
# new game's start by overworld_logic.py into each variant's "own"), in place of its table ways.
OWN_FROM = 26
OVERWORLD_MORE = {0xd1cef51cf294fb86: [frozenset((BM,))]}


def overworld_variant(open_deku, open_forest, gate_open, open_door, master=False):
    """the table's key for the seed's settings (overworld_logic.py variant_key): the forest (both ways open, the way out
    only, closed), Kakariko's gate (open from the start, or the letter's), the Door of Time"""
    forest = "open" if open_deku and open_forest else "closed_deku" if open_forest else "closed"
    return "%s,%s,%d%s" % (forest, "open" if gate_open else "zelda", 1 if open_door else 0, ",ms" if master and open_door else "")


# (the checks taken by name, not by a map's actor: a character's gift by its key, a shop's shelves by its key (each
#  shelf asks as its shop's first does, then for its price's wallet). The lessons keep their own rules (the story they
#  wait for in the remake: DEKU_STORY, Malon's), as do the Skulltula house (its tokens), the frogs, the bowling and the
#  Bombchu Shop (open from the start here; the other logic asks for bombs), the Great Fairies (their prices), and the
#  Potion Shop keeper's bottle (the remake's own errand))
OVERWORLD_GIFTS = {"darunia": "GC Darunias Joy", "lostwood_target": "LW Target in Woods", "forest_stage_skull": "Deku Theater Skull Mask",
                   "forest_stage_truth": "Deku Theater Mask of Truth", "diving": "ZD Diving Minigame", "fishing_child": "LH Child Fishing",
                   "fishing_adult": "LH Adult Fishing", "gallery_market": "Market Shooting Gallery Reward",
                   "gallery_kakariko": "Kak Shooting Gallery Reward", "cucco_lady": "Kak Anju as Child", "archery_heart": "GF HBA 1000 Points",
                   "archery_quiver": "GF HBA 1500 Points", "goron_tunic": "GC Rolling Goron as Adult", "zora_tunic": "ZD King Zora Thawed",
                   "rolling_goron": "GC Rolling Goron as Child", "roof_man": "Kak Man on Roof", "skull_kid_song": "LW Skull Kid",
                   "skull_kid_game": "LW Ocarina Memory Game", "dog_lady": "Market Lost Dog", "lab_dive": "LH Lab Dive"}
OVERWORLD_SHOPS = {"kokiri": "KF Shop Item 1", "general": "Market Bazaar Item 1", "medicine": "Market Potion Shop Item 1",
                   "goron": "GC Shop Item 1", "zora": "ZD Shop Item 1",
                   "kgeneral": "Kak Bazaar Item 1", "kmedicine": "Kak Potion Shop Item 1"}


def overworld_table(variant):
    """({an actor's hash: [way, ...]}, {a check's name: [way, ...]}, {an actor's hash: [way, ...]} of our own rules,
    OWN_FROM) of OVERWORLD_RULES_FILE's variant; ({}, {}, {}) without it"""
    if variant not in _OVERWORLD_TABLE:
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), OVERWORLD_RULES_FILE), encoding="utf-8") as f:
                table = json.load(f)["variants"][variant]
            _OVERWORLD_TABLE[variant] = ({int(h): e["ways"] for h, e in table["by_actor"].items()}, table.get("named", {}),
                                         {int(h): ways for h, ways in table.get("own", {}).items()})
        except (OSError, ValueError, KeyError):
            _OVERWORLD_TABLE[variant] = ({}, {}, {})
    return _OVERWORLD_TABLE[variant]


def overworld_rule(ways, progression, lessons=None, child_skulltula=False):
    """an overworld check's own rule from its table ways (see above), in our items. lessons: {a song: its lesson's
    rule} for the songs not shuffled; child_skulltula: a Gold Skulltula only a child reaches (a weapon asked for)"""
    out = []
    for way in ways:
        mine = set()
        for name, level in way.items():
            item = DUNGEON_AP_ITEMS.get((name, level)) or OVERWORLD_AP_ITEMS.get((name, level))
            if item in progression:
                mine.add(item)
            elif item and lessons and item in lessons:
                lesson = lessons[item]
                mine |= set(lesson if not isinstance(lesson, Either) else min(lesson, key=len))
        if child_skulltula and not mine & OVERWORLD_KILL:
            mine.add(S)
        out.append(frozenset(mine))
    return either(out) if out else None


# ---- Castle guards let Link pass (rando_castle_guards, asked 2026-11-21) ----
# Young Link's way to Zelda is a sneak past the castle's guards; one who sees him starts HyruleCastle_FoundBySecurity
# (FoundBySecurity on the grounds, FoundBySecurity_Courtyard in the courtyard): the others turn, he talks, the screen goes
# dark and Link is put back at the start (EventPlayerWarpToStarterLinkAnchor). With the setting each entry only sends the
# guard back to his post (EventWarpToHomeMatrix) and lifts the alert (EventAIScheduleNPCForceSecurityLifted), as the
# game's own end of it does, and the event ends there: Link stays where he is. The owner's word (2026-11-21): the castle
# itself can't be skipped (Malon and her egg, Talon, a Gold Skulltula) and the remake has no load between the gate and
# Zelda. Moves no item. NOT SEEN IN PLAY.
GUARDS_FLOW = "Event/EventFlow/HyruleCastle_FoundBySecurity.bfevfl.zs"
GUARDS_ENTRIES = ("FoundBySecurity", "FoundBySecurity_Courtyard")


def castle_guards_pass(data):
    """HyruleCastle_FoundBySecurity's flow with each of GUARDS_ENTRIES the guard's way home and the lifted alert alone (see
    above). The new bytes; ValueError: not the flow known."""
    import io
    evfl = evfl_module()
    flow = evfl.EventFlow()
    flow.read(data)
    fc = flow.flowchart
    entries = {e.name: e for e in fc.entry_points}
    if any(n not in entries for n in GUARDS_ENTRIES):
        raise ValueError("not the castle guards' flow")
    for name in GUARDS_ENTRIES:
        seen, todo, home, lift = set(), [entries[name].main_event.v], None, None
        while todo:   # (the steps the entry reaches, through its sub-flows of this file)
            e = todo.pop()
            if e is None or id(e) in seen:
                continue
            seen.add(id(e))
            d = e.data
            if isinstance(d, evfl.ActionEvent):
                act = d.actor_action.v.v
                if act == "EventWarpToHomeMatrix" and home is None:
                    home = e
                if act == "EventAIScheduleNPCForceSecurityLifted":
                    lift = e
            if isinstance(d, evfl.SubFlowEvent) and not d.res_flowchart_name and d.entry_point_name in entries:
                todo.append(entries[d.entry_point_name].main_event.v)
            for nxt in [getattr(d, "nxt", None)] + list(getattr(d, "cases", {}).values()) + list(getattr(d, "forks", [])) + [getattr(d, "join", None)]:
                if nxt is not None:
                    todo.append(nxt.v)
        if home is None or lift is None or home.data.nxt.v is not lift:
            raise ValueError("%s: no guard's way home followed by the lifted alert" % name)
        lift.data.nxt.v = None
        entries[name].main_event.v = home
    out = io.BytesIO()
    flow.write(out)
    return out.getvalue()


# ---- Gerudo guards don't jail Link (rando_gerudo_guards, asked 2026-11-23) ----
# A Gerudo guard at the fortress who catches adult Link starts SageOfSpirit's GerudoFortress_GotoPrison_Alert (or
# _Suprise: the same steps; GotoPrison, _sub, _004 and the _Pair entries reach them as sub-flows): her talk, the screen
# goes dark, Link is put in the cell (EventPlayerWarpToStarterLinkAnchor, Dm_Gerudo_0010) or, the first time with the
# Hookshot, out of the fortress (GerudoFortress_RunFromFortress). With the setting both entries only send the guard who
# caught him back to her post (Npc_EventStarter's EventWarpToHomeMatrix, a step of our own: the castle's guards' way
# home, castle_guards_pass) and lift the alert (the flow's own EventAIScheduleNPCForceSecurityLifted), and the event
# ends there: Link stays where he is. The rules never use the cell (GerudoFortress is reached by its own items).
# Moves no item. NOT SEEN IN PLAY.
GERUDO_GUARDS_FLOW = "Event/EventFlow/SageOfSpirit.bfevfl.zs"
GERUDO_GUARDS_ENTRIES = ("GerudoFortress_GotoPrison_Alert", "GerudoFortress_GotoPrison_Suprise")


def gerudo_guards_pass(data):
    """SageOfSpirit's flow with each of GERUDO_GUARDS_ENTRIES the guard's way home and the lifted alert alone (see above).
    The new bytes; ValueError: not the flow known, or changed already."""
    import copy
    import io
    evfl = evfl_module()
    flow = evfl.EventFlow()
    flow.read(data)
    fc = flow.flowchart
    entries = {e.name: e for e in fc.entry_points}
    if any(n not in entries for n in GERUDO_GUARDS_ENTRIES) or any(e.name.startswith("WillowGerudo") for e in fc.events):
        raise ValueError("not the fortress guards' flow, or changed already")
    lifts = [e for e in fc.events if isinstance(e.data, evfl.ActionEvent)
             and e.data.actor_action.v.v == "EventAIScheduleNPCForceSecurityLifted"]
    starter = [a for a in fc.actors if a.identifier.name == "Npc_EventStarter" and not a.identifier.sub_name]
    if not lifts or len(starter) != 1:
        raise ValueError("no lifted alert, or not one Npc_EventStarter")
    actor = starter[0]
    got = [h for h in actor.actions if h.v == "EventWarpToHomeMatrix"]
    if got:
        act = got[0]
    else:
        act = evfl.common.StringHolder("EventWarpToHomeMatrix")
        actor.actions.append(act)
    lift = evfl.Event()
    lift.name = "WillowGerudoLift"
    lift.data = evfl.ActionEvent()
    lift.data.actor.v, lift.data.actor_action.v = lifts[0].data.actor.v, lifts[0].data.actor_action.v
    lift.data.params = copy.deepcopy(lifts[0].data.params)
    lift.data.nxt.v = None
    home = evfl.Event()
    home.name = "WillowGerudoHome"
    home.data = evfl.ActionEvent()
    home.data.actor.v, home.data.actor_action.v = actor, act
    home.data.params = evfl.Container()
    home.data.params.data["IsWaitEnd"] = True   # (as the castle's own step has it)
    home.data.nxt.v = lift
    fc.events += [home, lift]
    for name in GERUDO_GUARDS_ENTRIES:
        entries[name].main_event.v = home
    out = io.BytesIO()
    flow.write(out)
    return out.getvalue()


# ---- Free Scarecrow's Song (rando_free_scarecrow, asked 2026-11-21) ----
# The Scarecrow's Song is the player's own: young Link plays notes to Bonooru at Lake Hylia, the adult plays them back,
# and Pierre answers them at his spots. Its notes are kept in the save (a Binary, empty in a new game: the list of flags
# gives only its size, so a new game can't start with one; bugs.md 105). With the setting the game's side gives a save
# that has no song of its own L R L R L, the scarecrow's quest done and the song in the pouch (host/hos_main.c
# oot_scarecrow_free), when the seed leaves FREE_SCARECROW_FILE beside it. Tried first and dropped: Pierre called by
# whatever is played at a spot (the game knows a spot only after its own song: seen in play, he never came).
# Moves no item.
FREE_SCARECROW_FILE = "scarecrow_free.txt"


def stick_need(need, letter, bolero=False):
    """one way of a rule with Deku Sticks for the Kokiri Sword (see above): the way as it was, or without the sword and
    with a child's way to Goron City's pots (letter: Zelda's Letter is shuffled; bolero: as letter_need's)"""
    if S not in need:
        return need
    base = frozenset(need - {S})
    if not letter or BB in base or LETTER in base:
        return base
    ways = letter_need(base, "GoronCity", bolero)
    return either([need] + (list(ways) if isinstance(ways, Either) else [ways]))


def letter_need(need, area, bolero=False):
    """a rule of a check on Death Mountain with the ways past Kakariko's gate named: each way that asks for neither bombs
    nor the letter becomes three, the letter's, the bombs' and (bolero) the Bolero's. Elsewhere, as it was."""
    if area not in LETTER_AREAS:
        return need

    def way(w):
        if BB in w or LETTER in w:
            return w
        return either([w | {LETTER}, w | {BB}] + ([w | {LETTER_BOLERO}] if bolero else []))
    return each(way, need)


# ---- The first Deku Nut and Deku Stick bags' "You got" words (bug 48) ----
# The game gives no first bag (its first nuts and sticks make room for them), so its item text has the first bags'
# names and captions but not the words of the "You got" window (<item>_GetMessage, _GetCaption); a chest made to give
# one stopped in its scene (2026-11-16), so the game's side showed the shuffled tier (the biggest bag) instead. Every
# seed adds them, made from the bigger bag's (FIRST_BAG_WORDS: its words, and the English ones without "bigger" and
# with the first bag's size), in every language's archive; the game's side then shows the first bag as it is
# (host/hos_main.c oot_no_show).
FIRST_BAG_WORDS = {"Item_NutBag_Small": ("Item_NutBag_Medium", b"up to 30", b"up to 20"),
                   "Item_StickBag_Small": ("Item_StickBag_Medium", b"up to 20", b"up to 10")}
FIRST_BAG_ENGLISH = ("USen", "EUen")
# (the owner's run 2026-11-23: a chest's Golden Gauntlets showed no model.) The gauntlets' "You got" words are only the
# pouch's spellings' (Armor_Child_Gauntlet_Goron, Armor_Adult_Gauntlet_*), which have no model to hold up, so a chest
# showed that spelling for its words and nothing over Link's head. Every seed copies those words to the items' own
# spellings (fixes 75), and the game's side shows those (host/hos_main.c oot_show_as without the gauntlets).
COPY_WORDS = {"Item_Gauntlet_Goron": "Armor_Child_Gauntlet_Goron", "Item_Gauntlet_Silver": "Armor_Adult_Gauntlet_Silver",
              "Item_Gauntlet_Gold": "Armor_Adult_Gauntlet_Gold"}


def first_bag_words(data, english):
    """the item text (SHOP_TEXT) with the first bags' GetMessage and GetCaption, made from the bigger bag's; the lines it
    has already are kept. (The new bytes, how many lines were added)."""
    added = 0
    for small, (bigger, was, now) in FIRST_BAG_WORDS.items():
        for suffix in ("_GetMessage", "_GetCaption"):
            try:
                msbt_text(data, small + suffix)
                continue
            except ValueError:
                pass
            a, b = msbt_text(data, bigger + suffix)
            words = bytes(data[a:b]).rstrip(b"\0")
            if english:
                words = words.replace(b"bigger ", b"").replace(b"a lot more ", b"").replace(was, now)
            data = msbt_add(data, small + suffix, words)
            added += 1
    for item, spelling in COPY_WORDS.items():   # (the gauntlets' words, as the pouch's spellings have them)
        for suffix in ("_GetMessage", "_GetCaption"):
            try:
                msbt_text(data, item + suffix)
                continue
            except ValueError:
                pass
            a, b = msbt_text(data, spelling + suffix)
            data = msbt_add(data, item + suffix, bytes(data[a:b]).rstrip(b"\0"))
            added += 1
    return data, added


# ---- The Fairy Ocarina shuffled (Songs: Anywhere, ocarina too, rando_songs 3; asked for 2026-11-15) ----
# Saria gives the Fairy Ocarina on the forest's bridge (Dm_Kokiri_0155): the scene adds it to the pouch itself (an
# action, EventTriggerAddOrRemovePouchContent with Actor Item_Ocarina_Fairy) and shows it (GetPouchContent's
# DisplayGetByActorName with ActorName the same), so both are made the seed's item (gift_items with kinds 0 and 4:
# OCARINA_KINDS). The ocarina is then a gating item: a song is played on one, so every way of a rule that names a song
# asks for it too, and so does every lesson (the teacher's notes are played back): ocarina_need. The Ocarina of Time
# (Zelda's, at the moat) is the other ocarina, given only with the three stones: the rules leave it out (too much,
# never too little). Saria waits on the bridge after the Deku Tree (DEKU_STORY keeps its CHILD).
OCARINA = "Item_Ocarina_Fairy"
OCARINA_GIFT = Gift("fairy_ocarina", "Dm_Kokiri_0155", (OCARINA,), OCARINA, "KokiriForest", "Saria's gift, on the bridge", CHILD, "ocarina")
# The Ocarina of Time too: Zelda gives it at the moat in the Song of Time's lesson (Dm_MelodyGet_Time: its pouch add
# and its "you got" call name Item_Ocarina_Time, as Saria's). It is not a gating item: the rules ask for the Fairy
# Ocarina wherever a song is played, so the Ocarina of Time can be anywhere (the Door of Time's scenes do not ask the
# pouch for it). The lesson's song is the songs' shuffle's, apart (its own call, SONG_FLOWS).
OCARINA_TIME = "Item_Ocarina_Time"
OCARINA_TIME_GIFT = Gift("ocarina_time", "Dm_MelodyGet_Time", (OCARINA_TIME,), OCARINA_TIME, "HyruleField",
                         "Zelda's gift at the moat: the Ocarina of Time", ADULT | {"Item_Melody_ZeldaLullaby", "Item_Melody_SariaSong"}, "ocarina")
OCARINA_KINDS = {"Dm_Kokiri_0155": (0, 4), "Dm_MelodyGet_Time": (0, 4)}
# ---- Shuffle the Master Sword (rando_master_sword, the owner's wish 2026-11-20) ----
# With Open Door of Time the game's plain way through time gives no sword, and the game's side gives it the first time
# young Link goes through (host/hos_main.c oot_time_door). With this setting the sword is an item of the shuffle and
# that first trip a place (MASTER_GIFT): the game's side gives what this place holds in the seed's list of checks, and
# marks it given by its key in the save (a gift's key, gift_keys), so it is given once. A chest gives the sword by
# its own name (seen without a window, 2026-11-20: "You got the Master Sword!", held up as the game shows it). The
# pedestal's item is put in the pouch by the game's side, so it holds only what the pouch takes by name
# (pedestal_holds). The rules: wherever only an adult goes, the sword is asked for too (door_need), so the logic
# never wants adult Link to fight without it. Adult Link can go through time and back without it (the game's side
# asks for the plain ways itself). Left as it is: the story's own drawing at the quest's Step06
# (Dm_TimeTemple_0030) gives the sword too, which can only make a seed easier. Needs Open Door of Time.
MASTER = "Weapon_Sword_Master"
MASTER_GIFT = Gift("master_sword", "", (), MASTER, "Market", "the Master Sword's pedestal: the first trip through time", CHILD, "master")
MASTER_SHUFFLED = False   # (main sets it: door_need asks for the sword in an adult's places)
# (where the Tracker's Go there puts Link for a gift whose place is not where he can stand: before the pedestal, as seen
#  without a window 2026-11-20, his feet at 106.1)
GIFT_STAND = {"master_sword": (137.6, 105.1, -32.3)}


def pedestal_holds(item):
    """whether the pedestal may hold `item`: what the pouch takes by name (an item's or a weapon's own), not a song, a
    dungeon's item, a token or a fairy's magic (each of those the game gives its own way)"""
    return (item.startswith(("Item_", "Weapon_")) and not item.startswith(("Item_Melody_", "Item_FairyBless_")) and
            item not in DUNGEON_ITEMS and item != TOKEN)


def ocarina_need(need, lesson=False):
    """a rule with the ocarina asked for in each way that names a song (and in every way of a lesson's)"""
    def way(w):
        return w | {OCARINA} if lesson or any(i.startswith("Item_Melody_") for i in w) else w
    return each(way, need)


# ---- The settings that move no item, on the stamp's second line (asked for 2026-11-17: QoL settings changed on a save
# being played) ----
# The stamp's first line is a seed's settings: a seed whose first line is another's is made anew with today's rules
# (placement), which moves its items. Skip opening, Skip cutscenes, Starting rupees and Gold Skulltulas by day change
# no rule and draw nothing from the shuffle's random: their words (QOL_STAMP) are on the second line, the fixes', so
# turning one on or off for a seed being played writes it again as it was. A stamp written before has them on its
# first line: they are taken out of it to compare (stamp_settings), and the Tracker's records of that seed
# (rando/collected.txt, rando/junk.txt: their first line is "seed " and the stamp's first line) are moved to the new
# first line, so the marks are kept (records_moved).
QOL_STAMP = (" intro skipped", " talks skipped", " rupees %d" % START_RUPEES, " skulltulas by day", " scrubs cheap")
RECORDS = ("collected.txt", "junk.txt")


def stamp_settings(line):
    """a stamp's first line without the words of the settings that move no item (QOL_STAMP)"""
    for word in QOL_STAMP:
        line = line.replace(word, "")
    return line


def records_moved(folder, was, now):
    """the Tracker's records in folder (RECORDS) of the stamp's first line `was` moved to `now`: how many were"""
    moved = 0
    for name in RECORDS:
        path = os.path.join(folder, name)
        try:
            with open(path, encoding="utf-8", newline="") as f:
                text = f.read()
        except OSError:
            continue
        first, sep, body = text.partition("\n")
        if first.rstrip("\r") != "seed " + was:
            continue
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("seed " + now + ("\r" if first.endswith("\r") else "") + sep + body)
        moved += 1
    return moved


# ---- The Door of Time by the Song of Time (rando_open_door 2, asked for 2026-11-16) ----
# With Open Door of Time off, the door opens once Link holds the Song of Time and an ocarina, no stones. The game opens a
# map file once a session and keeps it, so the door is not taken out of the map (door_away) but by the game's side: as
# the Market's actors are read at each entry into the area, it answers the door's name with an invisible effect marker
# of the temple's own once Link holds them (host/hos_main.c, the door's stand-in; seen without a window 2026-11-19:
# the doorway open, and Link walked through to x 124.8 where the door stops him at 117.5). It also sets the door's flags
# and gives the sword's way through time as Open Door of Time does. The seed moves Sheik aside (bug 19) and gives the
# adult the sword's prompt. Rules: with the songs shuffled (the Song of Time can come before the stones) the places only
# an adult has ask for the Song of Time in place of what it takes to be an adult (door_need, song); otherwise the song
# comes after the stones as in the game, and the rules are the game's.
DOOR_SONG = 2


def remove_old(mod):
    """the files a run before this one wrote (its list: rando_manifest.txt), and the folders they leave empty"""
    listing = os.path.join(mod, "rando_manifest.txt")
    if not os.path.isfile(listing):
        return 0
    n = 0
    with open(listing, encoding="utf-8") as f:
        rels = [line.strip() for line in f if line.strip()]
    for rel in rels + ["spoiler.txt", TRACKER, CHECKS, SHELF_FLAGS, SHELF_TIERS, "rando_stamp.txt", "rando_manifest.txt"]:
        path = os.path.normpath(os.path.join(mod, rel))
        if not path.startswith(os.path.normpath(mod) + os.sep) or not os.path.isfile(path):   # (only inside the mod's folder)
            continue
        os.remove(path)
        n += 1
        folder = os.path.dirname(path)
        while folder != os.path.normpath(mod) and not os.listdir(folder):
            os.rmdir(folder)
            folder = os.path.dirname(folder)
    if os.path.isdir(mod) and not os.listdir(mod):
        os.rmdir(mod)
    return n


def place(rng, spots, which, keys_mode, needs=None, bound=None, only=None, apart=(), holds=None, counted=False, fixed_more=(), loose=frozenset()):
    """What each chest holds. spots: {hash: (area, item, is a dungeon's chest, why it stays or None)}, in a fixed order.
    needs: {hash: what the chest asks for} for the logic, or None: no logic.
    Returns ({hash: item} for the chests that take part, how many chests stay for each reason, the spheres or None).
    With the logic, the thirteen gating items are placed so that each can be reached with the others (an assumed
    fill), counting the ones that stay in their own chests; then the rest goes where there is room.
    bound: None, or (items, hashes): those items go to those spots only, and those spots hold nothing else (the songs
    and the lessons); or a list of such pairs, each a group of its own (the songs, and the dungeons' rewards).
    only: None, or {hash: (items, more items)}: that spot holds one of those items and nothing else (Songs: Anywhere,
    the lessons asked about by name). It is given one of `items` when one is left, else one of `more items`; the
    logic may put a gating item of either there, and does when too few of the others are left for them all.
    apart: spots that are not a dungeon's chests though they are in its area (the lessons).
    holds: None, or {hash: the items that spot may hold}: it is given none other (placement 12: the Gold Skulltulas
    and the Pieces of Heart lying in the world, skulltula_holds and piece_holds); the others take the rest. A token
    the logic places goes to such a spot first while the items it does not place could not fill them all, and an
    arrangement whose items left could not is tried again.
    counted: the tokens are placed by the logic too, after the gating items, for the rules that count them (tokens):
    each where it can be reached with the items still to be placed, as a gating item is.
    fixed_more: [(what it asks for, its item)] of places that are not spots and keep an item the logic counts (a Gold
    Skulltula that keeps its token)."""
    only = only or {}
    groups = [g for g in ([bound] if isinstance(bound, tuple) else bound or []) if g]
    bound = groups or None
    bound_items = frozenset(i for items, _ in groups for i in items)
    bound_spots = frozenset(h for _, hashes in groups for h in hashes)
    group_of_item = lambda item: next((k for k, (items, _) in enumerate(groups) if item in items), None)
    group_of_spot = lambda h: next((k for k, (_, hashes) in enumerate(groups) if h in hashes), None)
    fits = lambda item, h: group_of_item(item) == group_of_spot(h) and (h not in only or item in only[h][0] or item in only[h][1])

    def fill_only(spots_left, items_left):
        """{spot: item} for the spots of `only` among spots_left, from items_left: the first kind while one is
        left, then the other. None when one of them has nothing it may hold."""
        out, left = {}, list(items_left)
        for h in [h for h in spots_left if h in only]:
            for kind in only[h]:
                mine = sorted(set(i for i in left if i in kind))
                if mine:
                    break
            else:
                return None
            out[h] = rng.choice(mine)
            left.remove(out[h])
        return out

    def holds_short(spots_left, items_left):
        """how many of the spots of `holds` among spots_left would find nothing they may hold among items_left: their
        kinds taken as nested, the smallest first (the Gold Skulltulas' within the pieces')"""
        left = [h for h in spots_left if h in holds]
        short = 0
        for kind in sorted({holds[h] for h in left}, key=len):
            short = max(short, sum(1 for h in left if holds[h] <= kind) - sum(1 for i in items_left if i in kind))
        return short
    stays = collections.Counter()
    pool = []
    for h, (area, item, dungeon, why) in spots.items():
        if not why and dungeon is not None and (which == 1 and dungeon or which == 2 and not dungeon):   # (None: a gift, of neither kind)
            why = "not this Chests setting's"
        if not why and keys_mode == 0 and item in DUNGEON_ITEMS and item not in loose:   # (loose: anywhere, MAPS_LOOSE)
            why = "a dungeon's key, map or compass (Dungeon keys: Off)"
        if why:
            stays[why] += 1
        else:
            pool.append(h)
    gives = {}
    # a dungeon's keys, map and compass first, among that dungeon's own chests
    by_area = collections.OrderedDict()
    for h in pool:
        by_area.setdefault(spots[h][0], []).append(h)
    for area, here in by_area.items():
        own = [spots[h][1] for h in here if spots[h][1] in DUNGEON_ITEMS and spots[h][1] not in loose]
        if bound or apart:   # (a lesson in a dungeon's area is not one of its chests)
            here = [h for h in here if h not in bound_spots and h not in apart]
        if holds:   # (a Gold Skulltula of a dungeon holds none of its keys)
            here = [h for h in here if h not in holds or set(own) <= holds[h]]
        for h, item in zip(rng.sample(here, len(own)), own):
            gives[h] = item
    rest = [h for h in pool if h not in gives]
    items = [spots[h][1] for h in pool if spots[h][1] not in DUNGEON_ITEMS or spots[h][1] in loose]
    spheres = None
    held = None   # (what the spots of `only` hold that the logic did not put there)
    if needs is not None:
        gating = sorted(i for i in items if i in PROGRESSION)
        tokens_in = [i for i in items if counted and i == TOKEN]   # (placed after the gating items: counted)
        # (a gating item in a chest that stays is got there, as the game has it; and a token that stays, counted)
        fixed = [(needs[h], spots[h][1]) for h in spots if h not in pool and (spots[h][1] in PROGRESSION or counted and spots[h][1] == TOKEN)]
        fixed += list(fixed_more)
        plain_items = [i for i in items if i not in PROGRESSION and not (counted and i == TOKEN)]   # (what the logic does not place)
        for attempt in range(400):
            order = list(gating)
            rng.shuffle(order)
            order += tokens_in
            placed, ok = {}, True
            # (the spots of `only` that the items of their first kind which are not gating cannot fill: so many gating
            #  items of that kind go to them, so that the second kind, the songs, is left for the world)
            short = songs_in = 0
            if only:
                plain = [i for i in items if i not in PROGRESSION]
                first = lambda i: any(i in kinds[0] for kinds in only.values())
                spots_only = sum(1 for h in rest if h in only)
                short = max(0, spots_only - sum(1 for i in plain if first(i)))
                # (and the ones that neither their first kind nor the second kind's plain items can fill: so many gating
                #  items of the second kind, songs, go to them after all)
                songs_in = max(0, spots_only - sum(1 for i in items if first(i)) - sum(1 for i in plain if not first(i) and any(i in kinds[1] for kinds in only.values())))
            for k, item in enumerate(order):
                # Link with every gating item still to be placed, and what the chests filled so far then give him
                have = reach(order[k + 1:], fixed + [(needs[h], i) for h, i in placed.items()])
                free = [h for h in rest if h not in placed and met(needs[h], have) and (not (bound or only) or fits(item, h)) and
                        (not holds or h not in holds or item in holds[h])]
                if short and any(h in only and item in only[h][0] for h in free):
                    free, short = [h for h in free if h in only and item in only[h][0]], short - 1
                elif only and not first(item) and songs_in and any(h in only for h in free):
                    free, songs_in = [h for h in free if h in only], songs_in - 1
                elif only and not first(item) and any(h not in only for h in free):
                    free = [h for h in free if h not in only]   # (an item of their second kind, a song: out in the world where it can be)
                if holds and counted and item == TOKEN and any(h in holds for h in free) and holds_short([h for h in rest if h not in placed], plain_items):
                    free = [h for h in free if h in holds]   # (a token to a Skulltula while the items left could not fill them all)
                if not free:
                    ok = False
                    break
                placed[rng.choice(free)] = item
            if ok and only:
                held = fill_only([h for h in rest if h not in placed], [i for i in items if i not in PROGRESSION and not (counted and i == TOKEN)])
                ok = held is not None
            if ok and holds:   # (the items left can fill the spots of `holds` that are left)
                left_items = list(plain_items)
                for i in (held or {}).values():
                    left_items.remove(i)
                ok = not holds_short([h for h in rest if h not in placed and h not in (held or {})], left_items)
            if ok:
                spheres = collect(fixed + [(needs[h], i) for h, i in placed.items()])
                if {i for sphere in spheres for i in sphere} >= {i for _, i in fixed if i in PROGRESSION} | set(gating):   # (a token kept in place is counted, not a sphere's)
                    break
            spheres = None
        if spheres is None:
            raise ValueError("no arrangement the logic accepts was found: fewer chests take part than it needs")
        gives.update(placed)
        rest = [h for h in rest if h not in placed]
        items = [i for i in items if i not in PROGRESSION and not (counted and i == TOKEN)]
    elif only:
        held = fill_only(rest, items)
        if held is None:
            raise ValueError("a lesson has nothing left that it may hold")
    if held:
        gives.update(held)
        rest = [h for h in rest if h not in held]
        for item in held.values():
            items.remove(item)
    for group_items, group_spots in groups:   # (the songs that are left, among the lessons that are left; and so each group)
        mine, theirs = [h for h in rest if h in group_spots], [i for i in items if i in group_items]
        rng.shuffle(theirs)
        gives.update(zip(mine, theirs))
        rest, items = [h for h in rest if h not in group_spots], [i for i in items if i not in group_items]
    # everything else among the chests that are left, wherever they are
    rng.shuffle(items)
    if holds:   # (a spot of `holds` first: the first of the shuffled items it may hold; the others take the rest)
        order = [h for h in rest if h in holds]
        if MASTER_SHUFFLED or loose:   # (and with MAPS_LOOSE every spot but a chest is one: the fussiest first) (the pedestal's few kinds before the shelves', which take nearly anything: the fewest first)
            order.sort(key=lambda h: len(holds[h]))
        for h in order:
            k = next((k for k, i in enumerate(items) if i in holds[h]), None)
            if k is None:
                raise ValueError("a Gold Skulltula or a Piece of Heart has nothing left that it may hold")
            gives[h] = items.pop(k)
        rest = [h for h in rest if h not in holds]
    for h, item in zip(rest, items):
        gives[h] = item
    return gives, stays, spheres


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("romfs")
    p.add_argument("--game", help="the game folder (default: the folder the romfs is in)")
    p.add_argument("--seed", type=int, help="in place of the options file's rando_seed (and the randomizer counts as on)")
    p.add_argument("--chests", type=int, choices=(0, 1, 2, 3), help="in place of rando_chests: 1 overworld, 2 dungeons, 3 all")
    p.add_argument("--keys", type=int, choices=(0, 1, 2), help="in place of rando_keys: 0 off, 1 own dungeon, 2 anywhere (as 1)")
    p.add_argument("--event-chests", action="store_true", help="chests that start an event take part too: most of the big items, placed by the logic")
    p.add_argument("--no-logic", action="store_true", help="with --event-chests: the big items anywhere, whether the seed can be finished or not")
    p.add_argument("--open-deku", action="store_true", help="as rando_open_deku=1: in a new game the way to the Deku Tree is open without a sword and a shield")
    p.add_argument("--open-forest", action="store_true", help="as rando_open_forest=1: in a new game the forest can be left before the Deku Tree is done")
    p.add_argument("--open-door", action="store_true", help="as rando_open_door=1: in a new game the Door of Time is open (OPEN_DOOR); the game's side lets the "
                                                             "Master Sword take Link through time from then on")
    p.add_argument("--skip-intro", action="store_true", help="as rando_skip_intro=1: a new game starts in Link's house, without the two opening cutscenes")
    p.add_argument("--skip-cutscenes", action="store_true", help="as rando_skip_cutscenes=1: the scenes played as flowcharts lose their talks, camera moves and waits (quiet_scene); the game's side skips the others")
    p.add_argument("--skulltulas", type=int, choices=(0, 1, 2, 3), help="in place of rando_skulltulas: the Gold Skulltulas whose tokens change places "
                                                                        "with the chests' rupees and supplies (from placement 12: that take part as chests do, "
                                                                        "skulltula_holds). 1 dungeons, 2 overworld, 3 all")
    p.add_argument("--quests", action="store_true", help="as rando_quests=1: what characters give takes part with the chests (GIFTS)")
    p.add_argument("--frogs", action="store_true", help="not used any more: with Quest rewards the frogs of Zora's River always take part")
    p.add_argument("--light-arrows", action="store_true", help="as rando_light_arrows=1: with Quest rewards, Zelda's Light Arrows take part too")
    p.add_argument("--scrubs", action="store_true", help="as rando_scrubs=1: the Business Scrubs' four one-time sales take part with the chests (SCRUBS)")
    p.add_argument("--shops", type=int, choices=(0, 1, 2, 3), help="in place of rando_shops: four shelves of each shop sell a shuffled item, once (SHOPS). "
                                                               "1: low prices, 2: any price, 3: Affordable, every shelf 10 rupees (shop_price)")
    p.add_argument("--shop-shelves", type=int, choices=(0, 1), help="in place of rando_shop_shelves: with Shops, 0 four shelves of each shop, 1 every shelf (shop_slots)")
    p.add_argument("--sword-shield", type=int, choices=(0, 1), help="in place of rando_sword_shield: 0 the Kokiri Sword stays in its chest and the Deku Shield on "
                                                                     "its shelf, 1 both take part (the chest with Major items, the shelf with Shops)")
    p.add_argument("--ageless", type=int, choices=range(8), help="a sum: 1 the swords for both ages, 2 the age-only items, 4 the tunics (as rando_ageless, rando_ageless_items and rando_ageless_tunics)")
    p.add_argument("--start", default=None, help="as rando_start_items=KS,SL,...: a new game starts with them (START_ITEMS)")
    p.add_argument("--free-scarecrow", action="store_true", help="as rando_free_scarecrow=1: a save without a Scarecrow's Song is given L R L R L (FREE_SCARECROW_FILE); moves no item")
    p.add_argument("--castle-guards", action="store_true", help="as rando_castle_guards=1: a castle guard who spots young Link lets him pass (castle_guards_pass); moves no item")
    p.add_argument("--ocarinas", action="store_true", help="as rando_ocarinas=1: both ocarinas are items of the shuffle (OCARINA_GIFT, OCARINA_TIME_GIFT); with Songs on")
    p.add_argument("--epona-song", action="store_true", help="as rando_epona_song=1: the first time an adult plays Epona's Song where Link can ride, Epona is his (epona_song_flows); moves no item")
    p.add_argument("--chest-size", action="store_true", help="as rando_chest_size=1: a chest holding a major item is a big chest, any other a small one (CHEST_SIZES); moves no item")
    p.add_argument("--letter", action="store_true", help="as rando_letter=1, Kakariko gate: Letter shuffled (letter_need)")
    p.add_argument("--master-sword", action="store_true", help="as rando_master_sword=1: the Master Sword is an item of the shuffle and the pedestal a place (MASTER_GIFT; needs Open Door of Time)")
    p.add_argument("--dampe-hookshot", action="store_true", help="as rando_dampe_hookshot=1: Dampe's race's Hookshot chest takes part and the Hookshot is a gating item (HOOK)")
    p.add_argument("--hints", action="store_true", help="as rando_hints=1: the Gossip Stones give hints (choose_hints)")
    p.add_argument("--skulltulas-day", action="store_true", help="as rando_skulltulas_day=1: the night-only Gold Skulltulas are out by day too (NOCTURNAL)")
    p.add_argument("--heart-pieces", action="store_true", help="as rando_heart_pieces=1: the Pieces of Heart lying in the world change places with "
                                                                "the chests' items a pick-up can be, and may hold a gating item (from placement 12: take "
                                                                "part as chests do, piece_holds)")
    p.add_argument("--songs", type=int, choices=(0, 1, 2), help="in place of rando_songs: 1, the twelve songs are shuffled among the twelve lessons (SONGS). "
                                                               "2, Anywhere: the songs are in the pool with every other item, and a lesson is a place as a gift is")
    p.add_argument("--dungeon-rewards", type=int, choices=(0, 1, 2), help="in place of rando_dungeon_rewards: the eight dungeons' stones and medallions are "
                                                                         "shuffled among their eight endings (REWARDS). 2, one in any item's place, is not made yet: as 1")
    p.add_argument("--progressive", action="store_true", help="as rando_progressive=1: the rules count an upgrade found as the next of its family")
    p.add_argument("--start-rupees", action="store_true", help="as rando_start_rupees=1: a new game starts with %d rupees" % START_RUPEES)
    p.add_argument("--if-changed", action="store_true", help="do nothing when the mod is already this seed's (the launcher, at Play)")
    p.add_argument("--dry-run", action="store_true", help="say what would change, write nothing")
    a = p.parse_args()
    romfs = os.path.abspath(a.romfs)
    game = os.path.abspath(a.game) if a.game else os.path.dirname(romfs)
    mod = os.path.join(game, "mods", MOD)
    ini = settings(game)
    on = ini["rando_on"] != 0 or a.seed is not None
    seed = a.seed if a.seed is not None else ini["rando_seed"]
    which = a.chests if a.chests is not None else ini["rando_chests"]
    keys_mode = a.keys if a.keys is not None else ini["rando_keys"]
    which = which if 0 <= which <= 3 else 0
    keys_mode = keys_mode if 0 <= keys_mode <= 2 else 0
    stamp_path = os.path.join(mod, "rando_stamp.txt")
    # A seed made before the Major items setting, with --event-chests (its spoiler lists the gating items; it has no
    # stamp): the setting is turned on for it, so that the same seed is made again and not another under its save.
    try:
        old = "" if os.path.isfile(stamp_path) else open(os.path.join(mod, "spoiler.txt"), encoding="utf-8").read()
    except OSError:
        old = ""
    if on and "the gating items" in old and not ini["rando_major"] and not a.event_chests and not a.dry_run:
        set_option(game, "rando_major", 1)
        ini["rando_major"] = 1
        print("this seed was made with the big items shuffled: Major items is now On in the options, to keep it as it is")
    a.event_chests = a.event_chests or ini["rando_major"] != 0
    a.songs = a.songs if a.songs is not None else ini["rando_songs"]
    # (the ocarinas shuffled: Songs' old fourth choice, "Anywhere, ocarina too", or rando_ocarinas with Songs on (the asked
    #  for songs name the ocarina, ocarina_need: without them shuffled nothing would), asked 2026-11-21. The stamp's word
    #  is the same, " ocarina 1" on the songs': a seed made with the fourth choice is the same seed)
    a.ocarina = SONGS_ANYWHERE and (a.songs == 3 or (bool(a.ocarinas or ini["rando_ocarinas"] == 1) and a.songs in (1, 2)))
    a.songs = 2 if a.songs == 3 else a.songs
    a.songs = (a.songs if SONGS_ANYWHERE else 1) if a.songs in (1, 2) else 0
    a.dungeon_rewards = a.dungeon_rewards if a.dungeon_rewards is not None else ini["rando_dungeon_rewards"]
    a.dungeon_rewards = 1 if a.dungeon_rewards in (1, 2) and REWARDS_READY else 0
    a.heart_pieces = a.heart_pieces or ini["rando_heart_pieces"] != 0
    a.skulltulas_day = a.skulltulas_day or ini["rando_skulltulas_day"] != 0
    a.hints = a.hints or ini["rando_hints"] != 0
    a.chest_size = a.chest_size or ini["rando_chest_size"] != 0
    a.epona_song = a.epona_song or ini["rando_epona_song"] != 0
    a.castle_guards = a.castle_guards or ini["rando_castle_guards"] != 0
    a.gerudo_guards = ini["rando_gerudo_guards"] != 0   # (GERUDO_GUARDS_FLOW, 2026-11-24: a Quality of life setting; moves no item)
    a.house_hints = ini["rando_house_hints"] != 0       # (HOUSE_HINT_TEXT, 2026-11-24: a Quality of life setting; moves no item)
    a.maps = ini["rando_maps"] if ini["rando_maps"] in (0, 1, 2) else 0   # (Maps and compasses: MAPS_START, MAPS_LOOSE)
    a.pots = ini["rando_pots"] == 1   # (Pots: the tables' pots take part, POT_OWN)
    a.boss_keys = ini["rando_boss_keys"] == 1   # (Boss Keys: Anywhere, boss_key_tag; with Small keys: Anywhere too, below)
    if keys_mode == 2:   # (Small keys: Anywhere: the Boss Keys and the maps "With the keys" go with them, key_tags)
        a.boss_keys = True
        a.maps = a.maps or 1
    a.soil_bottle = ini["rando_soil_bottle"] != 0       # (SOIL_FILES, 2026-11-24: a Quality of life setting; moves no item)
    a.fast_push = ini["rando_fast_push"] != 0           # (FAST_PUSH, 2026-11-24: the blocks' curves; moves no item)
    a.archery_wins = ini["rando_archery_wins"] != 0     # (ARCHERY_WINS, 2026-11-24: qol_flow; moves no item)
    a.any_fish = ini["rando_any_fish"] != 0             # (time savers, 2026-11-22: qol_flow; move no item)
    a.skull_kid_fast = ini["rando_skull_kid_fast"] != 0
    a.skip_tower = ini["rando_skip_tower"] != 0
    a.fairy_prices = FAIRY_PRICE_OLD.get(ini["rando_fairy_prices"], ini["rando_fairy_prices"])
    a.fairy_prices = a.fairy_prices if 0 <= a.fairy_prices <= 3 else 0   # (FAIRY_PRICE_MODES)
    a.free_scarecrow = a.free_scarecrow or ini["rando_free_scarecrow"] != 0
    a.start = start_codes(a.start if a.start is not None else start_option(game))   # (Starting items: START_ITEMS)
    a.gate_open = ini["rando_letter"] == 2   # (Kakariko gate Open: the overworld's rules by it, placement 23, OVERWORLD_RULES)
    a.letter = a.letter or ini["rando_letter"] == 1   # (Kakariko gate: 1 the letter shuffled, 2 open: the game's side's,
    #  host/hos_main.c oot_open_death_mountain, and the letter stays Zelda's)
    # (two settings since 2026-11-19: rando_ageless the swords, rando_ageless_items the age-only items; an older seed's
    #  rando_ageless=2 was both. a.ageless: 1 the swords, 2 the items, 3 both)
    if a.ageless is None:
        a.ageless = ((1 if ini["rando_ageless"] in (1, 2) else 0) | (2 if ini["rando_ageless"] == 2 or ini["rando_ageless_items"] == 1 else 0) |
                     (4 if ini["rando_ageless_tunics"] == 1 else 0))
    # (the songs gate the game: with them shuffled the logic places them, whatever Major items says)
    logic_now = (a.event_chests or bool(a.songs)) and not a.no_logic
    # (the options file's rando_open_deku and rando_open_forest too, so that the launcher's run at Play keeps them)
    a.open_deku = a.open_deku or ini["rando_open_deku"] != 0
    a.open_forest = a.open_forest or ini["rando_open_forest"] != 0
    a.door_song = not a.open_door and ini["rando_open_door"] == 2   # (DOOR_SONG: the door by the Song of Time)
    a.open_door = a.open_door or ini["rando_open_door"] == 1
    a.master_sword = a.master_sword or ini["rando_master_sword"] == 1   # (Shuffle the Master Sword: MASTER_GIFT)
    # (Dampe's Hookshot: shuffled in every seed from placement 19 (DAMPE_HOOK_FROM); before, by the setting it had for a
    #  day, rando_dampe_hookshot, which a seed made with it keeps: its stamp says " dampe hookshot 1")
    a.dampe_hookshot = a.dampe_hookshot or ini.get("rando_dampe_hookshot", 0) == 1
    global HOOK_SHUFFLED
    if a.master_sword and not (a.open_door or a.door_song):
        print("Shuffle the Master Sword needs Open Door of Time: left off")
        a.master_sword = False
    a.skip_intro = a.skip_intro or ini["rando_skip_intro"] != 0
    a.skip_cutscenes = a.skip_cutscenes or ini["rando_skip_cutscenes"] != 0
    a.start_rupees = a.start_rupees or ini["rando_start_rupees"] != 0
    a.scrubs = a.scrubs or ini["rando_scrubs"] != 0
    a.scrubs_cheap = a.scrubs and ini["rando_scrubs"] == 2   # (On, 10 rupees each: SCRUB_CHEAP)
    a.progressive = a.progressive or ini["rando_progressive"] != 0
    a.shops = a.shops if a.shops is not None else ini["rando_shops"]
    a.shops = a.shops if 0 <= a.shops <= 3 else 0
    a.shop_shelves = (a.shop_shelves if a.shop_shelves is not None else ini["rando_shop_shelves"]) == 1 and a.shops != 0
    a.sword_shield = (a.sword_shield if a.sword_shield is not None else ini["rando_sword_shield"]) == 1
    shield_shelf = a.sword_shield and a.shops != 0   # (the Deku Shield's shelf takes part: with Shops)
    a.skulltulas = a.skulltulas if a.skulltulas is not None else ini["rando_skulltulas"]
    a.skulltulas = a.skulltulas if 0 <= a.skulltulas <= 3 else 0
    a.quests = a.quests or ini["rando_quests"] != 0
    a.magic = ini["rando_magic"] == 1 and a.quests   # (Magic and the fairies' gifts: with Quest rewards)
    a.frogs = a.quests   # (no longer a choice of its own: the frogs take part whenever Quest rewards is on; rando_frogs and --frogs are read and not used)
    a.light_arrows = a.quests and (a.light_arrows or ini["rando_light_arrows"] != 0)
    # A test: <game folder>\rando\test_drops.txt, lines of "<an actor's hash> <an item>": that actor (a Gold Skulltula,
    # say) drops the item. For finding how the other kinds of check hold what they give; not a setting.
    drops = {}
    try:
        with open(os.path.join(game, "rando", "test_drops.txt"), encoding="utf-8") as f:
            for line in f:
                parts = line.split("#")[0].split()
                if len(parts) == 2:
                    drops[int(parts[0], 16)] = parts[1]
    except (OSError, ValueError):
        pass
    # Another: <game folder>\rando\test_chests.txt, lines of "<a chest's hash> <an item>": that chest gives the item,
    # whatever the seed put there (a gating item within reach, to try what comes after it). The seed's own count of
    # each item is not kept by it, and the spoiler's order of the gating items does not know of it.
    test_chests = {}
    try:
        with open(os.path.join(game, "rando", "test_chests.txt"), encoding="utf-8") as f:
            for line in f:
                parts = line.split("#")[0].split()
                if len(parts) == 2:
                    test_chests[int(parts[0], 16)] = parts[1]
    except (OSError, ValueError):
        pass
    # Another: <game folder>\rando\test_gifts.txt, lines of "<a flow's name> <the item it gives> <another item>": that
    # scene gives the other item (gift_item). For finding how a character's gift can be changed; not a setting.
    test_gifts = []
    try:
        with open(os.path.join(game, "rando", "test_gifts.txt"), encoding="utf-8") as f:
            test_gifts = [tuple(line.split("#")[0].split()) for line in f if len(line.split("#")[0].split()) == 3]
    except OSError:
        pass
    # Another: <game folder>\rando\test_pickups.txt, an item's actor on each line (Item_Boomerang): its pack is made a
    # pick-up's (pickup_pack), so that it can be collected where a Skulltula drops it.
    pickups, skull_tier_list = [], []
    try:
        with open(os.path.join(game, "rando", "test_pickups.txt"), encoding="utf-8") as f:
            pickups = sorted({line.split("#")[0].strip() for line in f} - {""})
    except OSError:
        pass
    flags = {}
    # (the loop's variable was named `on` once and wrote over the randomizer's switch: with the forest's way open the
    #  script took the randomizer for on whatever the options said, and never took a seed away. Seen in play: a normal
    #  game with a seed's chests)
    for name, opened in (("deku", a.open_deku), ("forest", a.open_forest)):
        if opened:
            flags.update(OPEN[name])
    # (the open ways are only named when one is open: the seeds made before them keep their stamp)
    try:   # (a seed made with Shuffle Dampe's Hookshot keeps it, whether or not the options file still names it)
        if " dampe hookshot 1" in open(stamp_path, encoding="utf-8").read().split("\n")[0]:
            a.dampe_hookshot = True
    except OSError:
        pass
    rest = " seed %d chests %d keys %d major %d logic %d%s\n" % (seed, which, keys_mode, a.event_chests, logic_now,
                                                               (" open %d%d flags" % (a.open_deku, a.open_forest) if flags else "") + (" door 7" if a.open_door else "") + (" door song 1" if a.door_song else "") + (" intro skipped" if a.skip_intro else "") + (" talks skipped" if a.skip_cutscenes else "") + (" rupees %d" % START_RUPEES if a.start_rupees else "") + ((" skulltulas %d" + " gated all" * logic_now) % a.skulltulas if a.skulltulas else "") +
                                                               (" quests 1%s%s" % (" frogs" * a.frogs, " light" * a.light_arrows) if a.quests else "") + (" scrubs 1 words 2" if a.scrubs else "") + (" scrubs cheap" if a.scrubs_cheap else "") + (" shops %d prices 5" % a.shops if a.shops else "") + (" shelves all" if a.shop_shelves else "") + (" fairies %d" % a.fairy_prices if a.fairy_prices else "") + (" sword and shield 1" if a.sword_shield else "") + (" progressive 1" if a.progressive else "") + (" songs 2%s%s" % (" anywhere 2" if a.songs == 2 else "", " ocarina 1" if a.ocarina else "") if a.songs else "") + (" rewards 1" if a.dungeon_rewards else "") + (" hearts 2" if a.heart_pieces else "") + (" skulltulas by day" if a.skulltulas_day else "") + (" letter 1" if a.letter else "") + (" gate open" if a.gate_open else "") + (" start " + ",".join(a.start) if a.start else "") + (" master sword 2" if a.master_sword else "") + (" dampe hookshot 1" if a.dampe_hookshot else "") + (" magic 1" if a.magic else "") + (" maps %d" % a.maps if a.maps else "") + (" boss keys 1" if a.boss_keys else "") + (" pots 1" if a.pots else "") + " checks 10" +
                                                               (" test drops %08x" % (zlib.crc32(repr(sorted(drops.items())).encode()) & 0xffffffff) if drops else "") +
                                                               (" test pickups " + ",".join(pickups) if pickups else "") +
                                                               (" test chests %08x" % (zlib.crc32(repr(sorted(test_chests.items())).encode()) & 0xffffffff) if test_chests else "") +
                                                               (" test gifts %08x" % (zlib.crc32(repr(sorted(test_gifts)).encode()) & 0xffffffff) if test_gifts else ""))
    # (the settings that move no item: on the second line, QOL_STAMP)
    qol = "".join(word for word in QOL_STAMP if word + " " in rest or word + "\n" in rest)
    rest = stamp_settings(rest)
    # (the seed in the game folder, made by an earlier version of the rules: made again as it was, not another one
    # under its save. A new seed, or other settings, take the rules of today)
    placement = PLACEMENT
    was_first = None
    try:
        was = open(stamp_path, encoding="utf-8").read()
        was_first = was.split("\n")[0]
        was = stamp_settings(was_first) + "\n"   # (the first line: the settings. The second, later: the fixes)
        if was.startswith("placement ") and was.split(" ", 2)[2:] == [rest[1:]] and 1 <= int(was.split()[1]) < PLACEMENT:
            placement = int(was.split()[1])
    except (OSError, ValueError):
        pass
    a.dampe_hookshot = a.dampe_hookshot or placement >= DAMPE_HOOK_FROM   # (Dampe's Hookshot shuffled: HOOK)
    HOOK_SHUFFLED = a.dampe_hookshot
    stamp = "placement %d%sfixes %d\n" % (placement, rest, FIXES_VERSION)   # (the fixes: the same items, written again)
    if qol:
        stamp = stamp[:-1] + qol + "\n"
    if was_first is not None and was_first != stamp.split("\n")[0] and stamp_settings(was_first) == stamp.split("\n")[0] and not a.dry_run:
        moved = records_moved(os.path.join(game, "rando"), was_first, stamp.split("\n")[0])
        if moved:
            print("the Tracker's records of this seed kept: %d moved to its stamp without the settings that move no item" % moved)
    if a.hints:   # (the hints move no item: on the fixes' line, so a seed's shuffle stays as it was with them turned on)
        stamp = stamp[:-1] + " hints %d\n" % HINTS_VERSION
    if a.chest_size:   # (moves no item: the same line)
        stamp = stamp[:-1] + " chests sized\n"
    if a.epona_song:   # (moves no item either: the same line)
        stamp = stamp[:-1] + " epona by song\n"
    if a.castle_guards:   # (moves no item either: the same line)
        stamp = stamp[:-1] + " guards pass\n"
    for saver_on, word in ((a.any_fish, " any fish"), (a.skull_kid_fast, " skull kid fast"), (a.skip_tower, " tower skipped"),
                           (a.archery_wins, " archery won"), (a.fast_push, " fast push"), (a.soil_bottle, " soil bottle"),
                           (a.gerudo_guards, " gerudo guards pass"), (a.house_hints, " house hints")):
        if saver_on:   # (the time savers: move no item either, the same line. Not `on`: that is the randomizer's own, below)
            stamp = stamp[:-1] + word + "\n"
    if a.free_scarecrow:   # (moves no item either: the same line)
        stamp = stamp[:-1] + " scarecrow free\n"
    if a.ageless:   # (moves no item either: the same line)
        stamp = stamp[:-1] + " ageless %d\n" % a.ageless
    if read_pins():   # (test pins: another file, another seed)
        stamp = stamp[:-1] + " pins %r\n" % (read_pins(),)
    print("randomizer %s, seed %d, chests %s, dungeon keys %s, major items %s" % (
        "on" if on else "off", seed, ("off", "overworld", "dungeons", "all")[which],
        ("off", "own dungeon", "anywhere")[keys_mode], "on" if a.event_chests else "off"))
    if a.if_changed and on and which:
        try:
            if open(stamp_path, encoding="utf-8").read() == stamp:
                print("the mod is already this seed's: nothing to do")
                return
        except OSError:
            pass
    # (the test mods change the same files, and one carries a size table of its own that would win over this one's)
    tests = [os.path.join(game, "mods", n) for n in ("rando-poc", "rando-zz-test2") if os.path.isdir(os.path.join(game, "mods", n))]
    if tests and not a.dry_run:
        sys.exit("Delete the test mods first, then run this again:\n  " + "\n  ".join(tests))
    if not on or which == 0:
        n = 0 if a.dry_run else remove_old(mod)
        print("nothing to shuffle (turn Randomizer on and set Chests in the menu's Randomizer tab)%s" % (
            ": %d files of the last seed removed" % n if n else ""))
        return
    try:
        import zstandard as zs
    except ImportError:
        sys.exit("the zstandard package is missing: python -m pip install zstandard")
    dicts = dictionaries(romfs, zs)

    # ---- every map file with chests ----
    files = collections.OrderedDict()   # rel -> (bytes, [Chest])
    maps = collections.defaultdict(set)  # a chest's or Gold Skulltula's hash -> the names of the map files that have it
    about = {}                                 # the same -> what its actor says of it (check_name)
    exits = collections.defaultdict(set)       # an area -> its ways out: (place, where it leads)
    sub_areas = collections.defaultdict(set)   # an area -> its parts with a name of their own: (place, reach, name)
    skulls = collections.OrderedDict()  # hash -> [area, position, can be given a drop (in every file it is in), a dungeon's, a child's map has it]
    pieces = collections.OrderedDict()  # a Piece of Heart lying in the world: hash -> [area, position]
    bosses = {}                          # the same of a boss's Heart Container in pieces (placement 12): hash -> its dungeon
    suns = set()                         # the same of Lake Hylia's Fire Arrows in pieces (SUN_FROM)
    pots = collections.OrderedDict()     # a pot of the tables taking part (Pots): hash -> [area, position]
    pot_table = pot_actors() if a.pots else {}
    every_skull = collections.OrderedDict()   # every Gold Skulltula, the setting's or not: hash -> [area, position]
    paths = []
    for top, dirs, names in os.walk(os.path.join(romfs, "Banc")):
        dirs.sort()
        paths += [os.path.join(top, n) for n in sorted(names) if ".bcett.byml" in n.lower()]
    for path in sorted(paths, key=lambda q: os.path.relpath(q, romfs).replace("\\", "/")):
        rel = os.path.relpath(path, romfs).replace("\\", "/")
        try:
            data = unpack(open(path, "rb").read(), zs, dicts)
            found, _, _ = chests(data)
        except Exception as e:
            print("skipped %s: %s" % (rel, e))
            continue
        try:   # (what the file has to name its checks by: check_name)
            folder = rel.split("/")[1] if rel.count("/") > 1 else "(Banc)"
            for h, gyaml, pos, scale, words in marks(data):
                leads = words.get("Location")
                if gyaml in MARKS:
                    if isinstance(leads, str) and leads and leads != folder and len(pos) == 3:
                        if gyaml == "LocationArea":
                            sub_areas[folder].add((pos, max(scale[0], scale[2], 60.0) if len(scale) == 3 else 60.0, leads))
                        else:
                            exits[folder].add((pos, leads))
                elif h is not None:
                    was = about.setdefault(h, {})
                    was["big"] = was.get("big") or gyaml.startswith("Obj_TBox_A_02")
                    was.setdefault("turned", words.get("Rotate", (0.0, 0.0, 0.0)))
                    was["night"] = was.get("night") or bool(words.get("Enemy_Skulltula_Gold_Nocturnal"))
                    was["soil"] = was.get("soil") or bool(words.get("Enemy_Skulltula_Gold_IsMagicBeanSoil"))
                    if "DefaultDungeonRoomIndex" in words:
                        was["room"] = words["DefaultDungeonRoomIndex"]
        except (ValueError, struct.error, IndexError):
            pass
        lying = []
        if a.heart_pieces:
            try:
                lying = hearts(data)
            except (ValueError, struct.error, IndexError):
                pass
            for h, pos in lying:
                maps[h].add(rel.split("/")[-1])
                pieces.setdefault(h, [folder, pos])
            if placement >= CONTAINERS_FROM and folder in BOSS_HEARTS:
                try:
                    for h, pos in boss_hearts(data):
                        maps[h].add(rel.split("/")[-1])
                        pieces.setdefault(h, [folder, pos])
                        bosses[h] = folder
                except (ValueError, struct.error, IndexError):
                    pass
        if placement >= SUN_FROM and folder == SUN_FOLDER:   # (Lake Hylia's Fire Arrows, whatever the Heart Pieces setting)
            try:
                for h, pos in sun_arrows(data):
                    maps[h].add(rel.split("/")[-1])
                    pieces.setdefault(h, [folder, pos])
                    suns.add(h)
            except (ValueError, struct.error, IndexError):
                pass
        try:   # (every Gold Skulltula, whatever the setting: its token is counted for the Skulltula house, placement 12)
            here = skulltulas(data)
        except (ValueError, struct.error, IndexError):
            here = []
        for h, pos, _, _ in here:
            every_skull.setdefault(h, [rel.split("/")[1] if rel.count("/") > 1 else "(Banc)", pos])
        here = here if a.skulltulas else []
        if any(not can for _, _, can, _ in here):
            try:   # (a file that has to be written anew for its Skulltulas: can it be read whole?)
                byml_parse(data)
                here = [(h, pos, True, dungeon) for h, pos, _, dungeon in here]
            except (ValueError, struct.error, IndexError):
                pass
        for h, pos, can, dungeon in here:
            parts = rel.split("/")
            maps[h].add(parts[-1])
            entry = skulls.setdefault(h, [parts[1] if len(parts) > 2 else "(Banc)", pos, True, False, False])
            entry[2], entry[3] = entry[2] and can, entry[3] or dungeon
            entry[4] = entry[4] or "_Child_" in parts[-1] or entry[0] in SKULLTULA_CHILD_DUNGEONS
        potted = False
        if pot_table:   # (Pots: the tables' pots in this file)
            for h, gyaml, pos, _, _ in marks(data):
                if gyaml.startswith("Obj_Pot") and h in pot_table and len(pos) == 3:
                    maps[h].add(rel.split("/")[-1])
                    pots.setdefault(h, [rel.split("/")[1] if rel.count("/") > 1 else "(Banc)", pos])
                    potted = True
        if found or here or potted or any(struct.pack("<Q", h) in data for h in drops):
            files[rel] = (data, found)

    # ---- the chests: one per hash (the same chest is in several files: child and adult, static and dynamic) ----
    spots = collections.OrderedDict()   # hash -> [area, item, dungeon, why it stays, type, position]
    for rel, (data, found) in files.items():
        parts = rel.split("/")
        area = parts[1] if len(parts) > 2 else "(Banc)"
        for c in found:
            if c.hash is None or not c.gyaml.startswith("Obj_TBox"):
                continue
            maps[c.hash].add(parts[-1])
            why = stays_why(c, a.event_chests, placement)
            if c.event == SWORD_EVENT and not a.sword_shield:   # (Shuffle sword and shield: Off)
                why = why or "the Kokiri Sword stays in its chest (Shuffle sword and shield: Off)"
            dungeon = "DefaultDungeonRoomIndex" in c.params
            if c.hash not in spots:
                spots[c.hash] = [area, c.item, dungeon, why, c.gyaml, c.pos, c.event]
            else:
                s = spots[c.hash]
                if s[1] != c.item:
                    s[3] = "holds different items in different files"
                elif s[0] != area:
                    s[3] = s[3] or "is in two areas' files"
                s[3] = s[3] or why
                s[2] = s[2] or dungeon
    # ---- Quest rewards: the gifts that take part, as spots among the chests' ----
    gifts = collections.OrderedDict()   # its hash -> the Gift
    global PROGRESSION
    if a.dampe_hookshot:   # (Shuffle Dampe's Hookshot: a gating item, HOOK)
        PROGRESSION = PROGRESSION | {HOOK}
    if a.quests:
        PROGRESSION = PROGRESSION | QUEST_GATES | (TUNICS if placement >= 12 else frozenset()) | ({GOLD_SCALE} if placement >= GOLD_SCALE_FROM else frozenset())
        for g in GIFTS:
            if g.key in GIFTS_FROM and placement < GIFTS_FROM[g.key]:
                continue
            if g.when is None or g.when == "frogs" and a.frogs or g.when == "light" and a.light_arrows:
                if g.key == "frogs" and placement >= FROGS_SPLIT_FROM:   # (the Song of Storms' prize alone: frogs_game has the other)
                    g = g._replace(entry=FROG_STORMS_ENTRY, name=FROG_STORMS_NAME)
                gifts[gift_hash(g.key)] = g
                spots[gift_hash(g.key)] = [g.area, g.item, None, None, "gift", g.name, ""]
    if a.scrubs:   # (Deku Scrubs: with or without Quest rewards)
        for g in (scrubs_swapped() if placement >= SCRUB_SWAP_FROM else SCRUBS):
            gifts[gift_hash(g.key)] = g
            spots[gift_hash(g.key)] = [g.area, g.item, None, None, "scrub", g.name, ""]

    def gift_place(key, default=None):
        """a gift's (ages, place) for the Tracker and the door's step: GIFT_PLACES, the two scrubs' swapped from SCRUB_SWAP_FROM"""
        if placement >= SCRUB_SWAP_FROM and key in SCRUB_PLACES_SWAPPED:
            return SCRUB_PLACES_SWAPPED[key]
        return GIFT_PLACES[key] if default is None else GIFT_PLACES.get(key, default)
    if a.ocarina:   # (the Fairy Ocarina: with Songs' Anywhere, ocarina_need)
        PROGRESSION = PROGRESSION | {OCARINA}
        gifts[gift_hash(OCARINA_GIFT.key)] = OCARINA_GIFT
        spots[gift_hash(OCARINA_GIFT.key)] = [OCARINA_GIFT.area, OCARINA_GIFT.item, None, None, "gift", OCARINA_GIFT.name, ""]
        gifts[gift_hash(OCARINA_TIME_GIFT.key)] = OCARINA_TIME_GIFT   # (not a gating item: OCARINA_TIME)
        spots[gift_hash(OCARINA_TIME_GIFT.key)] = [OCARINA_TIME_GIFT.area, OCARINA_TIME, None, None, "gift", OCARINA_TIME_GIFT.name, ""]
    magic_chest = None
    if a.magic:   # (Magic and the fairies' gifts: the other three fountains, and magic twice in the pool)
        PROGRESSION = PROGRESSION | {MAGIC_DOUBLE}
        for g in MAGIC_GIFTS:
            if g.key == "fairy_courage" and placement >= COURAGE_FROM:   # (an adult and the Golden Gauntlets: COURAGE_NEED)
                g = g._replace(need=COURAGE_NEED)
            gifts[gift_hash(g.key)] = g
            spots[gift_hash(g.key)] = [g.area, g.item, None, None, "gift", g.name, ""]
        junk = next((h for h in sorted(spots) if spots[h][1] == MAGIC_JUNK and spots[h][3] is None and h not in gifts), None)
        if junk is None:
            sys.exit("Magic and the fairies' gifts: no chest of a blue rupee that takes part to hold the second magic. Nothing written.")
        spots[junk][1] = MAGIC_DOUBLE
        magic_chest = junk   # (named by what it held, a blue rupee: the owner's run 2026-11-23, "Chest (Doubled Magic)")
    if a.letter:   # (Zelda's Letter: with or without Quest rewards, letter_need)
        PROGRESSION = PROGRESSION | {LETTER}
        gifts[gift_hash(LETTER_GIFT.key)] = LETTER_GIFT
        spots[gift_hash(LETTER_GIFT.key)] = [LETTER_GIFT.area, LETTER_GIFT.item, None, None, "gift", LETTER_GIFT.name, ""]
    global MASTER_SHUFFLED
    MASTER_SHUFFLED = a.master_sword
    global TIME_BLOCKS
    TIME_BLOCKS = placement >= TIME_BLOCKS_FROM   # (the Song of Time by its blocks, door_need)
    if a.master_sword:   # (Shuffle the Master Sword: the pedestal a place, the sword a gating item, MASTER_GIFT)
        PROGRESSION = PROGRESSION | {MASTER}
        gifts[gift_hash(MASTER_GIFT.key)] = MASTER_GIFT
        spots[gift_hash(MASTER_GIFT.key)] = [MASTER_GIFT.area, MASTER_GIFT.item, None, None, "gift", MASTER_GIFT.name, ""]
    lessons = collections.OrderedDict()   # a lesson's hash -> its Gift
    if a.songs:   # (Songs: with or without the others)
        PROGRESSION = PROGRESSION | SONG_GATES
        for g in SONGS:
            gifts[gift_hash(g.key)] = lessons[gift_hash(g.key)] = g
            spots[gift_hash(g.key)] = [g.area, g.item, None, None, "song", g.name, ""]
    endings = collections.OrderedDict()   # a dungeon's ending's hash -> its Gift
    if a.dungeon_rewards:   # (Dungeon rewards: with or without the others; none is a gating item)
        for g in REWARDS:
            gifts[gift_hash(g.key)] = endings[gift_hash(g.key)] = g
            spots[gift_hash(g.key)] = [g.area, g.item, None, None, "reward", g.name, ""]
    shelves = collections.OrderedDict()   # a shop shelf's hash -> (its Shop, its place in the goods list, the game's own actor there)
    shelf_prices = {}                     # the same -> what it costs
    if a.shops:   # (Shops: with or without the others)
        PROGRESSION = PROGRESSION | SHOP_GATES   # (the wallets: shuffled, and asked for by the shelves' prices)
        for g in GIFTS:
            if g.key in SHOP_WALLET_GIFTS and gift_hash(g.key) not in gifts:
                gifts[gift_hash(g.key)] = g
                spots[gift_hash(g.key)] = [g.area, g.item, None, None, "gift", g.name, ""]
        roll = random.Random("shop prices:%d:%d" % (seed, a.shops))
        for shop in shops(placement):
            for k, (index, actor) in enumerate(shop_slots(shop, a.shop_shelves, shield_shelf)):
                price = shop_price(roll, a.shops, placement)
                g = Gift("shop_%s_%d" % (shop.key, index), "", (), shelf_item(actor), shop.areas[0],
                         "%s: shelf %d, %d rupee%s" % (shop.name if placement < 4 or shop.key != "bombchu" else "the Bombchu Shop (at night)", k + 1, price, "" if price == 1 else "s"),
                         shop_need(shop, placement, a.open_forest) | wallet_need(price), "shops", None)
                gifts[gift_hash(g.key)], shelves[gift_hash(g.key)], shelf_prices[gift_hash(g.key)] = g, (shop, index, actor), price
                spots[gift_hash(g.key)] = [g.area, g.item, None, None, "shop", g.name, ""]
    # (the flag each shelf waits for, "still for sale": a test, RANDO_TEST_SHELF_FLAGS=0, leaves them to start false)
    try:
        shelf_flag = dict(zip(shelves, shelf_flags(len(shelves), a.shop_shelves, shield_shelf, placement)))
    except ValueError as e:
        sys.exit("the shops: %s. Nothing written." % e)
    shelf_start = {} if os.environ.get("RANDO_TEST_SHELF_FLAGS") == "0" else {name: True for name in shelf_flag.values()}
    # (Bombchu Bowling open from the start, every seed since fixes 59: its prizes a child's alone, BOWLING_FREE)
    if placement >= OVERWORLD_FROM:
        gifts.update((h, g._replace(need=CHILD)) for h, g in list(gifts.items()) if g.key in BOWLING_FREE)
    # (the Skulltula house's rewards ask for their tokens from placement 12: house_need)
    gifts.update((h, g._replace(need=house_need(g.key, g.need, placement))) for h, g in list(gifts.items()) if g.key in HOUSE_TOKENS)
    # (the Great Fairies' offerings: rolled with Shops, and a fairy past the child's wallet asks for its wallet: FAIRY_PRICES)
    fairy_mode = fairy_price_mode(a.fairy_prices, a.shops)
    fairy_cost = fairy_prices(seed, fairy_mode) if fairy_mode and placement >= FAIRY_PRICES_FROM else {}
    by_gift = {FAIRY_PRICES[flow][2]: price for flow, price in fairy_cost.items()}
    gifts.update((h, g._replace(need=frozenset(g.need) | wallet_need(by_gift[g.key]))) for h, g in list(gifts.items())
                 if g.key in by_gift and isinstance(g.need, (set, frozenset)))
    if placement >= BOTTLE_FROM and any(g.item == BOTTLE for g in gifts.values()):   # (a bottle shuffled: a gating item, bug 84)
        PROGRESSION = PROGRESSION | {BOTTLE}
    # (a string seed: the same on every Python 3. The seeds made before --event-chests keep their shuffle without it)
    logic = logic_now   # (without the event chests or the songs no gating item moves: nothing to ask)
    rng = random.Random("stage2:%d:%d:%d%s%s%s" % (seed, which, min(keys_mode, 1), ":events" if a.event_chests else "", ":logic" if logic else "",
                                                   ":songs2" if a.songs == 2 else ":songs" if a.songs else ""))
    dungeon_table_for(placement, a.master_sword)   # (placement 25: the newer dungeons' rules, DUNGEON_RULES2_FILE; SWORD_FROM)
    dungeon_on = placement >= DUNGEON_RULES_FROM and bool(dungeon_table())   # (each dungeon check by its own rule)
    if placement >= DUNGEON_RULES_FROM and not dungeon_table():
        print("each dungeon check's own rule: %s is not beside the script, so the dungeons ask as before" % DUNGEON_RULES_FILE)
    if dungeon_on and any(g.key == "fairy_din" for g in gifts.values()):   # (Din's Fire shuffled: the Shadow Temple's torches)
        PROGRESSION = PROGRESSION | DUNGEON_GATES
    pool = frozenset(s[1] for s in spots.values())

    def own_rule(h, area, otherwise):
        """a dungeon check's own rule (dungeon_rule), or what the rules asked before"""
        made = dungeon_rule(h, area, PROGRESSION, pool, a.open_door or (a.door_song and _TIME in PROGRESSION),
                            placement >= DUNGEON_AGES_FROM, placement >= WELL_FROM, placement >= BOTTLE_ENTRY_FROM) if dungeon_on else None
        if made is not None:
            ruled.add(h)
        return otherwise() if made is None else made
    ruled = set()   # (the checks with a rule of their own: no sword from door_need, SWORD_FROM)
    # (and the gifts and the shelves: a character's gift, a lesson, a fairy's, a shop's sale is no fight. The bosses'
    #  rewards keep it; the owner's run 2026-11-23: the Great Fairy of the crater asked for the sword)
    reward_keys = {g.key for g in REWARDS}
    no_sword = lambda h: placement >= SWORD_FROM and h not in bosses and (
        h in ruled or h in shelves or h in gifts and gifts[h].key not in reward_keys)
    needs = {h: own_rule(h, s[0], lambda s=s: rule(s[0], s[6])) for h, s in spots.items()}
    deep = a.quests and placement >= TUNIC_WATER_FROM   # (the tunics by hot rooms and deep water, TUNIC_WATER_FROM)
    if deep:   # (Zora's Fountain's chest above its water: an adult alone, TUNIC_DRY)
        needs = {h: TUNIC_DRY.get(h, n) for h, n in needs.items()}
    door_rules = a.open_door or (a.door_song and _TIME in PROGRESSION)   # (DOOR_SONG with the songs shuffled)
    if placement >= 10:   # (a chest's own rule, CHEST_NEEDS)
        needs = {h: chest_need(h, n, door_rules) for h, n in needs.items()}
    slingshot_room = {h for h in SLINGSHOT_ROOM if h in needs} if placement >= 7 else set()
    slingshot_room |= {h for h in DEKU_THIRD_FLOOR if h in needs} if placement >= DEKU_THIRD_FROM else set()
    needs = {h: each(lambda w: w | CHILD, n) if h in slingshot_room else n for h, n in needs.items()}
    if a.quests:   # (the rules with the gifts' two gating items named; a gift asks for what its line of GIFTS says)
        needs = {h: quest_need(gifts[h].need, gifts[h].area, placement >= 12, deep) if h in gifts else each(quest_need, n, spots[h][0], placement >= 12, deep) for h, n in needs.items()}
    elif gifts:    # (the scrubs alone)
        needs = {h: gifts[h].need if h in gifts else n for h, n in needs.items()}
    if a.songs:    # (the songs named: a lesson's line names its own; the frogs ask for everything)
        malon_hard = a.songs == 2 and MALON_HARD_FROM <= placement < MALON_FREE_FROM   # (Malon's lesson asked for everything: MALON_HARD)
        needs = {h: frozenset(PROGRESSION) if malon_hard and h in lessons and gifts[h].key in MALON_HARD else
                 n if h in lessons else frozenset(PROGRESSION) if h in gifts and gifts[h].key in (SONGS_HARD_SPLIT if placement >= FROGS_SPLIT_FROM else SONGS_HARD) else
                 each(song_need, n, spots[h][0], gifts[h].key if h in gifts else None) for h, n in needs.items()}
    if a.magic:   # (magic where the Lens of Truth is asked for: magic_need)
        needs = {h: each(magic_need, n) for h, n in needs.items()}
    if placement >= 5:   # (Zora's Domain by the river or by the lake, zora_ways)
        needs = {h: zora_ways(n, spots[h][0]) for h, n in needs.items()}
    gear = shield_need if shield_shelf and not a.open_deku else (lambda need: need)   # (the shield with the sword: Mido)
    if shield_shelf:
        PROGRESSION = PROGRESSION | SHIELD_GATES
    plain_step = (lambda need: progressive_need(gear(need), PROGRESSION)) if a.progressive else gear
    step = lambda need: each(plain_step, need)
    needs = {h: step(n) for h, n in needs.items()}
    # (Open forest exit: the forest's way out asked for no more, forest_open; with the place, for FOREST_FLOOR)
    forest = (lambda need, area: each(forest_open, need, area)) if placement >= 5 and a.open_forest else (lambda need, area: need)
    story = ({h for h, g in gifts.items() if g.key in DEKU_STORY} if placement >= 6 else set()) | slingshot_room
    needs = {h: n if h in story else forest(n, spots[h][0]) for h, n in needs.items()}
    # (Open Door of Time: what it takes to be an adult is not asked of an adult's own places, door_need)
    grown = lambda h, area: area in DOOR_ADULT_AREAS or check_ages(maps[h]) == "A" if h in maps else area in DOOR_ADULT_AREAS
    if door_rules:
        needs = {h: each(door_need, n, shelves[h][0].ages == "A" if h in shelves else
                              gift_place(gifts[h].key, ("CA",))[0] == "A" if h in gifts else grown(h, spots[h][0]), a.open_forest, spots[h][0],
                         a.door_song, sword_asked=not no_sword(h))
                 for h, n in needs.items()}
    bolero = LETTER_BOLERO in PROGRESSION and a.songs != 0
    letter_gate = (lambda need, area: letter_need(need, area, bolero)) if a.letter else (lambda need, area: need)
    gate = (lambda need, area: ocarina_need(letter_gate(need, area))) if a.ocarina else letter_gate
    needs = {h: gate(n, spots[h][0]) for h, n in needs.items()}
    if a.ocarina:   # (a lesson: its notes are played back on an ocarina)
        needs = {h: ocarina_need(n, True) if h in lessons else n for h, n in needs.items()}
    # (each overworld check by its own rule, placement 23: its table ways, through the items' own steps alone)
    over, over_named, over_own = overworld_table(overworld_variant(a.open_deku, a.open_forest, a.gate_open, a.open_door,
                                                                   a.master_sword and placement >= SWORD_FROM)) if placement >= OVERWORLD_FROM else ({}, {}, {})
    if placement >= OVERWORLD_FROM and not over:
        print("each overworld check's own rule: %s is not beside the script, so the overworld asks as before" % OVERWORLD_RULES_FILE)
    song_lessons = {g.item: g.need for g in SONGS if g.item not in PROGRESSION}

    def over_rule(h, area, child_skulltula=False, name=None):
        """an overworld check's own rule (by its actor, or by name), its items' steps done; None where the table doesn't know it"""
        ways = over_named.get(name) if name else (over_own.get(h) if placement >= OWN_FROM and h in over_own else over.get(h)) if area not in DUNGEON_ENTRY else None
        made = overworld_rule(ways, PROGRESSION, song_lessons, child_skulltula) if ways else None
        if made is None:
            return None
        if not name and h in OVERWORLD_MORE and placement >= OVERWORLD_MORE_FROM:   # (ways found in play: OVERWORLD_MORE)
            made = either(list(made if isinstance(made, Either) else [made]) + OVERWORLD_MORE[h])
        made = step(made)
        if a.magic:
            made = each(magic_need, made)
        return ocarina_need(made) if a.ocarina else made
    def mask_need(made):
        """a Forest Stage check's rule with the way to the Happy Mask Shop's masks (MASK_EXPS): a young Link in the Market,
        as the Bazaar's first shelf asks, and Kakariko's gate opened (Open, or Zelda's Letter shown: the letter where it
        is shuffled, else the meeting that gives it, a young Link's at the castle as the Market's)"""
        market = over_rule(None, "Market", name=OVERWORLD_SHOPS["general"]) if over else None
        market = CHILD if market is None else market
        gate = NONE if a.gate_open or LETTER not in PROGRESSION else frozenset((LETTER,))
        shop = each(lambda w: w | gate, market)
        return shop if made is None else each(lambda w: each(lambda v: w | v, shop), made)
    for h, s in spots.items():
        if h in shelves:   # (a shop's shelf: its shop's first, and its price's wallet)
            made = over_rule(h, s[0], name=OVERWORLD_SHOPS.get(shelves[h][0].key)) if over else None
            made = None if made is None else each(lambda w: w | wallet_need(shelf_prices[h]), made)
        elif h in gifts:
            made = over_rule(h, s[0], name=OVERWORLD_GIFTS.get(gifts[h].key)) if over and gifts[h].key in OVERWORLD_GIFTS else None
            if made is None and placement >= OWN_FROM and h in over_own:   # (a gift with a rule of our own: the secret scrubs' hearts)
                made = over_rule(h, s[0])
            if gifts[h].key in MASK_GIFTS and placement >= MASKS_FROM:   # (the Forest Stage: a mask from the Happy Mask Shop, MASK_EXPS)
                made = mask_need(made)
        else:
            made = over_rule(h, s[0])
        if made is not None:
            needs[h] = made
            ruled.add(h)
    door = (lambda need, h, area: gate(each(door_need, forest(need, area), grown(h, area), a.open_forest, area, a.door_song, sword_asked=not no_sword(h)), area)) if door_rules else (
        lambda need, h, area: gate(forest(need, area), area))   # (with Open forest exit's step: the Gold Skulltulas' and the Pieces of Heart's)
    # (what a Gold Skulltula asks for, by the same settings; from placement 8 without Open forest exit's step: in a
    #  Skulltula's rule CHILD is often a weapon to kill it, or the sword past Mido into the Deku Tree, not the forest's
    #  way out. Found 2026-11-15: a seed put the Kokiri Sword on a Deku Tree Skulltula, with Open Deku Tree off)
    skull_door = (lambda need, h, area: gate(each(door_need, need, grown(h, area), a.open_forest, area, a.door_song, sword_asked=not no_sword(h)), area)) if door_rules else (
        lambda need, h, area: gate(need, area))
    skull_door = skull_door if placement >= 8 else door
    bottles = BOTTLE in PROGRESSION   # (placement BOTTLE_FROM with the bottles shuffled: soil_need)
    skull_rule = lambda h, area: own_rule(h, area, lambda: skulltula_rule(h, area) | (CHILD if placement >= DEKU_THIRD_FROM and h in DEKU_THIRD_FLOOR else NONE))
    skull_asks = lambda h, at=None: (lambda area: skull_door(step((lambda n: each(song_need, n, area) if a.songs else n)(
        each(quest_need, soil_need(skull_rule(h, area), about.get(h, {}).get("soil"), bottles), area, placement >= 12, deep) if a.quests else
        skull_rule(h, area))), h, area))(at or skulls[h][0])
    # (a boss's container: without Open forest exit's step, as a Skulltula's: its CHILD is the weapons to beat the boss.
    #  Seen 2026-11-18: Gohma's asked for nothing)
    lying = collections.ChainMap(pieces, pots)   # (the pieces lying in the world, and the pots taking part: their rules alike)
    heart_asks = lambda h: (skull_door if h in bosses else door)(step((lambda n: each(song_need, n, lying[h][0]) if a.songs else n)(
        (lambda n: each(quest_need, n, lying[h][0], placement >= 12, deep) if a.quests else n)(
            own_rule(h, lying[h][0], lambda: boss_need(bosses[h]) if h in bosses else (boss_need("WaterTemple") | {BOW}) if h in suns else
                     TUNIC_DRY[h] if deep and h in TUNIC_DRY else heart_rule(h, lying[h][0]))))), h, lying[h][0])
    piece_own = lambda h: CONTAINER if h in bosses else SUN_ITEM if h in suns else HEART   # (what a piece's, a container's or the sun's spot holds of its own)
    if a.dampe_hookshot:   # (Shuffle Dampe's Hookshot: a Skulltula's and a piece's rule too, wherever it is written: hook_asks)
        skull_plain, heart_plain = skull_asks, heart_asks
        skull_asks = lambda h, at=None: (lambda n, area: each(hook_need, n, HOOK_OR.get(h)) if hook_asks(area, h=h) else n)(
            skull_plain(h, at), at or skulls[h][0])
        heart_asks = lambda h: (lambda n: each(hook_need, n) if hook_asks(lying[h][0], h=h) else n)(heart_plain(h))
    # (Deku Sticks for the Kokiri Sword, placement 20, with the Deku Tree and the forest's way out open: stick_need)
    sticks = placement >= STICKS_FROM and a.open_deku and a.open_forest
    if sticks:
        skull_sword, heart_sword = skull_asks, heart_asks
        skull_asks = lambda h, at=None: each(stick_need, skull_sword(h, at), a.letter, bolero)
        heart_asks = lambda h: each(stick_need, heart_sword(h), a.letter, bolero)
    if dungeon_on:   # (no more ways than the tracker reads: fit_rule)
        skull_long, heart_long = skull_asks, heart_asks
        skull_asks = lambda h, at=None: fit_rule(skull_long(h, at))
        heart_asks = lambda h: fit_rule(heart_long(h))
    if over:   # (an overworld Gold Skulltula's or Piece of Heart's own rule: over_rule, then sticks and the tracker's fit)
        skull_old, heart_old = skull_asks, heart_asks

        def over_done(made):
            return fit_rule(each(stick_need, made, a.letter, bolero) if sticks else made)

        def skull_over(h, at=None):
            area = at or skulls[h][0]
            made = over_rule(h, area, child_skulltula=h in maps and check_ages(maps[h]) == "C")
            return skull_old(h, at) if made is None else over_done(made)

        def heart_over(h):
            made = over_rule(h, lying[h][0]) if h not in bosses else None
            return heart_old(h) if made is None else over_done(made)
        skull_asks, heart_asks = skull_over, heart_over
    if a.start:   # (Starting items held: start_need, on what every step above made)
        skull_held, heart_held = skull_asks, heart_asks
        skull_asks = lambda h, at=None: start_need(skull_held(h, at), start_held(a.start))
        heart_asks = lambda h: start_need(heart_held(h), start_held(a.start))
    # (Songs: Anywhere: what the lessons asked about by name may hold, by this seed's items and the game's flags; the
    #  Great Fairies of the spells the same, FAIRY_GIFTS)
    lesson_safe, lesson_only = frozenset(), {}
    fairies = [h for h, g in gifts.items() if g.key in FAIRY_GIFTS or g.key in {m.key for m in MAGIC_GIFTS}]
    if a.songs == 2 or fairies or a.dampe_hookshot:
        try:
            folder = os.path.join(romfs, FLAG_LIST)
            n = sorted(n for n in os.listdir(folder) if n.startswith("GameDataList.") and ".byml" in n.lower())[0]
            flag_list = unpack(open(os.path.join(folder, n), "rb").read(), zs, dicts)
        except (OSError, IndexError, ValueError) as e:
            sys.exit("Songs: Anywhere (or the Great Fairies): the game's list of flags: %s. Nothing written." % e)

        def flagged(item):
            try:
                flag_defaults(flag_list, {word + item: False for word in SONG_WORDS if word})
            except ValueError:
                return False
            return True

        lesson_safe = lesson_items(collections.Counter(s[1] for s in spots.values()), a.progressive, flagged)
        lesson_only = {gift_hash(key): (lesson_safe, frozenset(SONG_ITEMS)) for key in SONG_ASKED} if a.songs == 2 else {}
        lesson_only.update((h, (lesson_safe, frozenset(SONG_ITEMS) if a.songs == 2 else frozenset())) for h in fairies)
        if a.dampe_hookshot and DAMPE_HOOK_CHEST in spots:   # (the race's chest is asked about by name: race_words)
            lesson_only[DAMPE_HOOK_CHEST] = (lesson_safe, frozenset(SONG_ITEMS) if a.songs == 2 else frozenset())
    # (placement 12, SHUFFLED_FROM: the Gold Skulltulas of the setting and the Pieces of Heart lying in the world are
    #  spots of the placement, with their token and their piece in the pool, each holding what it can: holds)
    skull_drops, able, mine = {}, [], []
    pot_drops = {}   # (Pots: a pot's hash -> the item it drops now)
    heart_drops = {}   # a piece's hash -> the item it gives now
    if a.skulltulas:
        mine = [h for h, s in skulls.items() if a.skulltulas == 3 or s[3] == (a.skulltulas == 1)]   # (this setting's)
        able = [h for h in mine if skulls[h][2]]
    joined = collections.OrderedDict()   # a Skulltula's or a piece's hash -> its spot (placement 12)
    holds = {}
    if placement >= SHUFFLED_FROM:
        joined.update((h, [skulls[h][0], TOKEN, None, None, "skulltula", skulls[h][1], ""]) for h in able)
        joined.update((h, [pieces[h][0], piece_own(h), None, None, "piece", pieces[h][1], ""]) for h in pieces if a.heart_pieces or h in suns)
        joined.update((h, [pots[h][0], POT_OWN, None, None, "pot", pots[h][1], ""]) for h in pots)   # (Pots)
        kinds = {s[1] for s in spots.values()} | {s[1] for s in joined.values()}
        skull_may = frozenset(i for i in kinds if skulltula_holds(i, PROGRESSION))
        piece_may = frozenset(i for i in kinds if piece_holds(i))
        for h, s in joined.items():
            spots[h] = s
            needs[h] = skull_asks(h) if s[4] == "skulltula" else heart_asks(h)
            holds[h] = skull_may if s[4] in ("skulltula", "pot") else piece_may | {CONTAINER} if h in bosses else piece_may | {SUN_ITEM} if h in suns else piece_may
    if a.master_sword:   # (the pedestal: what the pouch takes by name; the sword on no shelf, no scrub's sale and no Skulltula)
        every = {s[1] for s in spots.values()}
        holds[gift_hash(MASTER_GIFT.key)] = frozenset(i for i in every if pedestal_holds(i))
        for h, s in spots.items():
            if s[4] in ("shop", "scrub"):
                holds[h] = frozenset(every - {MASTER})
            elif h in holds and s[4] == "skulltula":
                holds[h] = holds[h] - {MASTER}
    if placement >= RAINY_FROM:   # (a check there only for a while: junk only, RAINY_ONLY)
        junk = frozenset(i for i in {s[1] for s in spots.values()} if junk_holds(i))
        holds.update((h, junk) for h in JUNK_ONLY if h in spots)
    # (the tokens are placed by the logic when a rule counts them: the Skulltula house's rewards. The Skulltulas that
    #  keep their token, of another setting or whose file cannot take a drop, are counted where they are)
    counted = placement >= HOUSE_FROM and logic and any(token_count(word) for n in needs.values() for way in (n if isinstance(n, Either) else (n,)) for word in way)
    kept_tokens = [(skull_asks(h, every_skull[h][0]), TOKEN) for h in every_skull if h not in joined] if counted else []
    if a.dampe_hookshot:   # (Shuffle Dampe's Hookshot: the Hookshot or the Longshot where the audit found it needed, hook_asks)
        for h, s in spots.items():
            if hook_asks(s[0], s[6] if len(s) > 6 else "", gifts[h].key if h in gifts else None, h):
                needs[h] = each(hook_need, needs[h], HOOK_OR.get(h))
    if placement >= AFTER_WATER_FROM:   # (Lake Hylia's chest there once the Water Temple is done: AFTER_WATER)
        water = frozenset(boss_need("WaterTemple"))
        for h in AFTER_WATER:
            if h in needs:
                needs[h] = each(lambda way: frozenset(way) | water, needs[h])
    if sticks:   # (Deku Sticks for the Kokiri Sword, stick_need)
        needs = {h: each(stick_need, n, a.letter, bolero) for h, n in needs.items()}
    if dungeon_on:   # (no more ways than the tracker reads: fit_rule)
        needs = {h: fit_rule(n) for h, n in needs.items()}
    if a.start:   # (Starting items: held from the start, start_need; one of each but the songs out of the pool, START_JUNK)
        needs = {h: start_need(n, start_held(a.start)) for h, n in needs.items()}
        for c in a.start:
            item = START_ITEMS[c][0]
            if item in SONG_ITEMS or c in START_SUPPLIES:
                continue
            for h in sorted(spots):
                if spots[h][1] == item:
                    spots[h][1] = START_JUNK
                    break
    if a.maps == 2:   # (Maps and compasses: From the start: their chests hold rupees, MAPS_START_JUNK)
        for h in spots:
            if spots[h][1] in MAPS_START_JUNK and spots[h][4].startswith("Obj_TBox"):
                spots[h][1] = MAPS_START_JUNK[spots[h][1]]
    loose = MAPS_LOOSE if a.maps == 1 else frozenset()
    boss_tags = {}   # (Boss Keys: Anywhere: a chest that held one -> its own name for the shuffle, boss_key_tag)
    if a.boss_keys:
        for h, s in spots.items():
            if s[1] == BOSS_KEY and str(s[4]).startswith("Obj_TBox") and s[0] in DUNGEON_FOLDERS:
                s[1] = boss_tags[h] = boss_key_tag(s[0])
        loose = loose | frozenset(boss_tags.values())
    small_tags = key_tags(spots, which) if keys_mode == 2 else {}   # (Small keys: Anywhere)
    key_sets = {}
    if small_tags:
        for h, t in small_tags.items():
            spots[h][1] = t
            key_sets.setdefault(t.split("@")[1].split("#")[0], set()).add(t)
        key_sets = {d: frozenset(ts) for d, ts in key_sets.items()}
        free = keyless_actors()
        if not free:
            sys.exit("Small keys: Anywhere: %s is missing (tools/rando/dungeon_keyless.py writes it). Nothing written." % KEYLESS_FILE)
        if logic:
            asked = 0
            for h in needs:
                area = spots[h][0] if h in spots else None
                if area in key_sets and h not in free:
                    needs[h] = each(lambda way, keys=key_sets[area]: frozenset(way) | keys, needs[h])
                    asked += 1
            print("Small keys: Anywhere: %d keys of %d dungeons are items of the shuffle; %d checks ask for their dungeon's keys" % (
                len(small_tags), len(key_sets), asked))
        PROGRESSION = PROGRESSION | frozenset(small_tags.values())
        loose = loose | frozenset(small_tags.values())
    if loose:   # (Anywhere: chests only, MAPS_LOOSE; a Boss Key to a chest its boss's rule covers, boss_key_fits)
        every = {s[1] for s in spots.values()}
        holds = dict(holds or {})
        caps = {t: (frozenset(boss_need(t.split("@")[1])) if t.split("@")[1] in BOSS_HEARTS else None) for t in set(boss_tags.values())}
        for t in small_tags.values():   # (a dungeon's keys where its ending's rule reaches, with its own keys)
            d = t.split("@")[1].split("#")[0]
            caps[t] = frozenset(boss_need(d)) | key_sets[d] if d in BOSS_HEARTS else None
        for h, s in spots.items():
            if not str(s[4]).startswith("Obj_TBox"):
                holds[h] = frozenset(holds.get(h, every)) - loose
            elif caps and logic:
                unfit = frozenset(t for t, cap in caps.items() if not boss_key_fits(needs.get(h), cap))
                if h in AFTER_WATER:   # (there only once the Water Temple is done: none of its own keys, whatever the items say)
                    unfit = unfit | frozenset(t for t in caps if t.split("@")[1].split("#")[0] == "WaterTemple")
                if unfit:
                    holds[h] = frozenset(holds.get(h, every)) - unfit
    try:
        gives, stays, spheres = place(rng, collections.OrderedDict((h, tuple(s[:4])) for h, s in spots.items()), which, keys_mode,
                                      needs if logic else None,
                                      [group for group in ((frozenset(SONG_ITEMS), frozenset(lessons)) if a.songs == 1 else None,
                                                           (frozenset(REWARD_ITEMS), frozenset(endings)) if a.dungeon_rewards else None) if group]
                                      + pin_groups(spots, read_pins()) or None,
                                      only=lesson_only, apart=frozenset(lessons) if a.songs == 2 else (),
                                      holds=holds or None, counted=counted, fixed_more=kept_tokens, loose=loose)
    except ValueError as e:
        if "a lesson has nothing left" in str(e) and fairies and not a.event_chests:   # (seen 2026-11-20: magic on, Major items off)
            sys.exit("%s: the Great Fairies may hold only items found once (a spell, the Lens, the Hammer...), and with Major items "
                     "off most of those stay in their own chests. Nothing written. Turn Major items on." % e)
        sys.exit("%s. Nothing written. Try Chests: All, or --no-logic." % e)
    unknown = sorted({s[0] for h, s in spots.items() if s[0] not in RULES and h not in gifts and h not in joined})
    if a.magic:   # (no magic on a shop's shelf: its "You got" words are the shelf's own, the doubled magic's, not the meter's)
        for h in [h for h in shelves if gives.get(h) == MAGIC_DOUBLE]:
            ways = list(needs[h]) if isinstance(needs.get(h), Either) else [needs.get(h, frozenset())]   # (every way of the shelf's rule)
            mate = next((m for m in sorted(gives) if m not in shelves and m not in lesson_only and m not in joined and (m not in holds or MAGIC_DOUBLE in holds[m])
                         and gives[m] not in PROGRESSION and gives[m] not in loose and (h not in holds or gives[m] in holds[h]) and isinstance(needs.get(m), frozenset)
                         and all(needs[m] <= way for way in ways)), None)   # (a place no harder than any of the shelf's ways)
            if mate is None:
                sys.exit("Magic and the fairies' gifts: magic on a shelf, and no place to trade it with. Nothing written.")
            gives[h], gives[mate] = gives[mate], gives[h]

    # (Maps and compasses: Anywhere: the dungeon each now belongs to, DUNGEON_ITEMS_FILE)
    owners = dungeon_owners(random.Random("dungeon items:%d" % seed), spots, gives, loose & MAPS_LOOSE) if loose & MAPS_LOOSE else {}
    for h in [h for h in gives if "@" in gives[h]]:   # (Boss Keys and small keys: Anywhere: each chest's, and the tags taken off)
        owners[h] = gives[h].split("@")[1].split("#")[0]
        gives[h] = gives[h].split("@")[0]
    for h in list(boss_tags) + list(small_tags):
        spots[h][1] = spots[h][1].split("@")[0]
    if any(not str(spots[h][4]).startswith("Obj_TBox") for h in owners):
        sys.exit("a dungeon's map or compass is somewhere else than a chest: nothing written")
    # (the game's own count of each item is kept: every item given was some chest's)
    before = collections.Counter(spots[h][1] for h in gives)
    if before != collections.Counter(gives.values()):
        sys.exit("the shuffle lost or made an item: nothing written")
    # (the Skulltulas and the pieces out of the chests' lists again: what each gives now is a drop)
    for h, s in joined.items():
        item = gives.pop(h)
        del spots[h]
        if s[4] == "skulltula" and item != TOKEN:
            skull_drops[h] = item
        elif s[4] == "piece" and item != piece_own(h):
            heart_drops[h] = item
        elif s[4] == "pot":   # (every pot taking part drops its item, its own a Deku Nut bundle: POT_OWN)
            pot_drops[h] = item
    if joined and any(not skulltula_holds(i, PROGRESSION) for i in skull_drops.values()) | any(not (piece_holds(i) or h in bosses and i == CONTAINER or h in suns and i == SUN_ITEM) for h, i in heart_drops.items()):
        sys.exit("a Gold Skulltula or a Piece of Heart was given what it may not hold: nothing written")

    # ---- the Gold Skulltulas: their tokens and the chests' rupees and supplies change places ----
    if a.skulltulas:
        if placement < SHUFFLED_FROM:
            gives, skull_drops = mix_skulltulas(random.Random("skulltulas:%d:%d:%d" % (seed, a.skulltulas, len(able))), gives, able)
        if logic and placement < SHUFFLED_FROM:   # (some of the gating items to the Skulltulas, where the rules still let the game be finished)
            fixed = [(needs[h], spots[h][1]) for h in spots if h not in gives and spots[h][1] in PROGRESSION]
            gives, skull_drops, spheres, gated = gate_skulltulas(
                random.Random("skulltulas gated:%d:%d:%d" % (seed, a.skulltulas, len(able))), gives, skull_drops,
                able, needs, {h: skull_asks(h) for h in able}, fixed,
                never=((SSC,) if a.quests else ()) + (tuple(SHOP_GATES) if a.shops else ()) + (tuple(SONG_GATES) if a.songs else ()),
                keep=frozenset(lesson_only))
            print("Gold Skulltulas: %d gating item%s now dropped by one" % (gated, "" if gated == 1 else "s"))
        for h, item in skull_drops.items():
            drops.setdefault(h, item)   # (a test's drop for the same Skulltula stays)
        skull_tier_list = skull_tiers(skull_drops.values()) if a.progressive else []
        pickups = sorted(set(pickups) | set(skull_drops.values()) | set(skull_tier_list))
        print("Gold Skulltulas %s: %d take part (%d more cannot be given a drop: their map file is not read whole; the map files have %d), %d now drop a "
              "chest's item, %d chests hold a token" % (("", "dungeons", "overworld", "all")[a.skulltulas], len(able),
                                                        len(mine) - len(able), len(skulls), len(skull_drops),
                                          sum(1 for i in gives.values() if i == TOKEN)))
        if placement >= SHUFFLED_FROM:
            print("Gold Skulltulas: %d gating item%s now dropped by one (they take part as chests do)" % (
                sum(1 for i in skull_drops.values() if i in PROGRESSION), "" if sum(1 for i in skull_drops.values() if i in PROGRESSION) == 1 else "s"))

    # ---- Heart Pieces: the pieces lying in the world and the chests' items a pick-up can be change places ----
    if a.heart_pieces and pieces and placement < SHUFFLED_FROM:
        if logic:   # (some of the gating items to the pieces, where the rules still let the game be finished)
            fixed = [(needs[h], spots[h][1]) for h in spots if h not in gives and spots[h][1] in PROGRESSION] + [
                (skull_asks(h), item) for h, item in skull_drops.items() if item in PROGRESSION]
            gives, heart_drops, spheres, gated = gate_skulltulas(
                random.Random("hearts gated:%d:%d" % (seed, len(pieces))), gives, heart_drops, list(pieces), needs,
                {h: heart_asks(h) for h in pieces}, fixed, token=HEART,
                never=((SSC,) if a.quests else ()) + (tuple(SHOP_GATES) if a.shops else ()) + (tuple(SONG_GATES) if a.songs else ()),
                keep=frozenset(lesson_only))
        else:
            print("Heart Pieces: nothing moves without the logic (Major items, or Songs)")
    if a.heart_pieces and pieces:
        for word in os.environ.get("RANDO_TEST_HEARTS", "").split():   # (a test: "<a piece's hash>=<an item>")
            heart_drops[int(word.split("=")[0], 16)] = word.split("=")[1]
        if placement < SHUFFLED_FROM:
            print("Heart Pieces: %d lying in the world take part, %d now give a gating item, and the chest each left holds a Piece of Heart" % (
                len(pieces), len(heart_drops)))
        else:
            print("Heart Pieces: %d lying in the world and %d bosses' Heart Containers take part as chests do, %d now give another item (%d a gating item)" % (
                len(pieces) - len(bosses) - len(suns), len(bosses), len(heart_drops), sum(1 for i in heart_drops.values() if i in PROGRESSION)))
    if suns:
        print("Lake Hylia's Fire Arrows: a check, giving %s" % next((heart_drops.get(h, SUN_ITEM) for h in suns)))

    if pot_drops:   # (Pots: their drops, pick-ups as a Skulltula's are, with their families' tiers)
        if any(not skulltula_holds(i, PROGRESSION) for i in pot_drops.values()):
            sys.exit("a pot was given what it may not drop: nothing written")
        for h, item in pot_drops.items():
            drops.setdefault(h, item)
        if a.progressive:
            skull_tier_list = sorted(set(skull_tier_list) | set(skull_tiers(pot_drops.values())))
        pickups = sorted(set(pickups) | set(pot_drops.values()) | set(skull_tier_list))
        print("Pots: %d of the tables' pots take part, %d drop a gating item" % (len(pot_drops), sum(1 for i in pot_drops.values() if i in PROGRESSION)))

    if test_chests:   # (a test: these chests give what the file says)
        strangers = sorted(h for h in test_chests if h not in gives)
        if strangers:
            sys.exit("rando\\test_chests.txt: no chest that takes part has the hash %s. Nothing written." % ", ".join("%#x" % h for h in strangers))
        gives.update(test_chests)
        print("TEST: %d chest%s given an item (rando\\test_chests.txt): %s" % (
            len(test_chests), "" if len(test_chests) == 1 else "s", ", ".join("%s in %s" % (i, spots[h][0]) for h, i in sorted(test_chests.items()))))

    # ---- the map files ----
    changed, sizes, fixes_done, drops_done, sized_files = collections.OrderedDict(), {}, 0, 0, 0
    for rel, (data, found) in files.items():
        try:
            new = rewrite(data, gives)
            if a.chest_size:   # (Chest size matches contents: CHEST_SIZES)
                sized = chest_kinds(new if new is not None else data, gives)
                if sized is not None:
                    new, sized_files = sized, sized_files + 1
            fixed = fix(new if new is not None else data)
            dropped = add_drop(fixed if fixed is not None else new if new is not None else data, drops,
                               anew=bool(os.environ.get("RANDO_DROPS_ANEW")))   # (a test: every file with a drop written anew)
        except Exception as e:
            sys.exit("%s: %s. Nothing was written to the mod." % (rel, e))
        if fixed is not None:
            new, fixes_done = fixed, fixes_done + 1
        if dropped is not None:
            new, drops_done = dropped, drops_done + 1
        if new is not None:
            changed[rel] = new
            sizes[rel[:-3] if rel.lower().endswith(".zs") else rel] = len(new)
    if a.chest_size:
        print("Chest size matches contents: %d map files' chests resized" % sized_files)
    moved = sum(1 for h, item in gives.items() if item != spots[h][1] and h not in gifts)
    print("%d chests take part, %d now hold another chest's item; %d map files change" % (len(gives) - len(gifts), moved, len(changed)))
    if a.quests:
        mine = [h for h, g in gifts.items() if g.when not in ("scrubs", "shops", "songs")]
        print("Quest rewards: %d gifts take part%s%s, %d now give another item" % (
            len(mine), "" if a.frogs else " (not the frogs: their setting is off)", "" if a.light_arrows else " (not the Light Arrows: their setting is off)",
            sum(1 for h in mine if gives[h] != gifts[h].item)))
    if a.scrubs:
        mine = [h for h, g in gifts.items() if g.when == "scrubs"]
        print("Deku Scrubs: %d one-time sales take part, %d now sell another item" % (len(mine), sum(1 for h in mine if gives[h] != gifts[h].item)))
    for why, n in stays.most_common():
        print("  left alone: %d (%s)" % (n, why))
    if len(drops) > len(skull_drops):
        print("TEST: %d actor%s given an item to drop (rando\\test_drops.txt)" % (
            len(drops) - len(skull_drops), "" if len(drops) - len(skull_drops) == 1 else "s"))
    # ---- the open ways: the game's list of flags, with theirs starting put out ----
    flag_files = {}
    if True:   # (every seed: Hyrule Field's clock, FIELD_CLOCK, and the d-pad's HUD, DPAD_HUD, with the open ways' flags and the rupees)
        folder = os.path.join(romfs, FLAG_LIST)
        lists = sorted(n for n in (os.listdir(folder) if os.path.isdir(folder) else []) if n.startswith("GameDataList.") and ".byml" in n.lower())
        if not lists:
            sys.exit("no list of flags in %s: the ways cannot be opened, nor the rupees given. Nothing written." % folder)
        for n in lists:
            try:
                was = unpack(open(os.path.join(folder, n), "rb").read(), zs, dicts)
                new = flag_defaults(was, dict(flags, **FIELD_CLOCK, **DPAD_HUD, **MINIMAP, **SHUFFLED_FIRSTS, **(OPEN_DOOR if a.open_door else {}), **(LINK_DOOR if a.skip_intro else {}), **(AREA_INTROS if a.skip_cutscenes else {}), **(FIRST_PICKUPS if a.skip_cutscenes else {}),
                                                     **({START_PICKUPS[c]: True for c in a.start if c in START_PICKUPS} if a.skip_cutscenes else {}),
                                                     **(MAPS_START if a.maps == 2 else {})))
                if shelf_flag:   # (the same file: the shelves' flags; a flag the game has not is an error)
                    assert not set(shelf_flag.values()) & set(FIRST_PICKUPS), "a shelf's flag is a first pick-up's"
                    flag_defaults(new if new is not None else was, {name: False for name in shelf_flag.values()})
                    more = flag_defaults(new if new is not None else was, shelf_start) if shelf_start else None
                    new = more if more is not None else new
                if a.start_rupees:   # (the same file: the rupees after the flags)
                    more = flag_defaults(new if new is not None else was, {RUPEES: START_RUPEES}, kind="Int")
                    new = more if more is not None else new
                new = always_exp(new if new is not None else was)   # (the same file: ALWAYS_EXP, for the Bombchu Shop and Bowling)
                new = masks_open(new)   # (the same file: every mask from the Happy Mask Shop, MASK_EXPS)
                new = enum_default(new)   # (the same file: the mask salesman's trade done, MASK_TRADE)
            except Exception as e:
                sys.exit("%s: %s. Nothing written." % (n, e))
            flag_files[FLAG_LIST + "/" + n] = new
            sizes[FLAG_LIST + "/" + (n[:-3] if n.lower().endswith(".zs") else n)] = len(new)
        if a.start_rupees:
            print("a new game starts with %d rupees" % START_RUPEES)
        print("Hyrule Field's day and night run from a new game's start (the Sun's Song works before the owl is met)")
        print("the d-pad's HUD (Navi and the boots) and the minimap are there from a new game's start")
        if a.open_door:
            print("the Door of Time is open in a new game (the Master Sword's way through time is the game's side's)")
    if flags:
        print("open ways in a new game: %s (%d flag%s start put out)" % (
            " and ".join(n for n, on in (("the Deku Tree's", a.open_deku), ("the forest's way out", a.open_forest)) if on), len(flags), "" if len(flags) == 1 else "s"))
    print("map fixes for a shuffled game: %d file%s (the warp songs work in the Forest Temple's Stalfos room)%s" % (
        fixes_done, "" if fixes_done == 1 else "s", "" if fixes_done else ": NOT FOUND, that room can shut Link in without the Bow"))
    if logic:
        print("logic: on. The %d gating items can be got in this order by the rules (%d rounds):" % (sum(map(len, spheres)), len(spheres)))
        for k, sphere in enumerate(spheres):
            print("  %d. %s" % (k + 1, ", ".join(sphere)))
        if unknown:
            print("  areas the rules do not know (their chests only get items the game can be finished without): " + ", ".join(unknown))
        if keys_mode:
            print("  NOTE: the logic does not look at a dungeon's keys: with Dungeon keys on Own dungeon a key can still be behind its door")
    elif a.event_chests:
        print("logic: OFF (--no-logic): the gating items are anywhere, and most seeds cannot be finished")

    # ---- TEST: items' packs made pick-ups' ----
    pack_files, pack_sizes, pack_parts, pack_new = {}, {}, set(), set()
    pouch_changed = {}   # (the pouch files the pick-ups changed: a shelf actor's pack takes them too)
    if pickups:
        def pack(name):
            return unpack(open(os.path.join(romfs, "Pack", "Actor", name + ".pack.zs"), "rb").read(), zs, dicts)
        try:
            base = pack(PICKUP_BASE)
            base_parts = sarc_read(base)
            pouch = pouch_changed
            for item in list(pickups):   # (an item made from another: that one's pack has a copy of the same actor)
                pickups += [n for n in pickup_family(item, pack(item))
                            if n not in pickups and os.path.isfile(os.path.join(romfs, "Pack", "Actor", n + ".pack.zs"))]
            for item in pickups:
                old = pack(item)
                # (each time: what can be got more than once. A gating item is got once, and is as it was seen in play)
                new = own_model_pack(item, pickup_pack(item, old, base, each_time=item not in PROGRESSION))   # (a shield's model file its own: bug 78)
                old_parts = sarc_read(old)
                pack_parts.update(name for name, data in sarc_read(new).items()   # (the files changed in it)
                                  if data != old_parts.get(name, base_parts.get(name)))
                pack_new.update(name for name in sarc_read(new) if name not in old_parts and name not in base_parts)
                pack_files["Pack/Actor/%s.pack.zs" % item] = new
                pack_sizes["Pack/Actor/%s.pack" % item] = len(new)
                pouch.update((name, data) for name, data in sarc_read(new).items()
                             if "/PouchContentParam/" in name and data != old_parts.get(name, base_parts.get(name)))
            # What an item is in the pouch is a file other packs carry a copy of, under the same name: the item in
            # the menu's (Pouch_*), the weapon in the hand's (Weapon_*), boots and gauntlets worn (Armor_*). The
            # Boomerang, made a pick-up just as the Megaton Hammer was, was not collected by touching it and the
            # Hammer was: a child's game loads the Boomerang's weapon first, with its copy. So the copies are
            # changed with it, in every pack that has one (seen in play: the Boomerang is collected by touch).
            for n in sorted(os.listdir(os.path.join(romfs, "Pack", "Actor"))) if pouch else []:
                if n.endswith(".pack.zs") and "Pack/Actor/" + n not in pack_files:
                    try:
                        parts = sarc_read(pack(n[:-len(".pack.zs")]))
                    except (ValueError, struct.error):
                        continue   # (not an archive of parameter files)
                    same = [name for name in pouch if name in parts and parts[name] != pouch[name]]
                    if same:
                        parts.update((name, pouch[name]) for name in same)
                        new = sarc_write(parts)
                        pack_files["Pack/Actor/" + n] = new
                        pack_sizes["Pack/Actor/" + n[:-len(".zs")]] = len(new)
        except (OSError, ValueError, struct.error) as e:
            sys.exit("an item's pack could not be made a pick-up's: %s. Nothing written." % e)
        print("%d item%s made a pick-up (what a Skulltula drops, and rando\\test_pickups.txt): %s" % (
            len(pickups), "" if len(pickups) == 1 else "s", ", ".join(pickups)))

    # ---- TEST: a character's gift made another item ----
    # ---- the gifts: each scene's flow made to give what the shuffle put there (and the tests' of test_gifts.txt) ----
    gift_files, gift_sizes = {}, {}
    gift_new = set()   # (files of our own, not the game's: their size table entries are made, EPONA_OWN_FLOW)
    swaps = collections.OrderedDict()   # a flow -> {the item it names: the item it gives now}
    for h, g in gifts.items():
        if gives[h] != g.item and g.flow and h not in lessons:   # (a shop's shelf has no scene: its actor is the sale; the songs: below)
            entries = g.entry if isinstance(g.entry, tuple) else (g.entry,) if g.entry else (None,)   # (a gift of several entries: the frogs' game)
            swaps.setdefault(g.flow, {}).update(((e, old) if e else old, gives[h]) for e in entries for old in g.olds)
    for flow, old, new in test_gifts:
        swaps.setdefault(flow, {})[old] = new
        print("TEST: %s gives %s in place of %s (rando\\test_gifts.txt)" % (flow, new, old))
    if a.scrubs_cheap:   # (Deku Scrubs, On, 10 rupees each: the sales' prices, before their items are changed, SCRUB_CHEAP)
        sales = {(g.entry, old) for g in SCRUBS for old in g.olds}
        twin = "%s/%s%s.bfevfl.zs" % (GIFT_FLOWS, SCRUB_FLOW, FLOW_TWIN)
        for rel in ["%s/%s.bfevfl.zs" % (GIFT_FLOWS, SCRUB_FLOW)] + ([twin] if os.path.isfile(os.path.join(romfs, *twin.split("/"))) else []):
            try:
                now, found = scrub_prices(unpack(open(os.path.join(romfs, *rel.split("/")), "rb").read(), zs, dicts), sales)
            except (OSError, ValueError, struct.error) as e:
                sys.exit("the Business Scrubs' flow, %s: %s. Nothing written." % (rel, e))
            if sales - found:
                sys.exit("%s names no %s. Nothing written." % (rel, ", ".join(sorted("%s %s" % s for s in sales - found))))
            gift_files[rel], gift_sizes[rel[:-3]] = now, len(now)
        print("Deku Scrubs: the four one-time sales cost %d rupees each" % SCRUB_CHEAP)
    for flow, change in swaps.items():
        twin = "%s/%s%s.bfevfl.zs" % (GIFT_FLOWS, flow, FLOW_TWIN)
        for rel in ["%s/%s.bfevfl.zs" % (GIFT_FLOWS, flow)] + ([twin] if os.path.isfile(os.path.join(romfs, *twin.split("/"))) else []):
            try:
                now, found = gift_items(gift_files[rel] if rel in gift_files else unpack(open(os.path.join(romfs, *rel.split("/")), "rb").read(), zs, dicts), change,
                                        kinds=OCARINA_KINDS.get(flow, (4,)))
            except (OSError, ValueError, struct.error) as e:
                sys.exit("a gift's flow, %s: %s. Nothing written." % (rel, e))
            if set(change) - found:
                sys.exit("%s gives no %s (rando\\test_gifts.txt, or the game's flow is not the one the gifts were listed from). Nothing written." % (
                    rel, ", ".join(sorted(str(k) for k in set(change) - found))))
            gift_files[rel], gift_sizes[rel[:-3]] = now, len(now)
    # (the Great Fairies of the spells: who asks whether a fountain gave its gift asks for what it gives now, FAIRY_GIFTS)
    fairy_now = {gifts[h].item: gives[h] for h in fairies if h in gives}
    if any(old != new for old, new in fairy_now.items()):
        stray = sorted(gifts[h].name for h in fairies if h in gives and gives[h] != gifts[h].item and
                       gives[h] not in lesson_safe and gives[h] not in SONG_ITEMS)
        if stray:
            sys.exit("a Great Fairy gives what has no flag of its own: %s. Nothing written." % ", ".join(stray))
        words = fairy_words(fairy_now)
        renamed = set()
        for flow in FAIRY_FLOWS:
            twin = "%s/%s%s.bfevfl.zs" % (GIFT_FLOWS, flow, FLOW_TWIN)
            for rel in ["%s/%s.bfevfl.zs" % (GIFT_FLOWS, flow)] + ([twin] if os.path.isfile(os.path.join(romfs, *twin.split("/"))) else []):
                try:
                    was = gift_files[rel] if rel in gift_files else unpack(open(os.path.join(romfs, *rel.split("/")), "rb").read(), zs, dicts)
                    now, found = gift_items(was, words, kinds=(0, 1))
                except (OSError, ValueError, struct.error) as e:
                    sys.exit("a Great Fairy's flow, %s: %s. Nothing written." % (rel, e))
                renamed |= found
                if now is not None:
                    gift_files[rel], gift_sizes[rel[:-3]] = now, len(now)
        missed = sorted(w for w in words if w.startswith("IsGet.") and w not in renamed)
        if missed:
            sys.exit("no Great Fairy's flow asks %s (the game's flows are not the ones the fountains were read from). Nothing written." % ", ".join(missed))
        print("the Great Fairies: %s" % ", ".join("%s gives %s" % (gifts[h].name, gives[h]) for h in fairies if h in gives))
    # (the Potion Shop keeper's errand: the bug passed over, his gift given at the first talk: potion_errand_skip)
    try:
        was = gift_files[POTION_FLOW] if POTION_FLOW in gift_files else unpack(open(os.path.join(romfs, *POTION_FLOW.split("/")), "rb").read(), zs, dicts)
        gift_files[POTION_FLOW] = potion_errand_skip(was)
        gift_sizes[POTION_FLOW[:-3]] = len(gift_files[POTION_FLOW])
    except (OSError, ValueError, struct.error) as e:
        sys.exit("%s: %s. Nothing written." % (POTION_FLOW, e))
    print("the Potion Shop keeper's errand: the bug passed over, the shop open after his gift")
    # (bug 68: back to a child, no Kokiri Sword put in an empty slot: era_sword_fix)
    try:
        was = gift_files[ERA_FLOW] if ERA_FLOW in gift_files else unpack(open(os.path.join(romfs, *ERA_FLOW.split("/")), "rb").read(), zs, dicts)
        gift_files[ERA_FLOW] = era_sword_fix(was, a.master_sword)
        gift_sizes[ERA_FLOW[:-3]] = len(gift_files[ERA_FLOW])
    except (OSError, ValueError, struct.error) as e:
        sys.exit("%s: %s. Nothing written." % (ERA_FLOW, e))
    print("back to a child: an empty sword slot stays empty (no Kokiri Sword Link never got)")
    # (bug 64: an adult's first visit to Goron City goes on to the rolling Goron's scene: goron_arrival_fix)
    try:
        was = gift_files[ARRIVE_FLOW] if ARRIVE_FLOW in gift_files else unpack(open(os.path.join(romfs, *ARRIVE_FLOW.split("/")), "rb").read(), zs, dicts)
        gift_files[ARRIVE_FLOW] = goron_arrival_fix(was)
        gift_sizes[ARRIVE_FLOW[:-3]] = len(gift_files[ARRIVE_FLOW])
    except (OSError, ValueError, struct.error) as e:
        sys.exit("%s: %s. Nothing written." % (ARRIVE_FLOW, e))
    print("Goron City's first visit: an adult goes on to the rolling Goron's scene")
    try:   # (the cucco lady's count of cuccos left starts at one: CUCCO_FLOW)
        was = gift_files[CUCCO_FLOW] if CUCCO_FLOW in gift_files else unpack(open(os.path.join(romfs, *CUCCO_FLOW.split("/")), "rb").read(), zs, dicts)
        gift_files[CUCCO_FLOW] = cucco_flow_one(was)
        gift_sizes[CUCCO_FLOW[:-3]] = len(gift_files[CUCCO_FLOW])
    except (OSError, ValueError, struct.error) as e:
        sys.exit("%s: %s. Nothing written." % (CUCCO_FLOW, e))
    try:   # (every Great Fairy answers Zelda's Lullaby from the start: FOUNTAIN_FLOW)
        was = gift_files[FOUNTAIN_FLOW] if FOUNTAIN_FLOW in gift_files else unpack(open(os.path.join(romfs, *FOUNTAIN_FLOW.split("/")), "rb").read(), zs, dicts)
        gift_files[FOUNTAIN_FLOW] = fountains_open(was)
        gift_sizes[FOUNTAIN_FLOW[:-3]] = len(gift_files[FOUNTAIN_FLOW])
    except (OSError, ValueError, struct.error) as e:
        sys.exit("%s: %s. Nothing written." % (FOUNTAIN_FLOW, e))
    print("the Great Fairies' fountains: every one answers Zelda's Lullaby from the start")
    if a.castle_guards:   # (Castle guards let Link pass: castle_guards_pass)
        try:
            was = gift_files[GUARDS_FLOW] if GUARDS_FLOW in gift_files else unpack(open(os.path.join(romfs, *GUARDS_FLOW.split("/")), "rb").read(), zs, dicts)
            gift_files[GUARDS_FLOW] = castle_guards_pass(was)
            gift_sizes[GUARDS_FLOW[:-3]] = len(gift_files[GUARDS_FLOW])
        except (OSError, ValueError, struct.error, ImportError) as e:
            sys.exit("Castle guards let Link pass: %s. Nothing written." % e)
        print("the castle guards: one who spots young Link goes back to his post, and Link carries on")
    if a.gerudo_guards:   # (Gerudo guards don't jail Link: gerudo_guards_pass, after the gifts' changes to the same flow)
        try:
            was = gift_files[GERUDO_GUARDS_FLOW] if GERUDO_GUARDS_FLOW in gift_files else unpack(open(os.path.join(romfs, *GERUDO_GUARDS_FLOW.split("/")), "rb").read(), zs, dicts)
            gift_files[GERUDO_GUARDS_FLOW] = gerudo_guards_pass(was)
            gift_sizes[GERUDO_GUARDS_FLOW[:-3]] = len(gift_files[GERUDO_GUARDS_FLOW])
        except (OSError, ValueError, struct.error, ImportError) as e:
            sys.exit("Gerudo guards don't jail Link: %s. Nothing written." % e)
        print("the Gerudo guards: one who catches adult Link goes back to her post, and Link stays where he is")
    if a.epona_song:   # (Epona by Epona's Song: epona_song_flows, epona_event_rows)
        try:
            was = gift_files[EPONA_SONG_FLOW] if EPONA_SONG_FLOW in gift_files else unpack(open(os.path.join(romfs, *EPONA_SONG_FLOW.split("/")), "rb").read(), zs, dicts)
            gift_files[EPONA_SONG_FLOW], gift_files[EPONA_OWN_FLOW] = epona_song_flows(was)
            gift_new.add(EPONA_OWN_FLOW[:-3])
            for rel, analyzed in zip(EVENT_TABLES, (False, True)):
                was = gift_files[rel] if rel in gift_files else unpack(open(os.path.join(romfs, *rel.split("/")), "rb").read(), zs, dicts)
                gift_files[rel] = epona_event_rows(was, analyzed)
            for rel in (EPONA_SONG_FLOW, EPONA_OWN_FLOW) + EVENT_TABLES:
                gift_sizes[rel[:-3]] = len(gift_files[rel])
        except (OSError, ValueError, struct.error, ImportError) as e:
            sys.exit("Epona by Epona's Song: %s. Nothing written." % e)
        print("Epona's Song: the first time an adult plays it where Link can ride, Epona is his")
    if fairy_cost:   # (the offerings: FAIRY_PRICES)
        try:
            for flow, price in fairy_cost.items():
                rel = "Event/EventFlow/%s.bfevfl.zs" % flow
                was = gift_files[rel] if rel in gift_files else unpack(open(os.path.join(romfs, *rel.split("/")), "rb").read(), zs, dicts)
                gift_files[rel] = fairy_price_flow(was, price)
                gift_sizes[rel[:-3]] = len(gift_files[rel])
            numbers = {FAIRY_PRICES[flow][0]: price for flow, price in fairy_cost.items()}
            folder, word_lines = os.path.join(romfs, "Mals"), 0
            for n in sorted(n for n in (os.listdir(folder) if os.path.isdir(folder) else []) if n.endswith(".sarc.zs")):
                rel = "Mals/" + n
                parts = sarc_read(gift_files[rel] if rel in gift_files else unpack(open(os.path.join(folder, n), "rb").read(), zs, dicts))
                if FAIRY_PRICE_TEXT not in parts:
                    continue
                parts[FAIRY_PRICE_TEXT], done = fairy_price_words(parts[FAIRY_PRICE_TEXT], numbers)
                if done:
                    gift_files[rel] = sarc_write(parts)
                    gift_sizes[rel[:-3]] = len(gift_files[rel])
                    word_lines += done
        except (OSError, KeyError, ValueError, struct.error, IndexError) as e:
            sys.exit("the Great Fairies' offerings: %s. Nothing written." % e)
        print("the Great Fairies' offerings: %s (%d lines of words)" % (", ".join("%s %d" % (flow.split("_")[-1], p) for flow, p in fairy_cost.items()), word_lines))
    # ---- the songs: each lesson gives the song the shuffle put there, and who asks about a lesson asks for that song ----
    song_parts = set()
    if lessons:
        now_gives = {g.item: gives[h] for h, g in lessons.items()}
        # (who asks about a lesson asks for what it gives now, when that has the flags asked about: a song, or one of
        #  the items a lesson asked about by name may hold. A lesson that gives anything else is one nothing asks about)
        asked = {old: new for old, new in now_gives.items() if new in SONG_ITEMS or new in lesson_safe}
        stray = sorted(g.name for h, g in lessons.items() if h in lesson_only and g.item not in asked)
        if stray:
            sys.exit("a lesson that is asked about by name gives what has no flag of its own: %s. Nothing written." % ", ".join(stray))
        words = song_words(asked)
        changes = any(old != new for old, new in now_gives.items())
        taught = set()
        own = {g.flow: g.item for g in lessons.values()}
        for flow in SONG_FLOWS if changes else ():
            rel = "%s/%s.bfevfl.zs" % (GIFT_FLOWS, flow)
            try:
                was = gift_files[rel] if rel in gift_files else unpack(open(os.path.join(romfs, *rel.split("/")), "rb").read(), zs, dicts)
                now = None
                if a.songs == 1:   # (Song spots: one pass, as its seeds were made)
                    now, found = gift_items(was, words, kinds=(0, 1, 4))
                    taught |= found
                elif flow in own and now_gives[own[flow]] != own[flow]:   # (the lesson's own gift: the call of the scene of an item got)
                    now, found = gift_items(was, {own[flow]: now_gives[own[flow]]}, kinds=(4,))
                    taught |= found
                if words and a.songs != 1:   # (what the flow sets and asks about)
                    then, found = gift_items(now if now is not None else was, words, kinds=(0, 1))
                    now = then if then is not None else now
            except (OSError, ValueError, struct.error) as e:
                sys.exit("a song's flow, %s: %s. Nothing written." % (flow, e))
            if now is not None:
                gift_files[rel], gift_sizes[rel[:-3]] = now, len(now)
        missed = sorted(old for old, new in now_gives.items() if old != new and old not in taught)
        if missed:
            sys.exit("no lesson gives %s (the game's flows are not the ones the songs were listed from). Nothing written." % ", ".join(missed))
        if changes:   # (the ocarina's own flow: what it adds when a lesson's notes have been played back)
            rel = "%s/%s.bfevfl.zs" % (GIFT_FLOWS, SONG_PLAY_FLOW)
            adds = {(entry, old): new if new in SONG_ITEMS else SONG_PLAY_OTHER
                    for old, new in now_gives.items() if old != new for entry in SONG_PLAY_ENTRIES}
            try:
                now, found = gift_items(unpack(open(os.path.join(romfs, *rel.split("/")), "rb").read(), zs, dicts), adds, kinds=(0,))
            except (OSError, ValueError, struct.error) as e:
                sys.exit("the ocarina's flow, %s: %s. Nothing written." % (SONG_PLAY_FLOW, e))
            missed = sorted(old for old, new in now_gives.items() if old != new and not any((entry, old) in found for entry in SONG_PLAY_ENTRIES))
            if missed:
                sys.exit("the ocarina's flow adds no %s when a lesson is done (not the flow the songs were listed from). Nothing written." % ", ".join(missed))
            gift_files[rel], gift_sizes[rel[:-3]] = now, len(now)
        for rel in SONG_STONES if words else ():
            try:
                now = song_stone(open(os.path.join(romfs, *rel.split("/")), "rb").read(), asked)
            except (OSError, ValueError, struct.error, IndexError) as e:
                sys.exit("a royal tomb's stone, %s: %s. Nothing written." % (rel, e))
            if now is not None:
                gift_files[rel] = now
                song_parts.add(rel)
        print("Songs%s: %d lessons take part, %d now %s%s" % (
            " (Anywhere)" if a.songs == 2 else "", len(lessons), sum(1 for old, new in now_gives.items() if old != new),
            "give something else, %d of them a song; %d songs are out in the world" % (
                sum(1 for old, new in now_gives.items() if old != new and new in SONG_ITEMS),
                sum(1 for i in SONG_ITEMS if i not in now_gives.values())) if a.songs == 2 else "teach another song",
            "; the royal tomb's stones ask for %s" % now_gives[SUN] if song_parts else ""))
    # ---- a scrub that sells another item no longer names its own (English) ----
    lines = sorted({label for h, g in gifts.items() if g.key in SCRUB_LINES and gives[h] != g.item for label in SCRUB_LINES[g.key]})
    for lang in SCRUB_LANGS if lines else ():
        folder = os.path.join(romfs, "Mals")
        for n in sorted(n for n in (os.listdir(folder) if os.path.isdir(folder) else []) if n.startswith(lang + ".") and n.endswith(".sarc.zs")):
            try:
                was = gift_files["Mals/" + n] if "Mals/" + n in gift_files else unpack(open(os.path.join(folder, n), "rb").read(), zs, dicts)   # (an earlier edit's first: the fairies' offerings)
                parts = sarc_read(was)
                text = parts[SCRUB_TEXT]
                for label in lines:
                    text = scrub_words(text, label) or text
                parts[SCRUB_TEXT] = text
                now = sarc_write(parts)
            except (OSError, KeyError, ValueError, struct.error) as e:
                sys.exit("the scrubs' words, Mals/%s: %s. Nothing written." % (n, e))
            if len(now) > len(was):   # (smaller it may be: the size table's entry is for the bigger one)
                sys.exit("the scrubs' words, Mals/%s: the archive would grow. Nothing written." % n)
            if now != was:
                gift_files["Mals/" + n] = now
    if lines:
        print("Deku Scrubs: %d sale line%s no longer name the scrub's own item (English)" % (len(lines), "" if len(lines) == 1 else "s"))


    # ---- Shops: the shelves that take part sell what the shuffle put there, once ----
    shop_files, shop_packs, shop_new, shop_sizes, shop_parts = {}, {}, set(), {}, set()
    tier_files, tier_maps = {}, {}   # (a shelf of a family: its map for each tier, SHELF_TIERS; a map: its shelves of a family)
    if shelves:
        def pack(name):
            rel = "Pack/Actor/%s.pack.zs" % name
            return pack_files[rel] if rel in pack_files else unpack(open(os.path.join(romfs, *rel.split("/")), "rb").read(), zs, dicts)
        # (a test: RANDO_TEST_SHOPS="<item> <item> ..." puts those items on the shelves in their order, the Kokiri shop's
        #  four first, then the Bazaar's, the Potion Shop's, the Bombchu Shop's, the Goron shop's and the Zora shop's: to
        #  see how every item stands on a shelf and what its name and words are there. The seed's rules are not asked)
        for h, item in zip(shelves, os.environ.get("RANDO_TEST_SHOPS", "").split()):
            gives[h] = item
        try:
            # (a shelf actor for each shelf: its item, at its price)
            on_sale = collections.OrderedDict((shop_actor("%s_%d" % (shop.key, index)), (gives[h], shelf_prices[h])) for h, (shop, index, _) in shelves.items())
            tiers = {}   # (with Progressive items, a shelf of a family: an actor for each of it, SHELF_FAMILIES)
            for actor, (item, price) in list(on_sale.items()) if a.progressive and os.environ.get("RANDO_TEST_SHELF_TIERS") != "0" else ():
                family = shelf_family(item)
                if family:   # (the shuffled item's tier is the shelf's own actor, the one its goods list names)
                    tiers[actor] = [actor if each == item else "%s_%d" % (actor, k) for k, each in enumerate(family)]
                    on_sale.update((tier, (each, price)) for tier, each in zip(tiers[actor], family) if tier != actor)
            base, sample, names = pack(SHOP_BASE), pack(SHOP_SAMPLE), {}
            for actor, (item, price) in list(on_sale.items()):
                if actor not in on_sale:   # (a family's taken out below)
                    continue
                try:
                    new, parts, names[actor] = shop_pack(item, unpack(open(os.path.join(romfs, "Pack", "Actor", item + ".pack.zs"), "rb").read(), zs, dicts),
                                                         base, sample, price, pouch_changed, actor,
                                                         pack(SHELF_MODEL_AS[item]) if item in SHELF_MODEL_AS else None)
                except (OSError, ValueError) as e:
                    owner = next((o for o, t in tiers.items() if actor in t), None)
                    if owner is None:
                        raise
                    print("a shelf of a family, %s: %s has no shelf actor (%s): the shelf shows its own item" % (owner, item, e))
                    for t in tiers.pop(owner):
                        if t == owner:
                            continue
                        on_sale.pop(t, None)
                        names.pop(t, None)
                        shop_files.pop("Pack/Actor/%s.pack.zs" % t, None)
                        shop_packs.pop("Pack/Actor/%s.pack" % t, None)
                    continue
                shop_files["Pack/Actor/%s.pack.zs" % actor] = new
                shop_packs["Pack/Actor/%s.pack" % actor] = len(new)
                shop_new.update(parts)
            folder = os.path.join(romfs, "RSDB")
            lifts, scales, turns = {}, {}, {}
            for kind in SHOP_TABLES:   # (the game's three lists of actors: a row for each shelf actor)
                n = next((n for n in sorted(os.listdir(folder)) if n.startswith(kind + ".") and ".byml" in n.lower()), None)
                if n is None:
                    raise ValueError("the game has no list %s" % kind)
                table = unpack(open(os.path.join(folder, n), "rb").read(), zs, dicts)
                if kind == "ActorInfo":   # (how high each shelf's actor stands: by its item's model)
                    fits = {actor: SHELF_FIT_SHOP.get(shelf_shop(actor), {}).get(item) or shelf_fit(item, model_box(table, SHELF_MODEL_AS.get(item, item)))
                            for actor, (item, _) in on_sale.items()}
                    lifts = {actor: lift for actor, (lift, _) in fits.items() if lift}
                    scales = {actor: scale for actor, (_, scale) in fits.items() if scale != 1.0}
                    turns = {actor: shelf_turn(actor, item) for actor, (item, _) in on_sale.items() if shelf_turn(actor, item)}
                    # (a test: RANDO_TEST_LIFTS="<metres> ..." puts the shelves, in RANDO_TEST_SHOPS' order, that much
                    #  higher in place of what their items ask for; "-" leaves one as it is)
                    for (shop, index, _), turn in zip(shelves.values(), os.environ.get("RANDO_TEST_TURNS", "").split()):
                        if turn != "-":   # (a test: "<x>,<y>,<z>" in radians for each shelf, "-" for none)
                            turns[shop_actor("%s_%d" % (shop.key, index))] = tuple(float(v) for v in turn.split(","))
                    for (shop, index, _), size in zip(shelves.values(), os.environ.get("RANDO_TEST_SCALES", "").split()):
                        if size != "-":
                            scales[shop_actor("%s_%d" % (shop.key, index))] = float(size)
                    for (shop, index, _), lift in zip(shelves.values(), os.environ.get("RANDO_TEST_LIFTS", "").split()):
                        if lift != "-":
                            lifts[shop_actor("%s_%d" % (shop.key, index))] = float(lift)
                for actor, (item, price) in on_sale.items():
                    table = shop_rows(table, kind, item, price, actor)
                shop_files["RSDB/" + n] = table
                shop_sizes["RSDB/" + (n[:-3] if n.lower().endswith(".zs") else n)] = len(table)
            packs = sorted(n[:-len(".pack.zs")] for n in os.listdir(os.path.join(romfs, "Pack", "Actor")) if "Shop" in n and n.startswith("Npc_") and n.endswith(".pack.zs"))
            if placement >= SHOP_TOWNS:   # (the adult Potion Shop keeper's goods list of his own)
                new, mine, actor = potion_adult(pack(POTION_KEEPER))
                pack_files["Pack/Actor/%s.pack.zs" % POTION_KEEPER] = new
                pack_sizes["Pack/Actor/%s.pack" % POTION_KEEPER] = len(new)
                shop_new.add(mine)
                shop_parts.add(actor)
            for shop in shops(placement):   # (the goods lists, in every pack that has a copy, and the shelves of the map files)
                sells = {index: (actor, shop_actor("%s_%d" % (shop.key, index))) for index, actor in shop_slots(shop, a.shop_shelves, shield_shelf)}
                shown = {index: shelf_flag[h] for h, (its, index, _) in shelves.items() if its is shop}
                for param in shop.params:
                    name, found = SHOP_PARAM % param, 0
                    for keeper in packs:
                        parts = sarc_read(pack(keeper))
                        if name not in parts:
                            continue
                        parts[name] = shop_goods(parts[name], sells, shown)
                        new = sarc_write(parts)
                        pack_files["Pack/Actor/%s.pack.zs" % keeper] = new
                        pack_sizes["Pack/Actor/%s.pack" % keeper] = len(new)
                        shop_parts.add(name)
                        found += 1
                    if not found:
                        raise ValueError("no pack has the goods list %s" % param)
                on_shelf, found = {(actor, index): new for index, (actor, new) in sells.items()}, 0
                for area in shop.areas:
                    folder_map = os.path.join(romfs, "Banc", area)
                    for n in sorted(os.listdir(folder_map)) if os.path.isdir(folder_map) else ():
                        rel = "Banc/%s/%s" % (area, n)
                        if ".bcett.byml" not in n.lower():
                            continue
                        data = changed[rel] if rel in changed else unpack(open(os.path.join(folder_map, n), "rb").read(), zs, dicts)
                        if not any(actor.encode() in data for actor, _ in on_shelf):
                            continue
                        new, count = shelf_actors(data, on_shelf, lifts, scales, turns)
                        if new is not None:
                            changed[rel] = new
                            sizes[rel[:-3] if rel.lower().endswith(".zs") else rel] = len(new)
                            found += count
                            # (its shelves of a family, of every shop in it: the versions are made once the map is
                            #  finished, below "the shelves of a family's maps". The Market has two shops' shelves)
                            mine = tier_maps.setdefault(rel, [])
                            mine += [actor for actor in tiers if actor not in mine and actor.encode() in new and
                                     actor in on_shelf.values()]
                if found < len(sells):
                    raise ValueError("%s: the map files have %d of its %d shelves" % (shop.name, found, len(sells)))
            folder = os.path.join(romfs, "Mals")   # (the words under an item's name, in every language)
            for n in sorted(n for n in (os.listdir(folder) if os.path.isdir(folder) else []) if n.endswith(".sarc.zs")):
                rel = "Mals/" + n
                parts = sarc_read(gift_files[rel] if rel in gift_files else unpack(open(os.path.join(folder, n), "rb").read(), zs, dicts))
                text = parts.get(SHOP_TEXT)
                if text is None:
                    continue
                was = text
                for name in sorted(set(names.values())):
                    caps = n.startswith(SHOP_NAME_CAPS) and shop_caption(text, name) is not None
                    text = shop_caption(text, name) or text
                    if caps:
                        text = shop_name_caps(text, name) or text
                if text != was:
                    parts[SHOP_TEXT] = text
                    gift_files[rel] = sarc_write(parts)
                    shop_sizes[rel[:-3]] = len(gift_files[rel])
        except (OSError, KeyError, ValueError, struct.error, IndexError) as e:
            sys.exit("the shops: %s. Nothing written." % e)
        print("Shops (%s): %d shelves of %d shops take part, each sold once; %d within the child's wallet, %d ask for the Adult's, %d for the Giant's" % (
            "any price" if a.shops == 2 else "every shelf 10 rupees" if a.shops == 3 else "most prices low", len(shelves), len(shops(placement)),
            *(sum(1 for p in shelf_prices.values() if wallet_need(p) == need) for _, need in WALLETS)))

    # ---- Hints from the Gossip Stones (rando_hints): every stone's line, in every language's archive ----
    hints, stones = [], {}
    if a.hints:
        held = [(spots[h][0], gives.get(h, spots[h][1]), h in gives) for h in spots]
        held += [(skulls[h][0], skull_drops.get(h) or TOKEN, True) for h in able]
        held += [(pieces[h][0], heart_drops[h], True) for h in heart_drops]
        folder = os.path.join(romfs, "Mals")
        try:
            for n in sorted(n for n in (os.listdir(folder) if os.path.isdir(folder) else []) if n.endswith(".sarc.zs")):
                rel = "Mals/" + n
                parts = sarc_read(gift_files[rel] if rel in gift_files else unpack(open(os.path.join(folder, n), "rb").read(), zs, dicts))
                text = parts.get(HINT_TEXT)
                if text is None:
                    continue
                if not hints:
                    labels = [l for l in msbt_labels(text) if l.startswith(HINT_PREFIX) and not l.startswith(HINT_NOT)]
                    hints = choose_hints(random.Random(HINT_RANDOM % seed), held, PROGRESSION, labels)
                for label, words in hints:
                    text = hint_line(text, label, words)
                parts[HINT_TEXT] = text
                gift_files[rel] = sarc_write(parts)
                shop_sizes[rel[:-3]] = len(gift_files[rel])
            was = gift_files[HINT_FLOW] if HINT_FLOW in gift_files else unpack(open(os.path.join(romfs, HINT_FLOW), "rb").read(), zs, dicts)
            gift_files[HINT_FLOW] = stone_heard_flow(stone_talk_open(was))   # (and a stone talked to is heard: the Tracker's row)
            stones = stone_places(romfs, zs, dicts, gift_files)
            gift_sizes[HINT_FLOW[:-3]] = len(gift_files[HINT_FLOW])
        except (OSError, KeyError, ValueError, struct.error, IndexError) as e:
            sys.exit("the Gossip Stones' hints: %s. Nothing written." % e)
        print("Hints: %d Gossip Stones give %d hints" % (len(hints), len(set(w for _, w in hints))))

    # ---- Skulltula House hints (rando_house_hints): the cursed man's next-goal lines list the rewards, every language ----
    if a.house_hints:
        house = {}
        for g in GIFTS:
            if g.key in HOUSE_TOKENS:
                h = gift_hash(g.key)
                house[HOUSE_TOKENS[g.key]] = gives.get(h, g.item) if h in gifts else g.item
        pages = house_hint_pages(house)
        folder, said = os.path.join(romfs, "Mals"), 0
        try:
            for n in sorted(n for n in (os.listdir(folder) if os.path.isdir(folder) else []) if n.endswith(".sarc.zs")):
                rel = "Mals/" + n
                parts = sarc_read(gift_files[rel] if rel in gift_files else unpack(open(os.path.join(folder, n), "rb").read(), zs, dicts))
                text = parts.get(HOUSE_HINT_TEXT)
                if text is None:
                    continue
                for label in HOUSE_HINT_LABELS:
                    text = house_hint_line(text, label, pages)
                parts[HOUSE_HINT_TEXT] = text
                gift_files[rel] = sarc_write(parts)
                shop_sizes[rel[:-3]] = len(gift_files[rel])
                said += 1
        except (OSError, KeyError, ValueError, struct.error, IndexError) as e:
            sys.exit("the Skulltula House hints: %s. Nothing written." % e)
        if not said:
            sys.exit("the Skulltula House hints: no language has the cursed man's lines. Nothing written.")
        print("Skulltula House hints: the cursed man lists the rewards (%s) in %d languages" % (
            ", ".join("%d %s" % (k, hint_item(house[k])) for k in sorted(house)), said))

    # ---- the first bags' "You got" words (every seed, FIRST_BAG_WORDS) ----
    try:
        folder, bag_lines = os.path.join(romfs, "Mals"), 0
        for n in sorted(n for n in (os.listdir(folder) if os.path.isdir(folder) else []) if n.endswith(".sarc.zs")):
            rel = "Mals/" + n
            parts = sarc_read(gift_files[rel] if rel in gift_files else unpack(open(os.path.join(folder, n), "rb").read(), zs, dicts))
            if SHOP_TEXT not in parts:
                continue
            text, added = first_bag_words(parts[SHOP_TEXT], n.startswith(FIRST_BAG_ENGLISH))
            if added:
                parts[SHOP_TEXT] = text
                gift_files[rel] = sarc_write(parts)
                shop_sizes[rel[:-3]] = len(gift_files[rel])
                bag_lines += added
    except (OSError, KeyError, ValueError, struct.error, IndexError) as e:
        sys.exit("the first bags' words: %s. Nothing written." % e)
    print("the first Deku Nut and Deku Stick bags have \"You got\" words (%d lines)" % bag_lines)

    # ---- Either age's items (rando_ageless): the pouch table's age marks ----
    if a.ageless:
        try:
            gift_files[AGELESS_TABLE], count = pouch_ageless(open(os.path.join(romfs, *AGELESS_TABLE.split("/")), "rb").read(),
                                                              ageless_actors(a.ageless))
            shop_parts.add(AGELESS_TABLE)   # (its entry raised by PART_GROWTH: the game's is about 3.25 times the file, and 756 bytes more fell without)
        except (OSError, ValueError, KeyError, struct.error, IndexError) as e:
            sys.exit("either age's items: %s. Nothing written." % e)
        print("Either age's items: %s usable by both ages (%d marks set)" % (
            " and ".join(n for bit, n in ((1, "the swords"), (2, "the age-only items"), (4, "the tunics")) if a.ageless & bit), count))
    try:   # (Zelda's Letter in the amiibo slot, every seed: the egg and the chicken stay choosable, LETTER_SLOT)
        was = gift_files[AGELESS_TABLE] if AGELESS_TABLE in gift_files else open(os.path.join(romfs, *AGELESS_TABLE.split("/")), "rb").read()
        gift_files[AGELESS_TABLE] = pouch_letter_slot(was)
        shop_parts.add(AGELESS_TABLE)
    except (OSError, ValueError, KeyError, struct.error, IndexError) as e:
        sys.exit("Zelda's Letter's slot: %s. Nothing written." % e)
    print("Zelda's Letter has a slot of its own (the amiibo slot): the Weird Egg and its Chicken keep the trade slot")
    if a.ageless & 2:   # (the age-only items: each Link lent the other's clips, AGELESS_ANIMS)
        try:
            lent = 0
            for who, (param, files) in AGELESS_ANIMS.items():
                rel = "Pack/Actor/%s.pack.zs" % who
                was = pack_files[rel] if rel in pack_files else unpack(open(os.path.join(romfs, *rel.split("/")), "rb").read(), zs, dicts)
                new, added = ageless_anims(was, param, files)
                pack_files[rel] = new
                pack_sizes["Pack/Actor/%s.pack" % who] = len(new)
                pack_parts.add(param)
                lent += added
        except (OSError, ValueError, KeyError, struct.error, IndexError) as e:
            sys.exit("either age's items' moves: %s. Nothing written." % e)
        try:
            packs = {who: pack_files["Pack/Actor/%s.pack.zs" % who] for who in AGELESS_HOLDERS}
            packs, held = ageless_holders(packs)
            packs, shot = ageless_shooters(packs)
            packs["Player_Child"], arrows = ageless_arrows(packs["Player_Child"])
            for who, new in packs.items():
                pack_files["Pack/Actor/%s.pack.zs" % who] = new
                pack_sizes["Pack/Actor/%s.pack" % who] = len(new)
                pack_parts.add(AGELESS_HOLDERS[who])
                pack_parts.add(AGELESS_SHOOTERS[who])
            pack_parts.add(AGELESS_ARROWS[0])
        except (ValueError, KeyError, struct.error, IndexError) as e:
            sys.exit("either age's items' holders: %s. Nothing written." % e)
        print("Either age's items: each Link lent the other's moves (%d animation files), items to hold (%d) and to shoot (%d); the child's own arrows %s" % (
            lent, held, shot, "yes" if arrows else "already"))

    # ---- Magic and the fairies' gifts: the first magic as an item of our own, no free magic (MAGIC_ITEM, magic_free) ----
    if a.magic:
        try:
            rel = "Pack/Actor/%s.pack.zs" % MAGIC_PARENT
            new, parts = custom_pack(MAGIC_ITEM, MAGIC_PARENT, unpack(open(os.path.join(romfs, *rel.split("/")), "rb").read(), zs, dicts))
            shop_files["Pack/Actor/%s.pack.zs" % MAGIC_ITEM] = new
            shop_packs["Pack/Actor/%s.pack" % MAGIC_ITEM] = len(new)
            shop_new.update(parts)
            folder = os.path.join(romfs, "RSDB")
            for kind in SHOP_TABLES:
                n = next(n for n in sorted(os.listdir(folder)) if n.startswith(kind + ".") and ".byml" in n.lower())
                table = shop_files.get("RSDB/" + n) or unpack(open(os.path.join(folder, n), "rb").read(), zs, dicts)
                fields = ({"MPMax": (0xD1, struct.pack("<i", 24)), "PouchSpecialDeal": ("string", "None")} if kind == "PouchActorInfo" else
                          {"ActorName": ("string", MAGIC_ITEM)} if kind == "ActorInfo" else None)   # (its own name: the words looked up by it)
                table = custom_rows(table, kind, MAGIC_ITEM, MAGIC_PARENT, fields)
                if kind == "PouchActorInfo":
                    table, freed = magic_free(table)
                shop_files["RSDB/" + n] = table
                shop_sizes["RSDB/" + (n[:-3] if n.lower().endswith(".zs") else n)] = len(table)
            worded = 0
            folder = os.path.join(romfs, "Mals")   # (its words, in every language: the English ones)
            for n in sorted(n for n in (os.listdir(folder) if os.path.isdir(folder) else []) if n.endswith(".sarc.zs")):
                rel = "Mals/" + n
                parts = sarc_read(gift_files[rel] if rel in gift_files else unpack(open(os.path.join(folder, n), "rb").read(), zs, dicts))
                text = parts.get(CUSTOM_TEXT)
                if text is None:
                    continue
                for word, words in MAGIC_WORDS.items():
                    text = msbt_add(text, MAGIC_ITEM + word, words.encode("utf-8"))
                parts[CUSTOM_TEXT] = text
                gift_files[rel] = sarc_write(parts)
                shop_sizes[rel[:-3]] = len(gift_files[rel])
                worded += 1
        except (OSError, ValueError, KeyError, StopIteration, struct.error) as e:
            sys.exit("Magic and the fairies' gifts: %s. Nothing written." % e)
        print("Magic and the fairies' gifts: %s made (its words in %d languages), %d items no longer give magic, the second magic "
              "in a blue rupee's chest" % (MAGIC_ITEM, worded, freed))

    # ---- Open Door of Time: the door out of the way, in the child's Market and the adult's (DOOR_SONG: Sheik alone) ----
    if a.open_door or a.door_song:
        doors = sheiks = 0
        folder_map = os.path.join(romfs, "Banc", DOOR_AREA)
        try:
            for n in sorted(os.listdir(folder_map)):
                rel = "Banc/%s/%s" % (DOOR_AREA, n)
                if ".bcett.byml" not in n.lower():
                    continue
                data = changed[rel] if rel in changed else unpack(open(os.path.join(folder_map, n), "rb").read(), zs, dicts)
                if DOOR_ACTOR.encode() not in data and DOOR_SHEIK.encode() not in data:
                    continue
                new, count, aside = door_away(data, door=a.open_door)
                if new is not None:
                    changed[rel] = new
                    sizes[rel[:-3] if rel.lower().endswith(".zs") else rel] = len(new)
                    doors += count
                    sheiks += aside
        except (OSError, ValueError, struct.error, IndexError) as e:
            sys.exit("the Door of Time: %s. Nothing written." % e)
        if not doors and a.open_door:
            sys.exit("the Door of Time: the Market's map files have no such door. Nothing written.")
        if not sheiks:
            sys.exit("the Door of Time: the Market's map files have no Sheik by the sword. Nothing written.")
        print("the Door of Time is out of the way in %d map file%s of the Market, and Sheik to the side of the sword" % (doors, "" if doors == 1 else "s")
              if a.open_door else "the Door of Time opens with the Song of Time and an ocarina (the game's side), Sheik to the side of the sword")

    # ---- the Bombchu Shop: its keeper, music and sign by the quest no longer (every seed, BOMBCHU_ACTORS) ----
    try:
        chu_done = 0
        folder_map = os.path.join(romfs, "Banc", "Market")
        for n in sorted(os.listdir(folder_map)):
            rel = "Banc/Market/" + n
            if not n.startswith("Market_Child_") or ".bcett.byml" not in n.lower():
                continue
            data = changed[rel] if rel in changed else unpack(open(os.path.join(folder_map, n), "rb").read(), zs, dicts)
            if BOMBCHU_QUEST.encode() not in data:
                continue
            new, count = bombchu_presence(data)
            if new is not None:
                changed[rel] = new
                sizes[rel[:-3] if rel.lower().endswith(".zs") else rel] = len(new)
                chu_done += count
    except (OSError, ValueError, struct.error, IndexError) as e:
        sys.exit("the Bombchu Shop: %s. Nothing written." % e)
    if chu_done != 3:
        sys.exit("the Bombchu Shop: %d of its keeper, music and sign found in the child's Market, not 3. Nothing written." % chu_done)
    print("the Bombchu Shop's keeper is there from the start, and its sign gone")
    try:   # (every seed: the shop's door and Bombchu Bowling by ALWAYS_EXP, CHU_LOGIC; the door's AND made OR first)
        for rel in CHU_LOGIC:
            data = changed[rel] if rel in changed else open(os.path.join(romfs, *rel.split("/")), "rb").read()
            if rel == BOMBCHU_DOOR_LOGIC:
                data = bombchu_door_open(data)
            changed[rel] = ainb_exp_swap(data)
            sizes[rel] = len(changed[rel])
    except (OSError, ValueError, struct.error) as e:
        sys.exit("Bombchu Bowling and the Bombchu Shop: %s: %s. Nothing written." % (rel, e))
    print("Bombchu Bowling is open from the start, and the Bombchu Shop day and night")
    try:   # (every seed: the Water Temple's gate switch without the Ice Cavern, WATER_WALL)
        rel = WATER_WALL_FILE
        data = changed[rel] if rel in changed else unpack(open(os.path.join(romfs, *rel.split("/")), "rb").read(), zs, dicts)
        changed[rel] = water_wall_out(data)
        sizes[rel[:-3]] = len(changed[rel])
    except (OSError, ValueError, struct.error, IndexError) as e:
        sys.exit("the Water Temple's gate: %s. Nothing written." % e)
    print("the Water Temple's gate switch can be hit without the Ice Cavern done")
    soils = 0
    try:   # (Soil Skulltulas without bugs, rando_soil_bottle: the bean-soil Gold Skulltulas there for a bottle got, SOIL_FILES)
        for rel in SOIL_FILES if a.soil_bottle else ():
            data = changed[rel] if rel in changed else unpack(open(os.path.join(romfs, *rel.split("/")), "rb").read(), zs, dicts)
            changed[rel], k = soil_by_bottle(data)
            sizes[rel[:-3]] = len(changed[rel])
            soils += k
        if a.soil_bottle and soils != SOIL_COUNT:
            raise ValueError("%d bean-soil Gold Skulltulas found, not %d" % (soils, SOIL_COUNT))
    except (OSError, ValueError, struct.error, IndexError) as e:
        sys.exit("the bean-soil Gold Skulltulas: %s. Nothing written." % e)
    if a.soil_bottle:
        print("the %d bean-soil Gold Skulltulas are there once Link has a bottle, no bugs" % soils)
    try:   # (every seed: Lake Hylia's dead tree takes the Longshot before the Water Temple, TREE_WALL, bug 119)
        for rel in TREE_WALL_FILES:
            data = changed[rel] if rel in changed else unpack(open(os.path.join(romfs, *rel.split("/")), "rb").read(), zs, dicts)
            changed[rel] = water_wall_out(data, TREE_WALL)
            sizes[rel[:-3]] = len(changed[rel])
    except (OSError, ValueError, struct.error, IndexError) as e:
        sys.exit("Lake Hylia's dead tree: %s: %s. Nothing written." % (rel, e))
    try:   # (every seed: the invisible climbing boxes over the tree's vines are a Hookshot catch, BAKED_TREE_FILES, bug 119)
        for rel in BAKED_TREE_FILES:
            changed[rel] = baked_climb_hook(unpack(open(os.path.join(romfs, *rel.split("/")), "rb").read(), zs, dicts))
            sizes[rel[:-3]] = len(changed[rel])
    except (OSError, ValueError, struct.error) as e:
        sys.exit("Lake Hylia's dead tree's vines: %s: %s. Nothing written." % (rel, e))
    print("Lake Hylia's dead tree without its hookshot-stopping wall, its vines a Hookshot catch")
    try:   # (every seed: Goron City's sign-order grotto gives its right chest after a wrong try, sign_grotto_fix)
        rel = SIGN_GROTTO_LOGIC
        data = changed[rel] if rel in changed else open(os.path.join(romfs, *rel.split("/")), "rb").read()
        changed[rel] = sign_grotto_fix(data)
        sizes[rel] = len(changed[rel])
    except (OSError, ValueError, struct.error) as e:
        sys.exit("Goron City's sign-order grotto: %s. Nothing written." % e)
    print("Goron City's sign-order grotto gives its right chest after a wrong try")
    try:   # (every seed: the Forest Temple's Bow room opens its barred door once its Stalfos are dead, bow_room_fix)
        rel = BOW_ROOM_LOGIC
        data = changed[rel] if rel in changed else open(os.path.join(romfs, *rel.split("/")), "rb").read()
        changed[rel] = bow_room_fix(data)
        sizes[rel] = len(changed[rel])
    except (OSError, ValueError, struct.error) as e:
        sys.exit("the Forest Temple's Bow room: %s. Nothing written." % e)
    print("the Forest Temple's Bow room opens its barred door once its Stalfos are dead")
    if a.skip_cutscenes:   # (the Fire Temple's jailed Gorons gone and their chests unlocked, FIRE_GORONS)
        try:
            for rel in FIRE_GORONS + FIRE_CHESTS:
                data = changed[rel] if rel in changed else open(os.path.join(romfs, *rel.split("/")), "rb").read()
                gorons = rel in FIRE_GORONS
                changed[rel] = ainb_fix_inputs(data, "Logic_Delete" if gorons else "Unlock", "ActorLogicNpc" if gorons else "ActorLogicTreasureBox", 2 if gorons else 1)
                sizes[rel] = len(changed[rel])
        except (OSError, ValueError, struct.error) as e:
            sys.exit("the Fire Temple's jailed Gorons: %s: %s. Nothing written." % (rel, e))
        print("the Fire Temple's jailed Gorons are gone, and the chests behind them unlocked")
    if a.dampe_hookshot:   # (Shuffle Dampe's Hookshot: the race's questions name what its chest gives now, race_words)
        race_now = gives.get(DAMPE_HOOK_CHEST, HOOK)
        words = race_words(race_now)
        rel = DAMPE_FLOW
        try:
            if words:
                now, found = gift_items(unpack(open(os.path.join(romfs, *rel.split("/")), "rb").read(), zs, dicts), words, kinds=(0, 1))
                if now is None or set(words) - found:
                    raise ValueError("it names no %s" % ", ".join(sorted(set(words) - found)))
                changed[rel], sizes[rel[:-3]] = now, len(now)
                for rel in DAMPE_LOGIC:
                    data = changed[rel] if rel in changed else open(os.path.join(romfs, *rel.split("/")), "rb").read()
                    changed[rel] = ainb_exp_swap(data, "IsGet." + HOOK, "IsGet." + lesson_flag(race_now))
                    sizes[rel] = len(changed[rel])
        except (OSError, ValueError, struct.error) as e:
            sys.exit("Shuffle Dampe's Hookshot: %s: %s. Nothing written." % (rel, e))
        print("Dampe's race: its first prize is %s%s" % (race_now, ", and the race and the tomb ask for it by name" if words else ""))

    # ---- three red rupees on Hyrule Castle's drawbridge, in every seed (DRAWBRIDGE_RUPEES) ----
    try:
        rel = DRAWBRIDGE_FILE
        data = changed[rel] if rel in changed else unpack(open(os.path.join(romfs, *rel.split("/")), "rb").read(), zs, dicts)
        new, count = drawbridge_rupees(data)
        changed[rel] = new
        sizes[rel[:-3] if rel.lower().endswith(".zs") else rel] = len(new)
    except (OSError, ValueError, struct.error, IndexError, KeyError) as e:
        sys.exit("the drawbridge's rupees: %s. Nothing written." % e)
    print("Hyrule Castle's drawbridge has %d red rupees" % count)

    # ---- Bombchus: a limit of their own, in every seed (the list of pouch actors, with the shops' rows when there are) ----
    try:
        folder = os.path.join(romfs, "RSDB")
        n = next((n for n in sorted(os.listdir(folder)) if n.startswith(POUCH_TABLE + ".") and ".byml" in n.lower()), None)
        if n is None:
            raise ValueError("the game has no list %s" % POUCH_TABLE)
        rel = "RSDB/" + n
        table = chu_limit(shop_files[rel] if rel in shop_files else unpack(open(os.path.join(folder, n), "rb").read(), zs, dicts))
        shop_files[rel] = table
        shop_sizes[rel[:-3] if rel.lower().endswith(".zs") else rel] = len(table)
    except (OSError, KeyError, ValueError, struct.error, IndexError) as e:
        sys.exit("the Bombchus' limit: %s. Nothing written." % e)
    print("Bombchus can be carried without a Bomb Bag: %d at most" % BOMBCHU_LIMIT)

    # ---- a song looks like Sheik's harp, in every seed (SONG_LOOK) ----
    try:
        looked = 0
        for song in SONG_ITEMS:
            rel = "Pack/Actor/%s.pack.zs" % song
            new, count = song_look_pack(pack_files[rel] if rel in pack_files else unpack(open(os.path.join(romfs, *rel.split("/")), "rb").read(), zs, dicts))
            if not count:
                raise ValueError("%s's pack has no ModelInfo of its own" % song)
            pack_files[rel] = new
            pack_sizes["Pack/Actor/%s.pack" % song] = len(new)
            looked += 1
        for files_of, sizes_of in ((pack_files, pack_sizes), (shop_files, shop_packs)):
            for rel in [r for r in files_of if r.startswith("Pack/Actor/") and r[len("Pack/Actor/"):-len(".pack.zs")] not in SONG_ITEMS]:
                new, count = song_look_pack(files_of[rel])
                if count:
                    files_of[rel] = new
                    sizes_of[rel[:-3]] = len(new)
        folder = os.path.join(romfs, "RSDB")
        n = next((n for n in sorted(os.listdir(folder)) if n.startswith("ActorInfo.") and ".byml" in n.lower()), None)
        if n is None:
            raise ValueError("the game has no list ActorInfo")
        rel = "RSDB/" + n
        rows = list(SONG_ITEMS) + ([actor for actor, (item, _) in on_sale.items() if item in SONG_ITEMS] if shelves else [])
        table, count = song_look_rows(shop_files[rel] if rel in shop_files else unpack(open(os.path.join(folder, n), "rb").read(), zs, dicts), rows)
        shop_files[rel] = table
        shop_sizes[rel[:-3] if rel.lower().endswith(".zs") else rel] = len(table)
    except (OSError, KeyError, ValueError, struct.error, IndexError) as e:
        sys.exit("the songs' look: %s. Nothing written." % e)
    print("a song looks like Sheik's harp (%d songs, %d rows of the list of actors)" % (looked, count))

    # ---- Faster block pushing (rando_fast_push): every copy of a block's push curve, FAST_PUSH_PARAMS ----
    if a.fast_push:
        try:
            changed_packs = 0
            for n in sorted(os.listdir(os.path.join(romfs, "Pack", "Actor"))):
                if not n.endswith(".pack.zs"):
                    continue
                rel = "Pack/Actor/" + n
                was = pack_files[rel] if rel in pack_files else unpack(open(os.path.join(romfs, *rel.split("/")), "rb").read(), zs, dicts)
                if not any((FAST_PUSH_PART % p).encode() in was for p in FAST_PUSH_PARAMS):
                    continue
                parts = sarc_read(was)
                done = 0
                for p in FAST_PUSH_PARAMS:
                    part = FAST_PUSH_PART % p
                    new = fast_push_param(parts[part]) if part in parts else None
                    if new is not None:
                        parts[part] = new
                        pack_parts.add(part)
                        done += 1
                if done:
                    pack_files[rel] = sarc_write(parts)
                    pack_sizes[rel[:-3]] = len(pack_files[rel])
                    changed_packs += 1
            if not changed_packs:
                raise ValueError("no pack with a block's push curve")
        except (OSError, ValueError, KeyError, struct.error, IndexError) as e:
            sys.exit("Faster block pushing: %s. Nothing written." % e)
        print("Faster block pushing: the blocks' pushes in half the frames (%d packs)" % changed_packs)

    # ---- bombs without the Goron's Bracelet, in every seed ----
    try:
        for name in BOMB_PACKS:
            rel = "Pack/Actor/%s.pack.zs" % name
            was = pack_files[rel] if rel in pack_files else unpack(open(os.path.join(romfs, *rel.split("/")), "rb").read(), zs, dicts)
            new = bomb_lift(was)
            pack_files[rel] = new
            pack_sizes["Pack/Actor/%s.pack" % name] = len(new)
    except (OSError, KeyError, ValueError, struct.error, IndexError) as e:
        sys.exit("the bombs' lifting grade: %s. Nothing written." % e)
    print("bombs can be lifted without the Goron's Bracelet (%d packs)" % len(BOMB_PACKS))

    # ---- Gold Skulltulas by day (rando_skulltulas_day): the night-only ones out by day too ----
    if a.skulltulas_day:
        day = 0
        try:
            for top, dirs, names in os.walk(os.path.join(romfs, "Banc")):
                dirs.sort()
                for n in sorted(names):
                    if ".bcett.byml" not in n.lower():
                        continue
                    rel = os.path.relpath(os.path.join(top, n), romfs).replace("\\", "/")
                    data = changed[rel] if rel in changed else unpack(open(os.path.join(top, n), "rb").read(), zs, dicts)
                    new, count = skulltulas_by_day(data)
                    if new is not None:
                        changed[rel] = new
                        sizes[rel[:-3] if rel.lower().endswith(".zs") else rel] = len(new)
                        day += count
            # (and their AI never told it is day: bug 82)
            rel = SKULLTULA_PACK
            was = pack_files[rel] if rel in pack_files else unpack(open(os.path.join(romfs, *rel.split("/")), "rb").read(), zs, dicts)
            parts = sarc_read(was)
            parts[SKULLTULA_AI] = skulltula_ai_day(parts[SKULLTULA_AI])
            new = sarc_write(parts)
            pack_files[rel] = new
            pack_sizes[rel[:-3]] = len(new)
            rel = NIGHT_SKULLTULA_LOGIC   # (and their map groups' logic never told it is day)
            changed[rel] = night_skulltula_logic_day(changed[rel] if rel in changed else open(os.path.join(romfs, *rel.split("/")), "rb").read())
        except (OSError, ValueError, struct.error, IndexError, KeyError) as e:
            sys.exit("Gold Skulltulas by day: %s. Nothing written." % e)
        print("Gold Skulltulas by day: %d night-only ones are out by day too, their AI never told it is day" % day)

    # ---- (fixes 93, 94) a Piece of Heart lying in the world, or a boss's Heart Container, that gives another item shows
    #      that item: PIECE_LOOK, CONTAINER_LOOK ----
    if a.heart_pieces and heart_drops:
        try:
            def actor_pack(name):
                rel = "Pack/Actor/%s.pack.zs" % name
                return pack_files[rel] if rel in pack_files else unpack(open(os.path.join(romfs, *rel.split("/")), "rb").read(), zs, dicts)
            folder = os.path.join(romfs, "RSDB")
            for base, look, of_boss in ((HEART, PIECE_LOOK, False), (CONTAINER, CONTAINER_LOOK, True)):
                given = sorted({i for h, i in heart_drops.items() if (h in bosses) == of_boss and h not in suns and i != base})
                made = {}
                for k, item in enumerate(given):
                    name = look % k
                    try:
                        new, own_parts = piece_variant_pack(item, actor_pack(base), actor_pack(item), name, base)
                    except (OSError, ValueError) as e:
                        print("a %s giving %s keeps its look (%s)" % (base, item, e))
                        continue
                    made[item] = name
                    shop_files["Pack/Actor/%s.pack.zs" % name] = new
                    shop_packs["Pack/Actor/%s.pack" % name] = len(new)
                    shop_new.update(own_parts)
                for kind in SHOP_TABLES if made else ():
                    n = next(n for n in sorted(os.listdir(folder)) if n.startswith(kind + ".") and ".byml" in n.lower())
                    table = shop_files.get("RSDB/" + n) or unpack(open(os.path.join(folder, n), "rb").read(), zs, dicts)
                    for item, name in made.items():
                        table = piece_rows(table, kind, item, name, base)
                    shop_files["RSDB/" + n] = table
                    shop_sizes["RSDB/" + (n[:-3] if n.lower().endswith(".zs") else n)] = len(table)
                renamed = {h: made[i] for h, i in heart_drops.items() if i in made and (h in bosses) == of_boss and h not in suns}
                shown = 0
                for h in renamed:
                    for file in maps.get(h, ()):
                        rel = "Banc/%s/%s" % (pieces[h][0], file)
                        if rel in changed or os.path.isfile(os.path.join(romfs, *rel.split("/"))):
                            data = changed[rel] if rel in changed else unpack(open(os.path.join(romfs, *rel.split("/")), "rb").read(), zs, dicts)
                            new, k = piece_named(data, {h: renamed[h]}, base)
                            if k:
                                changed[rel], shown = new, shown + 1
                                sizes[rel[:-3]] = len(new)
                print("%s: %d that give another item show it (%d map entries, %d items' looks)" % (
                    "the bosses' Heart Containers" if of_boss else "Pieces of Heart", len(renamed), shown, len(made)))
        except (OSError, ValueError, struct.error, IndexError, KeyError, StopIteration) as e:
            sys.exit("the Pieces of Heart's and Heart Containers' looks: %s. Nothing written." % e)

    def shop_table(tbl):
        """the size table with the shops' files: the new packs and their own files added, the keepers' packs' goods
        lists raised, the lists of actors and the texts' archives made to fit"""
        for path, size in shop_packs.items():
            tbl = size_table_add(tbl, [path], size_entry(size, PACK_EXTRA))
        return size_table_update(size_table_raise(size_table_add(tbl, shop_new), shop_parts | song_parts), shop_sizes, SHOP_EXTRA)

    # ---- the shelves of a family's maps: each map once for each choice of its shelves' tiers, every other edit of it made ----
    # (one entry a map, every shop's shelves in it: seen 2026-11-16, the Market listed twice, for two shops, each one's
    #  versions overwriting the other's and made before the map's later edits; the game stayed black entering it)
    for rel, held in list(tier_maps.items()):
        held = held[:SHELF_TIER_MOST]
        if not held:
            del tier_maps[rel]
            continue
        tier_maps[rel] = held
        sized = rel[:-3] if rel.lower().endswith(".zs") else rel
        for combo, version in shelf_tier_maps(changed[rel], held, tiers, lifts, scales, turns).items():
            tier_files["%s.%s" % (rel, combo)] = version
            sizes[sized] = max(sizes.get(sized, 0), len(version))

    if a.quests:   # (gifts kept when their quest is moved on first, and no quest moved back: QUEST_LATE, QUEST_ORDER, QUEST_MAKE)
        for n in [l[0] for l in QUEST_LATE] + [QUEST_ORDER[0], QUEST_MAKE[0]]:
            rel = "%s/%s.bfevfl.zs" % (GIFT_FLOWS, n)
            try:
                was = gift_files[rel] if rel in gift_files else unpack(open(os.path.join(romfs, *rel.split("/")), "rb").read(), zs, dicts)
                gift_files[rel] = quest_order_flow(was, n)
                gift_sizes[rel[:-3]] = len(gift_files[rel])
            except (OSError, ValueError, struct.error) as e:
                sys.exit("quest order, %s: %s. Nothing written." % (rel, e))
        print("Quest rewards: the rolling Goron's and King Zora's gifts kept when their quest is moved on first; the Fire quest "
              "never moved back")
        for n in (DARUNIA_LATE[0], DARUNIA_ORDER[0]):   # (Darunia's gift after Dodongo's Cavern, DARUNIA_LATE)
            rel = "%s/%s.bfevfl.zs" % (GIFT_FLOWS if n == DARUNIA_LATE[0] else SCENE_FLOWS, n)
            try:
                was = gift_files[rel] if rel in gift_files else unpack(open(os.path.join(romfs, *rel.split("/")), "rb").read(), zs, dicts)
                gift_files[rel] = darunia_late_flow(was, n)
                gift_sizes[rel[:-3]] = len(gift_files[rel])
            except (OSError, ValueError, struct.error) as e:
                sys.exit("Darunia's late gift, %s: %s. Nothing written." % (rel, e))
        print("Quest rewards: Darunia's gift is had after Dodongo's Cavern too")
    for saver_on, rel, saver in ((a.any_fish, FISH_FLOW, "fish"), (a.skull_kid_fast, SKULL_KID_FLOW, "skull kid"),
                           (a.skip_tower, GANON_FLOW, "tower"), (a.archery_wins, GALLERY_FLOW, "gallery"),
                           (a.archery_wins, HORSE_ARCHERY_FLOW, "horse")):   # (the time savers: qol_flow, on what the gifts made)
        if not saver_on:
            continue
        try:
            was = gift_files[rel] if rel in gift_files else unpack(open(os.path.join(romfs, *rel.split("/")), "rb").read(), zs, dicts)
            gift_files[rel] = qol_flow(was, saver)
            gift_sizes[rel[:-3]] = len(gift_files[rel])
            if saver == "tower":
                data = changed[TOWER_ANCHOR_FILE] if TOWER_ANCHOR_FILE in changed else unpack(
                    open(os.path.join(romfs, *TOWER_ANCHOR_FILE.split("/")), "rb").read(), zs, dicts)
                changed[TOWER_ANCHOR_FILE] = tower_anchor(data)
                sizes[TOWER_ANCHOR_FILE[:-3]] = len(changed[TOWER_ANCHOR_FILE])
        except (OSError, ValueError, struct.error, KeyError) as e:
            sys.exit("a time saver (%s), %s: %s. Nothing written." % (saver, rel, e))
        print({"fish": "Any fish wins: the fishing pond's prizes for any fish",
               "skull kid": "Faster Skull Kid game: one turn of 6 notes",
               "tower": "Skip the tower escape: Ganondorf's fall leads to the field below the tower",
               "gallery": "Archery games won: the shooting galleries' prize whatever the score",
               "horse": "Archery games won: the horseback archery's prizes whatever the score"}[saver])
    if BOWLING_FLOW in gift_files:   # (the bowling's gifts shuffled: its two checks the first two wins, bowling_order_flow)
        try:
            gift_files[BOWLING_FLOW] = bowling_order_flow(gift_files[BOWLING_FLOW])
            gift_sizes[BOWLING_FLOW[:-3]] = len(gift_files[BOWLING_FLOW])
        except (ValueError, struct.error, KeyError) as e:
            sys.exit("Bombchu Bowling's prizes, %s: %s. Nothing written." % (BOWLING_FLOW, e))
        print("Bombchu Bowling: the first win gives the bag's check, the second the Piece of Heart's")
    if a.shops:   # (the Empty Bottle sold without a bottle: shop_bottle_flow, bug 113)
        try:
            was = gift_files[SHOP_FLOW] if SHOP_FLOW in gift_files else unpack(open(os.path.join(romfs, *SHOP_FLOW.split("/")), "rb").read(), zs, dicts)
            gift_files[SHOP_FLOW] = shop_bottle_flow(was)
            gift_sizes[SHOP_FLOW[:-3]] = len(gift_files[SHOP_FLOW])
        except (OSError, ValueError, struct.error, KeyError) as e:
            sys.exit("the shops' flow, %s: %s. Nothing written." % (SHOP_FLOW, e))
    # ---- the size table ----
    folder = os.path.join(romfs, "System", "Resource")
    tables = sorted(n for n in (os.listdir(folder) if os.path.isdir(folder) else []) if "rsizetable" in n.lower())
    if not tables:
        sys.exit("no size table in %s: the grown map files would not load. Nothing written." % folder)
    new_tables = {}
    for n in tables:
        try:
            new_tables["System/Resource/" + n] = shop_table(size_table_update(size_table_add(size_table_raise(size_table_update(
                size_table_update(unpack(open(os.path.join(folder, n), "rb").read(), zs, dicts), sizes), pack_sizes, PACK_EXTRA),
                pack_parts - pack_new), pack_new | gift_new), gift_sizes, FLOW_EXTRA))
        except Exception as e:
            sys.exit("the size table %s could not be updated (%s). Nothing written." % (n, e))

    spoiler = []
    if logic:
        spoiler += ["", "the gating items, in the order the rules say they can be got:"] + [
            "  %d. %s" % (k + 1, ", ".join("%s (%s)" % (i, next(spots[h][0] for h in gives if gives[h] == i) if i in gives.values() else
                                                      next(skulls[h][0] for h in skull_drops if skull_drops[h] == i) + ", a Gold Skulltula"
                                                      if i in skull_drops.values() else
                                                      next(pieces[h][0] + (", the boss's Heart Container" if h in bosses else ", where Lake Hylia's Fire Arrows lay" if h in suns else ", where a Piece of Heart lay") for h in heart_drops if heart_drops[h] == i)
                                                      if i in heart_drops.values() else "its own chest")
                                           for i in sphere)) for k, sphere in enumerate(spheres)]
    area_now = None
    for h in sorted(gives, key=lambda q: (spots[q][0], str(spots[q][5]), q)):
        area, old, _, _, gyaml, pos, event = spots[h]
        if area != area_now:
            spoiler.append("")
            spoiler.append(area)
            area_now = area
        spoiler.append("  %-22s %-26s %-26s -> %s%s" % (gyaml, str(pos), old, gives[h] if gives[h] != old else "(the same)",
                                                         "   [event: %s]" % event if event and event not in PLAIN_EVENTS else ""))
    if a.skulltulas:
        spoiler += ["", "Gold Skulltulas (area, position -> what it drops)"]
        for h in sorted(skulls, key=lambda q: (skulls[q][0], str(skulls[q][1]), q)):
            area, pos, can = skulls[h][:3]
            spoiler.append("  %-22s %-26s -> %s" % (area, str(pos), skull_drops.get(h) or drops.get(h, "(its token)" if can else "(its token: cannot be given a drop)")))
    if a.heart_pieces:
        spoiler += ["", "Pieces of Heart lying in the world and the bosses' Heart Containers (area, position -> what it gives)"]
        for h in sorted(pieces, key=lambda q: (pieces[q][0], str(pieces[q][1]), q)):
            spoiler.append("  %-22s %-26s -> %s" % (pieces[h][0], str(pieces[h][1]), heart_drops.get(h, "(its container)" if h in bosses else "(its Fire Arrows)" if h in suns else "(its piece)")))
    if pots:
        spoiler += ["", "Pots (area, position -> what it drops)"]
        for h in sorted(pots, key=lambda q: (pots[q][0], str(pots[q][1]), q)):
            spoiler.append("  %-22s %-26s -> %s" % (pots[h][0], str(pots[h][1]), pot_drops.get(h, POT_OWN)))
    if suns and not a.heart_pieces:
        spoiler += ["", "Lake Hylia's Fire Arrows -> %s" % next(heart_drops.get(h, "(its Fire Arrows)") for h in suns)]
    if a.dry_run:
        print("\n".join(spoiler[:50]))
        print("(dry run: nothing written)")
        return
    written = []
    if a.skip_intro:
        try:
            flag_files[OPENING] = opening_skip(unpack(open(os.path.join(romfs, *OPENING.split("/")), "rb").read(), zs, dicts))
        except (OSError, ValueError, struct.error) as e:
            sys.exit("%s: %s. Nothing written." % (OPENING, e))
        print("a new game starts without its two opening cutscenes")
    try:   # (every seed: the cucco lady's game wants one cucco, CUCCO_LOGIC; her flow's count with the flows above)
        flag_files[CUCCO_LOGIC] = cucco_logic_one(unpack(open(os.path.join(romfs, *CUCCO_LOGIC.split("/")), "rb").read(), zs, dicts))
    except (OSError, ValueError, struct.error) as e:
        sys.exit("the cucco lady's game: %s. Nothing written." % e)
    print("the cucco lady's game wants one cucco")
    if a.open_door or a.door_song:   # (the adult's "A" at the sword from the start, SWORD_PROMPT_LOGIC)
        try:
            flag_files[SWORD_PROMPT_LOGIC] = sword_prompt_open(unpack(open(os.path.join(romfs, *SWORD_PROMPT_LOGIC.split("/")), "rb").read(), zs, dicts))
        except (OSError, ValueError, struct.error) as e:
            sys.exit("%s: %s. Nothing written." % (SWORD_PROMPT_LOGIC, e))
        print("an adult has the sword's prompt from the start")
    # (the Kokiri Sword's chest with another item in it: without the cutscene of the sword put on Link's back)
    if any(spots[h][6] == SWORD_EVENT and item != S for h, item in gives.items()):
        try:
            flag_files[SWORD_FLOW] = sword_chest_plain(unpack(open(os.path.join(romfs, *SWORD_FLOW.split("/")), "rb").read(), zs, dicts))
        except (OSError, ValueError, struct.error) as e:
            sys.exit("%s: %s. Nothing written." % (SWORD_FLOW, e))
        print("the Kokiri Sword's chest holds another item: it opens without the cutscene of the sword")
    # (Skip cutscenes: the scenes played as flowcharts without their talks, SCENE_SHOWS; a gift's scene as the gift made it)
    scene_files = {}
    if a.skip_cutscenes:
        folder, talks, kept = os.path.join(romfs, *SCENE_FLOWS.split("/")), 0, []
        called = collections.defaultdict(set)   # (a story's flow a lesson calls -> its entry points: SCENE_LESSON_SKIP_CALLS)
        for flow, stops in SCENE_STOPS.items():   # (and the characters who stop Link as he passes)
            called[flow].update(stops)
        for n in sorted(os.listdir(folder)):
            stem = n.split(".")[0]
            if not n.startswith("Dm_") or n.startswith("Dm_SY_") or stem.endswith(("_Effect", "_Env")) or not n.endswith(".bfevfl.zs"):
                continue
            rel = SCENE_FLOWS + "/" + n
            try:
                was = gift_files[rel] if rel in gift_files else unpack(open(os.path.join(folder, n), "rb").read(), zs, dicts)
                if struct.unpack_from("<H", was, 0x20)[0] != 1:
                    continue   # (a timeline: the game's side skips it)
                _, _, used = scene_steps(was)
                if "EventTalk" not in used and not any(g in used for g in SCENE_GIFTS) and stem not in SCENE_SILENT:
                    continue
                if stem in SCENE_KEEP or any(k in w for k in SCENE_KEEP_IF for w in used | {stem}):
                    kept.append(stem)
                    continue
                now, taken = quiet_scene(was, silent=stem in SCENE_SILENT)
                if stem.startswith("Dm_MelodyGet_"):
                    for s in scene_steps(was)[0]:
                        if s["kind"] == 4 and s["what"] and s["what"] not in SCENE_LESSON_SKIP_CALLS and not s["what"].startswith("Dm_"):
                            called[s["what"]].add(s["entry"])
            except (OSError, ValueError, struct.error) as e:
                sys.exit("a scene's flow, %s: %s. Nothing written." % (rel, e))
            if now is not None:
                (gift_files if rel in gift_files else scene_files)[rel] = now
                talks += taken
        print("Skip cutscenes: %d talks taken out of %d scene files; the scenes where Link answers or plays are as they were (%d: %s)" % (
            talks, len(scene_files) + sum(1 for r in gift_files if r.startswith(SCENE_FLOWS + "/Dm_")), len(set(kept)), ", ".join(sorted(set(kept)))))
        for flow, entries in sorted(called.items()):   # (the story's flows a lesson calls: only those entry points)
            for n in [flow + ".bfevfl.zs", flow + FLOW_TWIN + ".bfevfl.zs"]:
                if not os.path.isfile(os.path.join(folder, n)):
                    continue
                rel = SCENE_FLOWS + "/" + n
                files = gift_files if rel in gift_files else scene_files
                try:
                    was = files[rel] if rel in files else unpack(open(os.path.join(folder, n), "rb").read(), zs, dicts)
                    now, taken = quiet_scene(was, entries)
                except (OSError, ValueError, struct.error) as e:
                    sys.exit("a flow a lesson calls, %s: %s. Nothing written." % (rel, e))
                if now is not None:
                    files[rel] = now
                    talks += taken
                    print("Skip cutscenes: %s, called by a lesson: %d talks taken out of %s" % (flow, taken, ", ".join(sorted(entries))))
        videos = set()
        for n in sorted(os.listdir(folder)):
            if not n.endswith(".bfevfl.zs"):
                continue
            rel = SCENE_FLOWS + "/" + n
            files = gift_files if rel in gift_files else scene_files
            try:
                was = files[rel] if rel in files else unpack(open(os.path.join(folder, n), "rb").read(), zs, dicts)
                if not any(v.encode() in was for v in SCENE_VIDEOS) or struct.unpack_from("<H", was, 0x20)[0] != 1:
                    continue
                now, left_out = pass_videos(was, SCENE_VIDEOS)
            except (OSError, ValueError, struct.error) as e:
                sys.exit("a flow that plays a video, %s: %s. Nothing written." % (rel, e))
            if now is not None:
                files[rel] = now
                videos |= set(left_out)   # (not `which`: the chests' setting's name)
        print("Skip cutscenes: the videos %s are left out" % ", ".join(sorted(videos)))
    # (the last seed's files are taken away only now, when everything is made: a step above that fails leaves it whole.
    #  Seen: a flow a lesson calls that could not be quieted left the mod without its stamp and its checks)
    for rel, event in CHU_FLOWS:   # (every seed: the bowling's questions of the quest go on to "done", CHU_FLOWS; on what the steps above made)
        files = next((d for d in (gift_files, scene_files, shop_files, flag_files) if rel in d), flag_files)
        try:
            files[rel] = flow_switch_yes(files[rel] if rel in files else unpack(open(os.path.join(romfs, *rel.split("/")), "rb").read(), zs, dicts), event)
        except (OSError, ValueError, struct.error) as e:
            sys.exit("Bombchu Bowling: %s: %s. Nothing written." % (rel, e))
    removed = remove_old(mod)
    for rel, data in (list(changed.items()) + list(new_tables.items()) + list(flag_files.items()) + list(pack_files.items()) + list(gift_files.items()) +
                      list(shop_files.items()) + list(scene_files.items())):
        out = os.path.join(mod, "romfs", *rel.split("/"))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as f:
            f.write(zs.ZstdCompressor(level=9).compress(data) if rel.lower().endswith(".zs") else data)
        written.append("romfs/" + rel)
    for rel, data in tier_files.items():   # (outside romfs: the game's side gives one of them in place of the map, SHELF_TIERS)
        out = os.path.join(mod, SHELF_TIER_DIR, *rel.split("/"))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as f:
            f.write(zs.ZstdCompressor(level=9).compress(data))
        written.append(SHELF_TIER_DIR + "/" + rel)
    if tier_maps:   # (a map's path in the game's files, then the items its shelves of a family sell, in its versions' order,
        #  then those shelves' actors: the game's side names a shelf's tier as the map is read, bug 69, hos_oot_shelf_actor)
        with open(os.path.join(mod, SHELF_TIERS), "w", encoding="utf-8", newline="\n") as f:
            f.write("".join("%s|%s|%s\n" % (rel, ",".join(on_sale[actor][0] for actor in held), ",".join(held))
                            for rel, held in tier_maps.items()))
        print("Progressive items: %d map file%s of shops with shelves of a family, written for each tier" % (len(tier_maps), "" if len(tier_maps) == 1 else "s"))
    if hints:
        spoiler += ["", "the Gossip Stones' hints (the stone's name -> what it says)"] + ["  %-34s %s" % h for h in sorted(hints)]
    scarecrow = os.path.join(mod, FREE_SCARECROW_FILE)   # (Free Scarecrow's Song: the game's side gives the song)
    if a.free_scarecrow:
        with open(scarecrow, "w", encoding="utf-8", newline="\n") as f:
            f.write("L R L R L: a save without a Scarecrow's Song of its own is given this one (host/hos_main.c oot_scarecrow_free)\n")
    elif os.path.exists(scarecrow):
        os.remove(scarecrow)
    with open(os.path.join(mod, SKULL_TIERS), "w", encoding="utf-8", newline="\n") as f:   # (the game's side: hos_oot_drop_name)
        f.write("# the family tiers made pick-ups beside a Gold Skulltula's drop: its drop is shown as the family's next when it is one\n" +
                "".join(t + "\n" for t in skull_tier_list))
    with open(os.path.join(mod, START_FILE), "w", encoding="utf-8", newline="\n") as f:   # (the game's side gives them: oot_start_items)
        f.write("# the starting items, given to a save that does not hold them: <name> [<its ammo> <count>]\n" + "".join(l + "\n" for l in start_lines(a.start)))
    with open(os.path.join(mod, HINTS_FILE), "w", encoding="utf-8", newline="\n") as f:   # (the Tracker's: each stone, its place and its hint)
        f.write("# <the stone's name>|<its map folder>|<x y z>|<what it says>: the Tracker's Gossip Stones row lists the ones heard\n")
        f.write("".join("%s|%s|%.1f %.1f %.1f|%s\n" % (label, folder, pos[0], pos[1], pos[2], words)
                        for label, words in sorted(hints) for (name, folder), pos in sorted(stones.items()) if name == label))
    with open(os.path.join(mod, "spoiler.txt"), "w", encoding="utf-8") as f:
        f.write("seed %d, chests setting %d, dungeon keys setting %d\n(area: chest type, position, what it held -> what it holds now)\n" % (
            seed, which, keys_mode) + "\n".join(spoiler) + "\n")
    with open(os.path.join(mod, TRACKER), "w", encoding="utf-8", newline="\n") as f:   # (for the menu's Tracker tab)
        took = [h for h in able] if a.skulltulas else []
        f.write("\n".join(tracker_lines(collections.Counter(spots[h][0] for h in gives if h not in gifts), collections.Counter(skulls[h][0] for h in took),
                                        collections.Counter(g.area for g in gifts.values()), collections.Counter(p[0] for p in list(pieces.values()) + list(pots.values())))) + "\n")
    with open(os.path.join(mod, DUNGEON_ITEMS_FILE), "w", encoding="utf-8", newline="\n") as f:   # (the game's side: oot_dungeon_item)
        f.write("".join("%016x|%s|%s\n" % (h, owners[h], gives[h]) for h in sorted(owners)))
    # (the Tracker's rules only: a boss's Heart Container and its ending ask for its Boss Key when it moved, key_codes. The
    #  placement's rules never named it: boss_key_fits put it where the boss's rule reaches)
    moved_boss = {d for d in set(owners.values()) if any(gives.get(h) == BOSS_KEY and owners.get(h) == d for h in owners)}
    tracked = lambda h, n, d: fit_rule(each(lambda way: frozenset(way) | {boss_key_tag(d)}, n) if d in moved_boss and n is not None else n)   # (fit again: the keys' letters)
    ending_of = {gift_hash(BOSS_HEARTS[d][0]): d for d in BOSS_HEARTS}
    tneeds = {h: tracked(h, n, ending_of.get(h)) for h, n in needs.items()}
    with open(os.path.join(mod, CHECKS), "w", encoding="utf-8", newline="\n") as f:   # (for the Tracker tab's Go there)
        skull_need = skull_asks
        gift_key = gift_keys([h for h, g in gifts.items() if h in gives and g.key in GIFT_PLACES], list(spots))
        named = lambda kind, h, area, pos, item="": check_name(kind, item, about.get(h, {}), pos, exits[area], sub_areas[area])
        f.write("\n".join(check_lines([(spots[h][0], spots[h][5], CHEST_AGES.get(h) or check_ages(maps[h]), tneeds[h], named("Chest", h, spots[h][0], spots[h][5], MAGIC_JUNK if h == magic_chest else spots[h][1]), h, gives[h],
                                        CHEST_GO.get(h) or (chest_front(spots[h][5], about[h]["turned"]) if len(spots[h][5]) == 3 and "turned" in about.get(h, {}) else None))
                                       for h in gives if h not in gifts],
                                      [(skulls[h][0], skulls[h][1], check_ages(maps[h]), tneeds.get(h) or skull_need(h), named("Gold Skulltula", h, skulls[h][0], skulls[h][1]), h, skull_drops.get(h) or drops.get(h) or TOKEN,
                                        SKULL_GO.get(h))
                                       for h in took] +
                                      [(pots[h][0], pots[h][1], check_ages(maps[h]), tneeds.get(h) or heart_asks(h), "Pot", h, pot_drops.get(h, POT_OWN))
                                       for h in pots] +
                                      [(pieces[h][0], pieces[h][1], check_ages(maps[h]), tracked(h, needs.get(h) or heart_asks(h), bosses.get(h)),
                                        "Heart Container, " + BOSS_HEARTS[bosses[h]][1] if h in bosses else SUN_NAME if h in suns else named("Piece of Heart", h, pieces[h][0], pieces[h][1]), h,
                                        heart_drops.get(h, piece_own(h))) for h in pieces],
                                      [(g.area, gift_place(g.key)[1], gift_place(g.key)[0], tneeds[h], g.name, gift_key[h], gives[h], GIFT_STAND.get(g.key))
                                       for h, g in gifts.items() if h in gives and g.key in GIFT_PLACES] +
                                      [(shop.areas[0], shop.place, shop.ages, needs[h], gifts[h].name, None, gives[h])
                                       for h, (shop, _, _) in shelves.items() if h in gives])) + "\n")
    ways = check_ways(os.path.join(mod, CHECKS))   # (the Tracker tab's directions to a check: CHECK_WAYS)
    with open(os.path.join(mod, CHECK_WAYS), "w", encoding="utf-8", newline="\n") as f:
        f.write("".join("%s|%s\n" % w for w in ways))
    with open(os.path.join(mod, CHECKS), encoding="utf-8") as f:   # (the Tracker's "in logic after ...": CHECK_AFTER)
        after = check_after(f.read().splitlines())
    with open(os.path.join(mod, CHECK_AFTER), "w", encoding="utf-8", newline="\n") as f:
        f.write("".join("%s|%s\n" % (h, ",".join(temples)) for h, temples in after))
    if shelf_flag:   # (for the game's side: a shelf's name as the checks file has it, its flag's hash, the flag)
        with open(os.path.join(mod, SHELF_FLAGS), "w", encoding="utf-8", newline="\n") as f:
            f.write("".join("%s|%08x|%s\n" % ((gifts[h].name[:1].upper() + gifts[h].name[1:]).replace("|", "/")[:CHECK_NAME],
                                               murmur3(name.encode()), name) for h, name in shelf_flag.items()))
    with open(os.path.join(mod, "rando_manifest.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(written)) + "\n")
    with open(stamp_path, "w", encoding="utf-8") as f:   # (last: a run that stopped half way is made again)
        f.write(stamp)
    print("wrote %s: %d map files and the size table%s" % (mod, len(changed), " (%d files of the last seed replaced)" % removed if removed else ""))
    print("where everything went: %s" % os.path.join(mod, "spoiler.txt"))


if __name__ == "__main__":
    main()
