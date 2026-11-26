// (Willow Woods, from ProjectReLink 0.7.9.2, GPL-3.0-or-later: see vk_wheel.cpp)
// (relink) The item wheel's picture (vk_wheel.cpp): host/oot_wheel.c's state (oot_wheel_state.h) drawn on the CPU
// in the game's picture's size, and laid over the scene by vk_framegen.cpp framegen_wheel_backdrop, blurred and dimmed under it.
#pragma once

#include <cstdint>
#include <vector>

namespace mkwvk {

/// What wheel_picture drew: an area w x h at (x, y) of the game's picture, premultiplied RGBA8 rows, top down. version
/// changes whenever the pixels do (the backdrop uploads them again only then)
struct WheelPicture {
    const uint8_t* px = nullptr;
    uint32_t w = 0, h = 0;
    int x = 0, y = 0;
    uint64_t version = 0;
};

/// The item wheel for a game picture of pw x ph, this frame: false while it is closed (or the Item wheel row is off).
/// The present's thread only
bool wheel_picture(uint32_t pw, uint32_t ph, WheelPicture* out);

/// (Willow Woods: the HUD's Item buttons, vk_menu.cpp draw_item_buttons) the game's icon of an item (Item_Bomb), side x side
/// straight RGBA8; false while the icons are being read (it starts reading them) or for an item with none
bool wheel_icon_rgba(const char* name, int* side, std::vector<uint8_t>* rgba);

}  // namespace mkwvk
