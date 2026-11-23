/* (OoT debug cheats) the inventory editor's items, shared by the menu (gpu/vk/vk_menu.cpp) and the game side
   (host/hos_main.c). OOT_SECTION starts a heading in the menu list; OOT_ITEM(label, pouch content name, kind):
   kind 0 an item Link has or not (Enter unlocks / relocks), 1 a quantity (Left / Right change it).
   Pouch names come from the game's own event flows and actor packs (work/oot-teleport-research.md, "Inventory").
   The names marked (guess) are the likeliest of two spellings; the log's "inventory probe" line shows both. */
#ifndef OOT_CHEAT_ITEMS
#define OOT_CHEAT_ITEMS(OOT_SECTION, OOT_ITEM) \
    OOT_SECTION("Equipment") \
    OOT_ITEM("Kokiri Sword", "Weapon_Sword_Kokiri", 0) \
    OOT_ITEM("Master Sword", "Weapon_Sword_Master", 0) \
    OOT_ITEM("Giant's Knife", "Weapon_Sword_Giant", 0) \
    OOT_ITEM("Biggoron's Sword", "Weapon_Sword_Biggoron", 0) \
    OOT_ITEM("Deku Shield", "Weapon_Shield_Deku", 0) \
    OOT_ITEM("Hylian Shield", "Weapon_Shield_Hylian", 0) \
    OOT_ITEM("Mirror Shield", "Weapon_Shield_Mirror", 0) \
    OOT_ITEM("Goron Tunic", "Armor_Adult_Goron", 0) \
    OOT_ITEM("Zora Tunic", "Armor_Adult_Zora", 0) \
    OOT_ITEM("Iron Boots", "Armor_Adult_HeavyBoot", 0) \
    OOT_ITEM("Hover Boots", "Armor_Adult_HoverBoot", 0) \
    OOT_SECTION("Items") \
    OOT_ITEM("Deku Sticks", "Item_DekuStick", 1) \
    OOT_ITEM("Deku Nuts", "Item_DekuNut", 1) \
    OOT_ITEM("Bombs", "Item_Bomb", 1) \
    OOT_ITEM("Bombchus", "Item_Bombchu", 1) \
    OOT_ITEM("Fairy Slingshot", "Weapon_Range_SlingShot", 0) \
    OOT_ITEM("Deku Seeds", "Item_DekuSeed", 1) \
    OOT_ITEM("Fairy Bow", "Weapon_Range_Bow", 0) \
    OOT_ITEM("Arrows", "Item_Arrow_Normal", 1) \
    OOT_ITEM("Fire Arrow", "Item_Arrow_Fire", 0) \
    OOT_ITEM("Ice Arrow", "Item_Arrow_Ice", 0) \
    OOT_ITEM("Light Arrow", "Item_Arrow_Light", 0) \
    OOT_ITEM("Din's Fire", "Item_DinFire", 0) \
    OOT_ITEM("Farore's Wind", "Item_FaroreWind", 0) \
    OOT_ITEM("Nayru's Love", "Item_NayruLove", 0) \
    OOT_ITEM("Fairy Ocarina", "Item_Ocarina_Fairy", 0) \
    OOT_ITEM("Ocarina of Time", "Item_Ocarina_Time", 0) \
    OOT_ITEM("Hookshot", "Item_Hookshot", 0) \
    OOT_ITEM("Longshot", "Item_Longshot", 0) \
    OOT_ITEM("Boomerang", "Item_Boomerang", 0) \
    OOT_ITEM("Lens of Truth", "Item_GlassTruth", 0) \
    OOT_ITEM("Magic Beans", "Item_MagicBean", 1) \
    OOT_ITEM("Megaton Hammer", "Item_Hammer", 0) \
    OOT_ITEM("Empty Bottle", "Item_Bottle", 1) \
    OOT_SECTION("Masks") \
    OOT_ITEM("Keaton Mask", "Armor_Child_Mask_Keaton", 0) \
    OOT_ITEM("Skull Mask", "Armor_Child_Mask_Skull", 0) \
    OOT_ITEM("Spooky Mask", "Armor_Child_Mask_Spooky", 0) \
    OOT_ITEM("Bunny Hood", "Armor_Child_Mask_Bunny", 0) \
    OOT_ITEM("Goron Mask", "Armor_Child_Mask_Goron", 0) \
    OOT_ITEM("Zora Mask", "Armor_Child_Mask_Zora", 0) \
    OOT_ITEM("Gerudo Mask", "Armor_Child_Mask_Gerudo", 0) \
    OOT_ITEM("Mask of Truth", "Armor_Child_Mask_Truth", 0) \
    OOT_SECTION("Upgrades") \
    OOT_ITEM("Goron's Bracelet", "Item_Gauntlet_Goron", 0) \
    OOT_ITEM("Silver Gauntlets", "Armor_Adult_Gauntlet_Silver", 0) \
    OOT_ITEM("Golden Gauntlets", "Armor_Adult_Gauntlet_Gold", 0) \
    OOT_ITEM("Silver Scale", "Item_Scale_Silver", 0) \
    OOT_ITEM("Golden Scale", "Item_Scale_Gold", 0) \
    OOT_ITEM("Bomb Bag", "Item_BombBag_Small", 0) \
    OOT_ITEM("Big Bomb Bag", "Item_BombBag_Medium", 0) \
    OOT_ITEM("Biggest Bomb Bag", "Item_BombBag_Large", 0) \
    OOT_ITEM("Quiver", "Item_Quiver_Small", 0) \
    OOT_ITEM("Big Quiver", "Item_Quiver_Medium", 0) \
    OOT_ITEM("Biggest Quiver", "Item_Quiver_Large", 0) \
    OOT_ITEM("Bullet Bag", "Item_BulletBag_Small", 0) \
    OOT_ITEM("Big Bullet Bag", "Item_BulletBag_Medium", 0) \
    OOT_ITEM("Biggest Bullet Bag", "Item_BulletBag_Large", 0) \
    OOT_ITEM("Deku Stick Bag", "Item_StickBag_Small", 0) \
    OOT_ITEM("Bigger Stick Bag", "Item_StickBag_Medium", 0) \
    OOT_ITEM("Biggest Stick Bag", "Item_StickBag_Large", 0) \
    OOT_ITEM("Deku Nut Bag", "Item_NutBag_Small", 0) \
    OOT_ITEM("Bigger Nut Bag", "Item_NutBag_Medium", 0) \
    OOT_ITEM("Biggest Nut Bag", "Item_NutBag_Large", 0) \
    OOT_ITEM("Adult's Wallet", "Item_Wallet_Medium", 0) \
    OOT_ITEM("Giant's Wallet", "Item_Wallet_Large", 0) \
    OOT_ITEM("Improved Spin", "Item_FairyBless_MP", 0) \
    OOT_ITEM("Double Magic", "Item_FairyBless_MPDouble", 0) \
    OOT_ITEM("Double Defense", "Item_FairyBless_DefenseDouble", 0) \
    OOT_SECTION("Quest") \
    OOT_ITEM("Kokiri's Emerald", "Item_Stone_Forest", 0) \
    OOT_ITEM("Goron's Ruby", "Item_Stone_Fire", 0) \
    OOT_ITEM("Zora's Sapphire", "Item_Stone_Water", 0) \
    OOT_ITEM("Forest Medallion", "Item_Medal_Forest", 0) \
    OOT_ITEM("Fire Medallion", "Item_Medal_Fire", 0) \
    OOT_ITEM("Water Medallion", "Item_Medal_Water", 0) \
    OOT_ITEM("Shadow Medallion", "Item_Medal_Shadow", 0) \
    OOT_ITEM("Spirit Medallion", "Item_Medal_Spirit", 0) \
    OOT_ITEM("Light Medallion", "Item_Medal_Light", 0) \
    OOT_ITEM("Zelda's Lullaby", "Item_Melody_ZeldaLullaby", 0) \
    OOT_ITEM("Epona's Song", "Item_Melody_EponaSong", 0) \
    OOT_ITEM("Saria's Song", "Item_Melody_SariaSong", 0) \
    OOT_ITEM("Sun's Song", "Item_Melody_SunSong", 0) \
    OOT_ITEM("Song of Time", "Item_Melody_TimeSong", 0) \
    OOT_ITEM("Song of Storms", "Item_Melody_StormSong", 0) \
    OOT_ITEM("Minuet of Forest", "Item_Melody_ForestMinuet", 0) \
    OOT_ITEM("Bolero of Fire", "Item_Melody_FireBolero", 0) \
    OOT_ITEM("Serenade of Water", "Item_Melody_WaterSerenade", 0) \
    OOT_ITEM("Nocturne of Shadow", "Item_Melody_ShadowNocturne", 0) \
    OOT_ITEM("Requiem of Spirit", "Item_Melody_SpiritRequiem", 0) \
    OOT_ITEM("Prelude of Light", "Item_Melody_LightPrelude", 0) \
    OOT_ITEM("Echo Gem", "Item_AgonyStone", 0) \
    OOT_ITEM("Gerudo's Card", "Item_Token_Gerudo", 0) \
    OOT_ITEM("Gold Skulltula Tokens", "Item_Token_Gold", 1) \
    OOT_ITEM("Zelda's Letter", "Item_ZeldaLetter", 0) \
    OOT_ITEM("Magic Power", "Item_MagicMeter", 0)
