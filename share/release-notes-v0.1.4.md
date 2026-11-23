**Willow Woods v0.1.4**: the per-check logic finally reaches every player, a working Water Temple gate switch, a new settings page, newer dungeon logic, less stutter and a few new time savers. Test release; expect bugs and please report what you find.

## Important fixes
- **The per-check logic now actually ships.** v0.1.3's "every check has its own rule" only worked on the developer's PC: the builder left the logic tables out of your game folder, so your seeds quietly used the old whole-area rules. They are in the game folder now.
- **Gossip Stone hints and Epona by Epona's Song no longer stop the seed with an error.** The library those settings need was also left out of the game folder.
- **The Fire Temple's Boss Key chest opens with Skip cutscenes on.** Removing the jailed Gorons had left that chest locked for good, so the temple couldn't be finished.
- **The Water Temple's gate switch works.** Fire the Hookshot or Longshot at the ring above the door. New setting **Water Temple gate**: Shut (the default, as the game has it) or Open from the start.
- **Gifts no longer lost by doing things out of order** (with Quest rewards): the adult rolling Goron's gift if you entered the Crater first, and King Zora's thaw gift if you did the Water Temple first.
- **The Forest Temple's Bow room** opens its barred door once its Stalfos are dead, so you're never shut in without the Bow.
- **Shuffle the Master Sword:** adult Link no longer holds a Master Sword he hasn't found.

## Logic
- New seeds use the other randomizer's newer dungeon logic, rechecked against the remake: the Spirit Temple and Gerudo Training Ground rewritten, Ganon's trials and three of Dodongo's Cavern's checks updated. A seed you are already playing keeps its rules and items.

## Launcher
- **A new Randomizer page:** settings grouped by kind (What's shuffled, Open world, Items, Quality of life), a coloured dot on each (green tested, yellow should work, red not yet), and settings that belong together side by side with two pickers (Shops: Prices and Every shelf, and more). The New seed window looks the same way.
- **Starting items:** Deku Sticks and Deku Nuts.
- Seed IDs can now be 30 characters long (with the newest settings on). IDs from v0.1.3 still read the same.

## New settings (Quality of life, off by default)
- **Any fish wins:** any fish you hand in at the fishing pond wins the prize.
- **Faster Skull Kid game:** the Lost Woods ocarina game is one turn of 6 notes.
- **Skip the tower escape:** after Ganondorf, straight to the field below the tower. Experimental: not tried in play yet.
- **Either age's tunics:** a setting of its own (it was part of Either age's items). Known issue: young Link can't wear them yet.

## Performance (measured on an RX 9070 XT)
- **Less stutter entering areas:** about a third less time lost in hitches over a Market/Kakariko tour (fixes from Triforce, Ocarina Reborn and Longshot), and a 5x faster texture decoder for cards without hardware ASTC (AMD's desktop cards).
- **Higher 1% lows** in the Market: two changes worth about +2.5% each (from Longshot and Triforce).
- FSR 4 (and the other temporal upscalers) no longer ghost the previous view for a few frames after a camera cut.
- **A freeze after Alt+Tab** with frame generation on, full screen, on AMD's Windows driver: the picture now comes back on its own instead of staying frozen until F11.
- **A rare crash** in the game's message queues (seen after the first boss in another port) no longer ends the game.

## Known issues
- Young Link can't wear the tunics with Either age's tunics on.
- Skip the tower escape is untested.
- Lake Hylia's Water Temple gate: a save whose gate was already opened by an earlier version stays open.

Coming from v0.1.3: press **Update** in the launcher (or download the new zip and run the builder on your game folder). Your saves stay. A seed you are playing is rewritten at the next Play with the same items; start a new seed to get the newer dungeon logic.

## What you need
- **Your own copy of the game** at the supported version: program `0400486024DEC000`, update v131072. This release has no game files: the builder makes the game on your PC from your copy.
- Windows 10 or 11 (64-bit), a CPU with AVX2, 16 GB of RAM, about 60 GB free while building.
- A graphics card with Vulkan 1.3 and mesh shaders: AMD Radeon RX 6000 or newer, NVIDIA RTX 20 or newer, Intel Arc.

## Install
1. Download **WillowWoodsBuilder.zip** below and unzip it (right-click > Extract All).
2. Run **HookshotBuilder.exe** in the unzipped folder (the Willow Woods Builder).
3. Pick your game file, choose where the game goes and its language, and press **Build the game**. This takes around 45 minutes; you can use your PC meanwhile.
4. Start from the **Willow Woods** shortcut on your desktop. The launcher opens on the **Randomizer** tab: pick a preset (Beginner is a good start) or set each setting, and press **Continue**.

**Keeping your saves:** choose your existing game folder in the builder: a build never removes the saves (they are in the folder's `user\` folder).
