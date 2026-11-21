// (Triforce) The foliage in the sun's far shadow cascades, made cheaper (vk_draw.cpp draw_cull, for dynamic_state; and
// foliage_rate, for the mesh draws), apart from Vulkan so that tests/test_foliage_shadow.py can run its rules. After NX2navi's
// 754ded9 (epicmeme546's): 18 to 43 fps at Kokiri Forest's entrance on an RX 7900 XT there, the two halves together.
//
// The game draws its foliage cards (grass, ferns, leaves) double-sided with mesh programs, into the shadow cascades too: the
// sun's three cascades are the layers of one depth array, 1600 x 1600 in the owner's logs. Seen from the sun the stacked,
// alpha-tested cards cover the same texels many times over: NX2navi counted about 1,000 million fragments in one such draw of
// the far cascade. A cascade here is Triforce's own test for one, as for the cascades' depth bias in dynamic_state: depth only,
// square, wider than 768 (the characters' own shadow maps, 768 and less, are never touched).
//
// 1. The cull (RX_VK_FOLIAGE_SHADOW_CULL, on from layer 1 as NX2navi has it). A draw of a mesh program (native, or through the
// compute fallback) into a cascade from the given layer on, that culls neither face, is drawn with its back faces culled (its
// front ones with an "f"): half the cards' fragments there. Cull mode is dynamic state, so no other pipeline is made. It is not
// quite the same picture: a card that faces away from the sun no longer casts its shadow in those cascades. Where cards stand in
// crossed pairs or clumps (the game's foliage almost everywhere) the others cover the same texels; a lone card's shadow can go,
// in the middle and far cascades only, where a texel is tens of centimetres to metres of ground and such a card is a fraction of
// one. NX2navi kept it so (nothing done for a lone card), and so does this; the near cascade (layer 0) is drawn as the game asks.
// RX_VK_FOLIAGE_SHADOW_CULL=off: as the game asks everywhere.
//
// 2. The shading rate (RX_VK_FOLIAGE_SHADOW_VRS, from layer 2 as NX2navi has it). The same draws, of native mesh programs, from
// that layer on shade one fragment per 2 x 2 pixels (VK_KHR_fragment_shading_rate, pipelineFragmentShadingRate): the leaves'
// alpha test runs a quarter as often. Depth is still tested and written for each texel; what is coarser is the alpha cut-out, in
// 2 x 2 texels of the far cascade, metres of ground each. The rate is dynamic state in the pipelines that can draw such a draw and
// in no other: native mesh programs with no colour target and a depth one (pipeline_rate), whose key that already names; they
// set it at each draw (1 x 1 into any other target), their stage libraries are keyed apart. Where the device has no
// pipelineFragmentShadingRate (older Intel, some APUs), without native mesh shaders, or RX_VK_FOLIAGE_SHADOW_VRS=off, the
// extension is not enabled and no pipeline changes.
#pragma once

#include <cstdint>
#include <cstdlib>
#include <cstring>

namespace mkwvk::foliage_shadow {

constexpr int kNone = 0, kFront = 1, kBack = 2;   // (NVN's faces: NVN_FACE_NONE, _FRONT, _BACK)
constexpr uint32_t kCascadeMin = 769;             // (a cascade is wider than 768: vk_draw.cpp dynamic_state's test)
constexpr int kCullFrom = 1, kRateFrom = 2;       // (NX2navi's layers: the cull from the middle cascade, the rate in the far one)

struct Rule {
    int from = -1;        // (the first cascade layer it applies to; -1: off)
    bool front = false;   // (the front faces culled, not the back ones)
};

/// RX_VK_FOLIAGE_SHADOW_CULL=<layer>[f]: from that layer of the cascades on (the game has three, 0 to 2), the back faces culled,
/// the front ones with an "f" after the number. Unset or empty: from layer 1, the back faces (NX2navi's). Anything not starting
/// with a digit ("off", "-1"): off
inline Rule parse(const char* e) {
    Rule r;
    if (!e || !*e) return r.from = kCullFrom, r;
    if (*e < '0' || *e > '9') return r;
    r.from = std::atoi(e);
    r.front = std::strchr(e, 'f') != nullptr;
    return r;
}

/// RX_VK_FOLIAGE_SHADOW_VRS=<layer>: from that layer of the cascades on, one fragment per 2 x 2 pixels. Unset or empty: from
/// layer 2 (NX2navi's). Anything not starting with a digit ("off", "-1"): off, and the device's extension is not asked for.
/// Returns the first layer, -1 off
inline int parse_rate(const char* e) {
    if (!e || !*e) return kRateFrom;
    if (*e < '0' || *e > '9') return -1;
    return std::atoi(e);
}

/// A draw into a cascade from layer `from` on (no colour target, a depth target width x height, square and wider than 768, the
/// depth view's first layer at from or past it), of a mesh program, that culls neither face as the game draws it
inline bool far_foliage(int from, int game, bool mesh_program, int colour_targets, bool depth, uint32_t width, uint32_t height,
                        uint32_t layer) {
    if (from < 0 || game != kNone || !mesh_program || colour_targets != 0 || !depth) return false;
    return width == height && width >= kCascadeMin && layer >= (uint32_t)from;
}

/// The face a draw culls: the game's (cull, NVN's face), or under the rule the one it names, for far_foliage's draws
inline int cull(const Rule& rule, int game, bool mesh_program, int colour_targets, bool depth, uint32_t width, uint32_t height,
                uint32_t layer) {
    if (!far_foliage(rule.from, game, mesh_program, colour_targets, depth, width, height, layer)) return game;
    return rule.front ? kFront : kBack;
}

/// Whether a pipeline has the shading rate as dynamic state: the rate is on (on), the program a native mesh one, no colour
/// target and a depth one. Only what its key names (vk_draw.cpp pipeline_key): every pipeline of a key is made alike
inline bool pipeline_rate(bool on, bool native_mesh, int colour_targets, bool depth_format) {
    return on && native_mesh && colour_targets == 0 && depth_format;
}

/// The fragment size (1 or 2, both ways) a draw through such a pipeline sets: 2 for far_foliage's draws from layer `from` on
inline uint32_t rate(int from, int game, bool native_mesh, int colour_targets, bool depth, uint32_t width, uint32_t height,
                     uint32_t layer) {
    return far_foliage(from, game, native_mesh, colour_targets, depth, width, height, layer) ? 2u : 1u;
}

} // namespace mkwvk::foliage_shadow