#endif

/* (other spellings the game might use for the same item: logged once by the game side for checking) */
#define OOT_CHEAT_ITEM_PROBES \
    "Item_Sword_Kokiri", "Item_Sword_Giant", "Item_Sword_Biggoron", "Item_Shield_Mirror", "Item_Range_Bow", \
    "Item_Range_SlingShot", "Weapon_Range_Hookshot", "Weapon_Range_Longshot", "Weapon_Boomerang", "Weapon_Hammer", \
    "Item_HeavyBoot", "Item_HoverBoot", "Item_Mask_Keaton", "Item_Gauntlet_Silver", "Armor_GlassTruth", "Armor_Child_GlassTruth", "Armor_Adult_GlassTruth", \
    "Armor_Child_Gauntlet_Goron", "Item_Wallet_Small"

#define OOT_CHEAT_ITEM_BASE 4096   /* rx_option_set(OOT_CHEAT_ITEM_BASE + i, count) from the game side; -1 unknown */
/* (the randomizer's fork) the Tracker tab's checks, in the order of the seed's checks file: rx_option_set(OOT_TRACKER_BASE + i, done)
   from the game side: 1 collected, 0 not, -1 not known */
#define OOT_TRACKER_BASE 8192
/* (and that the randomizer's game is the one played: rx_option_set(OOT_TRACKER_ON, 1). Never sent in the normal game or in
   Master Quest, where the Tracker tab says so and reads no seed, though a seed's files may be in the folder) */
