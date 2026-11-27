// (Willow Woods, asked 2026-11-26) The Tracker's map pictures: the game's own (UI/CustomTex/Map), made from the player's
// RomFS at a build into <game folder>/maps by nx2/map_assets.py (index.txt and a .hmap a picture: the game's ASTC blocks,
// zstd), read here on a thread of their own, decoded by suyu's decoder, halved and handed to the menu as pictures.
// They are the game's: they stay in the game folder, and nothing here writes anything.
#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <mutex>
#include <span>
#include <string>
#include <thread>
#include <vector>

#include "vk_paths.h"
#include "vk_internal.h"
#include "vk_imgui.h"
#include "vk_map_pictures.h"
#include "video_core/textures/astc.h"

extern "C" size_t ZSTD_decompress(void* dst, size_t dst_cap, const void* src, size_t src_size);   // (third_party/zstd, in this dll)
extern "C" unsigned ZSTD_isError(size_t code);

namespace mkwvk {
namespace {

// ---- the index (maps/index.txt): what tests/test_map_pictures.py runs ----
/// A picture of the index: "<folder>|<ages>|<floor>|<name>|<camera x>|<camera z>|<height>|<width px>|<height px>"
struct MapRow {
    std::string folder, ages, floor, name;
    float cam_x = 0, cam_z = 0, height = 0;
    int w = 0, h = 0;
};
/// A line of the index into row: false for a comment, an empty line or one that is not a picture's
bool map_row_parse(const char* line, MapRow* row) {
    if (!line[0] || line[0] == '#') return false;
    std::string part[9];
    int n = 0;
    for (const char* p = line; *p && *p != '\n' && *p != '\r'; p++) {
        if (*p == '|') {
            if (++n >= 9) return false;
        } else part[n] += *p;
    }
    if (n != 8 || part[0].empty() || part[3].empty()) return false;
    row->folder = part[0], row->ages = part[1], row->floor = part[2], row->name = part[3];
    row->cam_x = (float)atof(part[4].c_str()), row->cam_z = (float)atof(part[5].c_str()), row->height = (float)atof(part[6].c_str());
    row->w = atoi(part[7].c_str()), row->h = atoi(part[8].c_str());
    return row->height > 0 && row->w > 0 && row->h > 0 && row->w <= 8192 && row->h <= 8192;
}
/// Where a picture lies in the world: its middle is the camera's x and z, its WIDTH the capture's height in metres (a
/// metre is width / height pixels both ways: nx2/map_assets.py's note), x to the right and z down. out: x0, z0, x1, z1
void map_row_rect(const MapRow& r, float out[4]) {
    const float half_w = r.height * 0.5f, half_h = r.height * 0.5f * (float)r.h / (float)r.w;
    out[0] = r.cam_x - half_w, out[1] = r.cam_z - half_h, out[2] = r.cam_x + half_w, out[3] = r.cam_z + half_h;
}
/// The rows to draw for a map, in the index's order: an outdoor map's pictures of Link's age (age 0 the child, 1 the
/// adult; -1 not known: the child's), any age's when it has none of his (Hyrule Castle's is the child's alone); a
/// dungeon's shape ("All") and, with a floor named, that floor's. At most max
int map_rows_pick(const std::vector<MapRow>& rows, const char* folder, int age, const char* floor, int* picked, int max) {
    const char want = age == 1 ? 'A' : 'C';
    int n = 0;
    bool of_age = false;
    for (const MapRow& r : rows) of_age |= r.folder == folder && r.floor.empty() && r.ages.find(want) != std::string::npos;
    for (int i = 0; i < (int)rows.size() && n < max; i++) {
        const MapRow& r = rows[i];
        if (r.folder != folder) continue;
        if (r.floor.empty() ? (!of_age || r.ages.find(want) != std::string::npos) : (r.floor == "All" || (floor[0] && r.floor == floor)))
            picked[n++] = i;
    }
    return n;
}
/// A dungeon's floors (the rows with a floor's name, in the index's order: from the bottom up). At most max
int map_rows_floors(const std::vector<MapRow>& rows, const char* folder, int* picked, int max) {
    int n = 0;
    for (int i = 0; i < (int)rows.size() && n < max; i++)
        if (rows[i].folder == folder && !rows[i].floor.empty() && rows[i].floor != "All") picked[n++] = i;
    return n;
}

// ---- reading a picture ----
struct Decoded {
    int w = 0, h = 0;              // (halved)
    std::vector<uint8_t> rgba;     // (straight alpha)
    float rect[4] = {0, 0, 0, 0}, drawn[4] = {0, 0, 0, 0};
};
constexpr int kMaskDiv = 4;   // (a floor's "drawn on here" mask: a cell this many of the halved picture's pixels)
struct Mask {
    int w = 0, h = 0;
    std::vector<uint8_t> on;
    float rect[4] = {0, 0, 0, 0};
};

std::string maps_folder() {
    char exe[MAX_PATH];
    const DWORD n = game_module_path(exe, MAX_PATH);
    std::string path(exe, n);
    return path.substr(0, path.find_last_of("\\/") + 1) + "maps/";
}

/// <name>.hmap decoded and halved (each pixel the average of four, colours weighed by their alpha). A dungeon's shape
/// ("All": the game draws it black) is made slate, so it shows on the menu's dark panel
bool picture_read(const MapRow& row, Decoded* out) {
    const std::string path = maps_folder() + row.name + ".hmap";
    FILE* f = fopen(path.c_str(), "rb");
    if (!f) return false;
    char magic[4];
    uint32_t hd[7];   // (version, format, width, height, block width, block height, bytes of blocks)
    std::vector<uint8_t> packed, blocks;
    bool ok = fread(magic, 1, 4, f) == 4 && !std::memcmp(magic, "HWMP", 4) && fread(hd, 4, 7, f) == 7 && hd[0] == 1 &&
              hd[2] && hd[3] && hd[2] <= 8192 && hd[3] <= 8192 && hd[4] >= 4 && hd[4] <= 12 && hd[5] >= 4 && hd[5] <= 12 &&
              hd[6] == (uint64_t)((hd[2] + hd[4] - 1) / hd[4]) * ((hd[3] + hd[5] - 1) / hd[5]) * 16;
    if (ok) {
        const long at = ftell(f);
        fseek(f, 0, SEEK_END);
        const long end = ftell(f);
        fseek(f, at, SEEK_SET);
        ok = end > at && end - at < (64 << 20);
        if (ok) packed.resize((size_t)(end - at)), ok = fread(packed.data(), 1, packed.size(), f) == packed.size();
    }
    fclose(f);
    if (!ok) return false;
    blocks.resize(hd[6]);
    const size_t got = ZSTD_decompress(blocks.data(), blocks.size(), packed.data(), packed.size());
    if (ZSTD_isError(got) || got != blocks.size()) return false;
    const uint32_t w = hd[2], h = hd[3];
    std::vector<uint8_t> full((size_t)w * h * 4);
    try {
        Tegra::Texture::ASTC::DecompressSerial(blocks, w, h, 1, hd[4], hd[5], full);
    } catch (...) {
        return false;
    }
    const bool shape = row.floor == "All";
    out->w = (int)(w + 1) / 2, out->h = (int)(h + 1) / 2;
    out->rgba.assign((size_t)out->w * out->h * 4, 0);
    int lo[2] = {out->w, out->h}, hi[2] = {-1, -1};
    for (int y = 0; y < out->h; y++)
        for (int x = 0; x < out->w; x++) {
            unsigned c[3] = {0, 0, 0}, a = 0, n = 0;
            for (int dy = 0; dy < 2; dy++)
                for (int dx = 0; dx < 2; dx++) {
                    const uint32_t sx = (uint32_t)x * 2 + dx, sy = (uint32_t)y * 2 + dy;
                    if (sx >= w || sy >= h) continue;
                    const uint8_t* q = &full[((size_t)sy * w + sx) * 4];
                    c[0] += q[0] * q[3], c[1] += q[1] * q[3], c[2] += q[2] * q[3], a += q[3], n++;
                }
            uint8_t* p = &out->rgba[((size_t)y * out->w + x) * 4];
            if (a) p[0] = (uint8_t)(c[0] / a), p[1] = (uint8_t)(c[1] / a), p[2] = (uint8_t)(c[2] / a);
            p[3] = (uint8_t)(n ? a / n : 0);
            if (shape) p[0] = 58, p[1] = 70, p[2] = 96;
            if (p[3] > 32) lo[0] = std::min(lo[0], x), lo[1] = std::min(lo[1], y), hi[0] = std::max(hi[0], x), hi[1] = std::max(hi[1], y);
        }
    map_row_rect(row, out->rect);
    if (hi[0] < 0) lo[0] = lo[1] = 0, hi[0] = out->w - 1, hi[1] = out->h - 1;
    const float px = (out->rect[2] - out->rect[0]) / out->w, pz = (out->rect[3] - out->rect[1]) / out->h;
    out->drawn[0] = out->rect[0] + lo[0] * px, out->drawn[1] = out->rect[1] + lo[1] * pz;
    out->drawn[2] = out->rect[0] + (hi[0] + 1) * px, out->drawn[3] = out->rect[1] + (hi[1] + 1) * pz;
    return true;
}

// ---- what the menu asks for, and the thread that reads it ----
std::mutex lock;   // (everything below)
std::vector<MapRow> rows;
bool index_tried = false;
struct Job {   // (the pictures of one map, age and floor)
    std::string key;
    std::vector<Decoded> done;
    bool ready = false, shown = false;
};
std::shared_ptr<Job> job;
ImTextureData* slots[kMapLayers] = {nullptr, nullptr, nullptr};
MapLayer shown[kMapLayers];
int shown_n = 0;
std::string shown_key;
struct Floors {   // (a dungeon's floors' masks, kept once read)
    std::string folder;
    std::vector<std::string> names;
    std::vector<Mask> masks;
    bool ready = false;
};
std::vector<std::shared_ptr<Floors>> floors;

void index_load() {   // (lock held)
    if (index_tried) return;
    index_tried = true;
    const std::string path = maps_folder() + "index.txt";
    FILE* f = fopen(path.c_str(), "r");
    if (!f) {
        logf("map pictures: none (%s): the Tracker's maps show the checks without a picture", path.c_str());
        return;
    }
    char line[512];
    while (fgets(line, sizeof line, f)) {
        MapRow r;
        if (map_row_parse(line, &r)) rows.push_back(r);
    }
    fclose(f);
    logf("map pictures: %d in %s", (int)rows.size(), path.c_str());
}

}  // namespace

int map_layers(const char* folder, int age, const char* floor, MapLayer out[kMapLayers]) {
    std::unique_lock<std::mutex> hold(lock);
    index_load();
    int picked[kMapLayers];
    const int n = map_rows_pick(rows, folder, age, floor, picked, kMapLayers);
    if (!n) return 0;
    std::string key;
    for (int i = 0; i < n; i++) key += rows[picked[i]].name + "|";
    if (!job || job->key != key) {   // (another map: read it, the one shown staying until it is there)
        job = std::make_shared<Job>();
        job->key = key;
        std::vector<MapRow> want;
        for (int i = 0; i < n; i++) want.push_back(rows[picked[i]]);
        std::thread([j = job, want] {
            std::vector<Decoded> done;
            for (const MapRow& r : want) {
                Decoded d;
                if (picture_read(r, &d)) done.push_back(std::move(d));
            }
            std::lock_guard<std::mutex> g(lock);
            j->done = std::move(done), j->ready = true;
        }).detach();
    }
    if (job->ready && !job->shown) {   // (read: into the menu's pictures, on its thread)
        job->shown = true;
        shown_n = 0;
        for (Decoded& d : job->done) {
            if (shown_n >= kMapLayers) break;
            MapLayer& l = shown[shown_n];
            l.tex = ui::picture(slots[shown_n], d.w, d.h, d.rgba.data());
            l.x0 = d.rect[0], l.z0 = d.rect[1], l.x1 = d.rect[2], l.z1 = d.rect[3];
            l.bx0 = d.drawn[0], l.bz0 = d.drawn[1], l.bx1 = d.drawn[2], l.bz1 = d.drawn[3];
            shown_n++;
        }
        job->done.clear();
        shown_key = key;
    }
    if (shown_key != key) return 0;   // (the pictures shown are another map's)
    for (int i = 0; i < shown_n; i++) out[i] = shown[i];
    return shown_n;
}

namespace {
std::shared_ptr<Floors> floors_of(const char* folder) {   // (lock held: the dungeon's floors, their reading started)
    for (const auto& f : floors)
        if (f->folder == folder) return f;
    index_load();
    int picked[kMapFloors];
    const int n = map_rows_floors(rows, folder, picked, kMapFloors);
    auto f = std::make_shared<Floors>();
    f->folder = folder;
    floors.push_back(f);
    if (!n) {
        f->ready = true;
        return f;
    }
    std::vector<MapRow> want;
    for (int i = 0; i < n; i++) want.push_back(rows[picked[i]]), f->names.push_back(rows[picked[i]].floor);
    std::thread([f, want] {
        std::vector<Mask> masks;
        for (const MapRow& r : want) {
            Decoded d;
            Mask m;
            if (picture_read(r, &d)) {
                m.w = (d.w + kMaskDiv - 1) / kMaskDiv, m.h = (d.h + kMaskDiv - 1) / kMaskDiv;
                m.on.assign((size_t)m.w * m.h, 0);
                std::memcpy(m.rect, d.rect, sizeof m.rect);
                for (int y = 0; y < d.h; y++)
                    for (int x = 0; x < d.w; x++)
                        if (d.rgba[((size_t)y * d.w + x) * 4 + 3] > 96) m.on[(size_t)(y / kMaskDiv) * m.w + x / kMaskDiv] = 1;
            }
            masks.push_back(std::move(m));   // (one a floor, empty when its picture could not be read)
        }
        std::lock_guard<std::mutex> g(lock);
        f->masks = std::move(masks), f->ready = true;
    }).detach();
    return f;
}
}  // namespace

int map_floors(const char* folder, const char* names[kMapFloors]) {
    std::lock_guard<std::mutex> hold(lock);
    const auto f = floors_of(folder);
    if (!f->ready) return -1;
    for (size_t i = 0; i < f->names.size(); i++) names[i] = f->names[i].c_str();
    return (int)f->names.size();
}

unsigned map_floors_at(const char* folder, float x, float z) {
    std::lock_guard<std::mutex> hold(lock);
    const auto f = floors_of(folder);
    if (!f->ready) return 0;
    unsigned bits = 0;
    for (size_t i = 0; i < f->masks.size(); i++) {
        const Mask& m = f->masks[i];
        if (!m.w || m.rect[2] <= m.rect[0] || m.rect[3] <= m.rect[1]) continue;
        // (the cell at the place and the eight around it: a chest against a wall is on the wall's line)
        const int cx = (int)floorf((x - m.rect[0]) / (m.rect[2] - m.rect[0]) * m.w), cz = (int)floorf((z - m.rect[1]) / (m.rect[3] - m.rect[1]) * m.h);
        bool on = false;
        for (int dz = -1; dz <= 1 && !on; dz++)
            for (int dx = -1; dx <= 1 && !on; dx++)
                on = cx + dx >= 0 && cx + dx < m.w && cz + dz >= 0 && cz + dz < m.h && m.on[(size_t)(cz + dz) * m.w + cx + dx];
        if (on) bits |= 1u << i;
    }
    return bits;
}

}  // namespace mkwvk
