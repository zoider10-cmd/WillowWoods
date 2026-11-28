// (Willow Woods, asked 2026-11-26) The Tracker's map pictures (vk_map_pictures.cpp): the game's own map pictures, made from
// the player's RomFS at a build into <game folder>/maps (nx2/map_assets.py), read and decoded here for the Tracker tab's maps
// (vk_menu.cpp tracker_area_map) to draw behind its checks.
#pragma once

struct ImTextureData;

namespace mkwvk {

constexpr int kMapLayers = 3;   // (pictures drawn for one map: Hyrule Field's and Lake Hylia's; a dungeon's shape and a floor)
constexpr int kMapFloors = 8;   // (a dungeon's floors at most: the Deku Tree and the Fire Temple have five)

/// A picture to draw: where it lies in the world (x0, z0 its top left corner, x1, z1 its bottom right: x to the right, z
/// down, as the Tracker's maps), and the part of it that is drawn on (bx0..bz1, in the world too: the rest is see-through)
struct MapLayer {
    ImTextureData* tex = nullptr;
    float x0 = 0, z0 = 0, x1 = 0, z1 = 0;
    float bx0 = 0, bz0 = 0, bx1 = 0, bz1 = 0;
};

/// The pictures of a map (folder: the checks' Banc folder) for Link's age (0 the child, 1 the adult, -1 not known) and, in
/// a dungeon, a floor ("": none, the dungeon's shape alone), in the order to draw them: how many are in out (0: none made
/// for this map, or still being read: it starts reading them, and a later call has them). The menu's thread only
int map_layers(const char* folder, int age, const char* floor, MapLayer out[kMapLayers]);

/// A dungeon's floors from the bottom up (names: "B2", "1F"): how many, 0 for a map without floors' pictures, -1 while
/// they are being read (it starts reading them)
int map_floors(const char* folder, const char* names[kMapFloors]);

/// (the owner, 2026-11-27: the Tracker's window "to show the map the tracker uses") The pictures handed to the launcher's
/// Tracker window, which cannot decode them: once it has asked (it makes <game folder>/maps/view/wanted.txt), every
/// picture of the index that has neither a .png nor a .raw in maps/view is decoded as the menu's are (halved) and written
/// there as <name>.raw ("HWRV", u32 width, u32 height, then RGBA, straight alpha); the window makes a .png of each and
/// takes the .raw away. On a thread of its own at the lowest priority, started once a session; this call only looks for
/// the file (call it seldom). Made from the game: they stay in the game folder
void map_export_wanted();

/// The floors whose picture is drawn on at a place (bit n: map_floors' n-th), 0 none or not read yet
unsigned map_floors_at(const char* folder, float x, float z);

}  // namespace mkwvk