#define OOT_TRACKER_ON 8191
/* (and where Link is: rx_option_set(OOT_TRACKER_HERE, i), a check of the seed's file that is in the map he is in, or -1:
   the Tracker tab puts that check's area first) */
#define OOT_TRACKER_HERE 8190
#define OOT_TRACKER_MAX 512
#define OOT_CHEAT_AGE_ID 4090      /* rx_option_set(OOT_CHEAT_AGE_ID, age) from the game side: 0 child, 1 adult, -1 unknown */
/* (Willow Woods, asked 2026-11-21) the game's time of day for the In-game clock row: rx_option_set(OOT_CLOCK_ID, seconds since
   midnight) from the game side, twice a second; -1 no save loaded */
#define OOT_CLOCK_ID 4089
/* (Willow Woods, asked 2026-11-23) the Damage numbers row: rx_option_set(OOT_DAMAGE_HIT, hit | (1 << 16) when it killed) from the
   game side at each life an actor other than Link loses (host/hos_main.c hos_oot_hit), the hit before it was clamped at 0 */
#define OOT_DAMAGE_HIT 4088
/* (and just before it, where: rx_option_set(OOT_DAMAGE_AT, (y << 15) | x), each from 0 to 32767 across the game's picture, over
   the enemy as the camera sees it; -1 not on the picture: the hit's number shows in the middle of the screen) */
#define OOT_DAMAGE_AT 4087
/* (Willow Woods, asked 2026-11-23) the Health bars row: the enemies hit lately, OOT_HEALTH_SLOTS of them, each frame from the game
   side (host/hos_main.c oot_health_tick): rx_option_set(OOT_HEALTH_AT + k, where over it on the game's picture, as OOT_DAMAGE_AT,
   or -1 not on it), then rx_option_set(OOT_HEALTH_LIFE + k, life | max << 16, or 0 the slot is free) and rx_option_set(
   OOT_HEALTH_KIND + k, 0 an enemy, or 1 + a boss's place in OOT_BOSS_NAMES: its bar at the foot of the screen, named) */
#define OOT_HEALTH_SLOTS 8
/* (Willow Woods, asked 2026-11-23) the Tracker's map: where Link is, ten times a second from the game side (host/hos_main.c
   oot_tracker_refresh), in the map files' coordinates as the checks' places: rx_option_set(OOT_LINK_X, x * 100),
   OOT_LINK_Z the same of z, then OOT_LINK_YAW, the way he faces in thousandths of a radian (atan2 of x over z) */
#define OOT_LINK_X 4044
#define OOT_LINK_Z 4045
#define OOT_LINK_YAW 4046
#define OOT_HEALTH_AT 4048
#define OOT_HEALTH_LIFE 4056
#define OOT_HEALTH_KIND 4064
/* (the bosses and mini-bosses by their actors, and the names their bars show; the boss parts that keep a life of their own,
   Morpha's tentacle, Barinade's jellyfish, Meg's copies, Flare Dancer's fire body, have none and show as enemies) */
#define OOT_BOSSES(B) \
    B("Enemy_DungeonBoss_Gohma", "Queen Gohma") B("Enemy_DungeonBoss_Dodongo", "King Dodongo") \
    B("Enemy_DungeonBoss_Barinade", "Barinade") B("Enemy_DungeonBoss_PhantomGanon", "Phantom Ganon") \
    B("Enemy_DungeonBoss_Volvagia", "Volvagia") B("Enemy_DungeonBoss_Morpha", "Morpha") \
    B("Enemy_DungeonBoss_BongoBongo", "Bongo Bongo") B("Enemy_DungeonBoss_Twinrova", "Twinrova") \
    B("Enemy_DungeonBoss_Kotake", "Kotake") B("Enemy_DungeonBoss_Koume", "Koume") \
    B("Enemy_DungeonBoss_Ganondorf", "Ganondorf") B("Enemy_DungeonBoss_Ganon", "Ganon") \
    B("Enemy_DungeonBoss_Ganon_SecondHalfBattle", "Ganon") B("Enemy_MiddleBoss_BigOcto", "Big Octo") \
    B("Enemy_MiddleBoss_DarkLink", "Dark Link") B("Enemy_MiddleBoss_FlareDancer", "Flare Dancer") \
    B("Enemy_MiddleBoss_IronKnuckle_Nabooru", "Iron Knuckle") B("Enemy_MiddleBoss_Lizalfos", "Lizalfos") \
    B("Enemy_MiddleBoss_Poe_Meg", "Meg")
/* (Willow Woods, asked 2026-11-20) the Inventory page's Add all: every item Link lacks given and every amount filled, but
   the masks, the Biggoron's Sword, the Giant's Knife and the Gold Skulltula tokens (host/hos_main.c oot_add_all_tick) */
#define OOT_CHEAT_ADD_ALL 8
#define OOT_CHEAT_ITEM_ACTION 3000 /* + item * 256 + op: op 0..127 adds op - 64; op 200 unlocks (1) or relocks (all) */
