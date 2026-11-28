/* Horizon OS layer, native host: process start and boot.

   What rtld and nn::init::Start do on hardware (see ports/zelda-totk/PORT.md, "How the game starts"), done here:
   map the guest window, load the relocated image (nx_image.py already linked it), make this host thread the
   guest main thread, run every module's DT_INIT in rtld's order (the SDK crt's _init: TLS registration with musl,
   then the module's constructors), then nninitStartup and nnMain.

   Usage: <game>.exe [image.bin] [--romfs <dir>] [--user <dir>] [--trace] [--prepare-shaders] [--compile-shaders all|most]
   Environment: HOS_TRACE=1 (log HLE calls), HOS_MEMORY_MB (memory the game is told it has),
                HOS_NVN_CONTINUE=1 (go on past nvnBootstrapLoader). */
#include "hos.h"
#ifndef HOOKSHOT_ENV_H   /* (env_on: the switches' one rule) */
#include "../gpu/vk/compat/hookshot_env.h"
#endif
#include "hos_paths.h"
#include "game_layout.h"
#include "options_path.h"
#include "hos_wide_size.h"   /* (the widescreen picture's size, shared with the Insert menu) */
#include "../gpu/vk/vk_api.h"
#include "../gpu/vk/oot_cheat_items.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifndef HOOKSHOT_VERSION   /* (nx2/build.py gives it: the release and a fingerprint of the sources, nx2/version.py) */
#define HOOKSHOT_VERSION "unknown"
#endif
const char *hos_version(void) { return HOOKSHOT_VERSION; }   /* (discord_rpc.c's status) */

#if defined(_WIN32) || defined(__EMSCRIPTEN__)
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <mmsystem.h>
#else
#include <windows.h>   /* (linux: host/posix's) */
#include <sys/mman.h>
#ifdef __linux__
#include <sys/prctl.h>
#include <sys/sysinfo.h>
#endif
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/syscall.h>
#endif
#include "hos_atomic_file.h"   /* (the files the saves' move copies, saves-moved.txt and the stand-ins' clean-up: whole or not at all) */
/* (linux) the separator of the paths the executable's folder is joined with */
#ifdef _WIN32
#define SEP 92
#define SEP_S "\\"
#else
#define SEP '/'
#define SEP_S "/"
#endif

/* (hookshot) the map Link is in and his age, as the last map: line, for the performance summary (gpu/vk/perf_report.cpp
   through MkwVkHost perf_info): "" while no save is loaded (before one, and back at the title) */
static SRWLOCK map_lock = SRWLOCK_INIT;
static char map_now[100];
void hos_movie_stats(int64_t out[5]);   /* nn_video.c */
const char *hos_perf_info(char *map, int cap, int64_t movie[5]) {
    AcquireSRWLockShared(&map_lock);
    snprintf(map, (size_t)cap, "%s", map_now);
    ReleaseSRWLockShared(&map_lock);
    hos_movie_stats(movie);
    return HOOKSHOT_VERSION;
}

#ifdef A64_MEM_ZERO
/* web: guest address = wasm address; the guest window is wasm memory below the host's data (-sGLOBAL_BASE) */
extern char __global_base;
uint64_t hos_space_end;
#define GUEST_SPACE (hos_space_end)
#else
#define GUEST_SPACE HOS_GUEST_SPACE
#endif
#define IMAGE_BASE hos_image_base   /* (the lift's: Eden's layout) */

#ifdef _WIN32
static void no_power_throttling(void) {
    const char *e = getenv("HOS_POWER_THROTTLING");
    if (e && atoi(e)) return;
    typedef BOOL(WINAPI * SetInfo)(HANDLE, int, LPVOID, DWORD);
    SetInfo set = (SetInfo)(void *)GetProcAddress(GetModuleHandleA("kernel32.dll"), "SetProcessInformation");
    if (!set) return;
    struct { ULONG version, control, state; } s = {1, 0x1 | 0x4, 0};
    if (!set(GetCurrentProcess(), 4, &s, sizeof s)) {
        s.control = 0x1;
        set(GetCurrentProcess(), 4, &s, sizeof s);
    }
}
#endif

int hos_game_is_mkw(void) { return !strcmp(hos_main_build_id, "d00e4f399e411d0613aa8d26b1c02fef"); }

/* gen/hos_image.c (build.py lift) */
extern const uint64_t hos_main_stack_size;
extern const int hos_main_priority, hos_main_core, hos_module_count;
extern const uint64_t hos_module_init[];
extern const char *const hos_module_name[];
extern const uint64_t hos_entry_nninitStartup, hos_entry_nnMain;
extern const uint64_t hos_entry_init_libc0, hos_entry_init_libc1, hos_entry_init_libc2, hos_entry_nnosInitialize,
    hos_entry_nninitInitializeSdkModule;
/* nn_fs.c */
extern const char *hos_romfs_dir, *hos_user_dir;

/* HOS_LARGE_PAGES=1 (experiment): the guest window in 2 MB pages, for fewer TLB misses (the game touches hundreds of MB
   of scattered heap; 4 KB pages cover only ~12 MB of it in the CPU's TLB). The whole window is then physical memory at
   once (4 GB, locked), and Windows needs the account to hold "Lock pages in memory" (SeLockMemoryPrivilege, Local
   Security Policy > User Rights Assignment; log off and on after): without it this logs why and uses normal pages. */
int hos_large_pages;   /* (hos_mem.c: freed pages are not discarded then) */
#if defined(_WIN32) && !defined(A64_MEM_ZERO)
#pragma comment(lib, "advapi32.lib")   /* (the token privilege calls) */
static void *reserve_large(SIZE_T size) {
    HANDLE token;
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY, &token)) return NULL;
    TOKEN_PRIVILEGES tp = {0};
    tp.PrivilegeCount = 1;
    tp.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED;
    const BOOL looked = LookupPrivilegeValueA(NULL, "SeLockMemoryPrivilege", &tp.Privileges[0].Luid);
    const BOOL adjusted = looked && AdjustTokenPrivileges(token, FALSE, &tp, 0, NULL, NULL);
    const DWORD err = GetLastError();
    CloseHandle(token);
    if (!adjusted || err == ERROR_NOT_ALL_ASSIGNED) {
        hos_log("mem: HOS_LARGE_PAGES: this account does not hold SeLockMemoryPrivilege (\"Lock pages in memory\"): "
                "normal pages");
        return NULL;
    }
    const SIZE_T large = GetLargePageMinimum();
    if (!large || size % large) return NULL;
    void *p = VirtualAlloc((void *)A64_HOST_BASE, size, MEM_RESERVE | MEM_COMMIT | MEM_LARGE_PAGES, PAGE_READWRITE);
    if (!p) hos_log("mem: HOS_LARGE_PAGES: %llu MB of large pages not available (error %lu): normal pages",
                    (unsigned long long)(size >> 20), GetLastError());
    return p;
}
#endif

#if !defined(_WIN32) && !defined(A64_MEM_ZERO)
extern int hos_guest_memfd;   /* (below) */
static int startup_stderr = -1;   /* (keep startup warnings visible if stderr becomes hookshot_log.txt) */
#endif
/* The guest window lives at the constant A64_HOST_BASE (rt/a64.h), so lifted code never loads its base. */
static int reserve_guest(void) {
#if defined(A64_MEM_ZERO)
    hos_space_end = (uint64_t)(uintptr_t)&__global_base & ~0xFFFFULL;
    return hos_space_end >= (1ULL << 30);
#elif defined(_WIN32)
    /* Committed but untouched pages cost no physical memory. Not write-watched: lifted stores and host writes mark
       their pages themselves (the soft write watch, rt/a64.h A64_MARK), and the renderer reads those marks. */
    if (env_on("HOS_LARGE_PAGES") && reserve_large(GUEST_SPACE) == (void *)A64_HOST_BASE) {
        hos_large_pages = 1;
        hos_log("mem: the guest window is in large pages (%llu MB)", (unsigned long long)(GUEST_SPACE >> 20));
        return 1;
    }
    /* mkw-recomp: 512 GB reserved, committed as the runtime hands memory out (hos_commit) or on first touch */
    void hos_commit_init(void);
    hos_commit_init();
    return VirtualAlloc((void *)A64_HOST_BASE, GUEST_SPACE, MEM_RESERVE, PAGE_NOACCESS) == (void *)A64_HOST_BASE;
#else
    /* (linux) the whole window readable and writable at once, its pages made as they are first touched (no commit
       step: MAP_NORESERVE). Decommitting is madvise (host/posix/win32_posix.c VirtualFree): the pages read as zero. */
    void hos_commit_init(void);
    hos_commit_init();   /* (the crash report) */
    /* The window is a memfd's, shared, so the Vulkan back end can hand the GPU the game's own pages as a dma-buf
       (udmabuf, gpu/vk/vk_memory.cpp import_dma_buf) instead of a host pointer: amdgpu checks every page of a host-pointer
       import again at each command submission, 15-45 ms a submission in Kokiri Forest. Pages of a shared mapping are freed
       with MADV_REMOVE, not MADV_DONTNEED (hos_posix_guest_discard). HOS_GUEST_MEMFD=0: anonymous memory, as before */
    {
        /* (only where /dev/udmabuf can be opened: a shared mapping's pages cannot be host-pointer imports (RADV:
           VK_ERROR_INVALID_EXTERNAL_HANDLE), so a pool udmabuf refused would be no import at all. A pool larger than udmabuf's
           size_limit_mb (64 MB unless raised) is imported as several dma-bufs bound into one sparse buffer, so no setting is
           needed. HOS_GUEST_MEMFD=1: the memfd all the same) */
        const char *e = getenv("HOS_GUEST_MEMFD");
        int usable = 0;
        {
            const int u = open("/dev/udmabuf", O_RDWR | O_CLOEXEC);
            if (u < 0 && (errno == EACCES || errno == EPERM)) {
                const int err = errno;
                static int warned;
                if (!warned) {
                    warned = 1;
                    const char *warning = "WARNING: /dev/udmabuf permission denied; GPU imports may be slower, especially on AMD/RADV. "
                        "Ask your administrator for access via its device group or a device-specific udev rule "
                        "(see README, On Linux). Do not run the game as root.";
                    if (startup_stderr >= 0) dprintf(startup_stderr, "%s (%s)\n", warning, strerror(err));
                    hos_log("%s (%s)", warning, strerror(err));
                }
            }
            if (startup_stderr >= 0) close(startup_stderr), startup_stderr = -1;
            if (u >= 0) {
                close(u);
                /* (issue 1135) usable whatever size_limit_mb says: the renderer reads the limit itself and takes udmabuf's
                   default, 64 MB, when it can't (gpu/vk/vk_memory.cpp import_dma_buf), and a limit too small only makes more
                   dma-bufs. A Flatpak's or Steam's container shows /dev/udmabuf but not /sys/module */
                FILE *f = fopen("/sys/module/udmabuf/parameters/size_limit_mb", "r");
                if (f)
                    fclose(f);
                else
                    hos_log("mem: udmabuf's size_limit_mb cannot be read (in a container?): its default, 64 MB, assumed");
                usable = 1;
            }
            if (!usable && !e)
                hos_log("mem: guest memory stays host-pointer imports for the GPU (slow submissions on AMD): "
                        "/dev/udmabuf cannot be opened");
        }
        if (e ? atoi(e) != 0 : usable) {
            const int fd = (int)syscall(SYS_memfd_create, "hookshot-guest", 1u /* MFD_CLOEXEC */ | 2u /* MFD_ALLOW_SEALING */);
            if (fd >= 0 && ftruncate(fd, (off_t)GUEST_SPACE) == 0) {
                fcntl(fd, 1033 /* F_ADD_SEALS */, 0x0002 /* F_SEAL_SHRINK */ | 0x0004 /* F_SEAL_GROW */);
                void *p = mmap((void *)A64_HOST_BASE, GUEST_SPACE, PROT_READ | PROT_WRITE,
                               MAP_SHARED | MAP_FIXED_NOREPLACE | MAP_NORESERVE, fd, 0);
                if (p == (void *)A64_HOST_BASE) {
                    hos_guest_memfd = fd;
                    hos_log("mem: the guest window is a memfd's (%d), shared with the GPU as dma-bufs", fd);
                    return 1;
                }
                if (p != MAP_FAILED) munmap(p, GUEST_SPACE);
            }
            if (fd >= 0) close(fd);
            hos_log("mem: no memfd for the guest window (errno %d): anonymous memory", errno);
        }
    }
    if (mmap((void *)A64_HOST_BASE, GUEST_SPACE, PROT_READ | PROT_WRITE,
             MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE | MAP_NORESERVE, -1, 0) != (void *)A64_HOST_BASE)
        return 0;
    /* (issue 312) no transparent huge pages in the guest window: the renderer imports its pools as userptr memory, and every
       collapse khugepaged makes in them changes their mappings, which the kernel answers by pinning the pages again at the
       next submission: ~250 ms a submit on RADV while the GPU sat idle. HOS_THP=1: as before */
    if (!env_on("HOS_THP")) madvise((void *)A64_HOST_BASE, GUEST_SPACE, MADV_NOHUGEPAGE);
#ifdef __linux__
    /* (HOS_NO_THP=1, experiment: none outside the window either. With THP "always" 400-450 MB of the host heap's and the binary's bss are huge
       pages, each resident whole when any of its 2 MB is touched) */
    if (env_on("HOS_NO_THP")) prctl(PR_SET_THP_DISABLE, 1, 0, 0, 0);
#endif
    return 1;
#endif
}

#if !defined(_WIN32) && !defined(A64_MEM_ZERO)
/* the guest window's memfd for the Vulkan back end (-1: anonymous memory), and freeing guest pages so that
   they read as zero again on either kind of mapping */
int hos_guest_memfd = -1;
int hos_posix_guest_memfd(void) { return hos_guest_memfd; }
int hos_posix_guest_discard(void *p, size_t n) {
    return madvise(p, n, hos_guest_memfd >= 0 ? MADV_REMOVE : MADV_DONTNEED);
}
#endif

/* The guest window, for the renderer (MkwVkHost.guest_base and guest_size, host/rx_backend.c). */
uint8_t *hos_guest_base(void) { return A64_MEM; }
uint64_t hos_guest_size(void) { return GUEST_SPACE; }

/* Call guest code at `addr` as a fresh call from the top of the main thread's stack, with whatever arguments the
   caller put in x0-x7 (call_guest clears x0 and x1 first; call_guest_args keeps them). */
static void call_guest_args(Ctx *c, uint64_t addr, uint64_t sp, const char *what) {
    A64Fn f = a64_lookup(addr);
    if (!addr || !f) hos_fatal(c, "%s: no function at %#llx", what, (unsigned long long)addr);
    hos_log("boot: %s (%#llx)", what, (unsigned long long)addr);
    c->x[30] = 0;
    c->x[31] = sp;
    void hos_mem_checkpoint(const char *what);
    hos_mem_checkpoint(what);
    f(c);
}
static void call_guest(Ctx *c, uint64_t addr, uint64_t sp, const char *what) {
    c->x[0] = c->x[1] = 0;
    call_guest_args(c, addr, sp, what);
}

#ifndef _WIN32
/* (linux) Saves live in $XDG_DATA_HOME/hookshot (~/.local/share/hookshot), so a rebuilt game folder still finds them.
   A user/ folder beside the executable from before is moved there the first time, entry by entry. Anything that
   cannot be moved keeps the old place. --user still wins.
   A symbolic link in it, to saves the player keeps elsewhere (a synced folder, another drive), is made again in the
   new place, to the same folder, and never entered. It was moved as it stood, and one written from where it stood
   ("../../saves") then named nothing; from another drive it was copied as the folder it names and delete_tree emptied
   that folder, which is not Hookshot's: the next start found the link still here, kept the old place, and showed no
   saves. A user/ that is a link itself is the player's choice of place, and is used as it is. */
static int is_dir(const char *p) {
    const DWORD a = GetFileAttributesA(p);
    return a != INVALID_FILE_ATTRIBUTES && (a & FILE_ATTRIBUTE_DIRECTORY);
}
static int is_link(const char *p) {
    struct stat st;
    return lstat(p, &st) == 0 && S_ISLNK(st.st_mode);
}
static const char *move_old, *move_from, *move_new;   /* (the user folder on the move, as realpath names it and as given, and the new place) */
static int moved_to(char *target, const char *dir) {   /* (a target under dir: named where it will be) */
    char there[MAX_PATH];
    const size_t n = dir && dir[0] == SEP ? strlen(dir) : 0;
    if (!n || strncmp(target, dir, n) || target[n] != SEP) return 0;
    snprintf(there, sizeof there, "%s%s", move_new, target + n);
    snprintf(target, MAX_PATH, "%s", there);
    return 1;
}
static int copy_link(const char *from, const char *to) {   /* (to what it names, in full; one that names nothing: as written) */
    char target[MAX_PATH];
    if (!realpath(from, target)) {
        const ssize_t n = readlink(from, target, sizeof target - 1);
        if (n < 0) return 0;
        target[n] = 0;
    }
    /* (to an entry that moves too: where it will be. One whose entry went first names nothing by now, so its text is
       checked too: else it named the old place, and only when the folder listed it before the entry) */
    if (!moved_to(target, move_old)) moved_to(target, move_from);
    return symlink(target, to) == 0;
}
static int has_link(const char *p) {
    if (is_link(p)) return 1;
    if (!is_dir(p)) return 0;
    char pattern[MAX_PATH];
    snprintf(pattern, sizeof pattern, "%s" SEP_S "*", p);
    WIN32_FIND_DATAA fd;
    HANDLE h = FindFirstFileA(pattern, &fd);
    int found = 0;
    if (h != INVALID_HANDLE_VALUE) {
        do {
            if (!strcmp(fd.cFileName, ".") || !strcmp(fd.cFileName, "..")) continue;
            char a[MAX_PATH];
            snprintf(a, sizeof a, "%s" SEP_S "%s", p, fd.cFileName);
            found = has_link(a);
        } while (!found && FindNextFileA(h, &fd));
        FindClose(h);
    }
    return found;
}
static int copy_tree(const char *from, const char *to) {
    if (is_link(from)) return copy_link(from, to);
    if (!is_dir(from)) {
        return hos_atomic_copy_file(from, to);   /* (each file whole under its name, or not there) */
    }
    if (!CreateDirectoryA(to, NULL) && !is_dir(to)) return 0;
    char pattern[MAX_PATH];
    snprintf(pattern, sizeof pattern, "%s" SEP_S "*", from);
    WIN32_FIND_DATAA fd;
    HANDLE h = FindFirstFileA(pattern, &fd);
    int ok = 1;
    if (h != INVALID_HANDLE_VALUE) {
        do {
            if (!strcmp(fd.cFileName, ".") || !strcmp(fd.cFileName, "..")) continue;
            char a[MAX_PATH], b[MAX_PATH];
            snprintf(a, sizeof a, "%s" SEP_S "%s", from, fd.cFileName);
            snprintf(b, sizeof b, "%s" SEP_S "%s", to, fd.cFileName);
            ok = copy_tree(a, b);
        } while (ok && FindNextFileA(h, &fd));
        FindClose(h);
    }
    return ok;
}
static void delete_tree(const char *p) {
    if (!is_dir(p) || is_link(p)) {   /* (a link goes; what it names stays) */
        DeleteFileA(p);
        return;
    }
    char pattern[MAX_PATH];
    snprintf(pattern, sizeof pattern, "%s" SEP_S "*", p);
    WIN32_FIND_DATAA fd;
    HANDLE h = FindFirstFileA(pattern, &fd);
    if (h != INVALID_HANDLE_VALUE) {
        do {
            if (!strcmp(fd.cFileName, ".") || !strcmp(fd.cFileName, "..")) continue;
            char a[MAX_PATH];
            snprintf(a, sizeof a, "%s" SEP_S "%s", p, fd.cFileName);
            delete_tree(a);
        } while (FindNextFileA(h, &fd));
        FindClose(h);
    }
    RemoveDirectoryA(p);
}
static const char *saves_dir(const char *beside) {
    static char dir[MAX_PATH];
    const char *xdg = getenv("XDG_DATA_HOME"), *home = getenv("HOME");
    if (is_link(beside)) return beside;
    if (xdg && xdg[0] == '/') snprintf(dir, sizeof dir, "%s", xdg);
    else if (home && home[0] == '/') {
        snprintf(dir, sizeof dir, "%s/.local", home);
        CreateDirectoryA(dir, NULL);
        snprintf(dir, sizeof dir, "%s/.local/share", home);
    } else return beside;
    CreateDirectoryA(dir, NULL);
    snprintf(dir + strlen(dir), sizeof dir - strlen(dir), "/hookshot");
    CreateDirectoryA(dir, NULL);
    if (GetFileAttributesA(dir) == INVALID_FILE_ATTRIBUTES) return beside;
    char pattern[MAX_PATH];
    snprintf(pattern, sizeof pattern, "%s" SEP_S "*", beside);
    int moved = 0, kept = 0;
    char real[MAX_PATH];
    move_old = realpath(beside, real), move_from = beside, move_new = dir;
    /* (looked at first, then moved: with an entry the new place has already, the old place is kept, and it keeps them all.
       The others used to go all the same, and the game then ran here without them. So does one that cannot go, a copy that
       fails (a full disk): the entries that went before it come back, and a copied one's old place goes only once all are
       there. They used to stay in the new place, and the next start found them there and kept the old place without them) */
    struct { char *name; int copied; } *went = NULL;
    size_t n_went = 0;
    for (int move = 0; move < 2 && !kept; move++) {
        WIN32_FIND_DATAA fd;
        HANDLE h = FindFirstFileA(pattern, &fd);
        if (h == INVALID_HANDLE_VALUE) return dir;
        do {
            if (!strcmp(fd.cFileName, ".") || !strcmp(fd.cFileName, "..") || (move && kept)) continue;
            char from[MAX_PATH], to[MAX_PATH];
            snprintf(from, sizeof from, "%s" SEP_S "%s", beside, fd.cFileName);
            snprintf(to, sizeof to, "%s" SEP_S "%s", dir, fd.cFileName);
            if (!move) {
                kept += GetFileAttributesA(to) != INVALID_FILE_ATTRIBUTES;
                continue;
            }
            void *more = realloc(went, (n_went + 1) * sizeof *went);
            char *name = more ? _strdup(fd.cFileName) : NULL;
            if (more) went = more;
            if (!name) kept++;
            else if (!has_link(from) && MoveFileExA(from, to, 0)) went[n_went].name = name, went[n_went++].copied = 0;
            else if (copy_tree(from, to)) went[n_went].name = name, went[n_went++].copied = 1;
            else delete_tree(to), free(name), kept++;
        } while (FindNextFileA(h, &fd));
        FindClose(h);
    }
    for (size_t i = 0; i < n_went; i++) {
        char from[MAX_PATH], to[MAX_PATH];
        snprintf(from, sizeof from, "%s" SEP_S "%s", beside, went[i].name);
        snprintf(to, sizeof to, "%s" SEP_S "%s", dir, went[i].name);
        if (!kept) {
            moved++;
            if (went[i].copied) delete_tree(from);
        } else if (went[i].copied) delete_tree(to);
        else if (!MoveFileExA(to, from, 0)) hos_log("saves: %s could not come back to %s", to, from);
        free(went[i].name);
    }
    free(went);
    if (kept) {
        hos_log("saves: %d of %s's entries could not go to %s: the saves stay in %s", kept, beside, dir, beside);
        return beside;
    }
    RemoveDirectoryA(beside);
    if (moved) {
        char note[MAX_PATH];
        const char *sep = strrchr(beside, SEP);
        snprintf(note, sizeof note, "%.*s" SEP_S "saves-moved.txt", sep ? (int)(sep - beside) : 0, beside);
        char text[MAX_PATH + 160];
        const int n = snprintf(text, sizeof text, "Willow Woods's saves are now in\n%s\n\nThey moved there from the user folder that was here.\n", dir);
        if (n > 0 && (size_t)n < sizeof text) hos_atomic_write(note, text, (size_t)n);
        hos_log("saves: moved from %s to %s", beside, dir);
    }
    return dir;
}
#endif

#ifdef _WIN32
/* (sharkiix version) "SAVE FOLDER" beside the game: a save dropped there (from Eden, Lichii, Ryujinx, a Switch, another
   Hookshot: the folder holding slot_00, slot_01 ... and account.sav, or a folder above it, at any depth) is copied into
   the game's saves at the start. The saves there before are kept in SAVE FOLDER\_backup <date>, what was imported goes to
   SAVE FOLDER\_imported <date>, and a message says so. option.sav (the game's settings) is not taken.
   HOS_NO_SAVE_FOLDER=1: off */
static int sf_is_dir(const char *p) {
    const DWORD a = GetFileAttributesA(p);
    return a != INVALID_FILE_ATTRIBUTES && (a & FILE_ATTRIBUTE_DIRECTORY);
}
static int sf_copy(const char *from, const char *to) {
    if (!sf_is_dir(from)) return CopyFileA(from, to, FALSE) != 0;
    if (!CreateDirectoryA(to, NULL) && !sf_is_dir(to)) return 0;
    char pattern[MAX_PATH];
    snprintf(pattern, sizeof pattern, "%s\\*", from);
    WIN32_FIND_DATAA fd;
    HANDLE h = FindFirstFileA(pattern, &fd);
    int ok = 1;
    if (h != INVALID_HANDLE_VALUE) {
        do {
            if (!strcmp(fd.cFileName, ".") || !strcmp(fd.cFileName, "..")) continue;
            char a[MAX_PATH], b[MAX_PATH];
            snprintf(a, sizeof a, "%s\\%s", from, fd.cFileName);
            snprintf(b, sizeof b, "%s\\%s", to, fd.cFileName);
            ok = sf_copy(a, b);
        } while (ok && FindNextFileA(h, &fd));
        FindClose(h);
    }
    return ok;
}
/* a folder holding slot_XX folders with a progress.sav in them */
const char *hos_save_dir(void);   /* (Mako) master_quest.c: "save", or "save_mq" in Master Quest */
static int sf_is_save_root(const char *dir) {
    char pattern[MAX_PATH];
    snprintf(pattern, sizeof pattern, "%s\\slot_*", dir);
    WIN32_FIND_DATAA fd;
    HANDLE h = FindFirstFileA(pattern, &fd);
    int found = 0;
    if (h == INVALID_HANDLE_VALUE) return 0;
    do {
        char p[MAX_PATH];
        snprintf(p, sizeof p, "%s\\%s\\progress.sav", dir, fd.cFileName);
        if ((fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) && GetFileAttributesA(p) != INVALID_FILE_ATTRIBUTES) found = 1;
    } while (!found && FindNextFileA(h, &fd));
    FindClose(h);
    return found;
}
static int sf_find(const char *dir, char *out, int depth, int top) {
    if (sf_is_save_root(dir)) {
        snprintf(out, MAX_PATH, "%s", dir);
        return 1;
    }
    if (depth <= 0) return 0;
    char pattern[MAX_PATH];
    snprintf(pattern, sizeof pattern, "%s\\*", dir);
    WIN32_FIND_DATAA fd;
    HANDLE h = FindFirstFileA(pattern, &fd);
    if (h == INVALID_HANDLE_VALUE) return 0;
    int found = 0;
    do {
        if (!(fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) || fd.cFileName[0] == '.') continue;
        if (top && fd.cFileName[0] == '_') continue;   /* (_backup, _imported: ours) */
        char sub[MAX_PATH];
        snprintf(sub, sizeof sub, "%s\\%s", dir, fd.cFileName);
        found = sf_find(sub, out, depth - 1, 0);
    } while (!found && FindNextFileA(h, &fd));
    FindClose(h);
    return found;
}
static void save_folder_import(const char *game_dir, const char *user_dir) {
    char sf[MAX_PATH], note[MAX_PATH], root[MAX_PATH];
    snprintf(sf, sizeof sf, "%s\\SAVE FOLDER", game_dir);
    CreateDirectoryA(sf, NULL);
    snprintf(note, sizeof note, "%s\\LISEZ-MOI - READ ME.txt", sf);
    if (GetFileAttributesA(note) == INVALID_FILE_ATTRIBUTES) {
        FILE *f = fopen(note, "w");
        if (f) {
            fprintf(f,
                "=== SAVE FOLDER (Willow Woods) ===\n\n"
                "FRANCAIS\n"
                "Pour jouer avec ta sauvegarde, glisse-la dans ce dossier puis lance le jeu.\n"
                "Ca marche avec une sauvegarde d'Eden, Lichii, Ryujinx, d'une Switch ou d'un autre Hookshot :\n"
                "mets le dossier qui contient slot_00, slot_01... et account.sav (par exemple le dossier\n"
                "0400486024DEC000 d'un emulateur), ou directement son contenu.\n"
                "Au lancement, le jeu l'importe tout seul et affiche un message.\n"
                "Tes anciennes sauvegardes sont gardees dans \"_backup <date>\", rien n'est perdu.\n"
                "Ce que tu as importe est range dans \"_imported <date>\".\n\n"
                "ENGLISH\n"
                "To play with your save, drop it into this folder, then start the game.\n"
                "Works with a save from Eden, Lichii, Ryujinx, a Switch or another Hookshot:\n"
                "put the folder holding slot_00, slot_01... and account.sav (for example an emulator's\n"
                "0400486024DEC000 folder), or just its contents.\n"
                "At start the game imports it by itself and shows a message.\n"
                "Your previous saves are kept in \"_backup <date>\": nothing is lost.\n"
                "What was imported is moved to \"_imported <date>\".\n");
            fclose(f);
        }
    }
    if (!sf_find(sf, root, 6, 1)) return;
    SYSTEMTIME t;
    GetLocalTime(&t);
    char stamp[64], target[MAX_PATH], backup[MAX_PATH], done[MAX_PATH];
    snprintf(stamp, sizeof stamp, "%04d-%02d-%02d %02dh%02d-%02d", t.wYear, t.wMonth, t.wDay, t.wHour, t.wMinute, t.wSecond);
    CreateDirectoryA(user_dir, NULL);
    /* (into the saves this start plays with: the randomizer's own folder while it is on, oot_rando.c) */
    const char *hos_save_folder(void);
    snprintf(target, sizeof target, "%s\\%s", user_dir, hos_save_folder());
    CreateDirectoryA(target, NULL);
    snprintf(target, sizeof target, "%s\\%s\\5a3c9e1f0b7d24680000000000000001", user_dir, hos_save_folder());
    snprintf(backup, sizeof backup, "%s\\_backup %s", sf, stamp);
    if (sf_is_dir(target) && !sf_copy(target, backup)) {
        hos_log("save folder: the saves could not be backed up into %s: nothing imported", backup);
        MessageBoxA(NULL, "SAVE FOLDER: the current saves could not be backed up, so nothing was imported.\n"
                          "SAVE FOLDER : les sauvegardes actuelles n'ont pas pu etre copiees, rien n'a ete importe.",
                    HOS_GAME_TITLE, MB_OK | MB_ICONWARNING | MB_TOPMOST);
        return;
    }
    CreateDirectoryA(target, NULL);
    int slots = 0, ok = 1;
    char pattern[MAX_PATH];
    snprintf(pattern, sizeof pattern, "%s\\*", root);
    WIN32_FIND_DATAA fd;
    HANDLE h = FindFirstFileA(pattern, &fd);
    if (h != INVALID_HANDLE_VALUE) {
        do {
            if (!strcmp(fd.cFileName, ".") || !strcmp(fd.cFileName, "..")) continue;
            const int slot = (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) && !strncmp(fd.cFileName, "slot_", 5);
            if (!slot && _stricmp(fd.cFileName, "account.sav")) continue;   /* (option.sav: the game's own settings stay) */
            char a[MAX_PATH], b[MAX_PATH];
            snprintf(a, sizeof a, "%s\\%s", root, fd.cFileName);
            snprintf(b, sizeof b, "%s\\%s", target, fd.cFileName);
            if (!sf_copy(a, b)) ok = 0;
            else slots += slot;
        } while (FindNextFileA(h, &fd));
        FindClose(h);
    }
    /* what was imported: everything in SAVE FOLDER but ours, moved aside so the next start does not import it again */
    snprintf(done, sizeof done, "%s\\_imported %s", sf, stamp);
    CreateDirectoryA(done, NULL);
    snprintf(pattern, sizeof pattern, "%s\\*", sf);
    h = FindFirstFileA(pattern, &fd);
    if (h != INVALID_HANDLE_VALUE) {
        do {
            if (!strcmp(fd.cFileName, ".") || !strcmp(fd.cFileName, "..") || fd.cFileName[0] == '_' ||
                !_stricmp(fd.cFileName, "LISEZ-MOI - READ ME.txt"))
                continue;
            char a[MAX_PATH], b[MAX_PATH];
            snprintf(a, sizeof a, "%s\\%s", sf, fd.cFileName);
            snprintf(b, sizeof b, "%s\\%s", done, fd.cFileName);
            MoveFileExA(a, b, 0);
        } while (FindNextFileA(h, &fd));
        FindClose(h);
    }
    hos_log("save folder: %d slots imported from %s (%s), the saves before kept in %s", slots, root,
            ok ? "all copied" : "some failed", backup);
    char msg[1600];
    snprintf(msg, sizeof msg,
             "SAVE FOLDER: %d save slot(s) imported%s.\nYour previous saves are kept in:\n%s\n\n"
             "SAVE FOLDER : %d emplacement(s) de sauvegarde importe(s)%s.\nTes anciennes sauvegardes sont gardees dans :\n%s",
             slots, ok ? "" : " (some files failed)", backup, slots, ok ? "" : " (certains fichiers ont echoue)", backup);
    MessageBoxA(NULL, msg, HOS_GAME_TITLE, MB_OK | MB_ICONINFORMATION | MB_TOPMOST | MB_SETFOREGROUND);
}
#endif
/* (hookshot) What a write of a setting that a kill cut left (host/hos_atomic_file.h), at the start, before the game reads any
   setting: a "<name>.hosnew" beside the setting. language.txt is the game folder's; mouse_sens.txt is the user folder's; the
   settings file is where options_path.c chose it (the user folder's with --user, HOS_OPTIONS_FILE's, else the game folder's):
   the options' one-time copy into the user folder leaves its stand-in there. */
static void recover_writes(void) {
    char path[MAX_PATH];
    const DWORD len = hos_game_path_a(path, MAX_PATH);
    char *slash = len ? strrchr(path, SEP) : NULL;
    if (slash) {
        snprintf(slash + 1, (size_t)(path + MAX_PATH - slash - 1), "language.txt");
        hos_atomic_remove_stale(path);
    }
    if (hos_options_file()[0]) hos_atomic_remove_stale(hos_options_file());
    snprintf(path, sizeof path, "%s" SEP_S "mouse_sens.txt", hos_user_dir);
    hos_atomic_remove_stale(path);
}

/* hookshot_env.txt beside the game: NAME=VALUE lines set as environment variables before anything reads them, for the
   switches players are asked to test (RX_VK_NOOPT and the rest). Lines starting with # are notes. On Linux this runs
   before the window, so HOS_HEADLESS and HOS_WINDOW_SIZE are already set when the window is made.
   HOS_ENV_FILE=<path> reads that file instead: a scripted or A/B test run brings its own switches and leaves the
   player's hookshot_env.txt as it is.
   (hookshot) hookshot_env.txt is a file players pass around, so it sets only the game's own switches (RX_, HOS_,
   HOOKSHOT_, EDEN_, NVN_ and SDL_ names), never HOS_ENV_FILE, HOS_CONTROL_PEER_SID or SDL's library override, and no
   value that is a path but RX_VK_DLSS_DIR's: the system's variables (the Vulkan loader's layers, PATH and the like) can
   load code, and the dump switches write files where they name. The file HOS_ENV_FILE names sets anything. */
static int env_line_allowed(const char *name, const char *value) {
    static const char *const prefixes[] = {"RX_", "HOS_", "HOOKSHOT_", "EDEN_", "NVN_", "SDL_"};
    int ok = 0;
    for (size_t i = 0; i < sizeof prefixes / sizeof *prefixes; i++) ok |= !strncmp(name, prefixes[i], strlen(prefixes[i]));
    if (!ok || !strcmp(name, "HOS_ENV_FILE") || !strcmp(name, "SDL_DYNAMIC_API")) return 0;
    /* (hookshot) nor HOS_CONTROL_PEER_SID: it lets one more account into the control bridge's pipe (host/control.c), so a
       shared file would let another user of this PC steer the game and read its memory. The environment still sets it */
    if (!strcmp(name, "HOS_CONTROL_PEER_SID")) return 0;
    /* (hookshot) nor the libraries SDL loads by name (SDL_VULKAN_LIBRARY, SDL_OPENGL_LIBRARY, SDL_VIDEO_GL_DRIVER,
       SDL_VIDEO_EGL_DRIVER...): a bare file name is looked for beside the game and in the current folder on Windows */
    if (!strncmp(name, "SDL_", 4) && (strstr(name, "_LIB") || strstr(name, "GL_DRIVER"))) return 0;
    for (const char *p = name; *p; p++)
        if (!((*p >= 'A' && *p <= 'Z') || (*p >= '0' && *p <= '9') || *p == '_')) return 0;
    /* (hookshot) the switches that name a file to write or a folder take no value here, not even a bare name: one
       resolves in the game's folder (HOS_SAMPLE_FILE=hookshot_vk.dll emptied the renderer) */
    const size_t nl = strlen(name);
    int names_file = (nl > 5 && (!strcmp(name + nl - 5, "_FILE") || !strcmp(name + nl - 4, "_DIR"))) ||
                     !strcmp(name, "RX_VK_FRAME_LOG") || !strcmp(name, "HOS_PRESENT_TRACE");
    /* (hookshot) and the test switches whose value is a file or folder under another name (HOS_AUDIO_DUMP=image.bin
       overwrote the game's image), or that press buttons and menu keys on a timer (a shared file erased a save from
       the file select) */
    static const char *const by_name[] = {
        "HOS_AUDIO_DUMP", "HOS_AUDIO_WB_DUMP", "HOS_SHADER_DUMP", "HOS_FS_OVERLAY", "HOS_MODS", "HOS_INPUT_LIVE",
        "HOS_INPUT_SCRIPT", "HOS_SAMPLE_ALL", "HOS_SLOW_FRAMES", "HOS_CHAIN", "HOS_WATCH", "HOS_CRASH_TEST", "HOOKSHOT_BUILDER_HOME", "RX_VK_SHOTS", "RX_VK_SHOT_GO",
        "RX_VK_FRAMELOG", "RX_VK_HANG_DUMP", "RX_VK_DUMP", "RX_VK_DUMP_SPV", "RX_VK_DUMP_MESH_SPV", "RX_VK_DUMP_STAGES",
        "RX_VK_DUMP_FAILED", "RX_VK_IR", "RX_VK_MENU_SCRIPT", "RX_VK_MENU_LIVE"};
    for (size_t i = 0; i < sizeof by_name / sizeof *by_name; i++) names_file |= !strcmp(name, by_name[i]);
    /* RX_VK_DLSS_DIR: a folder on this PC, not a share (\\server\x or //server/x) or a device path */
    if (!strcmp(name, "RX_VK_DLSS_DIR"))
        return !((value[0] == '\\' || value[0] == '/') && (value[1] == '\\' || value[1] == '/'));
    if (names_file) return 0;
    const int drive = ((value[0] | 0x20) >= 'a' && (value[0] | 0x20) <= 'z' && value[1] == ':');
    return !strpbrk(value, "/\\") && !drive && value[0] != '~' && strcmp(value, ".") && strcmp(value, "..");
}
static void load_hookshot_env(void) {
    char path[MAX_PATH + 32];
    const char *other = getenv("HOS_ENV_FILE");
    if (other && *other) {
        snprintf(path, sizeof path, "%s", other);
    } else {
        DWORD n = hos_game_path_a(path, MAX_PATH);
        while (n && path[n - 1] != 92 && path[n - 1] != 47) n--;
        memcpy(path + n, "hookshot_env.txt", 17);
    }
    FILE *f = fopen(path, "r");
    if (!f) return;
    /* The environment the game was started with wins over the file: a switch set for one launch (HOS_FULLSCREEN=0 in a
       shell, a script's RX_VK_PACE=1) beats the same name saved in the file. The file's own later lines still replace its
       earlier ones: the names it set are kept here (for the whole run: a second read sets them again), so they are not taken
       for the environment's */
    static char from_file[256][128];   /* (names of up to 127 characters; a file with more names than this has its later
                                          lines for the names past it taken as the environment's, logged as left out) */
    static int from_file_n;
    char line[512];
    while (fgets(line, sizeof line, f)) {
        char *s = line;
        if ((unsigned char)s[0] == 0xEF && (unsigned char)s[1] == 0xBB && (unsigned char)s[2] == 0xBF) s += 3;   /* (Notepad's BOM) */
        while (*s == ' ' || *s == 9) s++;
        size_t len = strlen(s);
        while (len && (s[len - 1] == 10 || s[len - 1] == 13 || s[len - 1] == ' ' || s[len - 1] == 9)) s[--len] = 0;
        if (!len || *s == '#' || !strchr(s, '=')) continue;
        char *eq = strchr(s, '=');
        *eq = 0;
        /* ((Triforce v0.8.x) a note after the value ("HOS_AUDIO=0  # mute"): cut at a '#' that follows a space or a tab, and
           the spaces before it, so the note is not read as part of the value: the renderer's switch rule read "0  # mute" as
           on) */
        for (char *v = eq + 1; *v; v++)
            if (*v == '#' && v > eq + 1 && (v[-1] == ' ' || v[-1] == 9)) {
                *v = 0;
                while (v > eq + 1 && (v[-1] == ' ' || v[-1] == 9)) *--v = 0;
                break;
            }
        if (!(other && *other) && !env_line_allowed(s, eq + 1)) {
            fprintf(stderr, "env: hookshot_env.txt: %s left out (only the game's switches, and no paths, are taken from it)\n", s);
            continue;
        }
        int ours = 0;
        for (int i = 0; i < from_file_n && !ours; i++) ours = !strcmp(from_file[i], s);
        if (!ours && getenv(s)) {
            fprintf(stderr, "env: %s: %s left out (set in the environment, which goes first)\n",
                    other && *other ? "HOS_ENV_FILE" : "hookshot_env.txt", s);
            continue;
        }
        if (!ours && from_file_n < (int)(sizeof from_file / sizeof *from_file) && strlen(s) < sizeof from_file[0])
            strcpy(from_file[from_file_n++], s);
#ifdef _WIN32
        *eq = '=';
        _putenv(s);
#else
        setenv(s, eq + 1, 1);
#endif
    }
    fclose(f);
}

/* Switches this build no longer reads, still set (in the environment or hookshot_env.txt, as older issues told players):
   one log line each, naming what took its place, so a bug report shows the switch did nothing. The host's own: the
   renderer's removed switches (RX_) are the GONE rows of gpu/vk/switches.def, said by its start (switches.h) */
static void removed_switch_notes(void) {
    static const char *const gone[][2] = {
        {"HOS_FIX_RES", NULL},
        {"HOS_RECORD_STUTTERS", "HOS_PROFILE=1 (the profiling mode: docs/development.md#the-profiling-mode)"},
        {"HOS_SCENE_NATIVE", NULL},
        {"TOTK_MINIMAL_LAYOUT", NULL},
    };
    for (size_t i = 0; i < sizeof gone / sizeof *gone; i++)
        if (getenv(gone[i][0])) {
            if (gone[i][1]) hos_log("env: %s is no longer read: use %s", gone[i][0], gone[i][1]);
            else hos_log("env: %s is no longer read: it does nothing", gone[i][0]);
        }
}

int hos_oot_protect_hearts;
/* Trace the request before the save manager queues it. */
int hos_oot_trace_save(Ctx *c) {
    int rx_option(int id, int otherwise);
    const uint64_t caller = c->x[30];
    const uint64_t parent = caller == 0x80bc7764ULL ? recomp_load64(c, c->x[31] + 24) : 0;
    if (env_on("HOS_OOT_TRACE_SAVES")) hos_log("save trace: reason=%u mode=%u caller=%#llx request_site=%#llx", (unsigned)c->x[1], (unsigned)c->x[2],
            (unsigned long long)caller, (unsigned long long)(parent ? parent : caller));
    const unsigned reason = (uint32_t)c->x[1];
    /* A crossing can queue both arrival requests in addition to the transition request. */
    const int transition = (parent == 0x80bc7710ULL && reason == 6) ||
        (parent == 0x80bc7864ULL && reason == 2) ||
        (parent == 0x832a9764ULL && reason == 1);
    if (caller == 0x80bc7764ULL && transition &&
        (uint32_t)c->x[2] == 0 && !rx_option(HOS_OPT_TRANSITION_AUTOSAVE, 1)) {
        if (env_on("HOS_OOT_TRACE_SAVES")) hos_log("save trace: transition autosave suppressed");
        c->x[0] = 0;
        return 1;
    }
    return 0;
}

volatile int hos_oot_live_action;   /* (test runs) the live input file's "!cheat <action>": host/nn_hid.c */

int hos_oot_hearts_enabled(void) {
    int rx_option(int id, int otherwise);
    const int menu = rx_option(HOS_OPT_CHEAT_HEARTS, -1);
    return menu < 0 ? hos_oot_protect_hearts : menu;
}

int hos_oot_is_player(Ctx *c, uint64_t actor) {
    if (recomp_load64(c, actor) != 0x84b6c460ULL) return 0;
    // Other actors share this vtable. The actor's resource record identifies Link.
    const uint64_t resource = recomp_load64(c, actor + 16);
    return resource && recomp_load32(c, resource + 88) == 0x79616c50 &&
           recomp_load16(c, resource + 92) == 0x7265 &&
           recomp_load8(c, resource + 94) == 0;
}

/* Damage numbers (asked 2026-11-23, share/damage-values.md): every life loss at the life component's write (nx2/oot_patches.py
   patch_life_hits: the actor, its old and new life, and the whole hit before it was clamped at 0), kept in a small ring the
   overlay reads (hos_oot_hits), Link's own losses left out. HOS_OOT_DAMAGE_LOG=1 logs each: "damage: <actor> took <hit>
   (<old> -> <new>)". The actor's name is its resource record's (+16, then +88), as hos_oot_is_player reads it. */
#define OOT_HITS 32
static float oot_load_float(Ctx *c, uint64_t addr);
/* (the number's place: OOT_DAMAGE_ABOVE metres over the actor's own place, [actor +0x18] +0x31c, the same +0x31c as Link's
   own; found headless on a Deku Baba, 2026-11-23: its map placement 2.9 100 -6.6 there) */
#define OOT_DAMAGE_ABOVE 1.2f

/* A point of the world on the screen, by the gameplay camera's view (oot_gameplay_view: its 3x4 view matrix at +8, rows
   right, up and back with the translation last; +0x128 the near distance, +0x13c the tangent of half the vertical field
   of view, +0x140 the picture's width over its height: 0.1, tan 25 degrees, 1.778 as read headless 2026-11-23): x and y
   each from 0 to 32767 across the game's picture (left to right, top to bottom), as (y << 15) | x; -1 when the point is
   behind the camera or the camera is not there. */
static uint64_t oot_gameplay_view(Ctx *c);
static int oot_damage_screen(Ctx *c, const float p[3]) {
    const uint64_t view = oot_gameplay_view(c);
    if (!view || recomp_load64(c, view) != 0x84c18a88ULL) return -1;
    float m[12];
    for (int i = 0; i < 12; i++) m[i] = oot_load_float(c, view + 8 + 4 * i);
    const float cx = m[0] * p[0] + m[1] * p[1] + m[2] * p[2] + m[3];
    const float cy = m[4] * p[0] + m[5] * p[1] + m[6] * p[2] + m[7];
    const float cz = m[8] * p[0] + m[9] * p[1] + m[10] * p[2] + m[11];
    const float znear = oot_load_float(c, view + 0x128), tan_half = oot_load_float(c, view + 0x13c), aspect = oot_load_float(c, view + 0x140);
    if (!(znear > 0 && tan_half > 0.01f && aspect > 0.1f) || !(-cz > znear)) return -1;
    const float nx = cx / (-cz * tan_half * aspect), ny = cy / (-cz * tan_half);
    if (!(fabsf(nx) <= 1.2f && fabsf(ny) <= 1.2f)) return -1;   /* (off the picture: the middle of the screen instead) */
    const int x = (int)((fminf(fmaxf(nx, -1), 1) * 0.5f + 0.5f) * 32767), y = (int)((0.5f - fminf(fmaxf(ny, -1), 1) * 0.5f) * 32767);
    return y << 15 | x;
}
static struct { uint64_t actor; int64_t at_ns; uint32_t hit, old, next; char name[48]; } oot_hits[OOT_HITS];
static volatile uint32_t oot_hit_count;   /* (how many were ever kept: the newest is at (count - 1) % OOT_HITS) */

static void oot_health_hit(Ctx *c, uint64_t actor, uint64_t life, uint32_t old, uint32_t next, const char *name);

/* Only enemies and bosses get a number and a health bar (bug 134, the owner 2026-11-24: a pot hit and a rock blown up with a
   bomb showed one, as every actor with a life loses it at the same write). Every enemy and boss of the game is an Enemy_ actor
   (Enemy_Stalfos, Enemy_DungeonBoss_Gohma, Enemy_MiddleBoss_DarkLink, the Gold Skulltulas' Enemy_Skulltula_Gold); pots,
   rocks, grass, signs and animals are Obj_, Land_, FldObj_, Animal_ and the like. */
static int oot_hit_is_enemy(const char *name) {
    return strncmp(name, "Enemy_", 6) == 0;
}

void hos_oot_hit(Ctx *c, uint64_t actor, uint32_t old, uint32_t next, uint32_t hit, uint64_t life) {
    if (!actor || hos_oot_is_player(c, actor)) return;
    /* (the name: the actor's resource record's, at its +88, as hos_oot_is_player reads "Player"; +0x260 named no Deku Baba) */
    const uint64_t resource = recomp_load64(c, actor + 16);
    char text[48] = {0};
    for (int i = 0; resource && i < (int)sizeof text - 1; i++) {
        text[i] = (char)recomp_load8(c, resource + 88 + (unsigned)i);
        if (!text[i]) break;
    }
    static int log = -1;
    if (log < 0) log = env_on("HOS_OOT_DAMAGE_LOG");
    if (!oot_hit_is_enemy(text)) {
        if (log) hos_log("damage: %s took %u (%u -> %u), not an enemy: no number", text[0] ? text : "?", hit, old, next);
        return;
    }
    const uint32_t n = __atomic_load_n(&oot_hit_count, __ATOMIC_RELAXED);
    __typeof__(oot_hits[0]) *h = &oot_hits[n % OOT_HITS];
    h->actor = actor, h->at_ns = hos_now_ns(), h->hit = hit, h->old = old, h->next = next;
    memcpy(h->name, text, sizeof h->name);
    __atomic_store_n(&oot_hit_count, n + 1, __ATOMIC_RELEASE);
    if (log) hos_log("damage: %s took %u (%u -> %u)", text[0] ? text : "?", hit, old, next);
    /* (where on the screen: the actor's place, a little above it, through the gameplay camera, oot_damage_screen) */
    float place[3];
    const uint64_t body = recomp_load64(c, actor + 0x18);
    for (int i = 0; i < 3; i++) place[i] = body ? oot_load_float(c, body + 0x31c + 4 * i) : 0;
    place[1] += OOT_DAMAGE_ABOVE;
    const int at = body ? oot_damage_screen(c, place) : -1;
    if (log) hos_log("damage: at %.2f %.2f %.2f, the screen's %d", place[0], place[1], place[2], at);
    oot_health_hit(c, actor, life, old, next, text);   /* (the Health bars row's) */
    void rx_option_set(int id, int value);
    rx_option_set(OOT_DAMAGE_AT, at);   /* (the renderer's Damage numbers row: where, then the hit) */
    rx_option_set(OOT_DAMAGE_HIT, (int)(hit > 0xffff ? 0xffff : hit) | (next == 0) << 16);
}

/* Movement speed (the Debug tab's row): Link's character controller and the row's percent, as oot_player_speed saw them on
   his last update (0: none, or 1x) */
static uint64_t oot_speed_controller;
static uint64_t oot_link_controller;   /* (Link's, whatever the speed: Link crawls faster, hos_oot_cct_speed) */
static int oot_speed_percent = 100;

/* A character controller's forward speed being set (nx2/oot_patches.py patch_cct_speed: s0, in metres a second, or a frame when
   per_second is 0): Link's scaled by the row while it is above 1x and the player steers him (a scene's walk, as the one into a
   map, keeps its pace), the physics step moving him by it with its collisions. Only speeds up to 15 m/s (his run is 4.5): a ledge
   climb sets some 55 for a frame, and scaled it threw him past the ledge. Every other controller as it is. */
/* (Link crawls faster, rando_fast_crawl, asked 2026-11-23) A crawl's forward speed comes through f_809552f0 called from the
   crawl's own step (the return address OOT_CRAWL_CALLER), 0.025 m a frame, seen without a window 2026-11-24 in Kokiri
   Forest's crawlspace (a walk's comes from 0x827f38e0). With the setting on it is made OOT_CRAWL_FASTER times as much; the
   crawl's animation keeps its pace. */
#define OOT_CRAWL_CALLER 0x82e98270ULL
#define OOT_CRAWL_FASTER 2.0f
void hos_oot_cct_speed(Ctx *c, uint64_t controller, int per_second) {
    int hos_rando_fast_crawl(void);   /* host/oot_rando.c */
    if (!per_second && c->x[30] == OOT_CRAWL_CALLER && controller && controller == __atomic_load_n(&oot_link_controller, __ATOMIC_RELAXED) &&
        hos_rando_fast_crawl()) {
        float crawl;
        memcpy(&crawl, &c->vreg[0][0], sizeof crawl);
        if (fabsf(crawl) <= 0.1f) {   /* (a crawl's pace, and not NaN) */
            crawl *= OOT_CRAWL_FASTER;
            memcpy(&c->vreg[0][0], &crawl, sizeof crawl);
        }
        return;
    }
    if (!controller || controller != __atomic_load_n(&oot_speed_controller, __ATOMIC_RELAXED)) return;
    const int percent = __atomic_load_n(&oot_speed_percent, __ATOMIC_RELAXED);
    int hos_move_stick_held(void);   /* host/nn_hid.c */
    if (percent <= 100 || percent > 400 || !hos_move_stick_held()) return;
    float speed;
    memcpy(&speed, &c->vreg[0][0], sizeof speed);
    if (!(fabsf(speed) * (per_second ? 1.0f : 60.0f) <= 15.0f)) return;   /* (and NaN) */
    speed *= percent / 100.0f;
    memcpy(&c->vreg[0][0], &speed, sizeof speed);
}

#if defined(_WIN32) || defined(__linux__)   /* (the debug tools: host/posix has what they call) */
/* OneShotAddOrRemovePouchContent (f_828d4a70) for one pouch content by actor name: delta > 0 adds, < 0 removes.
   Returns the event status (top bits of the result word), or -1 when the pouch is not ready. */
static int oot_pouch_change(Ctx *c, const char *name, int delta) {
    const uint64_t pouch_singleton = recomp_load64(c, 0x84c9e0d0ULL);
    const uint64_t state_singleton = recomp_load64(c, 0x84c9e2a8ULL);
    const uint64_t actor_db = recomp_load64(c, 0x84eb6888ULL);
    const uint64_t actor_info = recomp_load64(c, 0x84e8c060ULL);
    A64Fn edit = a64_lookup(0x828d4a70ULL);
    if (!edit || !pouch_singleton || !recomp_load64(c, pouch_singleton) ||
        !state_singleton || !recomp_load64(c, state_singleton) || !actor_db || !actor_info || !delta ||
        strlen(name) >= 0x60) return -1;

    // OneShotAddOrRemovePouchContent reads the event parameters through pointers.
    const Ctx saved = *c;
    const uint64_t event = (c->x[31] - 0xe0) & ~0xfULL;
    memset(A64_PTR(event), 0, 0xe0);
    memcpy(A64_PTR(event + 0x80), name, strlen(name) + 1);
    recomp_store64_sp(c, event + 0x20, event + 0x60);
    recomp_store64_sp(c, event + 0x30, event + 0x70);
    recomp_store64_sp(c, event + 0x38, event + 0x68);
    recomp_store64_sp(c, event + 0x48, event + 0x74);
    recomp_store64_sp(c, event + 0x50, event + 0x74);
    recomp_store64_sp(c, event + 0x60, event + 0x80);
    recomp_store64_sp(c, event + 0x68, 0x83f0a6d8ULL); // Script
    recomp_store32_sp(c, event + 0x70, (uint32_t)delta);
    c->x[31] = event;
    c->x[0] = event;
    edit(c);
    const int result = (int)(recomp_load32(c, event + 0x18) >> 30);
    *c = saved;
    return result;
}

/* QueryGetPouchContentNumByActorName (f_82a3c260): f_805b63e0(pouch manager, &name, 0, 0) counts one content. */
static int oot_pouch_count(Ctx *c, const char *name) {
    const uint64_t manager = recomp_load64(c, 0x84e98e28ULL);
    A64Fn count = a64_lookup(0x805b63e0ULL);
    if (!manager || !count || strlen(name) >= 0x60) return -1;
    const Ctx saved = *c;
    const uint64_t frame = (c->x[31] - 0x80) & ~0xfULL;
    memcpy(A64_PTR(frame + 0x10), name, strlen(name) + 1);
    recomp_store64_sp(c, frame, frame + 0x10);
    c->x[31] = frame;
    c->x[0] = manager, c->x[1] = frame, c->x[2] = 0, c->x[3] = 0;
    count(c);
    const int n = (int)(int32_t)c->x[0];
    *c = saved;
    return n;
}

static void oot_edit_pouch(Ctx *c, int action) {
    static const char *const items[] = {
        "Item_DekuSeed", "Item_DekuNut", "Item_DekuStick", "Item_Bomb", "Item_Arrow_Normal"
    };
    const unsigned item = (unsigned)(action - 200) / 32;
    const int delta = (action - 200) % 32 - 10;
    if (item >= sizeof items / sizeof items[0] || !delta || delta < -10 || delta > 10) return;
    const int result = oot_pouch_change(c, items[item], delta);
    if (result >= 0) hos_log("cheats: pouch %s %+d (event status %d)", items[item], delta, result);
}

/* The Inventory page (gpu/vk/oot_cheat_items.h): counts go to the menu twice a second, edits come back as actions. */
#define OOT_ITEM_NAME(label, name, kind) name,
#define OOT_ITEM_KIND(label, name, kind) kind,
#define OOT_NO_SECTION(name)
static const char *const oot_item_names[] = {OOT_CHEAT_ITEMS(OOT_NO_SECTION, OOT_ITEM_NAME)};
static const unsigned char oot_item_kinds[] = {OOT_CHEAT_ITEMS(OOT_NO_SECTION, OOT_ITEM_KIND)};
#define OOT_ITEM_COUNT (sizeof oot_item_names / sizeof oot_item_names[0])

static int oot_item_count(Ctx *c, const char *name);
static int oot_gamedata_int(Ctx *c, uint32_t hash, int32_t *value, int set);
static int oot_gamedata_bool(Ctx *c, uint32_t hash, int *value);
static uint32_t oot_flag_hash(const char *s);
static int oot_gamedata_set_bool(Ctx *c, uint32_t hash, int value);
static void oot_magic_fill_tick(Ctx *c);   /* (a magic found: its meter filled, below) */
static void oot_infinite_magic(Ctx *c);    /* (the Debug tab's Infinite magic, below) */
static int oot_gamedata_string(Ctx *c, uint32_t hash, char *buf, size_t size);
static int oot_event_playing(Ctx *c);

/* The first adult night's time lock (Longshot d0b9c543, their #1064): f_8347c020 holds the clock at 20:00 while the saved
   Bool HrlField_isFirstNightTime_Adult (0x8592aa82) is 1 and quest 0x4dbca27f is not Ready. The flag belongs to Hyrule
   Field's first night only; a save in any other map that still holds it cannot leave night. This clears it there with the
   game's own Bool, once, and says so, never in Hyrule Field nor while an event (the escape's cutscene) is running.
   (Willow Woods) OFF unless HOS_OOT_FIRST_NIGHT_FIX=1: the same Bool also picks a town's arrival time (20:00 rather than
   00:00, rekarina-2026-11-22.md) and gates Hyrule Field's first-night event, beside the randomizer's own clock work
   (bugs 58, 81), and no run of ours has been stuck at night: the owner decides. Returns 1 when it cleared the flag. */
static int oot_first_night_fix(Ctx *c, const char *map) {
    static int on = -1;
    if (on < 0) on = env_on("HOS_OOT_FIRST_NIGHT_FIX");
    if (!on || !map[0] || !strncmp(map, "HyruleField", 11) || oot_event_playing(c)) return 0;
    int set = 0;
    if (!oot_gamedata_bool(c, 0x8592aa82u, &set) || !set) return 0;
    if (!oot_gamedata_set_bool(c, 0x8592aa82u, 0)) return 0;
    hos_log("oot: cleared the first adult night's time lock (the save was in %s, outside Hyrule Field)", map);
    return 1;
}

static void oot_family_levels_refresh(Ctx *c);   /* (below: the shelves of a family, hos_oot_shelf_map) */
static void oot_inventory_refresh(Ctx *c, int64_t now) {
    void rx_option_set(int id, int value);
    static int64_t next;
    static int probed;
    if (now < next) return;
    next = now + 500000000LL;
    int loaded = 0;   /* (a save's counts read: the first item's is not -1) */
    for (unsigned i = 0; i < OOT_ITEM_COUNT; i++) {
        const int count = oot_item_count(c, oot_item_names[i]);
        if (!i) loaded = count >= 0;
        rx_option_set(OOT_CHEAT_ITEM_BASE + (int)i, count);
    }
    {   /* (Willow Woods, asked 2026-11-26) each dungeon's small keys in hand, map, compass and boss key, for the Tracker's
           Dungeon items row: OOT_DUNGEON_BASE */
        static const char *const dungeons[OOT_DUNGEON_COUNT] = {OOT_DUNGEONS};
        for (int d = 0; d < OOT_DUNGEON_COUNT; d++) {
            int value = -1;
            char flag[96];
            int32_t keys = 0;
            snprintf(flag, sizeof flag, "DungeonInfo.%s.SmallKeyNum", dungeons[d]);
            if (loaded && oot_gamedata_int(c, oot_flag_hash(flag), &keys, 0)) {
                value = keys < 0 ? 0 : keys > 255 ? 255 : keys;
                static const char *const fields[3] = {"IsGetMap", "IsGetCompass", "IsGetBossKey"};
                for (int k = 0; k < 3; k++) {
                    int got = 0;
                    snprintf(flag, sizeof flag, "DungeonInfo.%s.%s", dungeons[d], fields[k]);
                    if (oot_gamedata_bool(c, oot_flag_hash(flag), &got) && got) value |= 256 << k;
                }
            }
            rx_option_set(OOT_DUNGEON_BASE + d, value);
        }
    }
    {   /* Link's age for the Debug tab's Switch age row: 0 child, 1 adult, -1 no save loaded (Sequence_IsChildhood) */
        int child = 1;
        rx_option_set(OOT_CHEAT_AGE_ID, loaded && oot_gamedata_bool(c, 0xcea220d3u, &child) ? (child ? 0 : 1) : -1);
    }
    {   /* (Willow Woods) the time of day for the In-game clock row: the world's clock (the world manager's +0x510, its +0x28 the
           seconds in the day, as ExecuteWmSetTime sets them: oot_set_time); -1 with no save loaded */
        const uint64_t singleton = recomp_load64(c, 0x84c9e898ULL);
        const uint64_t world = singleton ? recomp_load64(c, singleton) : 0;
        const uint64_t clock = world ? recomp_load64(c, world + 0x510) : 0;
        rx_option_set(OOT_CLOCK_ID, loaded && clock ? (int)recomp_load32(c, clock + 0x28) : -1);
    }
    static char logged[100];
    if (!loaded && logged[0]) {   /* back to the title or the file select: the summary's time there is not the last map's */
        logged[0] = 0;
        AcquireSRWLockExclusive(&map_lock);
        map_now[0] = 0;
        ReleaseSRWLockExclusive(&map_lock);
    }
    if (loaded) {   /* the map Link is in and his age, logged when either changes: where a log's problem happened, the "Where in
                       the game" of the Insert menu's Bug report (gpu/vk/vk_bug_report.cpp reads the last of these lines) */
        char map[80], line[100];
        int child = 1;
        if (oot_gamedata_string(c, 0x1d6189dau, map, sizeof map) && map[0]) {   /* Sequence_CurrentBanc */
            snprintf(line, sizeof line, "%s (%s)", map,
                     oot_gamedata_bool(c, 0xcea220d3u, &child) ? (child ? "child" : "adult") : "age not known");
            if (strcmp(line, logged)) {
                hos_log("map: %s", line), snprintf(logged, sizeof logged, "%s", line);
                AcquireSRWLockExclusive(&map_lock);   /* (the performance summary's map: hos_perf_info) */
                snprintf(map_now, sizeof map_now, "%s", line);
                ReleaseSRWLockExclusive(&map_lock);
            }
            oot_first_night_fix(c, map);
        }
    }
    if (loaded) oot_family_levels_refresh(c);
    if (!probed && oot_pouch_count(c, "Item_DekuSeed") >= 0) {
        probed = 1;   /* (each editor value, plus the alternative pouch spellings) */
        static const char *const probes[] = {OOT_CHEAT_ITEM_PROBES};
        const unsigned total = (unsigned)(OOT_ITEM_COUNT + sizeof probes / sizeof probes[0]);
        char line[512];
        size_t used = 0;
        for (unsigned i = 0; i < total; i++) {   /* (several short lines: the log cuts long ones) */
            const char *name = i < OOT_ITEM_COUNT ? oot_item_names[i] : probes[i - OOT_ITEM_COUNT];
            const int count = i < OOT_ITEM_COUNT ? oot_item_count(c, name) : oot_pouch_count(c, name);
            used += (size_t)snprintf(line + used, sizeof line - used, " %s=%d", name, count);
            if (used > 300 || i + 1 == total) hos_log("cheats: inventory probe:%s", line), used = 0;
        }
    }
}

/* Learned songs use saved IsGet.<actor> Bool flags rather than pouch quantities.
   These are their MurmurHash3 x86-32 hashes with seed 0. */
static uint32_t oot_song_flag(const char *name) {
    static const struct { const char *name; uint32_t hash; } songs[] = {
        {"Item_Melody_ZeldaLullaby", 0x01c20002u},
        {"Item_Melody_EponaSong", 0xb492ac33u},
        {"Item_Melody_SariaSong", 0xd3f8bfccu},
        {"Item_Melody_SunSong", 0x165dd1adu},
        {"Item_Melody_TimeSong", 0x03b3450eu},
        {"Item_Melody_StormSong", 0x2b39dd4fu},
        {"Item_Melody_ForestMinuet", 0xdc0a0b54u},
        {"Item_Melody_FireBolero", 0x49041ab9u},
        {"Item_Melody_WaterSerenade", 0x3fa63986u},
        {"Item_Melody_ShadowNocturne", 0xc2fb95f4u},
        {"Item_Melody_SpiritRequiem", 0x802a36a8u},
        {"Item_Melody_LightPrelude", 0xd6320ba4u},
    };
    for (unsigned i = 0; i < sizeof songs / sizeof songs[0]; i++)
        if (!strcmp(name, songs[i].name)) return songs[i].hash;
    return 0;
}

/* Masks share one slot (the Happy Mask Shop lends one at a time). The game takes "Item_Mask_X" when adding one and
   may keep it as "Armor_Child_Mask_X", so both spellings count and a new mask first returns the one held. */
static int oot_mask_alias(const char *name, char *alias, size_t size) {
    if (!strncmp(name, "Armor_Child_Mask_", 17)) return snprintf(alias, size, "Item_Mask_%s", name + 17), 1;
    return 0;
}

static int oot_item_count(Ctx *c, const char *name) {
    if (!strcmp(name, "Item_MagicMeter")) {   /* (rando_magic's first magic: kept in no pouch, read from the meter) */
        int32_t most = 0;
        return oot_gamedata_int(c, 0x12d63a97u, &most, 0) ? most >= 240 : -1;   /* PlayerStatus.MPMax, in tenths: 240 the first meter */
    }
    const uint32_t song = oot_song_flag(name);
    if (song) {
        int learned = 0;
        return oot_gamedata_bool(c, song, &learned) ? learned : -1;
    }
    char alias[64];
    const int n = oot_pouch_count(c, name);
    if (!strcmp(name, "Item_Bottle")) {   /* (bug 156: a bottle is a slot of its own, no count of this name: host/oot_wheel.c) */
        int hos_oot_bottles(Ctx *c);
        const int had = hos_oot_bottles(c);
        return had > n ? had : n;
    }
    if (!oot_mask_alias(name, alias, sizeof alias)) return n;
    const int m = oot_pouch_count(c, alias);
    return n > m ? n : m;
}

/* (the randomizer's fork) What Link carries a counted item in. The game takes none of an item whose holder he has not: a
   Deku Seed added without a Bullet Bag was accepted (event status 2) and the count stayed 0, time after time; the same with
   Deku Nuts (their bag is in no row of the Inventory page) and Deku Sticks. Seen in the log of a game where Unlock worked and
   every amount stayed 0, the bags all 0 in the page's probe line. An amount raised from the page gives the smallest holder
   first when he has none. */
static const char *oot_item_holder(const char *name) {
    static const char *const pairs[][2] = {
        {"Item_DekuStick", "Item_StickBag_Small"}, {"Item_DekuNut", "Item_NutBag_Small"}, {"Item_Bomb", "Item_BombBag_Small"},
        {"Item_Bombchu", "Item_BombBag_Small"}, {"Item_DekuSeed", "Item_BulletBag_Small"}, {"Item_Arrow_Normal", "Item_Quiver_Small"},
    };
    for (unsigned i = 0; i < sizeof pairs / sizeof pairs[0]; i++)
        if (!strcmp(name, pairs[i][0])) return pairs[i][1];
    /* (the randomizer's fork) A song added without an ocarina was accepted and not kept, as a seed without a bag was
       (seen in the log: Item_Melody_ZeldaLullaby +1, had 0, now 0, event status 2, time after time, in a new game).
       Taken to be the same: a song is given the Fairy Ocarina first when Link has neither ocarina. Not seen yet. */
    if (!strncmp(name, "Item_Melody_", 12)) return "Item_Ocarina_Fairy";
    return NULL;
}

static void oot_inventory_edit(Ctx *c, int action) {
    const unsigned item = (unsigned)(action - OOT_CHEAT_ITEM_ACTION) / 256, op = (unsigned)(action - OOT_CHEAT_ITEM_ACTION) % 256;
    if (item >= OOT_ITEM_COUNT) return;
    const char *name = oot_item_names[item];
    const int have = oot_item_count(c, name);
    const uint32_t song = oot_song_flag(name);
    if (song) {
        if (op != 200 || have < 0) return;   /* songs have no editable quantity */
        if (!oot_gamedata_set_bool(c, song, !have)) {
            hos_log("cheats: song %s: learned flag unavailable", name);
            return;
        }
        hos_log("cheats: song %s %s (had %d, now %d)", name, have ? "relocked" : "unlocked", have, oot_item_count(c, name));
        return;
    }
    char alias[64];
    const int is_mask = oot_mask_alias(name, alias, sizeof alias);
    int delta = 0;
    if (op == 200) delta = have > 0 ? -have : 1;   /* unlock / relock */
    else if (op < 128) delta = (int)op - 64;
    if (!delta || have < 0) return;
    if (is_mask && delta > 0) {   /* return whichever mask is in the slot first */
        for (unsigned i = 0; i < OOT_ITEM_COUNT; i++) {
            char other_alias[64];
            if (i == item || !oot_mask_alias(oot_item_names[i], other_alias, sizeof other_alias)) continue;
            const char *spellings[2] = {oot_item_names[i], other_alias};
            for (unsigned k = 0; k < 2; k++) {
                const int held = oot_pouch_count(c, spellings[k]);
                if (held > 0) hos_log("cheats: inventory returned %s (status %d)", spellings[k], oot_pouch_change(c, spellings[k], -held));
            }
        }
        delta = 1;
    }
    {   /* (an amount raised: its holder first, when Link has none of that kind. Any size counts) */
        const char *holder = delta > 0 ? oot_item_holder(name) : NULL;
        if (holder) {
            char other[64];
            int held = oot_pouch_count(c, holder);
            const size_t stem = strlen(holder) - 5;   /* (..._Small: the same name with _Medium and _Large) */
            if (!strcmp(holder, "Item_Ocarina_Fairy")) {   /* (a song's: either ocarina) */
                if (oot_pouch_count(c, "Item_Ocarina_Time") > 0) held = 1;
            } else {
                snprintf(other, sizeof other, "%.*sMedium", (int)stem, holder);
                if (oot_pouch_count(c, other) > 0) held = 1;
                snprintf(other, sizeof other, "%.*sLarge", (int)stem, holder);
                if (oot_pouch_count(c, other) > 0) held = 1;
            }
            if (held == 0) hos_log("cheats: inventory %s first, to carry %s in (event status %d)", holder, name, oot_pouch_change(c, holder, 1));
        }
    }
    int result = -1;
    if (is_mask && delta < 0) {   /* remove under whichever spelling holds it */
        const char *spellings[2] = {name, alias};
        for (unsigned k = 0; k < 2; k++) {
            const int held = oot_pouch_count(c, spellings[k]);
            if (held > 0) result = oot_pouch_change(c, spellings[k], -held);
        }
    } else {
        result = oot_pouch_change(c, is_mask ? alias : name, delta);   /* (masks are added as Item_Mask_X, as the shop does) */
    }
    hos_log("cheats: inventory %s %+d (had %d, now %d, event status %d)", name, delta, have, oot_item_count(c, name), result);
}

/* (Willow Woods) The Inventory page's Add all (OOT_CHEAT_ADD_ALL, asked 2026-11-20): one change a frame, so the game is
   not handed every item at once. First every item Link lacks (the equipment, the items, the upgrades with the bags and
   quivers, the quest's: oot_inventory_edit's unlock, songs by their flags), then every amount filled to the largest bag's
   (the holders are there by then). Left out, as asked: the masks, the Biggoron's Sword and the Giant's Knife; and the Gold
   Skulltula tokens, a count the Skulltula house's rewards ask for, not an item. */
static int oot_add_all_at = -1;   /* (the next of 2 * OOT_ITEM_COUNT: the unlocks, then the amounts; -1 none) */
static int oot_add_all_full(const char *name) {   /* (an amount's fill: the largest bag's; 0 not filled) */
    static const struct { const char *name; int full; } fills[] = {
        {"Item_DekuStick", 30}, {"Item_DekuNut", 40}, {"Item_Bomb", 40}, {"Item_Bombchu", 50}, {"Item_DekuSeed", 50},
        {"Item_Arrow_Normal", 50}, {"Item_MagicBean", 10}, {"Item_Bottle", 4},
    };
    for (unsigned i = 0; i < sizeof fills / sizeof fills[0]; i++)
        if (!strcmp(name, fills[i].name)) return fills[i].full;
    return 0;
}
static void oot_add_all_tick(Ctx *c) {
    while (oot_add_all_at >= 0 && oot_add_all_at < 2 * (int)OOT_ITEM_COUNT) {
        const unsigned i = (unsigned)oot_add_all_at % OOT_ITEM_COUNT;
        const int amounts = oot_add_all_at >= (int)OOT_ITEM_COUNT;
        oot_add_all_at++;
        const char *name = oot_item_names[i];
        if (!strncmp(name, "Armor_Child_Mask_", 17) || !strcmp(name, "Weapon_Sword_Biggoron") || !strcmp(name, "Weapon_Sword_Giant"))
            continue;
        const int have = oot_item_count(c, name);
        if (have < 0 || (oot_item_kinds[i] != 0) != amounts) continue;
        if (!amounts) {
            if (have > 0) continue;
            oot_inventory_edit(c, OOT_CHEAT_ITEM_ACTION + (int)i * 256 + 200);   /* (unlock) */
            return;
        }
        const int full = oot_add_all_full(name), delta = full - have;
        if (delta <= 0) continue;
        oot_inventory_edit(c, OOT_CHEAT_ITEM_ACTION + (int)i * 256 + 64 + (delta > 63 ? 63 : delta));
        return;
    }
    if (oot_add_all_at >= 0) {
        hos_log("cheats: inventory: Add all done");
        oot_add_all_at = -1;
    }
}

/* (the randomizer's fork, asked 2026-11-21) Starting items: the seed's <game folder>/mods/rando-seed/start_items.txt
   (tools/rando/rando_seed.py START_ITEMS), a line "<name> [<its ammo> <count>]" each. An item of it that Link does not
   hold is given (the Inventory page's unlock), and its ammo with it; one change a call (once a second, from
   oot_tracker_refresh), so a new game gets them over its first seconds. Held: the item, or a bigger one of its family
   (a bag's _Medium or _Large, the Longshot for the Hookshot, the Ocarina of Time for the Fairy Ocarina). An item lost
   (a Deku Shield burnt) comes back the same way. */
#define OOT_START_MAX 48
static int oot_game_file(char *out, size_t size, const char *tail);
static int oot_start_held(Ctx *c, const char *name) {
    if (oot_item_count(c, name) > 0) return 1;
    if (!strcmp(name, "Item_Hookshot")) return oot_item_count(c, "Item_Longshot") > 0;
    if (!strcmp(name, "Item_Ocarina_Fairy")) return oot_item_count(c, "Item_Ocarina_Time") > 0;
    const size_t n = strlen(name);
    if (n > 6 && !strcmp(name + n - 6, "_Small")) {
        char other[64];
        snprintf(other, sizeof other, "%.*s_Medium", (int)(n - 6), name);
        if (oot_item_count(c, other) > 0) return 1;
        snprintf(other, sizeof other, "%.*s_Large", (int)(n - 6), name);
        if (oot_item_count(c, other) > 0) return 1;
    }
    return 0;
}
static void oot_start_items(Ctx *c, const char *seed) {
    static char names[OOT_START_MAX][48], ammo[OOT_START_MAX][32], seed_of[1024];
    static int counts[OOT_START_MAX], count = -1, fill = -1, fill_left;   /* (fill: the item whose ammo is being given) */
    if (count < 0 || strcmp(seed_of, seed)) {   /* (this seed's list, read again when the seed is another) */
        count = 0, fill = -1;
        snprintf(seed_of, sizeof seed_of, "%s", seed);
        char path[MAX_PATH + 48], line[160];
        FILE *f = oot_game_file(path, sizeof path, "mods/rando-seed/start_items.txt") ? fopen(path, "r") : NULL;
        while (f && count < OOT_START_MAX && fgets(line, sizeof line, f)) {
            if (line[0] == '#') continue;
            ammo[count][0] = 0, counts[count] = 0;
            if (sscanf(line, "%47s %31s %d", names[count], ammo[count], &counts[count]) >= 1) count++;
        }
        if (f) fclose(f);
        if (count) hos_log("rando: %d starting items in this seed", count);
    }
    if (fill >= 0) {   /* (the ammo of an item just given: up to 63 a change) */
        int i = -1;
        for (unsigned k = 0; k < OOT_ITEM_COUNT; k++) if (!strcmp(oot_item_names[k], ammo[fill])) i = (int)k;
        const int step = fill_left > 63 ? 63 : fill_left;
        if (i >= 0 && step > 0) oot_inventory_edit(c, OOT_CHEAT_ITEM_ACTION + i * 256 + 64 + step);
        fill_left -= step;
        if (i < 0 || fill_left <= 0) fill = -1;
        return;
    }
    for (int s = 0; s < count; s++) {
        if (oot_start_held(c, names[s])) continue;
        int i = -1;
        for (unsigned k = 0; k < OOT_ITEM_COUNT; k++) if (!strcmp(oot_item_names[k], names[s])) i = (int)k;
        if (i < 0) { hos_log("rando: starting item %s is not one the game side can give", names[s]); names[s][0] = 0; continue; }
        if (oot_item_count(c, names[s]) < 0) return;   /* (the pouch not readable yet: next time) */
        hos_log("rando: starting item %s given", names[s]);
        oot_inventory_edit(c, OOT_CHEAT_ITEM_ACTION + i * 256 + 200);   /* (unlock: Link holds none) */
        if (ammo[s][0] && counts[s] > 0) fill = s, fill_left = counts[s];
        return;
    }
}

static void oot_set_time(Ctx *c, unsigned hour) {
    // ExecuteWmSetTime passes seconds since midnight to the world manager.
    const uint64_t singleton = recomp_load64(c, 0x84c9e898ULL);
    const uint64_t world = singleton ? recomp_load64(c, singleton) : 0;
    A64Fn set_time = a64_lookup(0x834722d0ULL);
    if (!set_time || !world || !recomp_load64(c, world + 0x510)) {
        hos_log("cheats: world clock unavailable");
        return;
    }
    const Ctx saved = *c;
    c->x[0] = world;
    c->x[1] = hour * 3600;
    set_time(c);
    *c = saved;
    hos_log("cheats: requested %02u:00", hour);
}

/* Cross-map teleport (build e0f3ccfa). Map changes in this game only run through an event: an entrance actor
   requests the Dm_SY_BancChangeGo event with NextBanc / NextStartPos / BootEventName arguments, the event calls
   GameSystemActor's ReserveBancChange, and the sequence's ChangeBancOnEvent loads the map when the event ends.
   This builds the same event request (see work/oot-teleport-research.md). The menu labels in gpu/vk/vk_menu.cpp
   (teleport_names) follow this table's order. */
typedef struct {
    const char *child_banc, *child_start, *child_boot;
    const char *adult_banc, *adult_start, *adult_boot;
} OotDestination;
static const OotDestination oot_destinations[] = {   /* (generated: work/oot-teleport-tools/write_destinations.py) */
    {"KokiriForest_Child", "LostWoodBridge_FrontOfHyruleField", "Dm_SY_BancChangeArrive",
     "KokiriForest_Adult", "LostWoodBridge_FrontOfHyruleField", "Dm_SY_BancChangeArrive"},   /* Kokiri Forest */
    {"HyruleField_Child", "HyruleField_FrontOfLostWoodBridge", "Dm_SY_BancChangeArrive",
     "HyruleField_Adult", "HyruleField_FrontOfLostWoodBridge", "Dm_SY_BancChangeArrive"},   /* Hyrule Field */
    {"KakarikoVillage_Child", "KakarikoVillage_Entrance", "Dm_SY_BancChangeArrive_KakarikoVillage_01",
     "KakarikoVillage_Adult", "KakarikoVillage_Entrance", "Dm_SY_BancChangeArrive_KakarikoVillage_01"},   /* Kakariko Village */
    {"Market_Child", "Market_Entrance", "Dm_SY_BancChangeArrive_Market_02",
     "Market_Adult", "Market_Entrance", "Dm_SY_BancChangeArrive_Market_02"},   /* Market */
    {"HyruleCastle", "HyruleCastle_Entrance", "Dm_SY_BancChangeArrive_HyruleCastle_01",
     "GanonCastle", "GanonCastleEntrance", "Dm_SY_BancChangeArrive_GanonCastle_01"},   /* Hyrule Castle */
    {"LostWood_Child", "LostWood_FrontOfSacredForestMeadow", "Dm_SY_BancChangeArrive_LostWood",
     "LostWood_Adult", "LostWood_FrontOfSacredForestMeadow", "Dm_SY_BancChangeArrive_LostWood"},   /* Lost Woods */
    {"SacredForestMeadow_Child", "OutsideOfForestTemple", "Dm_SY_BancChangeArrive_SacredForestMeadow_01",
     "SacredForestMeadow_Adult", "OutsideOfForestTemple", "Dm_SY_BancChangeArrive_SacredForestMeadow_01"},   /* Sacred Forest Meadow */
    {"HyruleField_Child", "LakeHylia_FromGerudoValley", "Dm_SY_BancChangeArrive_LakeHylia_02",
     "HyruleField_Adult", "LakeHylia_FromGerudoValley", "Dm_SY_BancChangeArrive_LakeHylia_02"},   /* Lake Hylia */
    {"Graveyard_Child", "GraveYard_KakarikoSide", "Dm_SY_BancChangeArrive_Graveyard_01",
     "Graveyard_Adult", "GraveYard_KakarikoSide", "Dm_SY_BancChangeArrive_Graveyard_01"},   /* Graveyard */
    {"DeathMountainTrail_Child", "MountainTrail_KakarikoSide", "Dm_SY_BancChangeArrive_DeathMountainTrail_01",
     "DeathMountainTrail_Adult", "MountainTrail_KakarikoSide", "Dm_SY_BancChangeArrive_DeathMountainTrail_01"},   /* Death Mountain Trail */
    {"DeathMountainCrater_Child", "Crater_GoronCitySide", "DeathMountainCrater_Arrive",
     "DeathMountainCrater_Adult", "Crater_GoronCitySide", "DeathMountainCrater_Arrive"},   /* Death Mountain Crater */
    {"GoronCity_Child", "GoronCity_MountainTrailSide", "Dm_SY_BancChangeArrive_GoronCity_01",
     "GoronCity_Adult", "GoronCity_MountainTrailSide", "Dm_SY_BancChangeArrive_GoronCity_01"},   /* Goron City */
    {"ZoraRiver_Child", "ZoraRiver_Entrance", "Dm_SY_BancChangeArrive",
     "ZoraRiver_Adult", "ZoraRiver_Entrance", "Dm_SY_BancChangeArrive"},   /* Zora's River */
    {"ZoraDomain_Child", "ZoraDomain_FromZoraRiver", "Dm_SY_BancChangeArrive",
     "ZoraDomain_Adult", "ZoraDomain_FromZoraRiver", "Dm_SY_BancChangeArrive"},   /* Zora's Domain */
    {"ZoraFountain_Child", "ZoraFountain_FromZoraDomain", "Dm_SY_BancChangeArrive",
     "ZoraFountain_Adult", "ZoraFountain_FromZoraDomain", "Dm_SY_BancChangeArrive"},   /* Zora's Fountain */
    {"GerudoValley_Child", "GerudoValley_Entrance", "FromHyruleField_ArriveGerudoValley",
     "GerudoValley_Adult", "GerudoValley_Entrance", "FromHyruleField_ArriveGerudoValley"},   /* Gerudo Valley */
    {NULL, NULL, NULL,
     "GerudoFortress_Adult", "GerudoFortress_FromHountedWasteland", "Dm_SY_BancChangeArrive_GerudoFortress_02"},   /* Gerudo Fortress */
    {"HountedWasteland_Child", "HountedWasteland_FromGerudoFortress", "FromGerudoFortress_ArriveWateland",
     "HountedWasteland_Adult", "HountedWasteland_FromGerudoFortress", "FromGerudoFortress_ArriveWateland"},   /* Haunted Wasteland */
    {"DesertColossus_Child", "DesertColossus_FromHountedWasteland", "Dm_SY_BancChangeArrive_DesertColossus_01",
     "DesertColossus_Adult", "DesertColossus_FromHountedWasteland", "Dm_SY_BancChangeArrive_DesertColossus_01"},   /* Desert Colossus */
    {"InsideTheDekuTree", "Entrance", "Dm_SY_BancChangeArrive_InsideTheDekuTree_01",
     "InsideTheDekuTree", "Entrance", "Dm_SY_BancChangeArrive_InsideTheDekuTree_01"},   /* Inside the Deku Tree */
    {"DodongoCavern", "DodongoCavern_MountainTrailSide", "Dm_SY_BancChangeArrive",
     "DodongoCavern", "DodongoCavern_MountainTrailSide", "Dm_SY_BancChangeArrive"},   /* Dodongo's Cavern */
    {"InsideJabuJabuBelly", "InsideJabuJabuBelly_FromZoraFountain", "Dm_SY_BancChangeArrive",
     "InsideJabuJabuBelly", "InsideJabuJabuBelly_FromZoraFountain", "Dm_SY_BancChangeArrive"},   /* Jabu-Jabu's Belly */
    {"ForestTemple", "ForestTemple", "Dm_SY_BancChangeArrive",
     "ForestTemple", "ForestTemple", "Dm_SY_BancChangeArrive"},   /* Forest Temple */
    {"FireTemple", "FireTemple", "Dm_SY_BancChangeArrive",
     "FireTemple", "FireTemple", "Dm_SY_BancChangeArrive"},   /* Fire Temple */
    {"WaterTemple", "WaterTemple_FromLakeHylia", "SageOfWater_Arrival_WaterTemple",
     "WaterTemple", "WaterTemple_FromLakeHylia", "SageOfWater_Arrival_WaterTemple"},   /* Water Temple */
    {"ShadowTemple", "Entrance", "ShadowTemple_Arrive",
     "ShadowTemple", "Entrance", "ShadowTemple_Arrive"},   /* Shadow Temple */
    {"SpiritTemple", "SpiritTemple_FromRightHand", "Dm_SY_BancChangeArrive",
     "SpiritTemple", "SpiritTemple_FromRightHand", "Dm_SY_BancChangeArrive"},   /* Spirit Temple */
    {"BottomOfTheWell", "Well_KakarikoSide", "Dm_SY_BancChangeArrive",
     "BottomOfTheWell", "Well_KakarikoSide", "Dm_SY_BancChangeArrive"},   /* Bottom of the Well */
    {"IceCavern", "IceCavern_FromZoraFountain", "SageOfWater_Arrival_IceCavern",
     "IceCavern", "IceCavern_FromZoraFountain", "SageOfWater_Arrival_IceCavern"},   /* Ice Cavern */
    {"GerudoTrainingGround", "GerudoTrainingGround_FromGerudoFortress", "FromGerudoFortress_ArriveTrainingGround",
     "GerudoTrainingGround", "GerudoTrainingGround_FromGerudoFortress", "FromGerudoFortress_ArriveTrainingGround"},   /* Gerudo Training Ground */
    {"InsideGanonCastle", "Entrance", "Dm_SY_BancChangeArrive_InsideGanonCastle_01",
     "InsideGanonCastle", "Entrance", "Dm_SY_BancChangeArrive_InsideGanonCastle_01"},   /* Ganon's Castle */
};
/* (the randomizer's fork) The Debug tab's Teleport page, its Bosses: each boss's room, the action OOT_TELEPORT_ACTION + the
   destinations' count + its place here. The teleport to the dungeon's map, then Link put at the place as the Tracker's Go
   there puts him (a metre above it, held three seconds). The places are the game's own start points in each boss's room,
   by its door (the room's StartPos nearest the room's centre, from the map files), away from the room's blue warp: put
   where the boss is, Link was above Gohma's ceiling and was taken out of the dungeon (seen without a window). Twinrova's
   room has none: the place just inside its door. Asked for by the game's owner, to test the bosses without the dungeons.
   A fight starts as Link comes through the room's door (the door's shutter or a request at the doorway asks for the
   boss's event); put inside, he found the boss and no fight (King Dodongo, Barinade, Ganondorf: the owner, 2026-11-16).
   So the boss's own event (the game's event list, RSDB/EventSetting) is asked for once he has been held in the room. */
typedef struct {
    const char *folder, *ages;   /* (the dungeon's map folder; C the child, A the adult has it) */
    float place[3];
    const char *event;           /* (what starts the fight, from the map's request or door in the room) */
    uint32_t seen;               /* (0, or the dungeon's entry scene's played flag (HavePlayedEvent.Goto_<dungeon>), set first:
                                    that scene walked Link back to the entrance from the boss's room, and held the camera) */
} OotBossRoom;
static const OotBossRoom oot_boss_rooms[] = {
    {"InsideTheDekuTree", "CA", {6.7f, 47.0f, 67.6f}, "InsideTheDekuTree_BossArea_ShutIn"},           /* Gohma */
    {"DodongoCavern", "CA", {24.0f, 73.4f, -77.6f}, "Get_StoneOfFire_AppearBoss"},             /* King Dodongo */
    {"InsideJabuJabuBelly", "CA", {42.4f, 102.0f, -98.1f}, "Get_StoneOfWater_BossAppear"},      /* Barinade */
    {"ForestTemple", "CA", {-6.0f, 74.7f, -66.0f}, "ForestTemple_SageOfForest_PhantomGanonAppearance"},              /* Phantom Ganon */
    {"FireTemple", "CA", {-64.5f, 102.5f, 0.0f}, "SageOfFire_BossAppear", 0xde8666fau},                /* Volvagia */
    {"WaterTemple", "CA", {-4.5f, 131.4f, -75.3f}, "Demo_SageOfWater_BossAppears", 0x3be817e9u},              /* Morpha */
    {"ShadowTemple", "CA", {-138.3f, -11.5f, 22.0f}, "ShadowTemple_BossAppear"},            /* Bongo Bongo */
    {"SpiritTemple", "CA", {0.0f, 135.0f, -121.3f}, "SageOfSpirit_BossStart"},             /* Twinrova */
    {"InsideGanonCastle", "CA", {0.0f, 171.1f, -11.3f}, "Common_Dungeon_OpenDoorChainLock_UnlockGanonBossRoomMoveTo0"},
                                                                 /* Ganondorf: his door's unlock, which calls Defeat_Ganon's
                                                                    BossAppear_1 (his entrance scene alone left the room empty) */
};
#define OOT_DESTINATIONS (sizeof oot_destinations / sizeof oot_destinations[0])
#define OOT_BOSS_ROOMS (sizeof oot_boss_rooms / sizeof oot_boss_rooms[0])
static float oot_link_place[3];   /* (where Link is: defined with the tracker's, below) */
/* (Boss shuffle's record, oot_boss_doors_note) Link stands in the boss's room of the dungeon `folder`: within
   OOT_BOSS_ROOM_NEAR of the room's start point (the rooms are 20 to 40 m across, and no other room of a dungeon is so near) */
static int oot_boss_room_near(const char *folder) {
    for (unsigned i = 0; i < OOT_BOSS_ROOMS; i++) {
        if (strcmp(oot_boss_rooms[i].folder, folder)) continue;
        const float dx = oot_link_place[0] - oot_boss_rooms[i].place[0], dy = oot_link_place[1] - oot_boss_rooms[i].place[1],
                    dz = oot_link_place[2] - oot_boss_rooms[i].place[2];
        return dx * dx + dy * dy + dz * dz < 30.0f * 30.0f;
    }
    return 0;
}
#define OOT_AGE_ACTION 999   /* (the Cheats page's Age row) */
#define OOT_TELEPORT_ACTION 1000   /* (pouch edits use 200 to 348) */
#define OOT_GAMEDATA_SLOT 0x84c9e180ULL   /* GameDataMgr, as ReserveBancChange's readers load it */
#define OOT_EVENTMGR_SLOT 0x84c9e090ULL   /* EventMgr, as SeqOneShotRequestEvent loads it */
#define OOT_EVENT_ARG_SIZE 0x1b20ULL      /* EventRequestArg: SeqOneShotRequestEvent reserves this much stack */

static uint64_t oot_singleton(Ctx *c, uint64_t slot) {
    const uint64_t holder = recomp_load64(c, slot);
    return holder ? recomp_load64(c, holder) : 0;
}

/* GameDataMgr getters by MurMur3 name hash: f_8022d9c0 (bool) and f_80cd0ea0 (String64). 1 when found. */
static int oot_gamedata_bool(Ctx *c, uint32_t hash, int *value) {
    const uint64_t mgr = oot_singleton(c, OOT_GAMEDATA_SLOT);
    A64Fn get = a64_lookup(0x8022d9c0ULL);
    if (!mgr || !get) return 0;
    const Ctx saved = *c;
    const uint64_t out = (c->x[31] - 0x40) & ~0xfULL;
    recomp_store64_sp(c, out, 0);
    c->x[31] = out;
    c->x[0] = mgr, c->x[1] = out, c->x[2] = hash;
    get(c);
    const int found = (int)(c->x[0] & 1);
    *value = recomp_load8(c, out) & 1;
    *c = saved;
    return found;
}

static int oot_gamedata_string(Ctx *c, uint32_t hash, char *buf, size_t size) {
    const uint64_t mgr = oot_singleton(c, OOT_GAMEDATA_SLOT);
    A64Fn get = a64_lookup(0x80cd0ea0ULL);
    buf[0] = 0;
    if (!mgr || !get) return 0;
    const Ctx saved = *c;
    const uint64_t out = (c->x[31] - 0x40) & ~0xfULL;
    recomp_store64_sp(c, out, 0);
    c->x[31] = out;
    c->x[0] = mgr, c->x[1] = out, c->x[2] = hash;
    get(c);
    const int found = (int)(c->x[0] & 1);
    const uint64_t text = recomp_load64(c, out);
    *c = saved;
    if (!found || !text) return 0;
    for (size_t i = 0; i + 1 < size; i++) {
        buf[i] = (char)recomp_load8(c, text + i);
        buf[i + 1] = 0;
        if (!buf[i]) break;
    }
    return 1;
}

/* (Willow Woods, a test's) The labels of the functions a build traced (nx2/oot_patches.py patch_trace, HOOKSHOT_TRACE_FNS)
   counted, and every 3 s those that ran logged with how many times since: "trace f_<fn>: start 60, 80a99904 60, ...". */
#define HOS_TRACE_SLOTS 2048
static struct { unsigned long long fn, at; long long count, shown; } hos_trace_tab[HOS_TRACE_SLOTS];
void hos_trace_label(Ctx *c, unsigned long long fn, unsigned long long at) {
    /* (at a function's start, also its first argument's low byte, counted as "a<n>": which kind of call it was) */
    if (!at && c) hos_trace_label(NULL, fn, 0xa00 + (c->x[1] & 0xff));
    if (!at && c) hos_trace_label(NULL, fn, 0x100000000ULL | (c->x[30] & 0xffffffffULL));   /* (and who called it: "1<lr>") */
    const unsigned key = (unsigned)((fn * 31 + at) % HOS_TRACE_SLOTS);
    for (unsigned i = 0, k = key; i < HOS_TRACE_SLOTS; i++, k = (k + 1) % HOS_TRACE_SLOTS) {
        if (!hos_trace_tab[k].fn) { hos_trace_tab[k].fn = fn; hos_trace_tab[k].at = at; }
        if (hos_trace_tab[k].fn == fn && hos_trace_tab[k].at == at) { __atomic_add_fetch(&hos_trace_tab[k].count, 1, __ATOMIC_RELAXED); break; }
    }
    static long long next;
    const long long now = hos_now_ns();
    if (now < next) return;
    next = now + 3000000000LL;
    static char line[8192];
    unsigned long long fns[16]; int nf = 0;
    for (unsigned k = 0; k < HOS_TRACE_SLOTS; k++) {
        if (!hos_trace_tab[k].fn) continue;
        int seen = 0;
        for (int j = 0; j < nf; j++) seen |= fns[j] == hos_trace_tab[k].fn;
        if (!seen && nf < 16) fns[nf++] = hos_trace_tab[k].fn;
    }
    for (int j = 0; j < nf; j++) {
        size_t n = (size_t)snprintf(line, sizeof line, "trace f_%llx:", fns[j]);
        for (unsigned k = 0; k < HOS_TRACE_SLOTS && n + 40 < sizeof line; k++) {
            if (hos_trace_tab[k].fn != fns[j]) continue;
            const long long now_count = __atomic_load_n(&hos_trace_tab[k].count, __ATOMIC_RELAXED), d = now_count - hos_trace_tab[k].shown;
            if (!d) continue;
            hos_trace_tab[k].shown = now_count;
            if (hos_trace_tab[k].at) n += (size_t)snprintf(line + n, sizeof line - n, " %llx %lld", hos_trace_tab[k].at, d);
            else n += (size_t)snprintf(line + n, sizeof line - n, " start %lld", d);
        }
        hos_log("%s", line);
    }
}

/* (Willow Woods) Where a game-data string's text lives (its getter's answer, f_80cd0ea0): 0 when it is not there. */
/* (Either age's tunics, bug 107; the owner, 2026-11-27: "keep his own clothes") Young Link's tunics. The tunic worn is a
   name in a table of the player's (EquipArmor: Armor_Adult_Goron, Armor_Adult_Zora, Armor_Adult_Normal, or none; not the
   game data's strings: f_80a9a860 reads it, x3 the name's hash, the text's place written to x1's, as the boots'
   EquipBoot), and the game makes the actor of that name on Link. The adult's on a child was the adult's body's model on
   bones he has not: red spikes and a blue lump over his head and body (seen without a window, 2026-11-27), though the
   tunic's effect was there. The seed makes an actor of each tunic for him (tools/rando/rando_seed.py TUNIC_CHILD:
   Armor_Child_Goron, Armor_Child_Zora, Armor_Child_Normal: the tunic's model with every material of it hidden, his own
   clothes kept, the effect the same), and the name follows Link's age in two places:
   - where that reader answers (nx2/oot_patches.py patch_equip_name; hos_oot_equip_name), the name as it is kept: a
     child's is his own actor's, an adult's the adult's, written where the text is (never a longer name);
   - where the Equipment page takes Equip (patch_tunic_menu; hos_oot_menu_tunic), the chosen item's name in the page's
     own copy, before the page looks it up, shows it on its figure and writes it (the owner's test, 2026-11-28: a child's
     Equip on a tunic did nothing; and, once let through, the page's figure wore the adult's model). A child's own tunic
     there is Obj_Armor_Child_Normal, which worn was the adult's plain tunic on him: it is his Armor_Child_Normal too.
   With the setting off, or a seed that has not made the actors (one written before), a child's name left in a save is
   the adult's again (his plain one: none), so nothing asks for an actor that is not there. The pouch's items are the
   adult's for both ages: one of each tunic. */
#define OOT_EQUIP_ARMOR 0xb5f9aac7u   /* (EquipArmor) */
int hos_rando_ageless_tunics(void);
/* The seed's actors for young Link (looked for once): the newest of them, so a seed from before it counts as without */
static int oot_tunics_made(void) {
    static int made = -1;
    if (made < 0) {
        char path[MAX_PATH];
        FILE *f = oot_game_file(path, sizeof path, "mods/rando-seed/romfs/Pack/Actor/Armor_Child_Normal.pack.zs") ? fopen(path, "rb") : NULL;
        made = f != NULL;
        if (f) fclose(f);
    }
    return made;
}
/* The name a tunic's is to be (out, 24 bytes) for Link's age: 1 when it is another than now. his_own: a child whose
   own actors the seed has made, with the setting on */
static int oot_tunic_name(const char *now, int his_own, char out[24]) {
    static const char *const kinds[] = {"Goron", "Zora", "Normal"};
    out[0] = 0;
    for (int k = 0; k < 3; k++) {
        char adult[24], child[24];
        snprintf(adult, sizeof adult, "Armor_Adult_%s", kinds[k]);
        snprintf(child, sizeof child, "Armor_Child_%s", kinds[k]);
        if (his_own && !strcmp(now, adult)) return snprintf(out, 24, "%s", child), 1;
        if (!his_own && !strcmp(now, child)) return snprintf(out, 24, "%s", adult), 1;
    }
    if (his_own && !strcmp(now, "Obj_Armor_Child_Normal")) return snprintf(out, 24, "Armor_Child_Normal"), 1;
    return 0;
}
static void oot_tunic_write(Ctx *c, uint64_t text, const char *name) {
    for (size_t i = 0; i <= strlen(name); i++) recomp_store8(c, text + i, (uint8_t)name[i]);
}
void hos_oot_equip_name(Ctx *c, unsigned long long out, unsigned long long hash) {
    const uint64_t text = out ? recomp_load64(c, out) : 0;
    if (!text || (uint32_t)hash != OOT_EQUIP_ARMOR) return;
    char now[24];
    for (int i = 0; i < 23; i++) now[i] = (char)recomp_load8(c, text + (uint64_t)i);
    now[23] = 0;
    {   /* (a test's: HOS_OOT_TEST_TUNIC=Goron, Zora or None is the tunic worn, whatever the save says, written where the
           name is: the Goron Tunic's heat tried without the Equipment page. Goron's name is a letter longer than Zora's) */
        static const char *test;
        static int asked;
        if (!asked) asked = 1, test = getenv("HOS_OOT_TEST_TUNIC");
        if (test && *test && (now[0] == 0 || !strncmp(now, "Armor_", 6))) {
            char want[24] = "";
            if (!strcmp(test, "Goron") || !strcmp(test, "Zora")) snprintf(want, sizeof want, "Armor_%.5s_%s", now[0] && !strncmp(now + 6, "Child", 5) ? "Child" : "Adult", test);
            if (strcmp(want, now)) {
                oot_tunic_write(c, text, want);
                hos_log("test: the tunic worn \"%s\" written \"%s\"", now, want);
                snprintf(now, sizeof now, "%s", want);
            }
        }
    }
    if (strncmp(now, "Armor_", 6) && strcmp(now, "Obj_Armor_Child_Normal")) return;
    int child = 0;
    if (!oot_gamedata_bool(c, 0xcea220d3u, &child)) return;   /* (Sequence_IsChildhood, asked now: the name is read as a save loads) */
    const int his_own = child && oot_tunics_made() && hos_rando_ageless_tunics();
    char want[24];
    if (!oot_tunic_name(now, his_own, want)) {
        /* (a child without his own actors: his plain tunic is none worn, as the game has it for him) */
        if (child && !his_own && (!strcmp(now, "Armor_Adult_Normal") || !strcmp(now, "Obj_Armor_Child_Normal"))) want[0] = 0;
        else return;
    } else if (child && !his_own && !strcmp(want, "Armor_Adult_Normal")) want[0] = 0;
    oot_tunic_write(c, text, want);
    hos_log("rando: the tunic worn: %s made \"%s\" (%s)", now, want, his_own ? "young Link's own actor of it: his clothes stay" : child ? "no actor of young Link's for it here" : "the adult's");
}
/* The Equipment page's Equip, a child's: the chosen item's name (name: the page's own copy of it, a text of the
   function's own) made his own actor's before the page looks it up, and the function's word for the item (slot: where it
   keeps the place of the slot's own name, which every later call is given) pointed at that copy: the slot's name is
   left as the page has it, and what the page shows on its figure and writes as worn is his own actor */
void hos_oot_menu_tunic(Ctx *c, unsigned long long name, unsigned long long slot) {
    if (!name || !hos_rando_ageless_tunics() || !oot_tunics_made()) return;
    char now[24], want[24];
    for (int i = 0; i < 23; i++) now[i] = (char)recomp_load8(c, name + (uint64_t)i);
    now[23] = 0;
    if (strncmp(now, "Armor_Adult_", 12) && strcmp(now, "Obj_Armor_Child_Normal")) return;
    int child = 0;
    if (!oot_gamedata_bool(c, 0xcea220d3u, &child) || !child) return;
    if (!oot_tunic_name(now, 1, want)) return;
    oot_tunic_write(c, name, want);
    if (slot) recomp_store64(c, slot, name);
    hos_log("rando: the Equipment page: young Link's %s is %s", now, want);
}
static uint64_t oot_gamedata_string_at(Ctx *c, uint32_t hash) {
    const uint64_t mgr = oot_singleton(c, OOT_GAMEDATA_SLOT);
    A64Fn get = a64_lookup(0x80cd0ea0ULL);
    if (!mgr || !get) return 0;
    const Ctx saved = *c;
    const uint64_t out = (c->x[31] - 0x40) & ~0xfULL;
    recomp_store64_sp(c, out, 0);
    c->x[31] = out;
    c->x[0] = mgr, c->x[1] = out, c->x[2] = hash;
    get(c);
    const int found = (int)(c->x[0] & 1);
    const uint64_t text = recomp_load64(c, out);
    *c = saved;
    return found ? text : 0;
}

/* One argument of an EventRequestArg: the array of 200-byte entries at arg+8, capacity arg+0, count arg+16.
   Entry: +0 type (1 string pointer, 4 bool), +8 name buffer, +16 its capacity, +152 the value. As
   QueryBancChangeEventRequestArg (f_829df380) fills them. A string value is a pointer the request does not copy. */
static int oot_event_arg(Ctx *c, uint64_t arg, const char *name, uint32_t type, uint64_t value) {
    const uint32_t capacity = recomp_load32(c, arg), count = recomp_load32(c, arg + 16);
    if (count >= capacity) return 0;
    const uint64_t entry = recomp_load64(c, arg + 8) + (uint64_t)count * 200;
    const uint64_t name_buf = recomp_load64(c, entry + 8);
    const uint32_t name_cap = recomp_load32(c, entry + 16);
    const size_t length = strlen(name);
    if (!name_buf || length + 1 > name_cap) return 0;
    memcpy(A64_PTR(name_buf), name, length + 1);
    if (type == 4) recomp_store8(c, entry + 152, value & 1);
    else recomp_store64(c, entry + 152, value);
    recomp_store32(c, entry, type);
    recomp_store32(c, arg + 16, count + 1);
    return 1;
}

/* (the Main sequence's "Event" test: an event is playing) */
static int oot_event_playing(Ctx *c) {
    const uint64_t events = oot_singleton(c, OOT_EVENTMGR_SLOT);
    return events && recomp_load64(c, events + 104);
}

static struct {
    int64_t requested_at, check_at;
    unsigned destination;
    const char *why, *banc;   /* (the last call's: why it was not sent, the map it was sent to; the control bridge's reply) */
    uint64_t result;          /* (and the event manager's answer to the request: 0 seen when the map did not change) */
} teleport;

/* An event of the game's asked for by its name, with Link the one who starts it: the request oot_teleport makes,
   without a map to go to. 1 when it was sent. */
static int oot_event_request(Ctx *c, uint64_t actor, const char *event) {
    const uint64_t events = oot_singleton(c, OOT_EVENTMGR_SLOT);
    A64Fn make_arg = a64_lookup(0x80d99f10ULL), request = a64_lookup(0x80d9a820ULL);
    A64Fn set_link = a64_lookup(0x802dc440ULL), release_link = a64_lookup(0x8022b6f0ULL);
    if (!events || !make_arg || !request || !set_link || !release_link) return 0;
    const Ctx saved = *c;
    const uint64_t arg = (c->x[31] - OOT_EVENT_ARG_SIZE - 0x100) & ~0xfULL;
    c->x[31] = arg;
    c->x[0] = arg;
    make_arg(c);
    const uint64_t buf = recomp_load64(c, arg + 6800);
    const uint32_t cap = recomp_load32(c, arg + 6808);
    const int ok = buf && strlen(event) + 1 <= cap;
    if (ok) {
        memcpy(A64_PTR(buf), event, strlen(event) + 1);
        c->x[31] = arg;
        c->x[0] = arg + 0x1950, c->x[1] = actor, c->x[2] = 0;
        set_link(c);
        c->x[31] = arg;
        c->x[0] = events, c->x[1] = arg;
        request(c);
    }
    for (unsigned i = 0; i < 2; i++) {   /* (the arg's two actor links, as oot_teleport gives them back) */
        const uint64_t link = arg + (i ? 0x1950 : 0x1968);
        recomp_store64(c, link, 0x84994b20ULL);
        c->x[31] = arg;
        c->x[0] = link;
        release_link(c);
    }
    *c = saved;
    return ok;
}

/* (the randomizer's fork) Open Door of Time: the Master Sword takes Link through time from a new game's start.
   The sword's own logic asks for its events only at and after the story's step for them (the quest DoorOfTime at
   Step06: tools/rando/rando_seed.py OPEN_DOOR has what was found): before, the button at the sword does nothing.
   So when A is pressed beside the sword, in the Market's map of either age, and half a second later nothing of the
   game's is playing, the game's own plain way through time is asked for here: Market_Child_Field_ChildToAdult, or
   Market_Adult_Field_AdultToChild. Where the game answers the button itself (the story's drawing, the plain way once
   the story is past it, a talk) its event is playing by then and nothing is asked for.
   The door's flag is set here too for a save that has it put out (a save from before the setting was on). */
static float oot_link_place[3];   /* (where Link is: oot_tracker_refresh, below) */
static int oot_pouch_count(Ctx *c, const char *name);
static int oot_pouch_change(Ctx *c, const char *name, int by);
static int oot_pedestal_give(Ctx *c);   /* (below: Shuffle the Master Sword) */
#define OOT_SWORD_X 137.6f
#define OOT_SWORD_Z (-34.0f)
#define OOT_SWORD_NEAR 1.8f
#define OOT_DOOR_FLAG 0x727c2cbdu   /* Market_Child_TimeTempleDoor_Opened */
/* (the adult's Market has its location, and so its minimap, only once the scene of an adult leaving the temple has
   played, which the plain way through time never reaches: tools/rando/rando_seed.py OPEN_DOOR. Set like the door's) */
#define OOT_LEFT_TEMPLE_FLAG 0xc1b29b0au   /* HavePlayedEvent.Dm_TimeTemple_0065 */
/* (the Door of Time by the Song of Time, rando_open_door 2: tools/rando/rando_seed.py DOOR_SONG) Link holds the Song of
   Time and an ocarina: the door's name is answered with a stand-in as the Market's actors are read (hos_oot_shelf_actor),
   and the rest of Open Door of Time's work is done from then on. Read each second here, on the game's thread */
static int oot_door_song_open;
static int oot_door_song_held(Ctx *c) {   /* (as the Debug tab's inventory reads them: songs too) */
    return oot_item_count(c, "Item_Melody_TimeSong") > 0 &&
           (oot_item_count(c, "Item_Ocarina_Fairy") > 0 || oot_item_count(c, "Item_Ocarina_Time") > 0);
}
#define OOT_DOOR_STAND_IN "EftLoc_TimeTemple_Fog_HideOutside_00"   /* (an invisible effect marker of the temple's own) */
static void oot_time_door(Ctx *c, int64_t now, uint64_t actor) {
    int hos_rando_open_door(void);   /* host/oot_rando.c */
    int hos_pad_a_held(void);        /* host/nn_hid.c */
    static int held;
    static int64_t ask_at, flag_at;
    const int mode = hos_rando_open_door();
    if (!mode) return;
    if (mode == 2) {   /* (asked each second: another save loaded in the same run may not have them) */
        static int64_t song_at;
        if (now >= song_at) {
            song_at = now + 1000000000LL;
            const int open = oot_door_song_held(c);
            if (open != __atomic_load_n(&oot_door_song_open, __ATOMIC_RELAXED)) {
                __atomic_store_n(&oot_door_song_open, open, __ATOMIC_RELEASE);
                hos_log("rando: Link %s the Song of Time and an ocarina: the Door of Time is %s from the next entry into the temple",
                        open ? "holds" : "no longer holds", open ? "open" : "shut");
            }
        }
        if (!__atomic_load_n(&oot_door_song_open, __ATOMIC_RELAXED)) return;
    }
    if (now >= flag_at) {   /* (each second) */
        int open = 1;
        flag_at = now + 1000000000LL;
        if (oot_gamedata_bool(c, OOT_DOOR_FLAG, &open) && !open && oot_gamedata_set_bool(c, OOT_DOOR_FLAG, 1))
            hos_log("rando: the Door of Time's flag was put out in this save: it is set (Open Door of Time)");
        open = 1;
        if (oot_gamedata_bool(c, OOT_LEFT_TEMPLE_FLAG, &open) && !open && oot_gamedata_set_bool(c, OOT_LEFT_TEMPLE_FLAG, 1))
            hos_log("rando: the adult's Market had no location in this save: its flag is set (Open Door of Time)");
    }
    /* (Shuffle the Master Sword, bug 106: the scene of the way to an adult, Dm_TimeTemple_0080, puts the Master Sword in
       Link's hand to sheathe it whatever his slot says, and he keeps it until a save is loaded, though the Equipment
       screen has none (the owner's test, 2026-11-21: the slot was empty after the flow's fix, the hand was not). When
       the scene is over and Link, an adult, holds no Master Sword in the pouch, it is put in the pouch and taken out
       again: the pouch's removal of an item drops it from his hand, as a burnt Deku Shield's does. Each trip to an adult) */
    static int drop_stage;
    static int64_t drop_at;
    if (drop_stage && now >= drop_at) {
        int loading_now = 0, child_now = 1;
        if (oot_event_playing(c) || (oot_gamedata_bool(c, 0xef2b60c2u, &loading_now) && loading_now) ||
            !oot_gamedata_bool(c, 0xcea220d3u, &child_now) || child_now) {
            drop_at = now + 500000000LL;   /* (the scene, the map's load, or not an adult yet: later) */
            if (child_now && !oot_event_playing(c) && !loading_now && ++drop_stage > 40) drop_stage = 0;   /* (a child for 20 s: no trip after all) */
        } else if (drop_stage < 100) {
            if (oot_pouch_count(c, "Weapon_Sword_Master") > 0) drop_stage = 0;   /* (he found it: his own) */
            else {
                hos_log("rando: Shuffle the Master Sword: the scene's sword is put in the pouch (%d) to be taken out", oot_pouch_change(c, "Weapon_Sword_Master", 1));
                drop_stage = 100, drop_at = now + 700000000LL;
            }
        } else {
            hos_log("rando: Shuffle the Master Sword: the scene's sword is taken out of the pouch and Link's hand (%d)", oot_pouch_change(c, "Weapon_Sword_Master", -1));
            drop_stage = 0;
        }
    }
    const int a = hos_pad_a_held(), pressed = a && !held;
    held = a;
    const float dx = oot_link_place[0] - OOT_SWORD_X, dz = oot_link_place[2] - OOT_SWORD_Z;
    char banc[80];
    const int beside = dx * dx + dz * dz <= OOT_SWORD_NEAR * OOT_SWORD_NEAR && oot_gamedata_string(c, 0x1d6189dau, banc, sizeof banc) &&
                       !strncmp(banc, "Market_", 7);   /* Sequence_CurrentBanc */
    if (!beside) {
        ask_at = 0;
        return;
    }
    if (pressed && !ask_at && !oot_event_playing(c)) ask_at = now + 500000000LL;
    if (!ask_at || now < ask_at) return;
    ask_at = 0;
    int loading = 0, child = 1;
    if (oot_event_playing(c) || (oot_gamedata_bool(c, 0xef2b60c2u, &loading) && loading)) return;   /* (the game answered: Sequence_IsLoadingBanc) */
    oot_gamedata_bool(c, 0xcea220d3u, &child);   /* Sequence_IsChildhood */
    const char *event = child ? "Market_Child_Field_ChildToAdult" : "Market_Adult_Field_AdultToChild";
    /* (the plain way through time does not give the sword: the story's drawing does, Dm_TimeTemple_0030. Seen
       without a window: an adult made so had none. So Link is given it here the first time) */
    const int shuffled = child ? oot_pedestal_give(c) : 0;   /* (Shuffle the Master Sword: the pedestal's own item) */
    if (child && shuffled == 0 && oot_pouch_count(c, "Weapon_Sword_Master") == 0)
        hos_log("rando: Open Door of Time: the Master Sword is given (event status %d)", oot_pouch_change(c, "Weapon_Sword_Master", 1));
    if (child && shuffled == 1) drop_stage = 1, drop_at = now + 2000000000LL;   /* (the scene's sword dropped after it, bug 106) */
    hos_log("rando: Open Door of Time: %s asked for at the Master Sword (%s)", event, oot_event_request(c, actor, event) ? "sent" : "NOT SENT");
}

/* (the age switch: the age it has just set, for the teleport that follows it at once; -1: read Link's. The flag is set
   through the game's setter, which queues the write, so read back at once it was still the old age: the switch
   reloaded the same age's map, which put the age back, and Link was only taken to the start of the area. Reported in
   play, 2026-11-15) */
static int oot_teleport_child = -1;

static int oot_teleport(Ctx *c, uint64_t actor, unsigned index) {
    teleport.why = "no such destination", teleport.banc = NULL;
    if (index >= sizeof oot_destinations / sizeof oot_destinations[0]) return 0;
    const int64_t now = hos_now_ns();
    if (teleport.requested_at && now - teleport.requested_at < 8000000000LL) {
        hos_log("cheats: teleport ignored, a request is still in progress");
        teleport.why = "another teleport is still in progress (one every 8 s)";
        return 0;
    }
    const uint64_t events = oot_singleton(c, OOT_EVENTMGR_SLOT);
    A64Fn make_arg = a64_lookup(0x80d99f10ULL), request = a64_lookup(0x80d9a820ULL);
    A64Fn set_link = a64_lookup(0x802dc440ULL), release_link = a64_lookup(0x8022b6f0ULL);
    if (!events || !make_arg || !request || !set_link || !release_link) {
        hos_log("cheats: teleport unavailable (event manager %#llx)", (unsigned long long)events);
        teleport.why = "the game's event manager is not there yet";
        return 0;
    }
    if (recomp_load64(c, events + 104)) {   /* (the Main sequence's "Event" test: an event is playing) */
        hos_log("cheats: teleport waits until the current event ends");
        teleport.why = "an event is playing (a cutscene, a map change's)";
        return 0;
    }
    int loading = 0, child = 1;
    if (oot_gamedata_bool(c, 0xef2b60c2u, &loading) && loading) {   /* Sequence_IsLoadingBanc */
        hos_log("cheats: teleport ignored while a map loads");
        teleport.why = "a map is loading";
        return 0;
    }
    if (oot_teleport_child >= 0) child = oot_teleport_child;
    else if (!oot_gamedata_bool(c, 0xcea220d3u, &child)) hos_log("cheats: Sequence_IsChildhood not found, using child maps");
    const OotDestination *d = &oot_destinations[index];
    const char *banc = child ? d->child_banc : d->adult_banc;
    const char *start = child ? d->child_start : d->adult_start;
    const char *boot = child ? d->child_boot : d->adult_boot;
    if (!banc) {
        hos_log("cheats: teleport %u has no %s map", index, child ? "child" : "adult");
        teleport.why = child ? "this destination has no map for the child" : "this destination has no map for the adult";
        return 0;
    }

    /* The event reads its string arguments after this request returns, so they live in memory that stays. */
    static uint64_t strings;
    if (!strings) strings = hos_sys_alloc(512, 16);
    if (!strings) return teleport.why = "out of memory", 0;
    memset(A64_PTR(strings), 0, 512);
    memcpy(A64_PTR(strings), banc, strlen(banc) + 1);
    memcpy(A64_PTR(strings + 128), start, strlen(start) + 1);
    memcpy(A64_PTR(strings + 256), boot, strlen(boot) + 1);

    const char *event_env = getenv("HOS_OOT_TELEPORT_EVENT");
    const char *event = event_env && *event_env ? event_env : "Dm_SY_BancChangeGo";
    const char *starter_env = getenv("HOS_OOT_TELEPORT_STARTER");
    const int with_starter = !(starter_env && !strcmp(starter_env, "0"));

    const Ctx saved = *c;
    const uint64_t arg = (c->x[31] - OOT_EVENT_ARG_SIZE - 0x100) & ~0xfULL;
    c->x[31] = arg;
    c->x[0] = arg;
    make_arg(c);
    int ok = 1;
    {   /* the event's name: arg+6800 points at its buffer, arg+6808 the capacity */
        const uint64_t buf = recomp_load64(c, arg + 6800);
        const uint32_t cap = recomp_load32(c, arg + 6808);
        if (!buf || strlen(event) + 1 > cap) ok = 0;
        else memcpy(A64_PTR(buf), event, strlen(event) + 1);
    }
    ok = ok && oot_event_arg(c, arg, "NextBanc", 1, strings);
    ok = ok && oot_event_arg(c, arg, "NextStartPos", 1, strings + 128);
    ok = ok && oot_event_arg(c, arg, "BootEventName", 1, strings + 256);
    ok = ok && oot_event_arg(c, arg, "IsCheckAir", 4, 0);
    if (ok && with_starter) {   /* the starter actor (arg+0x1950), as OneShotEventMemberRequestEventByEventName sets it */
        c->x[31] = arg;
        c->x[0] = arg + 0x1950, c->x[1] = actor, c->x[2] = 0;
        set_link(c);
    }
    uint64_t result = 0;
    if (ok) {
        c->x[31] = arg;
        c->x[0] = events, c->x[1] = arg;
        request(c);
        result = c->x[0];
    }
    /* SeqOneShotRequestEvent's cleanup of the arg's two actor links */
    for (unsigned i = 0; i < 2; i++) {
        const uint64_t link = arg + (i ? 0x1950 : 0x1968);
        recomp_store64(c, link, 0x84994b20ULL);
        c->x[31] = arg;
        c->x[0] = link;
        release_link(c);
    }
    *c = saved;
    /* (issues 2217, 2588) A map-hiding area can leave this saved flag set when a debug teleport skips its exit.
       Only clear it once the event manager takes the request; the destination may hide its own minimap.
       Use the game's Bool setter (mgr, value, hash): it queues the change for the live value AND the save's copy.
       Writing only the live byte restores the HUD until the next load, but saves keep the old hidden value. */
    int hidden = 0;
    if (ok && result && oot_gamedata_bool(c, 0x9a4dd779u, &hidden) && hidden) {
        A64Fn set_bool = a64_lookup(0x806a2b20ULL);
        const uint64_t mgr = oot_singleton(c, OOT_GAMEDATA_SLOT);
        if (set_bool && mgr) {
            c->x[0] = mgr, c->x[1] = 0, c->x[2] = 0x9a4dd779u;   /* MapIconDeactivateByAreaActor */
            set_bool(c);
            *c = saved;
            hos_log("cheats: teleport: the area left had hidden the minimap (MapIconDeactivateByAreaActor): restore queued");
        } else {   /* (another game build: say so, a report's log then shows why the minimap stayed away) */
            hos_log("cheats: teleport: the area left had hidden the minimap (MapIconDeactivateByAreaActor): %s not found, left hidden",
                    set_bool ? "the game data manager" : "the game's Bool setter");
        }
    }
    teleport.requested_at = now;
    teleport.check_at = now + 1500000000LL;
    teleport.destination = index;
    hos_log("cheats: teleport %s to %s at %s (boot %s, event %s, starter %d): request %s, result %#llx",
            child ? "child" : "adult", banc, start, boot, event, with_starter, ok ? "sent" : "not built",
            (unsigned long long)result);
    teleport.result = result;
    if (ok) teleport.banc = banc;
    else teleport.why = "the game's event request could not be built";
    return ok;   /* (sent; the request's own result is only logged) */
}

/* Writes a GameData bool directly: GameDataMgr+32 is the (hash, index) table (+44 its size), the bools are 24-byte
   entries at GameDataMgr+24 (+16 their count) with the value at +22, as f_8022d9c0 reads them. 1 when found. */
/* A truth value of the list set. By the game's own setter (f_806a2b20: the manager, the value, the name's hash), which
   puts the write in the manager's queue: the value is the game's some frames later, and it is in the next save.
   (Until 2026-11-14 the value's byte was written where it is, +22 of the flag's 24 bytes: the game saw it at once, but
   a save made after did not have it. Seen in a save's file: HavePlayedEvent.Dm_TimeTemple_0065 set so, then the
   game's own save, and the file had it false.) Where the setter is not found the byte is written as before. */
static int oot_gamedata_set_bool(Ctx *c, uint32_t hash, int value) {
    const uint64_t mgr = oot_singleton(c, OOT_GAMEDATA_SLOT);
    if (!mgr) return 0;
    const uint64_t table = recomp_load64(c, mgr + 32);
    const uint32_t size = recomp_load32(c, mgr + 44);
    if (!table || !size) return 0;
    for (uint32_t probe = 0, slot = hash % size; probe < size; probe++, slot = (slot + 1) % size) {
        const uint32_t key = recomp_load32(c, table + slot * 8ULL);
        if (!key) return 0;
        if (key != hash) continue;
        const uint32_t index = recomp_load32(c, table + slot * 8ULL + 4), count = recomp_load32(c, mgr + 16);
        if (index >= count) return 0;
        A64Fn set = a64_lookup(0x806a2b20ULL);
        if (set) {
            const Ctx saved = *c;
            c->x[0] = mgr, c->x[1] = value ? 1 : 0, c->x[2] = hash;
            set(c);
            *c = saved;
        } else {
            recomp_store8(c, recomp_load64(c, mgr + 24) + index * 24ULL + 22, value ? 1 : 0);
        }
        return 1;
    }
    return 0;
}

/* A whole value of the list of flags that is one of a set of names (Data.Enum: a quest's step is one, the hash of the
   step's name), read and written directly: GameDataMgr+0x258 are the entries, 56 bytes each with the value at +0x1c
   and again at +0x20, and +0x260 their (hash, index) table (+0x26c its size), as the bools' are at +24 and +32 (found
   in the manager's memory written to a file: the quests AllSage and DoorOfTime, by their steps' hashes). 1 when found. */
static int oot_gamedata_enum(Ctx *c, uint32_t hash, uint32_t *value, int set) {
    const uint64_t mgr = oot_singleton(c, OOT_GAMEDATA_SLOT);
    if (!mgr) return 0;
    const uint64_t table = recomp_load64(c, mgr + 0x260);
    const uint32_t size = recomp_load32(c, mgr + 0x26c);
    if (!table || !size) return 0;
    for (uint32_t probe = 0, slot = hash % size; probe < size; probe++, slot = (slot + 1) % size) {
        const uint32_t key = recomp_load32(c, table + slot * 8ULL);
        if (!key) return 0;
        if (key != hash) continue;
        const uint32_t index = recomp_load32(c, table + slot * 8ULL + 4), count = recomp_load32(c, mgr + 0x250);
        if (index >= count) return 0;
        const uint64_t entry = recomp_load64(c, mgr + 0x258) + index * 56ULL;
        if (set) {
            recomp_store32(c, entry + 0x1c, *value);
            recomp_store32(c, entry + 0x20, *value);
        } else *value = recomp_load32(c, entry + 0x1c);
        return 1;
    }
    return 0;
}

/* (the randomizer's fork) Ganon's Castle's bridge (the setting rando_ganon_bridge: 1 open, 2 once Link holds the six
   medallions). The bridge (Obj_GanonCastle_Bridge_A_01 in GanonCastle_Static) is made once its scene has played
   (HavePlayedEvent.GanonCastle_Adult_Field_Rainbow), and the castle's field asks for that scene (Defeat_Ganon's flow,
   GanonCastle_Adult_Field_Rainbow) when the quest Defeat_Ganon is at its Ready step and Link stands at the castle's edge.
   The game sets Ready only after the Shadow and Spirit sages' scenes (AllSage's SageRoom_AllSage_LastSage, which moves
   that quest on). So here the quest is set from NotReady to Ready by the setting, and the bridge's own scene then plays
   and moves the quest on as the game does (its first action, to Step01); the castle's inside reads the later steps.
   Should the sages' scene later set the quest back to Ready after the bridge's has played, the step it had is put back
   (Ready with the bridge's scene played is a step the game never has). */
#define OOT_STEP_DEFEAT_GANON 0x746f47c0u   /* Step_Defeat_Ganon (a Data.Enum: its value the hash of a step's name) */
#define OOT_STEP_NOTREADY 0x57b849f0u        /* NotReady */
#define OOT_STEP_READY 0x17bfaa46u           /* Ready */
#define OOT_STEP_01 0xeb62add9u              /* Step01: what the bridge's scene moves Ready on to */
#define OOT_RAINBOW_FLAG 0x75022258u         /* HavePlayedEvent.GanonCastle_Adult_Field_Rainbow */
static const char *const oot_medallions[6] = {"Item_Medal_Forest", "Item_Medal_Fire", "Item_Medal_Water",
                                              "Item_Medal_Shadow", "Item_Medal_Spirit", "Item_Medal_Light"};
static void oot_ganon_bridge(Ctx *c, int64_t now) {
    int hos_rando_ganon_bridge(void);   /* host/oot_rando.c */
    static int64_t next_at;
    static uint32_t later;   /* (the quest's last step past Ready seen this session) */
    const int mode = hos_rando_ganon_bridge();
    if (!mode || now < next_at) return;
    next_at = now + 1000000000LL;   /* (each second) */
    uint32_t step = 0;
    if (!oot_gamedata_enum(c, OOT_STEP_DEFEAT_GANON, &step, 0)) return;
    /* (Willow Woods, the owner's test 2026-11-19: Open set no step in a new game. A quest the story has not touched may
       hold 0, no step yet: it is NotReady. What was read is logged once a session, to see it in play) */
    static uint32_t logged = 1;
    if (step != logged) { hos_log("rando: Ganon's quest's step read as %08x (Ganon's Castle bridge)", step); logged = step; }
    if (step == 0) step = OOT_STEP_NOTREADY;
    if (step != OOT_STEP_NOTREADY && step != OOT_STEP_READY) {
        later = step;
        return;
    }
    if (step == OOT_STEP_READY) {
        int played = 0;
        if (later || (oot_gamedata_bool(c, OOT_RAINBOW_FLAG, &played) && played)) {
            uint32_t back = later ? later : OOT_STEP_01;
            if (oot_gamedata_enum(c, OOT_STEP_DEFEAT_GANON, &back, 1))
                hos_log("rando: Ganon's quest was set back to Ready after the bridge's scene: its step %08x is put back (Ganon's Castle bridge)",
                        back);
            return;
        }
        /* (Ready with the scene not played: the bridge is made below, as from NotReady) */
    }
    int held = 0;
    int hos_rando_bridge_medallions(void);   /* host/oot_rando.c: 6 to 3 (the setting Bridge medallions) */
    const int need = hos_rando_bridge_medallions();
    if (mode == 2)
        for (int i = 0; i < 6; i++) held += oot_pouch_count(c, oot_medallions[i]) > 0;
    if (mode == 1 || (mode == 2 && held >= need)) {
        /* (Willow Woods, the owner's test 2026-11-19, then without a window 2026-11-20: with the quest at Ready, Link
           stood at the castle's edge and the bridge's scene never played: he fell. So the bridge is made as its scene
           leaves it: the scene marked played (the bridge is there from the map's next load) and the quest at Step01) */
        oot_gamedata_set_bool(c, OOT_RAINBOW_FLAG, 1);
        uint32_t next = OOT_STEP_01;
        if (oot_gamedata_enum(c, OOT_STEP_DEFEAT_GANON, &next, 1))
            hos_log("rando: Ganon's Castle's bridge made: its scene marked played, the quest at Step01 (Ganon's Castle bridge, %s, %d held)",
                    mode == 1 ? "Open" : "medallions", held);
    }
}

/* (the randomizer's fork) Kakariko gate: Open (the setting rando_letter at 2): Kakariko's gate to Death Mountain
   (Land_Kakariko_Gate_A_02) opens and closes for a child by the quest Get_StoneOfFire's step (the logic files
   KakarikoVillage_Child_OpenGate_Prefab_1fcc and _GateClose_Prefab_6b8b: HoldChallengeCurrentStepCheckOrder, bug 83), and
   showing Zelda's Letter to the guard (Npc_Hylia_Soldier_003) sets his flag Npc_Hylia_Soldier_003_GateOpen and takes the
   quest to KakarikoVillageLetter. The quest's steps, in the list of flags' order (Data.Enum RawValues): NotReady, Ready,
   KakarikoVillageNpc, KakarikoVillageLetter, DeathMtTrailIn, ... The open gate's logic file asks for DeathMtTrailIn
   (and the closed one's for KakarikoVillageLetter): the guard's scene opens it and arriving on the trail takes the quest
   on. So with the setting the quest, while before DeathMtTrailIn, is set to it (each second: a scene that sets it back,
   Zelda's meeting among them, is undone), and the guard's flag is set. That is the step an adult's first arrival on the
   trail leaves the quest at (bug 83: the gate was then open for the child, seen in play). The steps past it are the
   game's, as it plays. */
#define OOT_STEP_STONE_FIRE 0x1002b466u    /* Step_Get_StoneOfFire */
#define OOT_STEP_KAK_NPC 0x4011c4aau       /* KakarikoVillageNpc */
#define OOT_STEP_KAK_LETTER 0x4d329ec9u    /* KakarikoVillageLetter */
#define OOT_STEP_TRAIL_IN 0x1d5e4b01u      /* DeathMtTrailIn: what the open gate's logic asks for */
#define OOT_GATE_OPEN_FLAG 0x19898d14u     /* Npc_Hylia_Soldier_003_GateOpen */
static void oot_open_death_mountain(Ctx *c, int64_t now) {
    int hos_rando_open_dm(void);   /* host/oot_rando.c */
    static int64_t next_at;
    if (!hos_rando_open_dm() || now < next_at) return;
    next_at = now + 1000000000LL;   /* (each second) */
    uint32_t step = 0;
    if (!oot_gamedata_enum(c, OOT_STEP_STONE_FIRE, &step, 0)) return;
    if (step == OOT_STEP_NOTREADY || step == OOT_STEP_READY || step == OOT_STEP_KAK_NPC || step == OOT_STEP_KAK_LETTER) {
        uint32_t in = OOT_STEP_TRAIL_IN;
        if (oot_gamedata_enum(c, OOT_STEP_STONE_FIRE, &in, 1))
            hos_log("rando: the Goron's quest set from %08x to DeathMtTrailIn: Kakariko's gate is open (Kakariko gate: Open)", step);
    }
    int open = 0;
    if (oot_gamedata_bool(c, OOT_GATE_OPEN_FLAG, &open) && !open && oot_gamedata_set_bool(c, OOT_GATE_OPEN_FLAG, 1))
        hos_log("rando: the gate's guard has seen the letter (Kakariko gate: Open)");
}

/* A whole number of the list of flags (Data.Int: PlayerStatus.MaxLife, in quarter hearts), read or written directly:
   the Ints are kept as the Enums are, from GameDataMgr+0xc8 (host/oot_state_tap.c state_kind): +0xd0 how many, +0xd8
   the entries of 40 bytes with the value at +0x1c, +0xe0 the (hash, index) table and +0xec its size. 1 when found. */
static int oot_gamedata_int(Ctx *c, uint32_t hash, int32_t *value, int set) {
    const uint64_t mgr = oot_singleton(c, OOT_GAMEDATA_SLOT);
    if (!mgr) return 0;
    const uint64_t table = recomp_load64(c, mgr + 0xe0);
    const uint32_t size = recomp_load32(c, mgr + 0xec);
    if (!table || !size) return 0;
    for (uint32_t probe = 0, slot = hash % size; probe < size; probe++, slot = (slot + 1) % size) {
        const uint32_t key = recomp_load32(c, table + slot * 8ULL);
        if (!key) return 0;
        if (key != hash) continue;
        const uint32_t index = recomp_load32(c, table + slot * 8ULL + 4), count = recomp_load32(c, mgr + 0xd0);
        if (index >= count) return 0;
        const uint64_t entry = recomp_load64(c, mgr + 0xd8) + index * 40ULL;
        if (set) {
            if (recomp_load32(c, entry + 0x20) == recomp_load32(c, entry + 0x1c)) recomp_store32(c, entry + 0x20, (uint32_t)*value);
            recomp_store32(c, entry + 0x1c, (uint32_t)*value);
        } else *value = (int32_t)recomp_load32(c, entry + 0x1c);
        return 1;
    }
    return 0;
}

/* (Willow Woods) A whole number as the game reads it: GameDataMgr's second table first, its "live" entries (+0x140 the
   (hash, index) table, +0x14c its size, +0x130 how many, +0x138 the entries of 64 bytes: +0x28 a pointer to the number
   where it really lives, the player's own for PlayerStatus.MP), then the Ints (oot_gamedata_int). Found in the game's code
   2026-11-20 (f_805a7e80, f_8049b390 read PlayerStatus.MP so): the magic written in the Ints alone showed on the meter and
   was the player's own again at the end of an item's scene. Written: both. *live: 1 when a live entry was there. */
static int oot_gamedata_live_int(Ctx *c, uint32_t hash, int32_t *value, int set, int *live) {
    if (live) *live = 0;
    const uint64_t mgr = oot_singleton(c, OOT_GAMEDATA_SLOT);
    if (!mgr) return 0;
    const uint64_t table = recomp_load64(c, mgr + 0x140);
    const uint32_t size = recomp_load32(c, mgr + 0x14c);
    uint64_t where = 0;
    for (uint32_t probe = 0, slot = size ? hash % size : 0; table && size && probe < size; probe++, slot = (slot + 1) % size) {
        const uint32_t key = recomp_load32(c, table + slot * 8ULL);
        if (!key) break;
        if (key != hash) continue;
        const uint32_t index = recomp_load32(c, table + slot * 8ULL + 4), count = recomp_load32(c, mgr + 0x130);
        if (index < count) where = recomp_load64(c, recomp_load64(c, mgr + 0x138) + index * 64ULL + 0x28);
        break;
    }
    if (where && live) *live = 1;
    if (!set) {
        if (where) {
            *value = (int32_t)recomp_load32(c, where);
            return 1;
        }
        return oot_gamedata_int(c, hash, value, 0);
    }
    if (where) recomp_store32(c, where, (uint32_t)*value);
    return oot_gamedata_int(c, hash, value, 1) || where;
}

/* What the game knows by an actor's hash (the list of flags' Bool64bitKey: a chest, a shelf that sells out): found in
   the running game by looking for known hashes in its memory. GameDataMgr+0xc58 is how many there are, +0xc60 their
   table, sorted by the hash, of 16 bytes each (the hash, then its reset type in the low half of the next word), and
   +0xc70 what follows the table. The place of a hash in the table, or -1. */
#define OOT_KEYED_COUNT 0xc58
#define OOT_KEYED_TABLE 0xc60
#define OOT_KEYED_VALUES 0xc70
static int64_t oot_gamedata_keyed_index(Ctx *c, uint64_t key, uint32_t *reset) {
    const uint64_t mgr = oot_singleton(c, OOT_GAMEDATA_SLOT);
    if (!mgr) return -1;
    const uint32_t count = recomp_load32(c, mgr + OOT_KEYED_COUNT);
    const uint64_t table = recomp_load64(c, mgr + OOT_KEYED_TABLE);
    if (!table || !count || count > 0x100000) return -1;
    uint32_t low = 0, high = count;
    while (low < high) {
        const uint32_t mid = low + (high - low) / 2;
        const uint64_t at = recomp_load64(c, table + mid * 16ULL);
        if (at == key) {
            if (reset) *reset = recomp_load32(c, table + mid * 16ULL + 8);
            return mid;
        }
        if (at < key) low = mid + 1;
        else high = mid;
    }
    return -1;
}

/* The truth value the game keeps by an actor's hash: the byte at 12 of its 16 in the table (github.com/Mozencaz/OotrR
   live_memory.py has it so, after the PracticeROM's notes). 1 and *out, or 0 when the table has no such hash. */
static int oot_gamedata_keyed_bool(Ctx *c, uint64_t key, int *out) {
    const int64_t i = oot_gamedata_keyed_index(c, key, NULL);
    if (i < 0) return 0;
    *out = recomp_load8(c, recomp_load64(c, oot_singleton(c, OOT_GAMEDATA_SLOT) + OOT_KEYED_TABLE) + (uint64_t)i * 16 + 12) != 0;
    return 1;
}
/* (set by the game's own setter, f_80f27130: the manager, the value, the hash. It puts the write in a queue of the
   manager's, as the truth values by name have one; the byte written where it is was not in the next save) */
static int oot_gamedata_keyed_set_bool(Ctx *c, uint64_t key, int value) {
    const uint64_t mgr = oot_singleton(c, OOT_GAMEDATA_SLOT);
    A64Fn set = a64_lookup(0x80f27130ULL);
    if (!set || oot_gamedata_keyed_index(c, key, NULL) < 0) return 0;
    const Ctx saved = *c;
    c->x[0] = mgr, c->x[1] = value ? 1 : 0, c->x[2] = key;
    set(c);
    *c = saved;
    return 1;
}

/* (the randomizer's fork) What the Tracker tab says is collected: the randomizer's own record. The game's flag for a chest
   opened was looked for and not found (tools/rando/README.md says where), so the record is kept here: the pouch
   manager's add (hos_oot_pouch_add, below) sees every item given and tells oot_tracker_item, which marks the check of
   the seed that gives that item nearest to where Link stands, in the map he is in (a check further than
   OOT_CHECK_NEAR is not his; an item only one check of the whole seed still gives is that check's wherever he is: a
   gift given indoors). What each check gives is the last field of its line of <game folder>/mods/rando-seed/checks.txt.
   The record is <game folder>/rando/collected.txt: the seed's stamp it is of (the first line of the seed's
   rando_stamp.txt), then the collected checks' places in the checks file. Another seed's record is not taken. It is
   one record for the folder, not for a save: a new game of the same seed keeps it until it is forgotten (the Tracker
   tab's first row, the action 6), and a save from before a check was collected still says it is. Checks collected
   before there was a record are not in it.
   Since 2026-11-14 that is so only of a seed made before (a gift's line without a key): a gift's line has the key of
   a chest's second value, which nothing else uses (tools/rando/rando_seed.py gift_keys), and is marked as a chest is. A check
   that is an actor of a map (a chest, a Gold Skulltula, a Piece of Heart: its line has the actor's hash) is marked
   in the save itself: the game's list has a truth value for every such actor by its hash (Bool64bitKey), saved,
   which the game was not seen to set for a chest (no save looked at had one, and a chest with it set was shut as
   before: seen without a window in Mido's house). It is set when the check is collected, by the game's own setter,
   and the mark of such a check is what the save loaded says (oot_shelf_flags). A shelf has its own flag. So a save
   from before, and a new game of the seed, have their own marks.
   Found 2026-11-17 (bug 70, a blue rupee chest never marked): the game does keep a chest opened, in the flag
   IsTreasureBoxOpen.<the chest's actor hash, in decimal> (murmur3, as every flag; REALAZK's OOTRR named it, checked
   here in saves: 0 for the chests not opened, 1 for Mido's house's opened ones). A chest's check is marked by it too
   (oot_shelf_flags), so a chest whose item reaches Link by no add the record sees (a blue rupee's) is marked. */
#define OOT_CHECK_NEAR 60.0f
static float oot_load_float(Ctx *c, uint64_t addr);
static int oot_gamedata_string(Ctx *c, uint32_t hash, char *buf, size_t size);
int hos_rando_on(void);   /* host/oot_rando.c */
static int oot_banc_in_folder(const char *banc, const char *folder);
static struct {
    char item[64], folder[40];
    float place[3];
    signed char done;
    uint64_t piece;   /* (a Piece of Heart lying in the world: its actor's hash; 0: another kind of check) */
    int boss;         /* (a boss's Heart Container: tools/rando/rando_seed.py BOSS_HEARTS, bug 31) */
    uint32_t shelf;   /* (a shop's shelf: the hash of the flag it waits for, "still for sale"; 0: another kind of check) */
    signed char sold; /* (a shelf bought, or a check with a key collected, just now: its flag is to be set, oot_shelf_flags) */
    int price;        /* (a shop's shelf: its price, from its name's ", <n> rupees"; -1: none) */
    char ages[4];     /* (C, A or CA: which Link has it in the game's maps) */
    uint64_t key;     /* (an actor of a map: its hash, by which the save keeps a truth value; 0: none) */
    uint32_t opened;  /* (a chest: the hash of the game's own flag IsTreasureBoxOpen.<key in decimal>, set when it is opened, bug 70; 0: none) */
    char owner[24];   /* (a chest holding a dungeon item of another place: the dungeon it belongs to, dungeon_items.txt; "": none) */
    signed char pot;  /* (a pot of Pots, rando_pots: tools/rando/rando_seed.py names it "Pot", "Pot #2"...: oot_pot_again) */
    signed char pot_kept;   /* (a pot: in the record, collected in some game of the seed: oot_pot_progress) */
    int pot_at;             /* (a pot: the save's progress it was collected at, oot_pot_progress; -1 not known) */
    uint64_t broken;  /* (a pot's hash: the game's truth value by it is "broken", oot_pot_again) */
    signed char skull;      /* (a Gold Skulltula: tools/rando/rando_seed.py names it "Gold Skulltula...": oot_skull_item) */
    signed char claimed;    /* (a Gold Skulltula the save marked by itself: the drop it gave has been added since) */
    int64_t marked_at;      /* (when the save's own mark was first seen on it, oot_shelf_flags; 0: not seen, or the record's) */
} oot_checks[OOT_TRACKER_MAX];
static int oot_check_count = -1;
static int oot_dungeon_words;   /* (the seed has each dungeon's "You found" words: dungeon_words.txt, bug 141) */
#define OOT_KEYRING_MAX 16
static struct { char folder[24]; int keys; } oot_keyrings[OOT_KEYRING_MAX];   /* (Key rings: keyrings.txt, oot_keyring) */
static int oot_keyring_n;
static char oot_dungeon_own[24];   /* (oot_dungeon_owner: the dungeon whose item was got inside it, for its ring's other keys) */
/* (Dungeon entrances, the owner's ask 2026-11-27: "the tracker to only show what dungeon it leads to after you've entered
   it once already in the seed") The seed's doors, mods/rando-seed/entrances.txt (<a door's own dungeon>|<the dungeon behind
   it>|...), each found once Link has stood in the dungeon behind it. The found ones are the seed's record,
   rando/doors_seen.txt: "seed <the stamp>", then a door's own dungeon a line, which the Tracker reads (gpu/vk/vk_menu.cpp
   tracker_doors_load). Another seed's record is not taken. A teleport into the dungeon finds its door too. */
#define OOT_DOORS_MAX 16
static char oot_checks_seed[1024];   /* (defined with the tracker's lists below: the seed's stamp) */
static struct { char door[24], dungeon[24]; int seen; } oot_doors[OOT_DOORS_MAX];
static int oot_door_n;
static void oot_doors_save(void) {
    char path[MAX_PATH + 48];
    FILE *f = oot_game_file(path, sizeof path, "rando/doors_seen.txt") ? fopen(path, "w") : NULL;
    if (!f) return;
    fprintf(f, "seed %s\n", oot_checks_seed);
    for (int i = 0; i < oot_door_n; i++)
        if (oot_doors[i].seen) fprintf(f, "%s\n", oot_doors[i].door);
    fclose(f);
}
/* (oot_checks_lock held) the door of the dungeon whose map Link is in is found: 1 when one was just now */
static int oot_doors_note(const char *map) {
    int found = 0;
    for (int i = 0; i < oot_door_n; i++)
        if (!oot_doors[i].seen && map[0] && oot_banc_in_folder(map, oot_doors[i].dungeon)) {
            oot_doors[i].seen = 1, found = 1;
            hos_log("rando: dungeon entrances: %s's door found to lead to %s", oot_doors[i].door, oot_doors[i].dungeon);
        }
    if (found) oot_doors_save();
    return found;
}
static void oot_doors_load(const char *stamp) {
    char path[MAX_PATH + 48], line[1100];
    oot_door_n = 0;
    FILE *f = oot_game_file(path, sizeof path, "mods/rando-seed/entrances.txt") ? fopen(path, "r") : NULL;
    while (f && oot_door_n < OOT_DOORS_MAX && fgets(line, sizeof line, f)) {
        char door[24], dungeon[24];
        if (sscanf(line, "%23[A-Za-z]|%23[A-Za-z]", door, dungeon) != 2) continue;
        snprintf(oot_doors[oot_door_n].door, sizeof oot_doors[0].door, "%s", door);
        snprintf(oot_doors[oot_door_n].dungeon, sizeof oot_doors[0].dungeon, "%s", dungeon);
        oot_doors[oot_door_n++].seen = 0;
    }
    if (f) fclose(f);
    int seen = 0;
    f = oot_door_n && oot_game_file(path, sizeof path, "rando/doors_seen.txt") ? fopen(path, "r") : NULL;
    if (f && fgets(line, sizeof line, f)) {
        line[strcspn(line, "\r\n")] = 0;
        if (!strncmp(line, "seed ", 5) && !strcmp(line + 5, stamp))   /* (this seed's record) */
            while (fgets(line, sizeof line, f)) {
                line[strcspn(line, "\r\n")] = 0;
                for (int i = 0; i < oot_door_n; i++)
                    if (!strcmp(line, oot_doors[i].door) && !oot_doors[i].seen) oot_doors[i].seen = 1, seen++;
            }
    }
    if (f) fclose(f);
    if (oot_door_n) hos_log("rando: dungeon entrances: %d doors of the seed, %d of them found by the record", oot_door_n, seen);
}
/* (Boss shuffle, the owner's ask 2026-11-27: the Tracker says which boss a room leads to, as a door's dungeon, only once
   Link has been through it) The seed's boss rooms, mods/rando-seed/boss_doors.txt (<a boss's room's dungeon>|<the dungeon
   whose boss is fought from it>|...). A room that leads to another boss is found when Link's map changes from its dungeon
   straight to the boss's and he stands in that boss's room (the event of ours that sends him: nothing else changes map
   between two dungeons); a room that keeps its boss, when he stands in it. The found ones are the seed's record,
   rando/boss_rooms_seen.txt, as the doors' (gpu/vk/vk_menu.cpp reads it). */
#define OOT_BOSS_ROOM_NEAR 30.0f
static struct { char room[24], boss[24]; int seen; } oot_boss_doors[OOT_DOORS_MAX];
static int oot_boss_door_n;
static void oot_boss_doors_save(void) {
    char path[MAX_PATH + 48];
    FILE *f = oot_game_file(path, sizeof path, "rando/boss_rooms_seen.txt") ? fopen(path, "w") : NULL;
    if (!f) return;
    fprintf(f, "seed %s\n", oot_checks_seed);
    for (int i = 0; i < oot_boss_door_n; i++)
        if (oot_boss_doors[i].seen) fprintf(f, "%s\n", oot_boss_doors[i].room);
    fclose(f);
}
/* (oot_checks_lock held) map: where Link is, left: the map he was in before it, since: how long ago he left it (ns),
   place: where he stands; near(folder): he stands in that dungeon's boss's room. 1 when a room was found just now */
static int oot_boss_doors_note(const char *map, const char *left, int64_t since, int (*near)(const char *folder)) {
    int found = 0;
    for (int i = 0; i < oot_boss_door_n; i++) {
        if (oot_boss_doors[i].seen || !map[0] || !oot_banc_in_folder(map, oot_boss_doors[i].boss) || !near(oot_boss_doors[i].boss)) continue;
        const int same = !strcmp(oot_boss_doors[i].room, oot_boss_doors[i].boss);
        if (!same && !(left[0] && oot_banc_in_folder(left, oot_boss_doors[i].room) && since < 30000000000LL)) continue;
        oot_boss_doors[i].seen = 1, found = 1;
        hos_log("rando: boss shuffle: %s's boss's room found to lead to %s's boss", oot_boss_doors[i].room, oot_boss_doors[i].boss);
    }
    if (found) oot_boss_doors_save();
    return found;
}
static void oot_boss_doors_load(const char *stamp) {
    char path[MAX_PATH + 48], line[1100];
    oot_boss_door_n = 0;
    FILE *f = oot_game_file(path, sizeof path, "mods/rando-seed/boss_doors.txt") ? fopen(path, "r") : NULL;
    while (f && oot_boss_door_n < OOT_DOORS_MAX && fgets(line, sizeof line, f)) {
        char room[24], boss[24];
        if (sscanf(line, "%23[A-Za-z]|%23[A-Za-z]", room, boss) != 2) continue;
        snprintf(oot_boss_doors[oot_boss_door_n].room, sizeof oot_boss_doors[0].room, "%s", room);
        snprintf(oot_boss_doors[oot_boss_door_n].boss, sizeof oot_boss_doors[0].boss, "%s", boss);
        oot_boss_doors[oot_boss_door_n++].seen = 0;
    }
    if (f) fclose(f);
    int seen = 0;
    f = oot_boss_door_n && oot_game_file(path, sizeof path, "rando/boss_rooms_seen.txt") ? fopen(path, "r") : NULL;
    if (f && fgets(line, sizeof line, f)) {
        line[strcspn(line, "\r\n")] = 0;
        if (!strncmp(line, "seed ", 5) && !strcmp(line + 5, stamp))   /* (this seed's record) */
            while (fgets(line, sizeof line, f)) {
                line[strcspn(line, "\r\n")] = 0;
                for (int i = 0; i < oot_boss_door_n; i++)
                    if (!strcmp(line, oot_boss_doors[i].room) && !oot_boss_doors[i].seen) oot_boss_doors[i].seen = 1, seen++;
            }
    }
    if (f) fclose(f);
    if (oot_boss_door_n) hos_log("rando: boss shuffle: %d boss rooms of the seed, %d of them found by the record", oot_boss_door_n, seen);
}
static char oot_checks_seed[1024];   /* (the stamp the checks and the record are of: its whole first line. 200 cut a
   seed's 243-304 characters short, so a record written with the whole line was never this seed's, 2026-11-19) */
static float oot_link_place[3];
static char oot_link_map[80];
/* (bug 124, the owner's run 2026-11-23: the Song of Time's lesson at the castle's moat gave its item just as the game
   took Link to another map, and the check was not marked: the add was looked for in the new map only. The map Link
   left, and his last place there, count for OOT_LEFT_MAP_NS after: oot_tracker_item) */
static char oot_left_map[80];
static float oot_left_place[3];
static int64_t oot_left_at;
static float oot_link_place_was[3];
/* (bug 125, the owner's run 2026-11-23: Gerudo Valley's invisible grotto chest, an adult's, marked the child's copy at the
   same place, both giving a red rupee. Of the checks of an add's item, the ones Link's age has come first:
   oot_tracker_item. 1 child, 0 adult, -1 not known; oot_tracker_refresh reads it each second) */
static int oot_link_child = -1;   /* (Link's place at the last second's look: his last in a map he then leaves) */
#define OOT_LEFT_MAP_NS 30000000000LL
static SRWLOCK oot_checks_lock = SRWLOCK_INIT;

/* <game folder>/<tail>, into out: 1, or 0 when the game's folder is not known */
static int oot_game_file(char *out, size_t size, const char *tail) {
    char exe[MAX_PATH];
    const DWORD n = hos_game_path_a(exe, MAX_PATH);
    if (!n || n >= MAX_PATH) return 0;
    char *slash = strrchr(exe, '\\');
    char *other = strrchr(exe, '/');
    if (other > slash) slash = other;
    if (!slash) return 0;
    *slash = 0;
    snprintf(out, size, "%s/%s", exe, tail);
    return 1;
}

/* (the lock held) the record, written whole */
static void oot_tracker_save(void) {
    char path[MAX_PATH + 48];
    FILE *f = oot_game_file(path, sizeof path, "rando/collected.txt") ? fopen(path, "w") : NULL;
    if (!f) return;
    fprintf(f, "seed %s\n", oot_checks_seed);
    for (int i = 0; i < oot_check_count; i++)
        if (oot_checks[i].pot && oot_checks[i].pot_kept) fprintf(f, "%d:%d\n", i, oot_checks[i].pot_at);   /* (oot_pot_progress) */
        else if (!oot_checks[i].pot && oot_checks[i].done == 1) fprintf(f, "%d\n", i);
    fclose(f);
}

/* (the lock held) the seed's stamp as it is now, the first line of its file without the line's end: 1, or 0 with no seed */
static int oot_tracker_stamp(char *out, size_t size) {
    char path[MAX_PATH + 48];
    FILE *f = oot_game_file(path, sizeof path, "mods/rando-seed/rando_stamp.txt") ? fopen(path, "r") : NULL;
    out[0] = 0;
    if (!f) return 0;
    if (!fgets(out, (int)size, f)) out[0] = 0;
    fclose(f);
    out[strcspn(out, "\r\n")] = 0;
    return out[0] != 0;
}

/* MurmurHash3 x86 32, seed 0: the hash the game names its flags by (as host/oot_state_tap.c state_murmur) */
static uint32_t oot_flag_hash(const char *s) {
    const size_t n = strlen(s);
    uint32_t h = 0, k;
    size_t i = 0;
    for (; i + 4 <= n; i += 4) {
        k = (uint32_t)(unsigned char)s[i] | (uint32_t)(unsigned char)s[i + 1] << 8 | (uint32_t)(unsigned char)s[i + 2] << 16 |
            (uint32_t)(unsigned char)s[i + 3] << 24;
        k *= 0xcc9e2d51u, k = k << 15 | k >> 17, k *= 0x1b873593u;
        h ^= k, h = h << 13 | h >> 19, h = h * 5 + 0xe6546b64u;
    }
    k = 0;
    switch (n & 3) {
    case 3: k ^= (uint32_t)(unsigned char)s[i + 2] << 16; /* fall through */
    case 2: k ^= (uint32_t)(unsigned char)s[i + 1] << 8; /* fall through */
    case 1: k ^= (uint32_t)(unsigned char)s[i]; k *= 0xcc9e2d51u, k = k << 15 | k >> 17, k *= 0x1b873593u, h ^= k;
    }
    h ^= (uint32_t)n, h ^= h >> 16, h *= 0x85ebca6bu, h ^= h >> 13, h *= 0xc2b2ae35u, h ^= h >> 16;
    return h;
}

#define OOT_SUN_CHECK "Fire Arrows, the sun's shot"   /* (tools/rando/rando_seed.py SUN_NAME's start) */
/* (the lock held) the seed's checks with what each gives, and the record of that seed */
static void oot_tracker_load(const char *stamp) {
    char path[MAX_PATH + 48], line[1100];
    static char kinds[OOT_TRACKER_MAX + 1][80];   /* (each check's name, to find the shelves by) */
    oot_check_count = 0;
    snprintf(oot_checks_seed, sizeof oot_checks_seed, "%s", stamp);
    FILE *f = oot_game_file(path, sizeof path, "mods/rando-seed/checks.txt") ? fopen(path, "r") : NULL;
    while (f && oot_check_count < OOT_TRACKER_MAX && fgets(line, sizeof line, f)) {
        char area[48], ages[4], needs[192] = "", hash[32] = "", item[64] = "";   /* (needs: a rule's ways apart by "/", two of a whole rule each) */
        char *kind = kinds[oot_check_count];
        if (line[0] == '#') continue;   /* (the lines the menu takes, in its order: gpu/vk/vk_menu.cpp tracker_load) */
        const int got = sscanf(line, "%47[^|]|%79[^|]|%39[^|]|%3[^|]|%f %f %f|%191[A-Z0-9,/-]|%31[0-9a-fA-F-]|%63[A-Za-z0-9_]", area, kind,
                               oot_checks[oot_check_count].folder, ages, &oot_checks[oot_check_count].place[0],
                               &oot_checks[oot_check_count].place[1], &oot_checks[oot_check_count].place[2], needs, hash, item);
        if (got < 7) continue;
        snprintf(oot_checks[oot_check_count].item, sizeof oot_checks[0].item, "%s", got >= 10 ? item : "");
        snprintf(oot_checks[oot_check_count].ages, sizeof oot_checks[0].ages, "%s", ages);
        /* (tools/rando/rando_seed.py names such a check "Piece of Heart", and no other kind begins so) */
        oot_checks[oot_check_count].piece = got >= 9 && (!strncmp(kind, "Piece of Heart", 14) || !strncmp(kind, OOT_SUN_CHECK, sizeof OOT_SUN_CHECK - 1))
                                            ? strtoull(hash, NULL, 16) : 0;   /* (and Lake Hylia's Fire Arrows: oot_is_sun) */
        oot_checks[oot_check_count].boss = !strncmp(kind, "Heart Container, ", 17);   /* (the seed's name for a boss's) */
        oot_checks[oot_check_count].key = got >= 9 ? strtoull(hash, NULL, 16) : 0;   /* ("-": 0) */
        oot_checks[oot_check_count].opened = 0;
        if (oot_checks[oot_check_count].key && strstr(kind, "hest")) {   /* ("Chest ...", "Big chest ...": tools/rando/rando_seed.py's names) */
            char flag[64];
            snprintf(flag, sizeof flag, "IsTreasureBoxOpen.%llu", (unsigned long long)oot_checks[oot_check_count].key);
            oot_checks[oot_check_count].opened = oot_flag_hash(flag);
        }
        oot_checks[oot_check_count].shelf = 0;
        oot_checks[oot_check_count].sold = 0;
        oot_checks[oot_check_count].owner[0] = 0;
        oot_checks[oot_check_count].pot = !strncmp(kind, "Pot", 3) && (!kind[3] || kind[3] == ' ');
        oot_checks[oot_check_count].skull = !strncmp(kind, "Gold Skulltula", 14), oot_checks[oot_check_count].claimed = 0, oot_checks[oot_check_count].marked_at = 0;
        /* (a pot's own truth value in the save is "broken", put back when it is back after a day: its check is the item
           picked up, the record's, not that value. Seen without a window 2026-11-24: breaking the pot marked it) */
        oot_checks[oot_check_count].broken = oot_checks[oot_check_count].pot ? oot_checks[oot_check_count].key : 0;
        oot_checks[oot_check_count].pot_kept = 0, oot_checks[oot_check_count].pot_at = -1;
        if (oot_checks[oot_check_count].pot) oot_checks[oot_check_count].key = 0, oot_checks[oot_check_count].opened = 0;
        {   /* (a shelf's price: tools/rando/rando_seed.py names it "<shop>: shelf <k>, <n> rupees") */
            const char *r = strstr(kind, " rupees");
            const char *d = r;
            while (d && d > kind && d[-1] >= '0' && d[-1] <= '9') d--;
            oot_checks[oot_check_count].price = r && d < r && d >= kind + 2 && d[-1] == ' ' && d[-2] == ',' ? atoi(d) : -1;
        }
        oot_checks[oot_check_count++].done = 0;
    }
    if (f) fclose(f);
    /* (the shelves' flags: <a shelf's name in the checks file>|<its flag's hash>|<the flag>, tools/rando/rando_seed.py
       shelf_flags. A seed made before there were any has no such file, and its shelves are as they were) */
    int shelves = 0;
    f = oot_game_file(path, sizeof path, "mods/rando-seed/shelf_flags.txt") ? fopen(path, "r") : NULL;
    while (f && fgets(line, sizeof line, f)) {
        char name[80];
        unsigned flag = 0;
        if (sscanf(line, "%79[^|]|%x", name, &flag) != 2 || !flag) continue;
        for (int i = 0; i < oot_check_count; i++)
            if (!strcmp(kinds[i], name)) {
                oot_checks[i].shelf = flag, shelves++;
                break;
            }
    }
    if (f) fclose(f);
    if (shelves) hos_log("rando: tracker: %d shop shelves wait for a flag of their own", shelves);
    /* (Maps and compasses: Anywhere, tools/rando/rando_seed.py DUNGEON_ITEMS_FILE: <a chest's hash>|<the dungeon its
       dungeon item belongs to>|<the item>. A seed without it, or with it empty, has none: oot_dungeon_item) */
    int owned = 0;
    f = oot_game_file(path, sizeof path, "mods/rando-seed/dungeon_items.txt") ? fopen(path, "r") : NULL;
    while (f && fgets(line, sizeof line, f)) {
        char hash[32], owner[24];
        if (sscanf(line, "%31[0-9a-fA-F]|%23[A-Za-z]|", hash, owner) != 2) continue;
        const uint64_t key = strtoull(hash, NULL, 16);
        for (int i = 0; i < oot_check_count; i++)
            if (oot_checks[i].key == key || (oot_checks[i].pot && oot_checks[i].broken == key)) {   /* (a pot's hash is its .broken) */
                snprintf(oot_checks[i].owner, sizeof oot_checks[i].owner, "%s", owner), owned++;
                break;
            }
    }
    if (f) fclose(f);
    if (owned) hos_log("rando: tracker: %d checks hold a dungeon item that belongs to its own dungeon wherever it is", owned);
    /* (Key rings, rando_seed.py KEYRINGS_FILE: <a dungeon's folder>|<the small keys its ring is>. None without it) */
    oot_keyring_n = 0;
    f = oot_game_file(path, sizeof path, "mods/rando-seed/keyrings.txt") ? fopen(path, "r") : NULL;
    while (f && oot_keyring_n < OOT_KEYRING_MAX && fgets(line, sizeof line, f)) {
        char owner[24];
        int keys = 0;
        if (sscanf(line, "%23[A-Za-z]|%d", owner, &keys) != 2 || keys < 1 || keys > 99) continue;
        snprintf(oot_keyrings[oot_keyring_n].folder, sizeof oot_keyrings[0].folder, "%s", owner);
        oot_keyrings[oot_keyring_n++].keys = keys;
    }
    if (f) fclose(f);
    if (oot_keyring_n) hos_log("rando: key rings: %d dungeons' small keys are a ring each", oot_keyring_n);
    oot_doors_load(stamp);   /* (Dungeon entrances: the doors, and the ones found) */
    oot_boss_doors_load(stamp);   /* (Boss shuffle: the boss rooms, and the ones found) */
    /* (the seed's "You found" words for each dungeon's items, rando_seed.py DUNGEON_WORDS_FILE: oot_dungeon_window) */
    f = oot_game_file(path, sizeof path, "mods/rando-seed/dungeon_words.txt") ? fopen(path, "r") : NULL;
    oot_dungeon_words = f != NULL;
    if (f) fclose(f);
    int collected = 0;
    f = oot_game_file(path, sizeof path, "rando/collected.txt") ? fopen(path, "r") : NULL;
    if (f && fgets(line, sizeof line, f)) {
        line[strcspn(line, "\r\n")] = 0;
        if (!strncmp(line, "seed ", 5) && !strcmp(line + 5, oot_checks_seed))   /* (this seed's record) */
            while (fgets(line, sizeof line, f)) {
                const int i = atoi(line);
                if (line[0] >= '0' && line[0] <= '9' && i < oot_check_count && oot_checks[i].done != 1) {
                    oot_checks[i].done = 1, collected++;
                    if (oot_checks[i].pot) {   /* ("<index>:<progress>", or an older record's "<index>": not known) */
                        const char *at = strchr(line, ':');
                        oot_checks[i].pot_kept = 1, oot_checks[i].pot_at = at ? atoi(at + 1) : -1;
                    }
                }
            }
    }
    if (f) fclose(f);
    hos_log("rando: tracker: %d checks of the seed, %d of them collected by the record", oot_check_count, collected);
}

/* A shop's shelf that sold its item is for sale again when its map is loaded again (the shelf's actor keeps what it
   sold, and nothing saved: tools/rando/README.md). So each shelf of a seed waits for a flag of its own, "still for
   sale" (the goods list's Release). The flag is the save's, and it is what says a shelf was bought: a shelf bought
   just now (oot_tracker_item) has its flag put out here, once, and at every other time the record of a shelf is put
   as the flag says. (Until 2026-11-14 the flags were kept as the record said, and the record is the folder's, not a
   save's: reported from play, a quiver bought was not for sale again in a save from before it was bought, nor in a
   new game of the same seed.) Each second. Returns how many flags or marks were changed. */
static int oot_pot_junk(const char *item);
/* (Pots, reported 2026-11-25: a new game of a seed showed the pots collected in the last one, red and empty) A pot has no
   mark of its own in the save: its truth value by its hash is "broken", put back when it comes back (oot_shelf_flags below).
   The record is the folder's. So each pot in it carries the save's progress it was collected at: how many of the checks
   the save itself marks (a chest's, a Gold Skulltula's, a piece's by its hash, a shelf's flag) were collected then, a number
   a save only ever raises. A pot is collected in the save loaded when that save's progress is at least its own: a new game
   (0) has none of them, a save from before some has only the earlier ones, the game being played all of them. A pot not
   collected in the save loaded is dropped from the record: kept, a new game would reach its progress and show it again. A
   pot just collected takes the progress of now. An older record's pot (no progress written) takes the first one above 0 it
   meets, and is dropped in a new game. Left: a pot collected before any check the save marks (progress 0) stays collected
   in a new game. The lock held; returns how many marks changed. */
/* (tools/rando/rando_seed.py NEW_GAME_FLAG) The hash of the seed's flag that is true in a new game, or 0 (none, or no seed) */
static uint32_t oot_new_game_flag(void) {
    static uint32_t fresh;
    static char fresh_seed[sizeof oot_checks_seed];
    if (strcmp(fresh_seed, oot_checks_seed)) {
        snprintf(fresh_seed, sizeof fresh_seed, "%s", oot_checks_seed);
        fresh = 0;
        char path[MAX_PATH + 48], line[160];
        FILE *f = oot_game_file(path, sizeof path, "mods/rando-seed/new_game_flag.txt") ? fopen(path, "r") : NULL;
        if (f && fgets(line, sizeof line, f)) fresh = (uint32_t)strtoul(line, NULL, 16);
        if (f) fclose(f);
    }
    return fresh;
}
static int oot_pot_progress(Ctx *c) {
    int progress = 0, read = 0, changed = 0;
    for (int i = 0; i < oot_check_count; i++) {
        if (oot_checks[i].pot || (!oot_checks[i].key && !oot_checks[i].shelf)) continue;
        int now = 0;
        if (oot_checks[i].key && oot_gamedata_keyed_bool(c, oot_checks[i].key, &now)) read++;
        if (oot_checks[i].done == 1) progress++;
    }
    /* (judged only in a game being played, its progress the same five seconds running: the title's and a load's values are
       the defaults, progress 0, and would drop every pot) */
    static int last = -1, steady;
    steady = read && oot_link_map[0] && progress == last ? steady + 1 : 0;
    last = progress;
    /* (a new game of the seed: its own flag true, tools/rando/rando_seed.py NEW_GAME_FLAG. Every pot of the record is another
       game's: dropped, and the flag put out, so this game's own pots stay from now on) */
    const uint32_t fresh = oot_new_game_flag();
    int is_new = 0;
    if (fresh && steady >= 5 && oot_gamedata_bool(c, fresh, &is_new) && is_new) {
        int dropped = 0;
        for (int i = 0; i < oot_check_count; i++)
            if (oot_checks[i].pot && oot_checks[i].pot_kept)
                oot_checks[i].pot_kept = 0, oot_checks[i].pot_at = -1, oot_checks[i].done = 0, dropped++, changed++;
        const int out = oot_gamedata_set_bool(c, fresh, 0);
        hos_log("rando: tracker: a new game of the seed: %d pots of another game dropped from the record%s", dropped,
                out ? "" : " (its flag NOT put out)");
    }
    for (int i = 0; i < oot_check_count; i++) {
        if (!oot_checks[i].pot) continue;
        if (oot_checks[i].done == 1 && !oot_checks[i].pot_kept && read)   /* (collected just now: the progress of now) */
            oot_checks[i].pot_kept = 1, oot_checks[i].pot_at = progress, changed++;
        if (!oot_checks[i].pot_kept || steady < 5) continue;
        if (oot_checks[i].pot_at < 0 && progress > 0) {   /* (an older record's: this game's) */
            oot_checks[i].pot_at = progress, changed++;
            continue;
        }
        if (oot_checks[i].pot_at < 0 || oot_checks[i].pot_at > progress) {   /* (another game's, or later than this save: dropped) */
            static int told;
            if (told++ < 20) hos_log("rando: tracker: check %d, a pot collected at progress %d, is not collected in this save (progress %d): "
                                     "dropped from the record", i, oot_checks[i].pot_at, progress);
            oot_checks[i].pot_kept = 0, oot_checks[i].pot_at = -1, oot_checks[i].done = 0, changed++;
        }
    }
    return changed;
}
/* (asked 2026-11-26: "every dropped item carries its own check") A Gold Skulltula's drop was matched to its check by a
   guess: the nearest check not yet collected that gives the item, within OOT_CHECK_NEAR (60 m); and the check guessed
   had its own mark written into the save (sold). Two Skulltulas near each other giving the same item: the wrong one could
   be ticked, and a Skulltula never killed marked collected in the save.
   The save keeps a truth value by each Skulltula's own hash (key), and the record follows it each second (oot_shelf_flags).
   So a drop's check is the Skulltula the SAVE marks, and no mark is written on a guess:
   - a Skulltula here that gives the item and whose mark is set already, not yet ticked: that one;
   - else one the save marked a short while ago whose drop no add has claimed (marked at its death, the drop taken after);
   - else the add waits (oot_skull_wait: the Skulltulas here that could be it): the first of them the save marks within
     OOT_SKULL_WAIT_NS is the one (oot_skull_waited, each second). Only when the save marks none of them in that time is
     the nearest taken and its mark written, as before, and the log says so: then the game does not mark that kind of
     drop by itself, and it is to be looked at.
   Which of the three it was is logged ("rando: tracker: skulltula: ..."): when the game sets the mark was not known when
   this was written (no Skulltula could be killed in a run without a window). */
/* SEEN 2026-11-26 without a window, on the owner's save at Kakariko's Skulltula house (three Skulltulas of the map giving
   Deku Nuts, one in a tree 45 m off): the Skulltula killed, its nut bundle taken: at the add none was marked ("3
   Skulltula(s) here give it, none marked by the save yet"), and the record's next look had the right one marked ("the
   save marked it 0.0 s after the add"); the other two were left. So the game marks a Skulltula when its drop is added,
   not at its death, and for a drop that is no token too: the wait is the way it goes. */
#define OOT_SKULL_WAIT_NS 3000000000LL
#define OOT_SKULL_CLAIM_NS 600000000000LL   /* (how long after its mark a Skulltula's drop may still be picked up as its own) */
#define OOT_SKULL_WAITING 8
#define OOT_MARK_FLIPS 2                 /* (the save's marks seen set in one second that count as "just now, in play") */
#define OOT_MARK_STEADY_NS 5000000000LL  /* (and how long Link has been in his map by then) */
struct oot_wait { char item[64]; int n, at[OOT_SKULL_WAITING]; int64_t since; };
static struct oot_wait oot_skull_wait, oot_chest_wait;   /* (a Gold Skulltula's drop; a chest's item, oot_chest_item) */
static int oot_family_of(const char *name, int *spelling);   /* (below) */
static int oot_dungeon_check;                                 /* (below: the check the last item given was found to be) */
static int64_t oot_dungeon_check_at;
/* the checks waited for (w): one the save has marked since the add is the item's; none after the wait: the nearest, as
   before. what: "skulltula" or "chest", for the log. The lock held, each second. Returns how many marks changed */
static int oot_wait_settle(struct oot_wait *w, const char *what) {
    if (!w->n) return 0;
    const int64_t now = hos_now_ns();
    for (int k = 0; k < w->n; k++) {
        const int i = w->at[k];
        if (i < 0 || i >= oot_check_count || oot_checks[i].done != 1 || oot_checks[i].claimed) continue;
        oot_checks[i].claimed = 1;
        hos_log("rando: tracker: %s: %s was check %d's: the save marked it %.1f s after the add", what, w->item, i, (now - w->since) / 1e9);
        w->n = 0;
        return 0;   /* (its mark was counted when it was seen) */
    }
    if (now - w->since < OOT_SKULL_WAIT_NS) return 0;
    for (int k = 0; k < w->n; k++) {
        const int i = w->at[k];
        if (i < 0 || i >= oot_check_count || oot_checks[i].done == 1) continue;
        oot_checks[i].done = 1, oot_checks[i].claimed = 1, oot_checks[i].sold = 1;
        hos_log("rando: tracker: %s: %s: the save marked none of the %d here that give it in %.0f s: "
                "check %d, the nearest, is taken as before (its mark written)", what, w->item, w->n, OOT_SKULL_WAIT_NS / 1e9, i);
        w->n = 0;
        return 1;
    }
    w->n = 0;
    return 0;
}
static int oot_skull_waited(void) { return oot_wait_settle(&oot_skull_wait, "skulltula"); }
/* A pick-up's add (not an event's): the Gold Skulltula it is the drop of, by the save's own marks. 1: it is seen to (ticked,
   or waited for); 0: no Gold Skulltula here gives it. The lock held */
static int oot_skull_item(Ctx *c, const char *name, int family) {
    int flagged = -1, claimable = -1, n = 0, at[OOT_SKULL_WAITING];
    float rank[OOT_SKULL_WAITING], flagged_away = 1e30f, claim_away = 1e30f;
    const int64_t now = hos_now_ns();
    for (int i = 0; i < oot_check_count; i++) {
        if (!oot_checks[i].skull || !oot_checks[i].key || !oot_banc_in_folder(oot_link_map, oot_checks[i].folder)) continue;
        if (strcmp(oot_checks[i].item, name) && (family < 0 || oot_family_of(oot_checks[i].item, NULL) != family)) continue;
        const float dx = oot_checks[i].place[0] - oot_link_place[0], dy = oot_checks[i].place[1] - oot_link_place[1],
                    dz = oot_checks[i].place[2] - oot_link_place[2];
        const float away = sqrtf(dx * dx + dy * dy + dz * dz);
        if (oot_checks[i].done == 1) {   /* (ticked: marked by the save a while ago, its drop not yet taken?) */
            if (oot_checks[i].marked_at && !oot_checks[i].claimed && now - oot_checks[i].marked_at < OOT_SKULL_CLAIM_NS && away < claim_away)
                claimable = i, claim_away = away;
            continue;
        }
        int marked = 0;
        if (oot_gamedata_keyed_bool(c, oot_checks[i].key, &marked) && marked) {
            if (away < flagged_away) flagged = i, flagged_away = away;
            continue;
        }
        const int other_age = oot_link_child >= 0 && oot_checks[i].ages[0] && !strchr(oot_checks[i].ages, oot_link_child ? 'C' : 'A');
        const float r = away + (other_age ? OOT_CHECK_NEAR : 0.0f);   /* (bug 125: Link's age's first) */
        /* (kept in order, the nearest first; of more than OOT_SKULL_WAITING the farthest are left out) */
        if (n == OOT_SKULL_WAITING && r >= rank[n - 1]) continue;
        int k = n < OOT_SKULL_WAITING ? n++ : n - 1;
        for (; k > 0 && rank[k - 1] > r; k--) rank[k] = rank[k - 1], at[k] = at[k - 1];
        rank[k] = r, at[k] = i;
    }
    if (flagged >= 0) {
        oot_checks[flagged].done = 1, oot_checks[flagged].claimed = 1, oot_checks[flagged].marked_at = now;
        oot_dungeon_check = flagged, oot_dungeon_check_at = now;
        oot_tracker_save();
        hos_log("rando: tracker: skulltula: %s got: check %d, marked by the save before the add (%.1f m from Link)", name, flagged, flagged_away);
        return 1;
    }
    if (claimable >= 0) {
        oot_checks[claimable].claimed = 1;
        oot_dungeon_check = claimable, oot_dungeon_check_at = now;
        hos_log("rando: tracker: skulltula: %s got: check %d, which the save marked %.1f s ago (%.1f m from Link)", name, claimable,
                (now - oot_checks[claimable].marked_at) / 1e9, claim_away);
        return 1;
    }
    if (!n) return 0;
    if (oot_skull_wait.n) {   /* (another add still waited for: settled now, the old way, so each has its own) */
        oot_skull_wait.since = now - OOT_SKULL_WAIT_NS;
        if (oot_skull_waited()) oot_tracker_save();
        int m = 0;
        for (int k = 0; k < n; k++)
            if (oot_checks[at[k]].done != 1) at[m++] = at[k];
        n = m;
        if (!n) return 1;
    }
    snprintf(oot_skull_wait.item, sizeof oot_skull_wait.item, "%s", name);
    oot_skull_wait.n = n, oot_skull_wait.since = now;
    memcpy(oot_skull_wait.at, at, sizeof at);
    hos_log("rando: tracker: skulltula: %s: %d Skulltula(s) here give it, none marked by the save yet (the nearest, check %d, %.1f m): "
            "waiting for the save's own mark", name, n, at[0], rank[0]);
    return 1;
}
/* (the same day: chests the same way) A chest that gives an item was ticked by the same guess at the item's add, the nearest
   chest not yet collected that gives it, and that chest's own mark written. (A chest of rupees gives no add at all: it was
   ticked by the game's own flag already, IsTreasureBoxOpen.<its hash>, .opened: seen without a window on the owner's save
   in Mido's house.) By that flag for every chest now:
   - a chest here that gives the item and whose opened flag is set, not yet ticked: that one;
   - else one the record ticked by its opened flag a short while ago whose item no add has claimed (the flag set as the lid
     goes up, the item added after the scene): that one, and nothing more;
   - else, when the nearest check that gives the item is a chest, the add waits for the first of the chests here to have its
     flag set (oot_chest_wait), and only after the wait is the nearest taken as before. An add whose nearest check is no
     chest (a character's gift) goes as it did.
   SEEN 2026-11-26 without a window on the owner's save "Chest Check Test Save" (Mido's house: four chests, two of red
   rupees, one of Deku Nuts): the nut chest opened: "1 chest(s) here give it, none open by the game's flag yet", then "was
   check 575's: the save marked it 0.2 s after the add": the flag is set just after the add, so the wait is the way it goes.
   Returns 1: seen to (ticked or claimed); 0: not a chest's by its flag, with the chests here that could be it in wait
   (not yet waited for: oot_tracker_item arms it when the nearest check is one of them). The lock held */
static int oot_chest_item(Ctx *c, const char *name, int family, struct oot_wait *wait) {
    int open = -1, claimable = -1, n = 0;
    float rank[OOT_SKULL_WAITING], open_away = 1e30f, claim_away = 1e30f;
    const int64_t now = hos_now_ns();
    for (int i = 0; i < oot_check_count; i++) {
        if (!oot_checks[i].opened || !oot_banc_in_folder(oot_link_map, oot_checks[i].folder)) continue;
        if (strcmp(oot_checks[i].item, name) && (family < 0 || oot_family_of(oot_checks[i].item, NULL) != family)) continue;
        const float dx = oot_checks[i].place[0] - oot_link_place[0], dy = oot_checks[i].place[1] - oot_link_place[1],
                    dz = oot_checks[i].place[2] - oot_link_place[2];
        const float away = sqrtf(dx * dx + dy * dy + dz * dz);
        if (oot_checks[i].done == 1) {
            if (oot_checks[i].marked_at && !oot_checks[i].claimed && now - oot_checks[i].marked_at < OOT_SKULL_CLAIM_NS && away < claim_away)
                claimable = i, claim_away = away;
            continue;
        }
        int is_open = 0;
        if (oot_gamedata_bool(c, oot_checks[i].opened, &is_open) && is_open) {
            if (away < open_away) open = i, open_away = away;
            continue;
        }
        if (n == OOT_SKULL_WAITING && away >= rank[n - 1]) continue;
        int k = n < OOT_SKULL_WAITING ? n++ : n - 1;
        for (; k > 0 && rank[k - 1] > away; k--) rank[k] = rank[k - 1], wait->at[k] = wait->at[k - 1];
        rank[k] = away, wait->at[k] = i;
    }
    wait->n = n, wait->since = now;
    snprintf(wait->item, sizeof wait->item, "%s", name);
    if (open >= 0) {
        oot_checks[open].done = 1, oot_checks[open].claimed = 1, oot_checks[open].marked_at = now, oot_checks[open].sold = 1;
        oot_dungeon_check = open, oot_dungeon_check_at = now;
        oot_tracker_save();
        hos_log("rando: tracker: chest: %s got: check %d, its chest open by the game's flag at the add (%.1f m from Link)", name, open, open_away);
        return 1;
    }
    if (claimable >= 0) {
        oot_checks[claimable].claimed = 1;
        oot_dungeon_check = claimable, oot_dungeon_check_at = now;
        hos_log("rando: tracker: chest: %s got: check %d, ticked by its chest's flag %.1f s ago (%.1f m from Link)", name, claimable,
                (now - oot_checks[claimable].marked_at) / 1e9, claim_away);
        return 1;
    }
    return 0;
}
/* (Pots, asked 2026-11-25) A broken pot comes back when Link has left its area: its "broken" truth value is put back
   once he is in a map of another folder, so it is there the next time its area is entered, as in the original game. The
   game's own wait was about a day of play (bug 96), the Sun's Song not counting. The pots of the area he is in stay
   broken. The map last seen, to tell a move: */
static char oot_pots_map[80];
static int oot_shelf_flags(Ctx *c) {
    int changed = 0, marks = 0, back = 0, flips = 0, flip[OOT_MARK_FLIPS];
    static int64_t map_since;
    const int moved = oot_link_map[0] && strcmp(oot_pots_map, oot_link_map);
    if (moved) snprintf(oot_pots_map, sizeof oot_pots_map, "%s", oot_link_map);
    AcquireSRWLockExclusive(&oot_checks_lock);
    for (int i = 0; i < oot_check_count; i++) {
        int now = 0;
        if (oot_checks[i].pot && oot_checks[i].broken && moved && !oot_banc_in_folder(oot_link_map, oot_checks[i].folder) &&
            oot_gamedata_keyed_bool(c, oot_checks[i].broken, &now) && now) {
            if (oot_checks[i].done != 1 && oot_pot_junk(oot_checks[i].item)) oot_checks[i].done = 1, marks++;   /* (broken: collected) */
            if (oot_gamedata_keyed_set_bool(c, oot_checks[i].broken, 0)) back++;
            continue;
        }
        now = 0;
        /* (Pots, FIXES 98: a pot holding junk is collected once it is broken, whatever it dropped: the game drops a supply
           only where Link has use for it, else a green rupee or nothing, by its own rules; seen in play 2026-11-25, every
           junk pot of the guard house a green rupee with full bags, and its check left. oot_pot_junk) */
        if (oot_checks[i].pot && oot_checks[i].broken && oot_checks[i].done != 1 && oot_pot_junk(oot_checks[i].item)) {
            if (oot_gamedata_keyed_bool(c, oot_checks[i].broken, &now) && now) {
                oot_checks[i].done = 1, marks++;
                hos_log("rando: tracker: check %d, a pot holding %s, is broken: collected", i, oot_checks[i].item);
            }
            continue;
        }
        if (oot_checks[i].shelf) {
            if (!oot_gamedata_bool(c, oot_checks[i].shelf, &now)) continue;
            if (oot_checks[i].sold) {
                oot_checks[i].sold = 0;
                if (now && oot_gamedata_set_bool(c, oot_checks[i].shelf, 0)) changed++;
            } else if ((oot_checks[i].done == 1) != !now) {
                oot_checks[i].done = !now;
                marks++;
            }
        } else if (oot_checks[i].key) {   /* (an actor of a map: the save's truth value by its hash, true once collected) */
            if (!oot_gamedata_keyed_bool(c, oot_checks[i].key, &now)) continue;
            /* (bug 70: a chest the game says is open is collected, whatever it gave: a blue rupee's rupees reach Link by
               no add the record sees. Its own truth value is set too, so the mark stays with the save) */
            int open = 0;
            if (!now && !oot_checks[i].sold && oot_checks[i].opened && oot_gamedata_bool(c, oot_checks[i].opened, &open) && open) {
                if (oot_gamedata_keyed_set_bool(c, oot_checks[i].key, 1)) changed++;
                now = 1;
            }
            if (oot_checks[i].sold) {
                oot_checks[i].sold = 0;
                if (!now && oot_gamedata_keyed_set_bool(c, oot_checks[i].key, 1)) changed++;
            } else if ((oot_checks[i].done == 1) != now) {
                oot_checks[i].done = now;
                marks++;
                /* (a Gold Skulltula the save marks by itself: its drop's add may come after, oot_skull_item. When, below) */
                oot_checks[i].claimed = 0, oot_checks[i].marked_at = 0;
                if (now && flips < OOT_MARK_FLIPS) flip[flips] = i;
                flips += now;
            }
        }
    }
    /* (marked just now, in play: one or two at a time, Link some seconds in his map. A save loaded, or another game's
       record, marks many at once or as the map comes: those are no Skulltula just killed, and their drops are long taken) */
    if (moved) map_since = hos_now_ns();
    if (flips && flips <= OOT_MARK_FLIPS && oot_link_map[0] && hos_now_ns() - map_since > OOT_MARK_STEADY_NS)
        for (int k = 0; k < flips; k++) oot_checks[flip[k]].marked_at = hos_now_ns();
    marks += oot_skull_waited();
    marks += oot_wait_settle(&oot_chest_wait, "chest");
    marks += oot_pot_progress(c);
    if (marks) oot_tracker_save();
    ReleaseSRWLockExclusive(&oot_checks_lock);
    if (back) hos_log("rando: pots: %d broken pots of other areas are back (Link is in %s)", back, oot_link_map);
    return changed + marks + back;
}

/* (the randomizer's fork) Progressive items: the families, smallest first; a tier may have a second spelling (the
   pouch's name of the same thing). Used by the pouch's add (hos_oot_pouch_add), by a chest's content name as the
   chest is made (hos_oot_drop_name: what it shows and says), and by the tracker (a check whose item is of the same
   family as the one given). */
static const char *const oot_families[][3][2] = {
    {{"Item_BombBag_Small"}, {"Item_BombBag_Medium"}, {"Item_BombBag_Large"}},
    {{"Item_Range_Bow", "Weapon_Range_Bow"}, {"Item_Quiver_Medium"}, {"Item_Quiver_Large"}},
    {{"Item_Range_SlingShot", "Weapon_Range_SlingShot"}, {"Item_BulletBag_Medium"}, {"Item_BulletBag_Large"}},
    {{"Item_Hookshot"}, {"Item_Longshot"}},
    {{"Item_Gauntlet_Goron", "Armor_Child_Gauntlet_Goron"}, {"Item_Gauntlet_Silver", "Armor_Adult_Gauntlet_Silver"}, {"Item_Gauntlet_Gold", "Armor_Adult_Gauntlet_Gold"}},
    {{"Item_Scale_Silver"}, {"Item_Scale_Gold"}},
    {{"Item_Wallet_Medium"}, {"Item_Wallet_Large"}},
    {{"Item_StickBag_Small"}, {"Item_StickBag_Medium"}, {"Item_StickBag_Large"}},
    {{"Item_NutBag_Small"}, {"Item_NutBag_Medium"}, {"Item_NutBag_Large"}},
    {{"Item_FairyBless_MP"}, {"Item_FairyBless_MPDouble"}},
};
#define OOT_FAMILIES ((int)(sizeof oot_families / sizeof oot_families[0]))
/* (what a chest can show and say: the game has a "You got" message (PouchContent.msbt, <name>_GetMessage) for these
   spellings and not for the others of the same thing. A chest made to give one without a message stopped in its
   scene, the model shown and no words (seen without a window 2026-11-16, the first Deku Nut bag). So a chest shows
   the spelling with the message; the first Stick and Nut bags have none: such a chest shows its own item as before) */
static const char *const oot_show_as[][2] = {
    {"Item_Range_Bow", "Weapon_Range_Bow"}, {"Item_Range_SlingShot", "Weapon_Range_SlingShot"},
    /* (the gauntlets were shown as Armor_Child_Gauntlet_Goron, Armor_Adult_Gauntlet_*: words but no model, the owner's run
       2026-11-23. Every seed from fixes 75 gives the Item_Gauntlet_* spellings the words, tools/rando/rando_seed.py
       COPY_WORDS, so they are shown as they are) */
};
/* (bug 48: the first Stick and Nut bags had no "You got" words in the game; every seed adds them from fixes 49,
   tools/rando/rando_seed.py FIRST_BAG_WORDS, so they are shown as they are. The list is kept for an item that has none) */
static const char *const oot_no_show[] = {"(none)"};

/* the family a content is of (its index), and which spelling it was given by; -1 for none */
static int oot_family_of(const char *name, int *spelling) {
    for (int f = 0; f < OOT_FAMILIES; f++)
        for (int t = 0; t < 3 && oot_families[f][t][0]; t++)
            for (int a = 0; a < 2; a++)
                if (oot_families[f][t][a] && !strcmp(name, oot_families[f][t][a])) {
                    if (spelling) *spelling = a;
                    return f;
                }
    return -1;
}

int hos_rando_progressive(void);   /* host/oot_rando.c */

/* HOS_OOT_TRACK_SHOP=0: shelves matched by any add, as before 2026-11-23 */
static int oot_tracker_shop_on = 1;

/* An item given (hos_oot_pouch_add): the check that gives it is collected.
   shop: the add is a shop's sale (the game's add from 0x828d50ac with x4 5: every shelf bought in the owner's run of
   2026-11-23 had it, and no chest, gift or pick-up did). A sale is a shelf's and only a shelf's: bug 115, two shelves of
   one item in a shop, the first in the list was marked and hidden, not the one bought; and the adult rolling Goron's
   Heart Container marked the Goron shop's Heart Container shelf (the nearer), which then vanished. price: the game's
   Shop_SelectItemPrice at the sale (-1: not read), which tells the shelves of one item apart. */
/* (the pot a pick-up came from, oot_pot_again, for the record that follows on the same thread; -1: none) */
static _Thread_local int oot_pot_chosen = -1;
/* (the lying Piece of Heart, boss's Heart Container or Fire Arrows whose item is being added, oot_piece_gives: the check
   found at the piece's own place is the one the record ticks, not the nearest check that gives its item; -1: none) */
static _Thread_local int oot_piece_chosen = -1;
/* (the check the last item given was found to be, and when: a dungeon item from a Gold Skulltula or a pot is that check's
   dungeon's, oot_dungeon_owner. Written under oot_checks_lock) */
static int oot_dungeon_check = -1;
static int64_t oot_dungeon_check_at;
#define OOT_DUNGEON_CHECK_NS 3000000000LL
static _Thread_local char oot_pickup_folder[24];   /* (the dungeon of a pick-up of a dungeon's own being added: oot_dungeon_pickup) */
static void oot_tracker_item(Ctx *c, const char *name, int shop, int price, int pickup) {
    static int read;
    if (!read) {
        const char *e = getenv("HOS_OOT_TRACK_SHOP");
        oot_tracker_shop_on = !(e && *e == '0');
        read = 1;
    }
    if (oot_pot_chosen == -2) {   /* (a junk pot's item, its pot collected when it broke: oot_pot_again) */
        oot_pot_chosen = -1;
        hos_log("rando: tracker: %s from a pot collected when it broke: no other check marked", name);
        return;
    }
    AcquireSRWLockExclusive(&oot_checks_lock);
    int best = -1, elsewhere = -1, others = 0;
    float nearest = 1e30f;
    /* (with Progressive items a check gives the family's next, by its own name or, since the chest says so, by that
       next's: a check of the same family is the one) */
    const int family = hos_rando_progressive() ? oot_family_of(name, NULL) : -1;
    /* (a pick-up's add that no pot gave: a Gold Skulltula's drop is its check's by the save's own marks, oot_skull_item) */
    if (pickup && !shop && oot_pot_chosen < 0 && oot_piece_chosen < 0 && oot_skull_item(c, name, family)) {
        ReleaseSRWLockExclusive(&oot_checks_lock);
        return;
    }
    /* (an event's add: a chest's item is its chest's by the game's own opened flag, oot_chest_item) */
    struct oot_wait chests = {.n = 0};
    if (!pickup && !shop && oot_chest_item(c, name, family, &chests)) {
        ReleaseSRWLockExclusive(&oot_checks_lock);
        return;
    }
    /* (pass 0: the map Link is in; pass 1, when nothing near was found there: the map he left within OOT_LEFT_MAP_NS) */
    const int left = oot_left_map[0] && hos_now_ns() - oot_left_at < OOT_LEFT_MAP_NS;
    for (int pass = 0; pass < 1 + left && best < 0; pass++) {
        const char *map = pass ? oot_left_map : oot_link_map;
        const float *at = pass ? oot_left_place : oot_link_place;
        nearest = 1e30f, others = 0, elsewhere = -1;
        float ranked = 1e30f;
        for (int i = 0; i < oot_check_count; i++) {
            if (oot_checks[i].done == 1) continue;
            if (oot_tracker_shop_on && (!oot_checks[i].shelf) != !shop) continue;   /* (a sale is a shelf's; anything else is not) */
            if (shop && price >= 0 && oot_checks[i].price >= 0 && oot_checks[i].price != price) continue;
            if (strcmp(oot_checks[i].item, name) && (family < 0 || oot_family_of(oot_checks[i].item, NULL) != family)) continue;
            if (!oot_banc_in_folder(map, oot_checks[i].folder)) {
                others++, elsewhere = i;
                continue;
            }
            const float dx = oot_checks[i].place[0] - at[0], dy = oot_checks[i].place[1] - at[1], dz = oot_checks[i].place[2] - at[2];
            const float away = sqrtf(dx * dx + dy * dy + dz * dz);
            /* (another age's check counts as farther, so one of Link's age at the same place comes first: bug 125) */
            const int other_age = oot_link_child >= 0 && oot_checks[i].ages[0] && !strchr(oot_checks[i].ages, oot_link_child ? 'C' : 'A');
            const float rank = away + (other_age ? OOT_CHECK_NEAR : 0.0f);
            if (rank < ranked) ranked = rank, nearest = away, best = i;
        }
        if (best >= 0 && nearest > OOT_CHECK_NEAR) best = -1;
        if (best >= 0 && pass) hos_log("rando: tracker: %s: the check is in the map Link just left (%s)", name, map);
    }
    if (best < 0 && others == 1 && nearest > 1e29f) best = elsewhere;   /* (the one check left that gives it, in another map's file) */
    if (oot_pot_chosen >= 0 && oot_pot_chosen < oot_check_count && oot_checks[oot_pot_chosen].done != 1) {
        best = oot_pot_chosen;   /* (the broken pot it came from: oot_pot_again) */
        hos_log("rando: tracker: %s came from the pot just broken (check %d)", name, best);
    }
    oot_pot_chosen = -1;
    if (oot_piece_chosen >= 0 && oot_piece_chosen < oot_check_count && oot_checks[oot_piece_chosen].done != 1 && !shop) {
        best = oot_piece_chosen;   /* (the piece lying where Link took it: oot_piece_gives) */
        hos_log("rando: tracker: %s came from the piece lying here (check %d)", name, best);
    }
    oot_piece_chosen = -1;
    if (best < 0) {
        /* (a shop's shelf gives its item by the name the pouch has it by, which is not always the seed's: seen without
           a window, the Lens of Truth bought was Armor_Child_GlassTruth and a purple rupee Obj_Rupee_Purple, and
           neither shelf was marked. So a shelf near Link whose item's name without its first word (Item_, TBox_,
           Obj_) is the end of the name given is the one) */
        const size_t length = strlen(name);
        for (int i = 0; i < oot_check_count && best < 0; i++) {
            const char *tail = oot_checks[i].shelf && oot_checks[i].done != 1 && (shop || !oot_tracker_shop_on) &&
                               (!shop || price < 0 || oot_checks[i].price < 0 || oot_checks[i].price == price) ? strchr(oot_checks[i].item, '_') : NULL;
            const size_t n = tail ? strlen(tail) : 0;   /* (with its "_": a whole word's end) */
            if (n < 2 || n > length || strcmp(name + length - n, tail) || !oot_banc_in_folder(oot_link_map, oot_checks[i].folder)) continue;
            const float dx = oot_checks[i].place[0] - oot_link_place[0], dy = oot_checks[i].place[1] - oot_link_place[1],
                        dz = oot_checks[i].place[2] - oot_link_place[2];
            const float away = sqrtf(dx * dx + dy * dy + dz * dz);
            if (away <= OOT_CHECK_NEAR) best = i, nearest = away;
        }
    }
    if (best >= 0 && chests.n && oot_checks[best].opened) {
        /* (the nearest check that gives it is a chest whose flag does not say open: not ticked on that guess. The chests
           here that give it are waited for, oot_wait_settle; one waited for already is settled first, each its own) */
        if (oot_chest_wait.n) {
            oot_chest_wait.since = hos_now_ns() - OOT_SKULL_WAIT_NS;
            if (oot_wait_settle(&oot_chest_wait, "chest")) oot_tracker_save();
        }
        oot_chest_wait = chests;
        hos_log("rando: tracker: chest: %s: %d chest(s) here give it, none open by the game's flag yet (the nearest, check %d): "
                "waiting for the flag", name, chests.n, chests.at[0]);
        best = -1;
    }
    if (best >= 0) {
        oot_checks[best].done = 1;
        oot_dungeon_check = best, oot_dungeon_check_at = hos_now_ns();   /* (its dungeon item's dungeon: oot_dungeon_owner) */
        if (oot_checks[best].shelf || oot_checks[best].key) oot_checks[best].sold = 1;
        oot_tracker_save();
        if (nearest < 1e29f) hos_log("rando: tracker: %s got: check %d is collected (%.1f m from Link)", name, best, nearest);
        else hos_log("rando: tracker: %s got: check %d is collected (the one left that gives it)", name, best);
    }
    ReleaseSRWLockExclusive(&oot_checks_lock);
}

/* (the randomizer's fork) Heart Pieces: what a Piece of Heart lying in the world gives. The seed leaves the piece in
   its map as the game has it, so it is taken once and stays taken as every piece does, and says in its check's line
   what it gives (tools/rando/rando_seed.py HEART). When a Piece of Heart enters the pouch within OOT_PIECE_NEAR metres
   of such a check's place, in that place's map, and not by an event's action (a chest's and a character's piece come
   from 0x828d50ac), the item of that check is put in the pouch in its place (hos_oot_pouch_add). The scene is the
   piece's: it shows a Piece of Heart and says so.
   Tried before this, and left: the item itself lying there, made a pick-up. Made from the token it was there again
   each time its map was entered; made from the piece too (seen in play, the Megaton Hammer of Zora's River); and with
   the saved truth value of the piece's own hash set by the game's setter (f_80f27130, as the piece's own
   OneShotHeartPieceTakenDeadAfter calls it) it was there again all the same. out: the item, when 1 is returned.
   The piece is counted all the same: its own taking counts it, apart from the pouch's add (seen in play and in runs
   with HOS_OOT_PIECES=1, which logs the count as it changes: an ordinary piece is counted some tenths of a second
   after the add, the Gerudo Valley's two seconds before it; with the add's name changed, and the name the caller
   tells the item got by changed too, it was counted still). So one piece is taken out of the pouch again
   (hos_oot_pouch_add, and oot_piece_back for a piece counted when Link had none). Left: the Gerudo Valley's piece
   taken with three in the pouch has made a heart by the time of the add, and that heart stays. */
#define OOT_PIECE_NEAR 12.0f
#define OOT_PIECE "Obj_Heart_Piece"
#define OOT_PIECE_VALLEY "Obj_GerudoValley_Heart_Piece"
/* (fixes 93, tools/rando/rando_seed.py PIECE_LOOK: a piece that gives another item is an actor of its own with that item's
   model, Obj_Heart_Piece_R<nn>; the pouch's add is named by it (seen without a window 2026-11-24: "pouch add
   Obj_Heart_Piece_R01"), so it is a piece as Obj_Heart_Piece is) */
static int oot_is_piece(const char *name) {
    return !strcmp(name, OOT_PIECE) || !strncmp(name, OOT_PIECE "_R", sizeof OOT_PIECE "_R" - 1);
}
#define OOT_CONTAINER "Obj_Heart_Container"
/* (fixes 94, CONTAINER_LOOK: a boss's Heart Container that gives another item is an actor of its own, Obj_Heart_Container_R<nn>) */
/* (placement 28, tools/rando/rando_seed.py SUN_ARROWS: Lake Hylia's Fire Arrows, lying on the island after the sun's
   shot, take part as a lying piece does: the check's name begins OOT_SUN_CHECK, the pick-up's add is the actor's or the
   item's name) */
static int oot_is_sun(const char *name) {
    return !strcmp(name, "Obj_Arrow_Fire") || !strcmp(name, "Item_Arrow_Fire");
}
static int oot_is_container(const char *name) {
    return !strcmp(name, OOT_CONTAINER) || !strncmp(name, OOT_CONTAINER "_R", sizeof OOT_CONTAINER "_R" - 1);
}
#define OOT_PIECE_WAIT 600   /* (the player's updates a piece counted late is waited for: some seconds) */
static int oot_piece_back;   /* (a piece to take back out of the pouch: the updates it is still waited for) */
/* (bug 31: a boss's Heart Container that gives the seed's item still made a heart, seen without a window: five hearts
   became six with the add renamed. Its own taking raises PlayerStatus.MaxLife, as a piece's counts the piece. So the
   max is followed at each update (oot_max_was: what it was before its last rise, oot_max_rose: when), and after the
   renamed add it is put back for some seconds to what it was before the container: oot_container_max) */
#define OOT_MAX_LIFE 0xfbe01da1u   /* (PlayerStatus.MaxLife, Int, quarter hearts: host/oot_state_tap.c) */
#define OOT_LIFE 0x31ab5580u       /* (PlayerStatus.Life) */
#define OOT_MAX_RECENT 5000000000LL
static int32_t oot_max_now = -1, oot_max_was = -1, oot_container_max = -1;
static int64_t oot_max_rose;
static int oot_container_back;   /* (the updates the container's heart is still taken back for) */
/* (a piece that gives another item still healed Link, as a piece does: bug 4, reported 2026-11-13. Until this time
   Link's life is not let rise over what it was before the piece: oot_piece_heal, in the player's update. The heal is
   not the life write that patch_life hooks (tried: no heal went through it, and Link was healed all the same)) */
#define OOT_PIECE_NO_HEAL 15000000000LL
static int64_t oot_no_heal_until;
static uint32_t oot_life_seen, oot_life_held;   /* (Link's life, in quarters, at the player's last update; kept) */
static void oot_piece_heal(Ctx *c, int64_t now, uint64_t actor) {
    if (!hos_oot_is_player(c, actor)) return;
    const uint64_t life_at = recomp_load64(c, actor + 7184);
    if (life_at < HOS_HEAP_BASE || (life_at & 7)) return;   /* (not made yet: seen 0x2f) */
    const uint32_t life = recomp_load32(c, life_at + 8);
    /* (bug 31: the boss container's heart in Link's own max life too, which the hearts shown and the heals go by: the
       actor's +7192, as its life is +7184 (the heal's clamp in f_804bd8c0). PlayerStatus.MaxLife alone was put back
       and six hearts were still shown) */
    const int32_t keep = __atomic_load_n(&oot_container_max, __ATOMIC_RELAXED);
    const uint64_t max_at = recomp_load64(c, actor + 7192);
    if (keep > 0 && __atomic_load_n(&oot_container_back, __ATOMIC_ACQUIRE) > 0 && max_at >= HOS_HEAP_BASE && !(max_at & 7)) {
        const uint32_t max = recomp_load32(c, max_at + 8);
        if (max > (uint32_t)keep) {
            recomp_store32(c, max_at + 8, (uint32_t)keep);
            if (life > (uint32_t)keep) recomp_store32(c, life_at + 8, (uint32_t)keep);
            hos_log("rando: the boss's Heart Container's heart is taken back from Link (max life %u -> %d quarters)", max, keep);
        }
    }
    static int told;
    if (!told && env_on("HOS_OOT_PIECES")) told = 1, hos_log("rando: Link's life read: %u quarters (at 0x%llx)", life, (unsigned long long)life_at);
    if (now >= __atomic_load_n(&oot_no_heal_until, __ATOMIC_ACQUIRE)) {
        __atomic_store_n(&oot_life_seen, life, __ATOMIC_RELAXED);
        return;
    }
    const uint32_t held = __atomic_load_n(&oot_life_held, __ATOMIC_RELAXED);
    if (life > held) {
        recomp_store32(c, life_at + 8, held);
        hos_log("rando: the Piece of Heart's heal is taken back (%u -> %u quarters)", life, held);
    } else {
        __atomic_store_n(&oot_life_held, life, __ATOMIC_RELAXED);   /* (a hit taken meanwhile stands) */
    }
}
/* (the randomizer's fork) A bag found is a full bag. What Link carries a counted item in (a Bomb Bag, a quiver or the
   bow, a Bullet Bag or the Slingshot, a Deku Stick bag, a Deku Nut bag) came empty when a seed gave it: a Deku Nut bag
   bought with no nuts held showed nothing in the Items screen, and was taken for a thing that did nothing (its owner's
   report, 2026-11-13, and their word: fill it, a bigger quiver or Bomb Bag too). So when one is put in the pouch
   (hos_oot_pouch_add notes which, the one given after the progressive step), what it holds is added until the count
   stops going up: the pouch keeps what the bag holds and no more. The adds are a few updates later, when the bag is in
   the pouch, and a few updates apart: an add is counted an update after it is made (seen: the count read at once was
   the one before), so each is looked at before the next (the player's update, oot_update_player_cheats). Seen without
   a window: the game fills a bigger bag itself, and the first one too for bombs, arrows and seeds; the first Deku
   Stick bag and Deku Nut bag came empty and are filled by this. With the randomizer on only. */
enum { OOT_FILL_WAIT = 12, OOT_FILL_STEP = 10, OOT_FILL_STEPS = 12, OOT_FILL_APART = 4 };
#define OOT_FILL_RUPEES "TBox_Rupee_Gold"
static const char *const oot_fills[][2] = {   /* what a holder's name starts with, and what it holds */
    {"Item_BombBag_", "Item_Bomb"}, {"Item_Quiver_", "Item_Arrow_Normal"}, {"Item_Range_Bow", "Item_Arrow_Normal"},
    {"Weapon_Range_Bow", "Item_Arrow_Normal"}, {"Item_BulletBag_", "Item_DekuSeed"}, {"Item_Range_SlingShot", "Item_DekuSeed"},
    {"Weapon_Range_SlingShot", "Item_DekuSeed"}, {"Item_StickBag_", "Item_DekuStick"}, {"Item_NutBag_", "Item_DekuNut"},
    /* (and a wallet its rupees, asked for after the bags: the game leaves a wallet found as full as the one before it.
       Rupees are added as the chests' gold rupee, 200 of them, and the count of that content is the rupees Link has:
       seen without a window, 24, 224, 424 after each. One at a time, OOT_FILL_RUPEES: ten would be 2000) */
    {"Item_Wallet_", OOT_FILL_RUPEES},
};
enum { OOT_FILLS = sizeof oot_fills / sizeof oot_fills[0] };
/* A bow or a Slingshot got with nothing to carry its ammunition in. Seen in the logs of a game, 2026-11-14 (its
   owner asked for the bow and the Slingshot to come full): a bow bought from a shelf, and a Slingshot, had ten of
   theirs added and Link then had none ("filled: Link has 0 (1 adds)"). The game gives the first quiver and the first
   Bullet Bag in the scenes of its own bow and Slingshot, not with the items; another randomizer of this game gives
   both at a new game's start for the same reason (github.com/Mozencaz/OotrR randomizer_core.py BASE_REQUIRED). So
   when what a holder holds is to be filled and Link has none of the things that carry it, the smallest is given
   first, once, and the fill is made after it. NOT SEEN YET: the game was being played. */
static const char *const oot_fill_bags[][4] = {   /* what is held; the smallest thing that carries it; the larger ones */
    {"Item_Arrow_Normal", "Item_Quiver_Small", "Item_Quiver_Medium", "Item_Quiver_Large"},
    {"Item_DekuSeed", "Item_BulletBag_Small", "Item_BulletBag_Medium", "Item_BulletBag_Large"},
};
static int oot_fill_bagged[OOT_FILLS];   /* (the smallest carrier was looked for, since the holder was got) */
static int oot_fill_wait[OOT_FILLS];   /* (a holder got: the updates until what it holds is added, or looked at again) */
static int oot_fill_last[OOT_FILLS];   /* (the count before the last add; -1: none made yet) */
static int oot_fill_adds[OOT_FILLS];   /* (the adds made) */
/* (a bag the game itself gives with what goes in it, when Link has none: three Deku Nuts bought with no bag came with
   the bag, and the fill then made them twenty. Reported from play, 2026-11-14, and seen in that game's log: the bag
   added from 0x828d50ac with x4 2 and x7 0, as the Bomb Bag given with a chest's bombs is. Such a bag is not filled:
   hos_oot_pouch_add sets this for the add it is in) */
static int oot_fill_quiet;
/* (the randomizer's fork) Ammo pick-ups and Rupees fill the wallet (launcher settings, asked for 2026-11-17): a pick-up
   lying in the world or dropped by grass, pots and enemies comes into the pouch from 0x80c8f7e8 (seen without a window:
   Hyrule Field's Deku Nut, "pouch add Obj_DekuNut x1 (lr 0x80c8f7e8", as Pieces of Heart and the bosses' containers
   do), not from a chest's (0x828d50ac) nor a shop's. Ammo: 5 each raises the add's count to 5; Fill the bag fills what
   it holds the way a bag found is filled (oot_fills), without giving a bag Link has not. Rupees: the wallet filled. */
static const char *const oot_pickup_ammo[][2] = {   /* a pick-up's name (its start), and what it adds to */
    {"Obj_Bomb", "Item_Bomb"}, {"Obj_DekuNut", "Item_DekuNut"}, {"Obj_DekuSeed", "Item_DekuSeed"},
    {"Obj_DekuStick", "Item_DekuStick"}, {"Obj_ArrowBundle_", "Item_Arrow_Normal"},
};
static void oot_fill_start(const char *holds, const char *why) {
    for (int k = 0; k < (int)OOT_FILLS; k++)
        if (!strcmp(oot_fills[k][1], holds)) {
            oot_fill_last[k] = -1, oot_fill_adds[k] = 0, oot_fill_bagged[k] = 1;   /* (no bag given: oot_fill_bags) */
            __atomic_store_n(&oot_fill_wait[k], OOT_FILL_WAIT, __ATOMIC_RELEASE);
            hos_log("rando: %s: %s will be filled", why, holds);
            return;
        }
}
#define OOT_RUPEE_FILL_COUNT 1000   /* (a rupee pick-up's count with Rupees fill the wallet: 1000 green ones fill the biggest wallet, 999) */
int hos_rando_ammo_pickups(void);   /* host/oot_rando.c */
int hos_rando_rupee_fill(void);
static void oot_pickup_qol(Ctx *c, const char *name) {
    if (c->x[30] != 0x80c8f7e8ULL || (int32_t)c->x[3] <= 0) return;
    const int ammo = hos_rando_ammo_pickups();
    for (unsigned k = 0; ammo && k < sizeof oot_pickup_ammo / sizeof oot_pickup_ammo[0]; k++) {
        if (strncmp(name, oot_pickup_ammo[k][0], strlen(oot_pickup_ammo[k][0])) || (!strcmp(oot_pickup_ammo[k][0], "Obj_Bomb") && strcmp(name, "Obj_Bomb")))
            continue;
        if (ammo == 1 && (int32_t)c->x[3] < 5) {
            hos_log("rando: ammo pick-up %s x%d: 5 given", name, (int)(int32_t)c->x[3]);
            c->x[3] = 5;
        } else if (ammo == 2) {
            oot_fill_start(oot_pickup_ammo[k][1], name);
        }
        return;
    }
    /* (Rupees fill the wallet: the pick-up's own add made the fill, bug 79. Filled by later adds, the counter over Link
       showed the count at this one, "120/200" for a wallet filled to 200 (the owner's picture, 2026-11-18). As many as
       OOT_RUPEE_FILL_COUNT of the rupee: the pouch keeps what the wallet holds and no more, as it did each fill add) */
    if (hos_rando_rupee_fill() && !strncmp(name, "Obj_Rupee_", 10)) {
        hos_log("rando: rupee pick-up %s x%d: x%d, the wallet filled", name, (int)(int32_t)c->x[3], OOT_RUPEE_FILL_COUNT);
        c->x[3] = OOT_RUPEE_FILL_COUNT;
    }
}
static void oot_fill_note(const char *item) {
    for (int k = 0; k < (int)OOT_FILLS; k++)
        if (!strncmp(item, oot_fills[k][0], strlen(oot_fills[k][0]))) {
            if (oot_fill_quiet) {
                hos_log("rando: %s is the game's own, given with what goes in it: not filled", item);
                return;
            }
            oot_fill_last[k] = -1, oot_fill_adds[k] = 0, oot_fill_bagged[k] = 0;
            __atomic_store_n(&oot_fill_wait[k], OOT_FILL_WAIT, __ATOMIC_RELEASE);
            hos_log("rando: %s got: its %s will be filled", item, oot_fills[k][1]);
            return;
        }
}
static int oot_piece_gives(char *out, size_t size, int boss) {   /* (boss: a boss's Heart Container's check instead) */
    int best = -1;
    float nearest = boss ? 1e30f : OOT_PIECE_NEAR;   /* (a dungeon has one boss container: where it falls is not asked) */
    AcquireSRWLockShared(&oot_checks_lock);
    for (int i = 0; i < oot_check_count; i++) {
        if (!(boss ? oot_checks[i].boss : oot_checks[i].piece != 0) || !oot_banc_in_folder(oot_link_map, oot_checks[i].folder)) continue;
        const float dx = oot_checks[i].place[0] - oot_link_place[0], dy = oot_checks[i].place[1] - oot_link_place[1],
                    dz = oot_checks[i].place[2] - oot_link_place[2];
        const float away = sqrtf(dx * dx + dy * dy + dz * dz);
        if (away < nearest) nearest = away, best = i;
    }
    const int other = best >= 0 && oot_checks[best].item[0] && strcmp(oot_checks[best].item, boss ? OOT_CONTAINER : OOT_PIECE);
    if (other) snprintf(out, size, "%s", oot_checks[best].item);
    oot_piece_chosen = best;   /* (its own check, whatever it gives: the record's, oot_tracker_item) */
    ReleaseSRWLockShared(&oot_checks_lock);
    return other;
}

/* The record forgotten (the Tracker tab's first row: a new game of the same seed) */
static void oot_tracker_forget(void) {
    AcquireSRWLockExclusive(&oot_checks_lock);
    for (int i = 0; i < oot_check_count; i++) oot_checks[i].done = 0, oot_checks[i].pot_kept = 0, oot_checks[i].pot_at = -1;
    oot_tracker_save();
    ReleaseSRWLockExclusive(&oot_checks_lock);
    hos_log("rando: tracker: the record of what is collected is forgotten");
}

/* (Shuffle the Master Sword, tools/rando/rando_seed.py MASTER_GIFT) The first trip through time: the pedestal's check is
   the seed's check in the Market at the sword's place. Its item is put in the pouch once, its key in the save marking it
   given (a gift's key: kept by the save, so another save of the seed has its own). 1: the seed has the check (given now
   or before), 0: it has none (the sword is not shuffled), -1: the checks are not read yet */
static int oot_pedestal_give(Ctx *c) {
    char item[64] = "";
    uint64_t key = 0;
    int found = 0;
    AcquireSRWLockExclusive(&oot_checks_lock);
    const int loaded = oot_check_count >= 0;
    for (int i = 0; i < oot_check_count && !found; i++) {
        const float dx = oot_checks[i].place[0] - OOT_SWORD_X, dz = oot_checks[i].place[2] - OOT_SWORD_Z;
        if (!strcmp(oot_checks[i].folder, "Market") && dx * dx + dz * dz < 1.0f && oot_checks[i].key && oot_checks[i].item[0]) {
            found = 1, key = oot_checks[i].key;
            snprintf(item, sizeof item, "%s", oot_checks[i].item);
        }
    }
    ReleaseSRWLockExclusive(&oot_checks_lock);
    if (!found) return loaded ? 0 : -1;
    int given = 0;
    if (!oot_gamedata_keyed_bool(c, key, &given)) {
        hos_log("rando: the Master Sword's pedestal: its key %016llx is not in the save's list: nothing given", (unsigned long long)key);
        return 1;
    }
    if (given) return 1;
    const int status = oot_pouch_change(c, item, 1);
    const int marked = oot_gamedata_keyed_set_bool(c, key, 1);
    hos_log("rando: the Master Sword's pedestal gives %s (event status %d)%s", item, status, marked ? "" : ", its key NOT SET");
    return 1;
}

/* Where Link is, each frame, and each second: the seed's checks read when the seed is another, and each check's word to
   the menu, in the file's order */
/* (the randomizer's fork, asked 2026-11-21) The Gossip Stones heard, for the Tracker tab's row of them (vk_menu.cpp
   tracker_stones_load). A stone's talk sets the game's flag GossipStone_NaviTalk_Temporary just before the stone speaks
   (tools/rando/rando_seed.py stone_heard_flow; the flow's question of it is passed over with the hints on, so it has no
   other use then): seen set here, it is put out and the stone nearest Link in the map he is in (within OOT_STONE_NEAR) is
   heard. The stones and their places: <game folder>/mods/rando-seed/rando_hints.txt, "<name>|<folder>|<x y z>|<words>";
   the record: <game folder>/rando/hints_heard.txt, "seed <the seed's stamp>", then each stone's name, once. */
#define OOT_STONE_FLAG 0x05ab3f3du
#define OOT_STONE_NEAR 8.0f
#define OOT_STONES_MAX 64
static void oot_stone_heard(Ctx *c) {
    static char names[OOT_STONES_MAX][48], folders[OOT_STONES_MAX][40];
    static float places[OOT_STONES_MAX][3];
    static int count = -1;
    static char seed_of[sizeof oot_checks_seed];
    int set = 0;
    if (!oot_gamedata_bool(c, OOT_STONE_FLAG, &set) || !set) return;
    oot_gamedata_set_bool(c, OOT_STONE_FLAG, 0);
    char path[MAX_PATH + 48];
    if (count < 0 || strcmp(seed_of, oot_checks_seed)) {   /* (the stones of this seed, read again when the seed is another) */
        count = 0;
        snprintf(seed_of, sizeof seed_of, "%s", oot_checks_seed);
        FILE *f = oot_game_file(path, sizeof path, "mods/rando-seed/rando_hints.txt") ? fopen(path, "r") : NULL;
        char line[512];
        while (f && count < OOT_STONES_MAX && fgets(line, sizeof line, f)) {
            if (line[0] == '#') continue;
            if (sscanf(line, "%47[^|]|%39[^|]|%f %f %f|", names[count], folders[count], &places[count][0], &places[count][1], &places[count][2]) == 5) count++;
        }
        if (f) fclose(f);
    }
    int best = -1;
    float best_d = OOT_STONE_NEAR * OOT_STONE_NEAR;
    for (int i = 0; i < count; i++) {
        if (!oot_banc_in_folder(oot_link_map, folders[i])) continue;
        float d = 0;
        for (int k = 0; k < 3; k++) d += (places[i][k] - oot_link_place[k]) * (places[i][k] - oot_link_place[k]);
        if (d < best_d) best_d = d, best = i;
    }
    if (best < 0) { hos_log("rando: a Gossip Stone talked to, but none of the seed's is near Link"); return; }
    /* (the record: kept when it is this seed's and has the stone already, else written with it) */
    char seen[OOT_STONES_MAX][48];
    int n = 0, ours = 0, had = 0;
    FILE *f = oot_game_file(path, sizeof path, "rando/hints_heard.txt") ? fopen(path, "r") : NULL;
    if (f) {
        char line[1100];
        while (fgets(line, sizeof line, f)) {
            line[strcspn(line, "\r\n")] = 0;
            if (!strncmp(line, "seed ", 5)) { ours = !strcmp(line + 5, oot_checks_seed); continue; }
            if (ours && n < OOT_STONES_MAX) { snprintf(seen[n], sizeof seen[n], "%s", line); had |= !strcmp(line, names[best]); n++; }
        }
        fclose(f);
    }
    if (had) return;
    f = oot_game_file(path, sizeof path, "rando/hints_heard.txt") ? fopen(path, "w") : NULL;
    if (!f) return;
    fprintf(f, "seed %s\n", oot_checks_seed);
    for (int i = 0; i < n; i++) fprintf(f, "%s\n", seen[i]);
    fprintf(f, "%s\n", names[best]);
    fclose(f);
    hos_log("rando: Gossip Stone %s heard", names[best]);
}

/* (the randomizer's fork, asked 2026-11-21) The run's stats, for the Tracker's first row (vk_menu.cpp tracker_stats_load):
   the seconds played (counted once a second while Link is in the world, oot_tracker_refresh: not on the title or in the
   menu), the deaths (the game over's event, DmF_SY_GameOver) and the second Ganon fell (Defeat_Ganon, the first time).
   Kept for the seed: <game folder>/rando/run_stats.txt, "seed <the seed's stamp>" then "seconds N", "deaths N",
   "finished N" (0: not yet); another seed's are started over. Written every OOT_STATS_SAVE seconds and at each event. */
#define OOT_STATS_SAVE 15
static struct { char seed[sizeof oot_checks_seed]; long seconds, deaths, finished; int loaded, dirty; } oot_stats;
static void oot_stats_load(void) {
    if (oot_stats.loaded && !strcmp(oot_stats.seed, oot_checks_seed)) return;
    memset(&oot_stats, 0, sizeof oot_stats);
    snprintf(oot_stats.seed, sizeof oot_stats.seed, "%s", oot_checks_seed);
    oot_stats.loaded = 1;
    char path[MAX_PATH + 48], line[1100];
    FILE *f = oot_game_file(path, sizeof path, "rando/run_stats.txt") ? fopen(path, "r") : NULL;
    int ours = 0;
    while (f && fgets(line, sizeof line, f)) {
        line[strcspn(line, "\r\n")] = 0;
        if (!strncmp(line, "seed ", 5)) ours = !strcmp(line + 5, oot_checks_seed);
        else if (ours) sscanf(line, "seconds %ld", &oot_stats.seconds), sscanf(line, "deaths %ld", &oot_stats.deaths),
                       sscanf(line, "finished %ld", &oot_stats.finished);
    }
    if (f) fclose(f);
}
static void oot_stats_save(void) {
    char path[MAX_PATH + 48];
    FILE *f = oot_game_file(path, sizeof path, "rando/run_stats.txt") ? fopen(path, "w") : NULL;
    if (!f) return;
    fprintf(f, "seed %s\nseconds %ld\ndeaths %ld\nfinished %ld\n", oot_stats.seed, oot_stats.seconds, oot_stats.deaths, oot_stats.finished);
    fclose(f);
    oot_stats.dirty = 0;
}
static void oot_stats_second(void) {
    if (oot_check_count <= 0) return;   /* (the seed's stamp known: the checks read) */
    oot_stats_load();
    oot_stats.seconds++, oot_stats.dirty = 1;
    if (oot_stats.seconds % OOT_STATS_SAVE == 0) oot_stats_save();
}
static void oot_stats_event(const char *name) {
    const int death = !strcmp(name, "DmF_SY_GameOver"), ganon = !strcmp(name, "Defeat_Ganon");
    if ((!death && !ganon) || oot_check_count <= 0) return;
    oot_stats_load();
    if (death) oot_stats.deaths++;
    if (ganon && !oot_stats.finished) oot_stats.finished = oot_stats.seconds ? oot_stats.seconds : 1;
    hos_log("rando: stats: %s (%ld s played, %ld deaths)", death ? "a death" : "Ganon defeated", oot_stats.seconds, oot_stats.deaths);
    oot_stats_save();
}

/* (the randomizer's fork, asked 2026-11-21) Free Scarecrow's Song: a save with no Scarecrow's Song of its own is given one,
   L R L R L, as if young Link had taught it to Bonooru and the adult had played it back: the song (the game data Binary
   0x3339df55, 0x178 bytes of (note, time) records: 0x02808003 L, 0x02808005 R, 0x01808001 the silence between; the
   owner's own L R L R L, read from their save, 2026-11-21), the scarecrow's quest at Complete (the Enum 0x9472302b) and the
   song learned (IsGet.Item_Melody_ScarecrowSong and its get scene's flag: the song list shows it). Pierre then answers it at his spots. The seed
   asks for it by <game folder>/mods/rando-seed/scarecrow_free.txt (rando_seed.py FREE_SCARECROW_FILE). A save that has a
   song of its own keeps it. The manager keeps a Binary in a table of entries (mgr+OOT_BIN_ENTRIES, 0x48 bytes each: two
   buffers, each a capacity, a pointer and a size, at +0x18) found by a hash index (mgr+OOT_BIN_INDEX, mgr+OOT_BIN_INDEX_N
   pairs of hash and entry): seen in the manager's memory with the owner's save loaded (HOS_OOT_FIND64, 2026-11-21). */
#define OOT_BIN_ENTRIES 0x6d8
#define OOT_BIN_INDEX 0x6e0
#define OOT_BIN_INDEX_N 0x6ec
#define OOT_SCARECROW_SONG 0x3339df55u
#define OOT_SCARECROW_QUEST 0x9472302bu
#define OOT_QUEST_COMPLETE 1275749364u   /* (murmur3 "Complete") */
#define OOT_SCARECROW_GOT 0x5e86fb4du        /* (IsGet.Item_Melody_ScarecrowSong: the song list shows it) */
#define OOT_SCARECROW_GOT_SCENE 0x23e7e426u  /* (HavePlayedGetEvent.Item_Melody_ScarecrowSong) */
/* (and what else the adult's playback sets, by the owner's two saves around it (Scarecrow 4 adult before / 5 after,
   2026-11-21): three truth values, two numbers and a step, unnamed in the game's files. The song list showed no notes
   and Pierre did not come with the song, its length and the quest alone) */
static const uint32_t oot_scarecrow_bools[] = {0x82cce1c8u, 0xaf77d894u, 0xb43290f9u};
#define OOT_SCARECROW_INT_A 0x37c3f735u   /* (20 before, -1 after) */
#define OOT_SCARECROW_INT_B 0x8566048eu   /* (0 before, 12 after) */
#define OOT_SCARECROW_STEP 0x5b3d04c1u    /* (3069107721 before, 3661746881 after) */
#define OOT_SCARECROW_STEP_AFTER 3661746881u
static uint64_t oot_binary_entry(Ctx *c, uint32_t hash) {
    const uint64_t mgr = oot_singleton(c, OOT_GAMEDATA_SLOT);
    if (!mgr) return 0;
    const uint64_t index = recomp_load64(c, mgr + OOT_BIN_INDEX), entries = recomp_load64(c, mgr + OOT_BIN_ENTRIES);
    const uint32_t n = recomp_load32(c, mgr + OOT_BIN_INDEX_N);
    if (!index || !entries || !n || n > 4096) return 0;
    for (uint32_t i = 0; i < n; i++)
        if (recomp_load32(c, index + 8ULL * i) == hash) return entries + 0x48ULL * recomp_load32(c, index + 8ULL * i + 4);
    return 0;
}
/* (2026-11-21, the second try) The song is kept twice: the recording above, and its notes alone, up to eight, in the
   game data's Int array 0xcc535536 (4 = L, 7 = R; the owner's L R L R L: 4 7 4 7 4 0 0 0). Bonooru's recorder
   (OneShotSetScarecrowMelodyGameData, 0x8295d000) writes both (0x832b8d00 the notes, 0x80d7e730 the recording, and only
   when the first note is not 0), and the ocarina's code reads both back (0x811544e0); the song list and Pierre's check
   read the notes. The first try wrote the recording alone: a learned song with an empty staff that Pierre did not
   answer. The Int arrays are kept as the Binaries are, from GameDataMgr+0x7e8: +0x7f0 how many, +0x7f8 the entries of
   0x40 bytes (+0x20 how many numbers, +0x28 the numbers), +0x800 the (hash, entry) table and +0x80c its size, as the
   game's reader 0x8377b980 walks them. */
#define OOT_SCARECROW_NOTES 0xcc535536u
static uint64_t oot_int_array_entry(Ctx *c, uint32_t hash) {
    const uint64_t mgr = oot_singleton(c, OOT_GAMEDATA_SLOT);
    if (!mgr) return 0;
    const uint64_t table = recomp_load64(c, mgr + 0x800), entries = recomp_load64(c, mgr + 0x7f8);
    const uint32_t size = recomp_load32(c, mgr + 0x80c), count = recomp_load32(c, mgr + 0x7f0);
    if (!table || !entries || !size || size > 65536) return 0;
    for (uint32_t probe = 0, slot = hash % size; probe < size; probe++, slot = (slot + 1) % size) {
        const uint32_t key = recomp_load32(c, table + slot * 8ULL);
        if (!key) return 0;
        if (key != hash) continue;
        const uint32_t index = recomp_load32(c, table + slot * 8ULL + 4);
        return index < count ? entries + 0x40ULL * index : 0;
    }
    return 0;
}
static void oot_scarecrow_free(Ctx *c) {
    static const uint32_t notes[8] = {4, 7, 4, 7, 4, 0, 0, 0};
    static const uint32_t song[20] = {0x02808003, 16, 0x01808001, 18, 0x02808005, 18, 0x01808001, 20, 0x02808003, 14,
                                      0x01808001, 24, 0x02808005, 16, 0x01808001, 22, 0x02808003, 14, 0x01808001, 0};
    static int want = -1;
    static char seed_of[sizeof oot_checks_seed];
    if (want < 0 || strcmp(seed_of, oot_checks_seed)) {
        char path[MAX_PATH + 48];
        snprintf(seed_of, sizeof seed_of, "%s", oot_checks_seed);
        FILE *f = oot_game_file(path, sizeof path, "mods/rando-seed/scarecrow_free.txt") ? fopen(path, "r") : NULL;
        want = f != NULL;
        if (f) fclose(f);
    }
    if (!want) return;
    const uint64_t entry = oot_binary_entry(c, OOT_SCARECROW_SONG);
    static int told;
    if (!told++) {   /* (once a run: what it found, for a log read after a test) */
        const uint64_t mgr = oot_singleton(c, OOT_GAMEDATA_SLOT);
        hos_log("rando: Free Scarecrow's Song: manager %#llx, index %#llx (%u), entries %#llx, the song's entry %#llx, its first words %08x %08x",
                (unsigned long long)mgr, (unsigned long long)(mgr ? recomp_load64(c, mgr + OOT_BIN_INDEX) : 0), mgr ? recomp_load32(c, mgr + OOT_BIN_INDEX_N) : 0,
                (unsigned long long)(mgr ? recomp_load64(c, mgr + OOT_BIN_ENTRIES) : 0), (unsigned long long)entry,
                entry && recomp_load64(c, entry + 0x20) ? recomp_load32(c, recomp_load64(c, entry + 0x20)) : 0,
                entry && recomp_load64(c, entry + 0x20) ? recomp_load32(c, recomp_load64(c, entry + 0x20) + 4) : 0);
    }
    const uint64_t notes_entry = oot_int_array_entry(c, OOT_SCARECROW_NOTES);
    const uint64_t notes_at = notes_entry && recomp_load32(c, notes_entry + 0x20) >= 8 ? recomp_load64(c, notes_entry + 0x28) : 0;
    if (told == 1) {
        told++;
        hos_log("rando: Free Scarecrow's Song: the notes' entry %#llx: %016llx %016llx %016llx %016llx %016llx %016llx %016llx %016llx, the first note %u",
                (unsigned long long)notes_entry, (unsigned long long)(notes_entry ? recomp_load64(c, notes_entry) : 0),
                (unsigned long long)(notes_entry ? recomp_load64(c, notes_entry + 8) : 0), (unsigned long long)(notes_entry ? recomp_load64(c, notes_entry + 0x10) : 0),
                (unsigned long long)(notes_entry ? recomp_load64(c, notes_entry + 0x18) : 0), (unsigned long long)(notes_entry ? recomp_load64(c, notes_entry + 0x20) : 0),
                (unsigned long long)(notes_entry ? recomp_load64(c, notes_entry + 0x28) : 0), (unsigned long long)(notes_entry ? recomp_load64(c, notes_entry + 0x30) : 0),
                (unsigned long long)(notes_entry ? recomp_load64(c, notes_entry + 0x38) : 0), notes_at ? recomp_load32(c, notes_at) : 0);
    }
    if (!entry || !notes_at) return;
    /* (the song: written where the save has none; a song of the save's own (taught to Bonooru) is kept, and only the
       quest and the pouch are seen to, so Pierre answers it) */
    /* (no song: the length 0 (a new game's: the room is there, 0x178 bytes, the length not), or nothing in it. A song
       written without its length is an empty song to the game: seen in play 2026-11-21, the list showed no notes) */
    int wrote = 0;
    const uint64_t first = recomp_load64(c, entry + 0x20);
    /* (or no notes: the game's own sign of no song (0x80d7e730), and what a save of the first try has, the recording
       without them: it gets both again) */
    if (first && (recomp_load64(c, entry + 0x28) == 0 || recomp_load32(c, first) == 0 || recomp_load32(c, notes_at) == 0)) {
        for (int b = 0; b < 2; b++) {   /* (both lists of 8, as the recording's two: +0x20/+0x28 and +0x30/+0x38, seen in a run) */
            const uint64_t list = recomp_load32(c, notes_entry + 0x20 + 0x10 * b) >= 8 ? recomp_load64(c, notes_entry + 0x28 + 0x10 * b) : 0;
            for (unsigned k = 0; list && k < 8; k++) recomp_store32(c, list + 4 * k, notes[k]);
        }
        for (int b = 0; b < 2; b++) {   /* (both buffers: the song as the save has it and the one kept beside it) */
            const uint64_t cap = recomp_load64(c, entry + 0x18 + 0x18 * b), data = recomp_load64(c, entry + 0x20 + 0x18 * b);
            if (!data || cap < 0x178) continue;
            for (unsigned k = 0; k < 0x178 / 4; k++) recomp_store32(c, data + 4 * k, k < sizeof song / 4 ? song[k] : 0);
            recomp_store64(c, entry + 0x28 + 0x18 * b, 0x178);   /* (its length: the whole room, as a taught song's) */
            wrote++;
        }
    }
    uint32_t quest = 0;
    const int quest_done = oot_gamedata_enum(c, OOT_SCARECROW_QUEST, &quest, 0) && quest == OOT_QUEST_COMPLETE;
    int in_pouch = 0, played = 0;   /* (the song learned: its flags, as the other songs', oot_song_flag) */
    oot_gamedata_bool(c, OOT_SCARECROW_GOT, &in_pouch);
    oot_gamedata_bool(c, OOT_SCARECROW_GOT_SCENE, &played);
    int32_t count_b = 0;
    oot_gamedata_int(c, OOT_SCARECROW_INT_B, &count_b, 0);
    if (!wrote && quest_done && in_pouch && played && count_b == 12) return;
    for (unsigned k = 0; k < sizeof oot_scarecrow_bools / sizeof oot_scarecrow_bools[0]; k++) oot_gamedata_set_bool(c, oot_scarecrow_bools[k], 1);
    int32_t a = -1, b = 12, a_now = 0;
    const int set_a = oot_gamedata_int(c, OOT_SCARECROW_INT_A, &a, 1), set_b = oot_gamedata_int(c, OOT_SCARECROW_INT_B, &b, 1);
    uint32_t step = OOT_SCARECROW_STEP_AFTER, step_now = 0;
    const int set_step = oot_gamedata_enum(c, OOT_SCARECROW_STEP, &step, 1);
    oot_gamedata_int(c, OOT_SCARECROW_INT_A, &a_now, 0);
    oot_gamedata_enum(c, OOT_SCARECROW_STEP, &step_now, 0);
    hos_log("rando: Free Scarecrow's Song: set %08x %d (now %d), %08x %d, %08x %d (now %u)", OOT_SCARECROW_INT_A, set_a, a_now,
            OOT_SCARECROW_INT_B, set_b, OOT_SCARECROW_STEP, set_step, step_now);
    if (!quest_done) {
        uint32_t done = OOT_QUEST_COMPLETE;
        oot_gamedata_enum(c, OOT_SCARECROW_QUEST, &done, 1);
    }
    if (!in_pouch) oot_gamedata_set_bool(c, OOT_SCARECROW_GOT, 1);
    if (!played) oot_gamedata_set_bool(c, OOT_SCARECROW_GOT_SCENE, 1);
    hos_log("rando: Free Scarecrow's Song: %s, the scarecrow's quest %s, the song %s", wrote ? "L R L R L given" : "the save's own song kept",
            quest_done ? "was done" : "done now", in_pouch ? "was learned" : "learned now");
}

static void oot_tracker_refresh(Ctx *c, int64_t now, uint64_t actor) {
    void rx_option_set(int id, int value);
    static int64_t next, next_stamp;
    for (unsigned i = 0; i < 3; i++) oot_link_place[i] = oot_load_float(c, actor + 796 + i * 4);
    {   /* (the Tracker's map: where Link is and the way he faces, ten times a second) */
        static int64_t next_place;
        if (now >= next_place) {
            next_place = now + 100000000LL;
            const float yaw = atan2f(oot_load_float(c, actor + 816), oot_load_float(c, actor + 840));
            if (fabsf(oot_link_place[0]) < 2e6f && fabsf(oot_link_place[2]) < 2e6f && yaw == yaw) {
                rx_option_set(OOT_LINK_X, (int)lrintf(oot_link_place[0] * 100));
                rx_option_set(OOT_LINK_Z, (int)lrintf(oot_link_place[2] * 100));
                rx_option_set(OOT_LINK_YAW, (int)lrintf(yaw * 1000));
                if (fabsf(oot_link_place[1]) < 2e6f) rx_option_set(OOT_LINK_Y, (int)lrintf(oot_link_place[1] * 100));
            }
            static int log_place = -1;   /* (HOS_OOT_PLACE_LOG=1, test runs: where Link is, twice a second, for fitting the minimap) */
            static int64_t next_log;
            if (log_place < 0) log_place = env_on("HOS_OOT_PLACE_LOG");
            if (log_place && now >= next_log) {
                next_log = now + 500000000LL;
                char banc[80] = "";
                oot_gamedata_string(c, 0x1d6189dau, banc, sizeof banc);   /* Sequence_CurrentBanc */
                hos_log("place: %.2f %.2f %.2f %s", oot_link_place[0], oot_link_place[1], oot_link_place[2], banc);
            }
        }
    }
    if (now < next) return;
    {   /* (Link's age, for the checks of an add's item: bug 125) */
        int child = 0;
        oot_link_child = oot_gamedata_bool(c, 0xcea220d3u, &child) ? (child != 0) : -1;   /* Sequence_IsChildhood */
    }
    next = now + 1000000000LL;
    if (!hos_rando_on()) return;
    rx_option_set(OOT_TRACKER_ON, 1);   /* (the Tracker tab reads the seed only then: vk_menu.cpp tracker_load) */
    {   /* (the temples done, a bit each: their awakening scenes played, what the game's AllSage asks before Zelda's Light Arrows.
           The Tracker says "in logic after ..." of a check that waits for one: tools/rando/rando_seed.py check_after) */
        static const char *const oot_story_scenes[] = {"HavePlayedEvent.Dm_Awake_Forest", "HavePlayedEvent.Dm_Awake_Fire",
                                                       "HavePlayedEvent.Dm_Awake_Water", "HavePlayedEvent.Dm_Awake_Shadow",
                                                       "HavePlayedEvent.Dm_Awake_Spirit"};
        int temples = 0;
        for (unsigned i = 0; temples >= 0 && i < sizeof oot_story_scenes / sizeof oot_story_scenes[0]; i++) {
            int played = 0;
            if (!oot_gamedata_bool(c, oot_flag_hash(oot_story_scenes[i]), &played)) temples = -1;   /* (no save's list yet) */
            else if (played) temples |= 1 << i;
        }
        rx_option_set(OOT_TRACKER_TEMPLES, temples);
    }
    {
        const int changed = oot_shelf_flags(c);
        if (changed) hos_log("rando: tracker: %d shop shelves put out, or marked as the save says", changed);
    }
    oot_stone_heard(c);   /* (a Gossip Stone talked to: its hint is the Tracker's) */
    oot_stats_second();   /* (the run's time played: oot_stats) */
    if (oot_check_count > 0) oot_scarecrow_free(c);   /* (Free Scarecrow's Song: a save without one given L R L R L) */
    if (oot_check_count > 0) oot_start_items(c, oot_checks_seed);   /* (the seed's starting items, each one Link lacks; once the
        seed's checks are read: before, the seed's stamp is not yet known, and a list read again dropped an item's ammo) */
    {   /* (a test's: HOS_OOT_SETFLAG="<hash in hex>=<0 or 1>,..." sets those truth values of the game's list once, some
           seconds into the game, and says what each was: to try a scene's steps one at a time) */
        static int turn;
        const char *set = getenv("HOS_OOT_SETFLAG");
        if (set && ++turn == 8) {
            while (*set) {
                char *end;
                const uint32_t hash = (uint32_t)strtoul(set, &end, 16);
                if (*end != '=') break;
                const int value = end[1] == '1';
                int was = -1;
                const int found = oot_gamedata_bool(c, hash, &was);
                hos_log("test: flag %08x was %d%s: set to %d (%s)", hash, was, found ? "" : " (not found)", value,
                        oot_gamedata_set_bool(c, hash, value) ? "done" : "NOT DONE");
                set = end + 2;
                if (*set == ',') set++;
            }
        }
    }
#ifdef _WIN32
    {   /* (a test's: HOS_OOT_FIND64="<64-bit value in hex>,..." looks for those values in all of the game's memory at
           the seconds of HOS_OOT_FIND64_AT="<second>,..." (20 without it), and says where each is and what is beside
           it, with the flags' manager's own words: to find where the game keeps what it knows by an actor's hash) */
        static int turn;
        const char *find = getenv("HOS_OOT_FIND64");
        if (find && *find) {
            const char *at = getenv("HOS_OOT_FIND64_AT");
            turn++;
            int now_is = at ? 0 : turn == 20;
            for (const char *p = at; p && *p;) {
                char *end;
                if ((int)strtol(p, &end, 10) == turn) now_is = 1;
                if (end == p) break;
                p = *end == ',' ? end + 1 : end;
            }
            if (now_is) {
                uint64_t keys[16];
                int n = 0, hits[16] = {0};
                for (const char *p = find; *p && n < 16;) {
                    char *end;
                    keys[n] = strtoull(p, &end, 16);
                    if (end == p) break;
                    n++;
                    p = *end == ',' ? end + 1 : end;
                }
                const uint64_t mgr = oot_singleton(c, OOT_GAMEDATA_SLOT);
                hos_log("test: find64 at second %d: the flags' manager is at %#llx", turn, (unsigned long long)mgr);
                for (unsigned row = 0; mgr && row < 0x4c0 / 32; row++)
                    hos_log("test: mgr+%03x: %016llx %016llx %016llx %016llx", row * 32,
                            (unsigned long long)recomp_load64(c, mgr + row * 32), (unsigned long long)recomp_load64(c, mgr + row * 32 + 8),
                            (unsigned long long)recomp_load64(c, mgr + row * 32 + 16), (unsigned long long)recomp_load64(c, mgr + row * 32 + 24));
                for (uint64_t a = 0x1000; a < HOS_GUEST_SPACE && !(n == 1 && !keys[0]);) {   /* ("0": no search) */
                    MEMORY_BASIC_INFORMATION m;
                    if (!VirtualQuery(GP(a), &m, sizeof m)) break;
                    const uint64_t base = (uint64_t)((uint8_t *)m.BaseAddress - (uint8_t *)GP(0));
                    const uint64_t end = base + m.RegionSize;
                    const int readable = m.State == MEM_COMMIT && !(m.Protect & (PAGE_GUARD | PAGE_NOACCESS)) &&
                                         (m.Protect & (PAGE_READWRITE | PAGE_READONLY | PAGE_EXECUTE_READ | PAGE_EXECUTE_READWRITE | PAGE_WRITECOPY));
                    if (readable && base >= 0x84000000ULL)   /* (past the game's code) */
                        for (uint64_t g = base > a ? base : a; g + 8 <= end; g += 4) {
                            uint64_t v;
                            memcpy(&v, GP(g), 8);
                            for (int k = 0; k < n; k++)
                                if (v == keys[k] && hits[k]++ < 24) {
                                    uint64_t w[6] = {0};
                                    if (g >= base + 16 && g + 32 <= end) memcpy(w, GP(g - 16), sizeof w);
                                    hos_log("test: find64 %016llx at %#llx: %016llx %016llx [%016llx] %016llx %016llx %016llx",
                                            (unsigned long long)keys[k], (unsigned long long)g, (unsigned long long)w[0], (unsigned long long)w[1],
                                            (unsigned long long)w[2], (unsigned long long)w[3], (unsigned long long)w[4], (unsigned long long)w[5]);
                                }
                        }
                    a = end > a ? end : a + 0x1000;
                }
                {   /* (HOS_OOT_KEYED_DUMP="<file>": the keyed table and the manager's words about it, as they are) */
                    const char *path = getenv("HOS_OOT_KEYED_DUMP");
                    char name[600];
                    if (path) snprintf(name, sizeof name, "%s.%d", path, turn);
                    FILE *f = path && mgr ? fopen(name, "wb") : NULL;
                    if (f) {
                        /* (everything the manager keeps is in one stretch of memory, from the manager itself to past
                           the keyed table: seen in its own words) */
                        const uint64_t last = recomp_load64(c, mgr + OOT_KEYED_VALUES) + 0x4000;
                        uint64_t done = 0;
                        for (uint64_t a = mgr & ~0xfffULL; a < last && last - mgr < (64ULL << 20); a += 0x1000) {
                            MEMORY_BASIC_INFORMATION m;
                            static const uint8_t none[0x1000];
                            const int ok = VirtualQuery(GP(a), &m, sizeof m) && m.State == MEM_COMMIT && !(m.Protect & (PAGE_GUARD | PAGE_NOACCESS));
                            fwrite(ok ? (const uint8_t *)GP(a) : none, 1, 0x1000, f);
                            done += 0x1000;
                        }
                        fclose(f);
                        hos_log("test: the manager's memory written, %llu bytes from %#llx", (unsigned long long)done, (unsigned long long)(mgr & ~0xfffULL));
                    }
                }
                for (int k = 0; k < n; k++) {
                    uint32_t reset = 0;
                    const int64_t i = oot_gamedata_keyed_index(c, keys[k], &reset);
                    const uint64_t values = mgr ? recomp_load64(c, mgr + OOT_KEYED_VALUES) : 0;
                    hos_log("test: find64 %016llx: %d places; place %lld of the keyed table, reset %u; after the table: word %08x (bit %d), byte %02x (bit %d), byte of its own %02x",
                            (unsigned long long)keys[k], hits[k], (long long)i, reset,
                            i >= 0 && values ? recomp_load32(c, values + (i >> 5) * 4) : 0,
                            i >= 0 && values ? (int)(recomp_load32(c, values + (i >> 5) * 4) >> (i & 31) & 1) : -1,
                            i >= 0 && values ? (unsigned)recomp_load8(c, values + (i >> 3)) : 0,
                            i >= 0 && values ? (int)(recomp_load8(c, values + (i >> 3)) >> (i & 7) & 1) : -1,
                            i >= 0 && values ? (unsigned)recomp_load8(c, values + i) : 0);
                }
            }
        }
    }
#endif
    if (env_on("HOS_OOT_WHERE"))   /* (a test's: HOS_OOT_WHERE=1 says where Link is each second) */
        hos_log("test: Link is at %.2f %.2f %.2f", oot_link_place[0], oot_link_place[1], oot_link_place[2]);
    {   /* (a test's: HOS_OOT_WATCHFLAG="<hash in hex>,..." says each of those truth values of the game's list when it
           is first read and each time it changes: to see which flag an item given sets) */
        static int was[32], first = 1;
        const char *watch = getenv("HOS_OOT_WATCHFLAG");
        for (int k = 0; watch && *watch && k < 32; k++) {
            char *end;
            const uint32_t hash = (uint32_t)strtoul(watch, &end, 16);
            if (end == watch) break;
            int value = -1;
            if (!oot_gamedata_bool(c, hash, &value)) value = -1;
            if (first || value != was[k]) hos_log("test: flag %08x is %d", hash, value);
            was[k] = value;
            watch = *end == ',' ? end + 1 : end;
        }
        first = 0;
    }
    {   /* (a test's: HOS_OOT_KEYED="<hash in hex>,..." says each second from the 60th what the truth values kept by
           those actors' hashes are, when one changed; HOS_OOT_KEYED_SET="<second>" sets them all true at that second) */
        static int turn;
        static char last[64];
        const char *keys = getenv("HOS_OOT_KEYED"), *at = getenv("HOS_OOT_KEYED_SET");
        if (keys && ++turn >= 60) {
            char now_is[64] = "";
            int n = 0;
            while (*keys && n < 60) {
                char *end;
                const uint64_t key = strtoull(keys, &end, 16);
                int v = 0;
                if (end == keys) break;
                if (at && turn == atoi(at)) oot_gamedata_keyed_set_bool(c, key, 1);
                now_is[n++] = oot_gamedata_keyed_bool(c, key, &v) ? (v ? '1' : '0') : '?';
                keys = *end ? end + 1 : end;
            }
            now_is[n] = 0;
            if (strcmp(now_is, last)) hos_log("test: keyed, second %d: %s", turn, now_is), strcpy(last, now_is);
        }
    }
    {   /* (a test's: HOS_OOT_SETENUM="<hash in hex>=<a value's hash in hex>,..." sets those values of the list's Data.Enum
           once, some seconds into the game, and says what each was: a quest's step) */
        static int turn;
        const char *set = getenv("HOS_OOT_SETENUM");
        if (set && ++turn == 8) {
            while (*set) {
                char *end;
                const uint32_t hash = (uint32_t)strtoul(set, &end, 16);
                if (*end != '=') break;
                uint32_t value = (uint32_t)strtoul(end + 1, &end, 16), was = 0;
                const int found = oot_gamedata_enum(c, hash, &was, 0);
                hos_log("test: enum %08x was %08x%s: set to %08x (%s)", hash, was, found ? "" : " (not found)", value,
                        oot_gamedata_enum(c, hash, &value, 1) ? "done" : "NOT DONE");
                set = end;
                if (*set == ',') set++;
            }
        }
    }
    {   /* (a test's: HOS_OOT_GIVE="<item>,<item>,..." puts those in the pouch, one a second from the tenth second on, as
           a scene's gift is put there, and says how many Link then has: to try what follows an item without playing up
           to it (a Deku Nut bag is in no row of the Debug tab's inventory) */
        static int turn;
        const char *give = getenv("HOS_OOT_GIVE");
        if (give && ++turn >= 10) {
            int k = turn - 10;
            while (k > 0 && *give) {
                give += strcspn(give, ",");
                if (*give == ',') give++;
                k--;
            }
            char item[64];
            const size_t length = strcspn(give, ",");
            if (length && length < sizeof item) {
                memcpy(item, give, length);
                item[length] = 0;
                const int result = oot_pouch_change(c, item, 1);
                hos_log("test: %s given (event status %d): Link has %d", item, result, oot_pouch_count(c, item));
            }
            {   /* (a test's: HOS_OOT_TEST_BOOTS=<boots actor> logs the boots wanted (game data EquipBoot, a string the
                   player's boots code, f_80a98d40, compares with the boots worn) each second, and at the 25th writes it there) */
                const char *boots = getenv("HOS_OOT_TEST_BOOTS");
                if (boots && turn < 60) {
                    char now[80];
                    const int have = oot_gamedata_string(c, 0x6aa85ab3u, now, sizeof now);   /* (EquipBoot) */
                    hos_log("test: EquipBoot %s\"%s\"", have ? "" : "(not found) ", now);
                    if (turn == 25 && *boots) {
                        const uint64_t at = oot_gamedata_string_at(c, 0x6aa85ab3u);
                        if (at > 0xffffffffULL) { for (size_t i = 0; i <= strlen(boots) && i < 64; i++) recomp_store8(c, at + i, (uint8_t)boots[i]); }   /* (a heap buffer only: not the image's own empty text) */
                        hos_log("test: EquipBoot written \"%s\" (%#llx)", boots, (unsigned long long)at);
                    }
                }
            }
            int32_t mp = -1, most = -1;   /* (what the magic is a second after each, for a test of a refill) */
            oot_gamedata_live_int(c, 0x76b18200u, &mp, 0, NULL);   /* PlayerStatus.MP */
            oot_gamedata_live_int(c, 0x12d63a97u, &most, 0, NULL);   /* PlayerStatus.MPMax */
            if (turn < 40) hos_log("test: magic %d of %d", (int)mp, (int)most);
        }
    }
    {   /* (the randomizer's fork) Hyrule Field's clock. Until the owl's first cutscene there the field's sky stays the
           day's whatever time is asked for: no day turned to night, and the Sun's Song's night was day again at once
           (seen in play). What ends it is the flag HyruleField_ArriveEntrance (its MurmurHash3 below), the first thing
           the owl's event sets; tools/rando/rando_seed.py FIELD_CLOCK has how it was found. A seed's new game starts
           with it set; a save made before that has it put out still, so it is set here, once a second while it is
           not. The owl's event begins all the same. */
        int reached = 1;
        if (oot_gamedata_bool(c, 0x804aec99u, &reached) && !reached) {
            const int done = oot_gamedata_set_bool(c, 0x804aec99u, 1);
            static int said;
            if (said++ < 4) hos_log("rando: Hyrule Field's sky was held as the day's (HyruleField_ArriveEntrance was not set): the flag is set%s",
                                    done ? "" : ", NOT FOUND");
        }
    }
    {   /* (the randomizer's fork) The d-pad's HUD (Navi and the boots, by the hearts): a new game has none of it until the
           first scene in the Deku Tree. What shows it is a flag no file of the game names, known by its hash alone
           (tools/rando/rando_seed.py DPAD_HUD has how it was found). A seed's new game starts with it set; a save made
           before that has it put out, so it is set here, once a second while it is not. The HUD comes at the next
           load of an area. */
        int shown = 1;
        if (oot_gamedata_bool(c, 0x7be57cb0u, &shown) && !shown) {
            const int done = oot_gamedata_set_bool(c, 0x7be57cb0u, 1);
            static int said;
            if (said++ < 4) hos_log("rando: the d-pad's HUD was not shown yet (flag 7be57cb0 put out): the flag is set%s", done ? "" : ", NOT FOUND");
        }
    }
    {   /* (Willow Woods, 2026-11-20) The Water Temple's gate by Lake Hylia open: its switch's cutscene marked played
           (HavePlayedEvent.Dm_WaterTemple_0000, 392b86fb) and the gate's pillars risen (WaterTemple_EmitGatePillar,
           ab74fd3c), the state the game leaves once the switch is hit, which it would not be before the Ice Cavern
           (seen in play). They are set here, once a second while they are not: a new game's within its first second,
           long before the lake is loaded (until 2026-11-22 a seed's new game also started with them, rando_seed.py
           WATER_GATE). Not with the Water Temple gate setting at Shut (rando_water_gate): the gate is then as the
           save has it, and its switch opens it. */
        static const uint32_t gate[2] = {0x392b86fbu, 0xab74fd3cu};
        static int skip = -1;   /* (a test's: HOS_OOT_NO_WATER_GATE=1 leaves the gate as the save has it, to try its switch;
                                   =clear also puts the two out once, in the first area the save is in that is not Hyrule
                                   Field (the lake's gate reads them when the field loads, so they go before it):
                                   the gate shut and its cutscene not played) */
        static int cleared;
        int hos_rando_water_gate_shut(void);   /* host/oot_rando.c: the Water Temple gate setting at Shut: left to its switch */
        if (skip < 0) skip = getenv("HOS_OOT_NO_WATER_GATE") != NULL || hos_rando_water_gate_shut();
        if (skip && !cleared && getenv("HOS_OOT_NO_WATER_GATE") && !strcmp(getenv("HOS_OOT_NO_WATER_GATE"), "clear")) {
            char map[80];
            if (oot_gamedata_string(c, 0x1d6189dau, map, sizeof map) && map[0] && strncmp(map, "HyruleField", 11)) {   /* Sequence_CurrentBanc */
                cleared = 1;
                for (int g = 0; g < 2; g++)
                    hos_log("test: the Water Temple's gate shut: flag %08x put out (%s)", gate[g], oot_gamedata_set_bool(c, gate[g], 0) ? "done" : "NOT DONE");
            }
        }
        for (int g = 0; g < 2 && !skip; g++) {
            int on = 1;
            if (oot_gamedata_bool(c, gate[g], &on) && !on) {
                const int done = oot_gamedata_set_bool(c, gate[g], 1);
                static int said;
                if (said++ < 4) hos_log("rando: the Water Temple's gate was shut (flag %08x put out): the flag is set%s", gate[g], done ? "" : ", NOT FOUND");
            }
        }
    }
    {   /* (the randomizer's fork) The minimap, the same way: a new game had none of it until the owl's scenes in Hyrule
           Field. Its flag too is known by its hash alone (tools/rando/rando_seed.py MINIMAP); set here for a save that
           has it put out, once a second while it is not. It comes at the next load of an area. */
        int shown = 1;
        if (oot_gamedata_bool(c, 0x2e315eb6u, &shown) && !shown) {
            const int done = oot_gamedata_set_bool(c, 0x2e315eb6u, 1);
            static int said;
            if (said++ < 4) hos_log("rando: the minimap was not shown yet (flag 2e315eb6 put out): the flag is set%s", done ? "" : ", NOT FOUND");
        }
    }
    {   /* (the randomizer's fork, 2026-11-23) An area's minimap shows once the area is "visited" (IsVisitLocation.<location>),
           which its first-visit scene sets: with Skip cutscenes those scenes are marked played (tools/rando/rando_seed.py
           AREA_INTROS) and never run, so Lake Hylia, Kakariko, Zora's Fountain, Gerudo Valley and Hyrule Castle had no
           minimap (seen headless: the lake's came with the flag set). The location Link is in is marked visited here, once a
           second: his map's folder, the field's by where he stands (Lake Hylia's LocationArea, a sphere of 199; Lon Lon
           Ranch inside its walls, as the Minimap checks row has it); Ganon's Castle's grounds are Hyrule Castle's (MapMenuInfo). */
        static const struct { const char *location; uint32_t hash; } visit[] = {{"KokiriForest", 0x2e315eb6u}, {"KakarikoVillage", 0x5c9e740fu}, {"LonLonRanch", 0x009c5b53u}, {"Market", 0xc88633f0u}, {"GoronCity", 0xecf401b9u}, {"ZoraDomain", 0xede02703u}, {"GerudoFortress", 0x3d07b702u}, {"LostWood", 0xbd536912u}, {"SacredForestMeadow", 0xeb724c83u}, {"HyruleField", 0xdda673cbu}, {"HyruleCastle", 0xb7c0f231u}, {"Graveyard", 0x671a6e1bu}, {"DeathMountainTrail", 0x3c72143au}, {"DeathMountainCrater", 0xd0e4b0dau}, {"ZoraRiver", 0x2e975eedu}, {"ZoraFountain", 0x5de8bbd8u}, {"LakeHylia", 0x36778630u}, {"GerudoValley", 0x5a6c8704u}, {"HountedWasteland", 0x6160c3ecu}, {"DesertColossus", 0x607d9fe6u}};
        char banc[80] = "";
        oot_gamedata_string(c, 0x1d6189dau, banc, sizeof banc);   /* Sequence_CurrentBanc */
        char folder[48];
        snprintf(folder, sizeof folder, "%s", banc);
        folder[strcspn(folder, "_")] = 0;
        const char *location = !strcmp(folder, "GanonCastle") ? "HyruleCastle" : folder;
        if (!strcmp(folder, "HyruleField")) {
            const float x = oot_link_place[0], z = oot_link_place[2];
            static const float ranch[][2] = {{-62.3f, 186.1f}, {-34.5f, 191.3f}, {-19.8f, 270.2f}, {-90.9f, 294.3f}, {-137.4f, 234.8f}, {-100.4f, 177.7f}};
            int in = 0;   /* (Lon Lon Ranch inside its walls, as the Minimap checks row's in_ranch: the owner's screenshots, 2026-11-24) */
            for (int i = 0, j = 5; i < 6; j = i++)
                if ((ranch[i][1] > z) != (ranch[j][1] > z) && x < (ranch[j][0] - ranch[i][0]) * (z - ranch[i][1]) / (ranch[j][1] - ranch[i][1]) + ranch[i][0]) in = !in;
            location = hypotf(x + 205.4f, z - 559.2f) <= 199 ? "LakeHylia" : in ? "LonLonRanch" : "HyruleField";
        }
        for (unsigned i = 0; i < sizeof visit / sizeof visit[0]; i++) {
            int was = 1;
            if (strcmp(visit[i].location, location) || !oot_gamedata_bool(c, visit[i].hash, &was) || was) continue;
            const int done = oot_gamedata_set_bool(c, visit[i].hash, 1);
            hos_log("rando: %s marked visited (IsVisitLocation, its minimap)%s", location, done ? "" : ", NOT FOUND");
        }
    }
    char map[80];
    oot_gamedata_string(c, 0x1d6189dau, map, sizeof map);   /* Sequence_CurrentBanc */
    AcquireSRWLockExclusive(&oot_checks_lock);
    if (map[0] && strcmp(map, oot_link_map)) {   /* (the map left, for an add that comes as it changes: bug 124) */
        memcpy(oot_left_map, oot_link_map, sizeof oot_left_map);
        memcpy(oot_left_place, oot_link_place_was, sizeof oot_left_place);
        oot_left_at = now;
    }
    memcpy(oot_link_place_was, oot_link_place, sizeof oot_link_place_was);
    memcpy(oot_link_map, map, sizeof oot_link_map);
    if (oot_check_count < 0 || now >= next_stamp) {   /* (a seed made anew while the game runs: its checks, and no record of another's) */
        next_stamp = now + 15000000000LL;
        char stamp[sizeof oot_checks_seed];
        oot_tracker_stamp(stamp, sizeof stamp);
        if (oot_check_count < 0 || strcmp(stamp, oot_checks_seed)) oot_tracker_load(stamp);
    }
    oot_doors_note(oot_link_map);   /* (Dungeon entrances: the door of the dungeon Link is in is found) */
    oot_boss_doors_note(oot_link_map, oot_left_map, now - oot_left_at, oot_boss_room_near);   /* (Boss shuffle: the room he was sent from) */
    for (int i = 0; i < oot_check_count; i++) rx_option_set(OOT_TRACKER_BASE + i, oot_checks[i].done == 1);
    {   /* (where Link is, for the Tracker tab's order: a check of the map he is in, the first of the file) */
        int here = -1;
        for (int i = 0; i < oot_check_count && here < 0; i++)
            if (oot_banc_in_folder(oot_link_map, oot_checks[i].folder)) here = i;
        rx_option_set(OOT_TRACKER_HERE, here);
    }
    ReleaseSRWLockExclusive(&oot_checks_lock);
}

/* Age toggle: flips Sequence_IsChildhood (what the Temple of Time event sets) and reloads the current map, or the
   Market when this map is not in oot_destinations, through the teleport so the other age's map and Link load. 1: the map
   change was sent (teleport.banc its map); 0: not, teleport.why says why (the control bridge's reply) */
static int oot_toggle_age(Ctx *c, uint64_t actor) {
    int child = 1;
    if (!oot_gamedata_bool(c, 0xcea220d3u, &child)) {
        hos_log("cheats: age toggle: Sequence_IsChildhood not found");
        teleport.why = "Link's age is not in the game's data (Sequence_IsChildhood not found)", teleport.banc = NULL;
        return 0;
    }
    char current[80];
    oot_gamedata_string(c, 0x1d6189dau, current, sizeof current);   /* Sequence_CurrentBanc */
    unsigned target = 3;   /* Market (the Temple of Time is in it) */
    for (unsigned i = 0; i < sizeof oot_destinations / sizeof oot_destinations[0]; i++) {
        const OotDestination *d = &oot_destinations[i];
        const char *other = child ? d->adult_banc : d->child_banc;
        if (other && ((d->child_banc && !strcmp(d->child_banc, current)) || (d->adult_banc && !strcmp(d->adult_banc, current)))) {
            target = i;
            break;
        }
    }
    if (!oot_gamedata_set_bool(c, 0xcea220d3u, !child)) {
        hos_log("cheats: age toggle: could not write Sequence_IsChildhood");
        teleport.why = "Link's age could not be written (Sequence_IsChildhood)", teleport.banc = NULL;
        return 0;
    }
    hos_log("cheats: age toggle: %s -> %s, reloading via destination %u (current map \"%s\")",
            child ? "child" : "adult", child ? "adult" : "child", target, current);
    oot_teleport_child = !child;   /* (the age just set: the setter's write is queued, oot_teleport_child) */
    const int sent = oot_teleport(c, actor, target);
    oot_teleport_child = -1;
    if (!sent) {
        oot_gamedata_set_bool(c, 0xcea220d3u, child);
        hos_log("cheats: age toggle undone, the map change was not requested");
        return 0;
    }
    return 1;
}

static void oot_teleport_followup(Ctx *c) {
    if (!teleport.check_at || hos_now_ns() < teleport.check_at) return;
    teleport.check_at = 0;
    char next[80], current[80];
    oot_gamedata_string(c, 0xee27bf71u, next, sizeof next);     /* Sequence_ReservedNextBanc */
    oot_gamedata_string(c, 0x1d6189dau, current, sizeof current);   /* Sequence_CurrentBanc */
    const uint64_t events = oot_singleton(c, OOT_EVENTMGR_SLOT);
    hos_log("cheats: teleport check: reserved \"%s\", current \"%s\", event playing %d", next, current,
            events && recomp_load64(c, events + 104) ? 1 : 0);
}

/* (hookshot) the control bridge (host/control.c): the map the game is in (Sequence_CurrentBanc), read on the game's thread
   with the player's update every 250 ms and kept for the bridge's thread; the last one known (it stays through loads and
   menus, where Link is not updated). And the debug teleport by destination, as the Cheats page asks for it: taken at the
   next update of the player, in play, and what came of it (sent, or refused and why) kept for the bridge's reply */
static SRWLOCK oot_map_lock = SRWLOCK_INIT;
static char oot_map[80];
static int oot_flags = -1;   /* (1 an event playing, 2 a map loading, 4 the child; -1 not read yet) */
static void oot_map_refresh(Ctx *c, int64_t now) {
    static int64_t next;
    if (now < next) return;
    next = now + 250000000LL;
    char map[80];
    if (!oot_gamedata_string(c, 0x1d6189dau, map, sizeof map) || !map[0]) return;   /* Sequence_CurrentBanc */
    int loading = 0, child = 1;
    oot_gamedata_bool(c, 0xef2b60c2u, &loading);   /* Sequence_IsLoadingBanc */
    oot_gamedata_bool(c, 0xcea220d3u, &child);     /* Sequence_IsChildhood */
    const uint64_t events = oot_singleton(c, OOT_EVENTMGR_SLOT);
    const int flags = (events && recomp_load64(c, events + 104) ? 1 : 0) | (loading ? 2 : 0) | (child ? 4 : 0);
    AcquireSRWLockExclusive(&oot_map_lock);
    memcpy(oot_map, map, sizeof oot_map);
    oot_flags = flags;
    ReleaseSRWLockExclusive(&oot_map_lock);
}
/* (with the map) whether an event (a cutscene, a map change's) is playing, a map is loading, Link is the child: 0 before any */
int hos_oot_state(int *event, int *loading, int *child) {
    AcquireSRWLockShared(&oot_map_lock);
    const int f = oot_flags;
    ReleaseSRWLockShared(&oot_map_lock);
    if (f < 0) return 0;
    *event = f & 1, *loading = (f >> 1) & 1, *child = (f >> 2) & 1;
    return 1;
}
int hos_oot_current_map(char *out, size_t cap) {
    AcquireSRWLockShared(&oot_map_lock);
    const int have = oot_map[0] != 0;
    if (have) snprintf(out, cap, "%s", oot_map);
    ReleaseSRWLockShared(&oot_map_lock);
    return have;
}
int hos_oot_destination(int index, const char **child, const char **adult) {
    if (index < 0 || index >= (int)(sizeof oot_destinations / sizeof oot_destinations[0])) return 0;
    *child = oot_destinations[index].child_banc, *adult = oot_destinations[index].adult_banc;
    return 1;
}
/* The bridge's teleport: asked on its thread, taken at the player's next update (oot_bridge_teleport_take), and what came
   of it kept for the bridge, by ticket. A later ask replaces one not taken yet. (oot_map_lock) */
#define OOT_BRIDGE_AGE 0x10000   /* (oot_bridge_tp.asked: the age switch to the child, | 1 to the adult; not a destination) */
static struct {
    int asked;    /* the destination + 1 waiting to be taken, OOT_BRIDGE_AGE | adult the age switch; 0 none */
    int ticket;   /* the last ask's */
    int taking;   /* the ticket taken by the player's update and not done yet (it is not replaced meanwhile) */
    int done_ticket, result, accepted;   /* the last one taken: 1 sent, -1 refused, 2 (the age switch) Link was that age
                                            already; accepted: the event manager's answer */
    char why[96], map[80];
} oot_bridge_tp;
int hos_oot_teleport_ask(int index) {
    if (index < 0 || index >= (int)(sizeof oot_destinations / sizeof oot_destinations[0])) return 0;
    AcquireSRWLockExclusive(&oot_map_lock);
    const int ticket = ++oot_bridge_tp.ticket;
    __atomic_store_n(&oot_bridge_tp.asked, index + 1, __ATOMIC_RELAXED);   /* (read without the lock first: take) */
    ReleaseSRWLockExclusive(&oot_map_lock);
    return ticket;
}
/* The bridge's age switch to the adult (1) or the child (0): the Debug tab's Switch age (oot_toggle_age), asked and taken as
   a teleport is, with the same tickets, result and cancel. The age wanted goes with it and is checked when it is taken (the
   bridge's sample of Link's age can be old): already that age, nothing is done (result 2) */
int hos_oot_age_ask(int adult) {
    AcquireSRWLockExclusive(&oot_map_lock);
    const int ticket = ++oot_bridge_tp.ticket;
    __atomic_store_n(&oot_bridge_tp.asked, OOT_BRIDGE_AGE | (adult ? 1 : 0), __ATOMIC_RELAXED);
    ReleaseSRWLockExclusive(&oot_map_lock);
    return ticket;
}
/* 1 sent (map: the map it goes to; accepted: whether the game's event manager took the request), -1 refused (why: the
   reason), 2 (the age switch) Link was that age already, nothing done, 0 not taken yet (or being taken), -2 replaced by a
   later ask or cancelled */
int hos_oot_teleport_result(int ticket, char *why, size_t why_cap, char *map, size_t map_cap, int *accepted) {
    AcquireSRWLockShared(&oot_map_lock);
    int r = -2;
    if (oot_bridge_tp.done_ticket == ticket) {
        r = oot_bridge_tp.result, *accepted = oot_bridge_tp.accepted;
        snprintf(why, why_cap, "%s", oot_bridge_tp.why);
        snprintf(map, map_cap, "%s", oot_bridge_tp.map);
    } else if (oot_bridge_tp.taking == ticket || (oot_bridge_tp.ticket == ticket && oot_bridge_tp.asked)) r = 0;
    ReleaseSRWLockShared(&oot_map_lock);
    return r;
}
void hos_oot_teleport_cancel(int ticket) {   /* (the bridge gave up waiting: not taken later behind its back) */
    AcquireSRWLockExclusive(&oot_map_lock);
    if (oot_bridge_tp.ticket == ticket) __atomic_store_n(&oot_bridge_tp.asked, 0, __ATOMIC_RELAXED);
    ReleaseSRWLockExclusive(&oot_map_lock);
}
static int oot_bridge_teleport_take(int *ticket) {   /* (the player's update) the destination + 1 asked for, or 0 */
    if (!__atomic_load_n(&oot_bridge_tp.asked, __ATOMIC_RELAXED)) return 0;
    AcquireSRWLockExclusive(&oot_map_lock);
    const int asked = oot_bridge_tp.asked;
    *ticket = oot_bridge_tp.ticket;
    if (asked) oot_bridge_tp.taking = *ticket;   /* (still "not taken yet" to the bridge until done) */
    __atomic_store_n(&oot_bridge_tp.asked, 0, __ATOMIC_RELAXED);
    ReleaseSRWLockExclusive(&oot_map_lock);
    return asked;
}
static void oot_bridge_teleport_done(int ticket, int sent) {   /* sent: 1, 0 refused (teleport.why), 2 already that age */
    AcquireSRWLockExclusive(&oot_map_lock);
    if (sent == 2) {
        oot_bridge_tp.done_ticket = ticket, oot_bridge_tp.result = 2, oot_bridge_tp.taking = 0, oot_bridge_tp.accepted = 0;
        oot_bridge_tp.why[0] = oot_bridge_tp.map[0] = 0;
        ReleaseSRWLockExclusive(&oot_map_lock);
        return;
    }
    oot_bridge_tp.done_ticket = ticket, oot_bridge_tp.result = sent ? 1 : -1, oot_bridge_tp.taking = 0;
    oot_bridge_tp.accepted = sent && teleport.result != 0;
    snprintf(oot_bridge_tp.why, sizeof oot_bridge_tp.why, "%s", sent || !teleport.why ? "" : teleport.why);
    snprintf(oot_bridge_tp.map, sizeof oot_bridge_tp.map, "%s", sent && teleport.banc ? teleport.banc : "");
    ReleaseSRWLockExclusive(&oot_map_lock);
}

static uint64_t oot_gameplay_view(Ctx *c) {
    const uint64_t singleton = recomp_load64(c, 0x84ca6bc0ULL);
    const uint64_t manager = singleton ? recomp_load64(c, singleton) : 0;
    const uint64_t cameras = manager && recomp_load32(c, manager + 32) ? recomp_load64(c, manager + 40) : 0;
    const uint64_t camera = cameras ? recomp_load64(c, cameras) : 0;
    return camera ? recomp_load64(c, camera + 120) : 0;
}

static float oot_load_float(Ctx *c, uint64_t addr) {
    const uint32_t bits = recomp_load32(c, addr);
    float value;
    memcpy(&value, &bits, sizeof value);
    return value;
}

static _Thread_local uint64_t flight_transform_controller;
static _Thread_local uint64_t flight_pose_actor;
static _Thread_local float flight_transform_yaw;
static int64_t flight_player_seen;

/* Link's controller (vtable 0x84c54f10, the one OneShotPhysicsCctChangePosition moves) from his components, 0 when the chain
   is not there */
static uint64_t oot_player_controller(Ctx *c, uint64_t components) {
    const unsigned offsets[] = {80, 32, 16, 8};
    uint64_t controller = components;
    for (unsigned i = 0; i < sizeof offsets / sizeof offsets[0]; i++) {
        controller = recomp_load64(c, controller + offsets[i]);
        if (!controller) return 0;
    }
    return recomp_load64(c, controller) == 0x84c54f10ULL ? controller : 0;
}

/* Movement speed (the Debug tab's row, HOS_OPT_CHEAT_SPEED in percent): Link's controller and the percent for
   hos_oot_cct_speed, which scales the forward speed the game sets on it. (The controller's speed rate beside it, +476, is no
   use: the game sets it again before each step.) */
static void oot_player_speed(Ctx *c, uint64_t components) {
    int rx_option(int id, int otherwise);
    static int logged = 100;
    int percent = rx_option(HOS_OPT_CHEAT_SPEED, 100);
    if (percent < 100 || percent > 400) percent = 100;
    const uint64_t link = oot_player_controller(c, components);
    __atomic_store_n(&oot_link_controller, link, __ATOMIC_RELAXED);
    __atomic_store_n(&oot_speed_controller, percent > 100 ? link : 0, __ATOMIC_RELAXED);
    __atomic_store_n(&oot_speed_percent, percent, __ATOMIC_RELAXED);
    if (percent != logged) hos_log("cheats: movement speed %d%%", percent);
    logged = percent;
}

/* Whether the game moved Link since the flight last placed him: he is more than 2 units (the flight moves him 4 a second)
   from where it holds him. A respawn after a fall or a warp keeps his actor, so the flight took him straight back to
   where it had him, over the same drop: he fell, respawned and fell again until the flight was switched off. It starts
   again from where the game put him instead. */
static int oot_flight_moved_away(Ctx *c, uint64_t actor, const float held[3]) {
    float apart = 0;
    for (unsigned i = 0; i < 3; i++) {
        const float d = oot_load_float(c, actor + 796 + i * 4) - held[i];
        apart += d * d;
    }
    return apart > 2.0f * 2.0f;
}

/* (the randomizer's fork) a map (banc: "KokiriForest_Child", "HyruleCastle") is of a Banc folder ("KokiriForest") */
static int oot_banc_in_folder(const char *banc, const char *folder) {
    const size_t n = strlen(folder);
    return n && !strncmp(banc, folder, n) && (!banc[n] || banc[n] == '_');
}

/* (Maps and compasses: Anywhere, tools/rando/rando_seed.py MAPS_LOOSE) The pouch counts a chest's map, compass, Boss Key
   or small key for the dungeon Link is in: the save's DungeonInfo.<the dungeon's Banc folder>.IsGetMap, .IsGetCompass,
   .IsGetBossKey, .SmallKeyNum. One from a chest of dungeon_items.txt (the chest Link just opened: the nearest of them
   within OOT_DUNGEON_NEAR metres of him, in his map, holding that item) in another place than its dungeon: its dungeon's
   flag is set (a small key: its count raised) and the add is taken away (1). 0: the add goes on as it is. */
/* (Pots, rando_pots) Which pot an item picked up came from: the game's truth value by a pot's hash is "broken", set when it
   breaks and put back when it is back after about a day (bug 96). So the pots of Link's map giving that item (or its
   family's) that are broken now are the ones it can be from: one not yet collected is the one (oot_pot_chosen, which the
   record marks: oot_tracker_item), and with every such pot collected already, the pot is one back after a day and its
   item is nothing (1). 0: the add goes on; with no such pot broken (none read), the record finds its check as it does.
   (Until 2026-11-25 it went by distance: a pot within 3 m of Link done with that item was "back". Seen in play in the
   Market's guard house, 22 pots in 8 m, four of them a Gold Skulltula token: a second token from the pot beside a
   collected one was refused, and a thrown pot's item lands far from it, so the record marked another pot.) */
/* (FIXES 97, tools/rando/rando_seed.py POT_WORLD) A pot holding junk drops the game's own pick-up of it (no "You got"
   scene): the seed's item of the check, by the pick-up's name; NULL for any other name */
static const char *const oot_pot_world[][2] = {
    {"Obj_DekuNut", "TBox_DekuNutBundle"}, {"Obj_DekuStick", "Item_DekuStickBundle_Small"}, {"Obj_DekuSeed", "Item_ScrubBusinessSeed"},
    {"Obj_Bomb", "Item_BombBundle_Small"}, {"Obj_ArrowBundle_Medium", "TBox_ArrowBundle_Medium"},
    {"Obj_ArrowBundle_Large", "TBox_ArrowBundle_Large"}, {"Obj_MagicJar_Large", "Tbox_MagicJar_Large"},
};
static int oot_pot_junk(const char *item) {   /* (a pot's junk: collected when the pot breaks, oot_shelf_flags) */
    for (unsigned k = 0; k < sizeof oot_pot_world / sizeof oot_pot_world[0]; k++)
        if (!strcmp(item, oot_pot_world[k][1])) return 1;
    return 0;
}
static const char *oot_pot_world_item(const char *name) {
    for (unsigned k = 0; k < sizeof oot_pot_world / sizeof oot_pot_world[0]; k++)
        if (!strcmp(name, oot_pot_world[k][0])) return oot_pot_world[k][1];
    return NULL;
}
/* (a world pick-up marks a pot within this of Link only: grass and the game's own pots drop the same) */
#define OOT_POT_WORLD_NEAR 20.0f
/* (the pot of Link's map giving name, or its family's, that is broken now and not yet collected: its index, or -1;
   broken: how many broken ones give it. A world pick-up's name (oot_pot_world_item) stands for its check's item, from a
   pot within OOT_POT_WORLD_NEAR of Link) */
static int oot_pot_open(Ctx *c, const char *name, int *broken) {
    int open = -1, alike = -1;
    const char *world = oot_pot_world_item(name);
    if (world) name = world;
    const int family = hos_rando_progressive() ? oot_family_of(name, NULL) : -1;
    if (broken) *broken = 0;
    AcquireSRWLockShared(&oot_checks_lock);
    for (int i = 0; i < oot_check_count && open < 0; i++) {
        int now = 0;
        if (!oot_checks[i].pot || !oot_checks[i].broken || !oot_banc_in_folder(oot_link_map, oot_checks[i].folder)) continue;
        if (strcmp(oot_checks[i].item, name) && (family < 0 || oot_family_of(oot_checks[i].item, NULL) != family)) continue;
        if (world) {
            const float dx = oot_checks[i].place[0] - oot_link_place[0], dy = oot_checks[i].place[1] - oot_link_place[1],
                        dz = oot_checks[i].place[2] - oot_link_place[2];
            if (dx * dx + dy * dy + dz * dz > OOT_POT_WORLD_NEAR * OOT_POT_WORLD_NEAR) continue;
        }
        if (!oot_gamedata_keyed_bool(c, oot_checks[i].broken, &now) || !now) continue;
        if (broken) ++*broken;
        if (oot_checks[i].done != 1) {
            /* (a dungeon's own pick-up, oot_pickup_folder: the broken pot of its dungeon. Two broken by one swing, the
               first in the list was marked for the other's key, seen without a window 2026-11-26) */
            if (oot_pickup_folder[0] && strcmp(oot_checks[i].owner, oot_pickup_folder)) { if (alike < 0) alike = i; continue; }
            open = i;
        }
    }
    if (open < 0) open = alike;   /* (none of its dungeon: as before) */
    ReleaseSRWLockShared(&oot_checks_lock);
    return open;
}
static int oot_pot_again(Ctx *c, const char *name) {
    int broken = 0;
    const int open = oot_pot_open(c, name, &broken);
    /* (-2: the item of a junk pot broken just now and collected already, oot_shelf_flags: no record of it, which would mark
       another check giving the same within OOT_CHECK_NEAR; seen without a window, a pot's nut bundle marked a check 36 m off) */
    oot_pot_chosen = open >= 0 ? open : broken && (oot_pot_world_item(name) || oot_pot_junk(name)) ? -2 : -1;
    if (open >= 0 || oot_pot_world_item(name) || oot_pot_junk(name)) return 0;   /* (a world pick-up is grass's and the game's pots' too, and a
       junk pot is collected when it breaks, oot_shelf_flags, its bundle got after: never refused) */
    if (broken) hos_log("rando: %s from a pot whose check is collected already (%d broken pots give it): nothing is added", name, broken);
    return broken > 0;
}
#define OOT_DUNGEON_NEAR 4.0f
/* the dungeon a dungeon item (name) of the chest Link just opened belongs to: the nearest chest of dungeon_items.txt within
   OOT_DUNGEON_NEAR in Link's map giving it. 0 (owner "") when none is, or when Link is in that dungeon (the game's own) */
static int oot_dungeon_recent(const char *name) {   /* (oot_checks_lock held: the check just collected gives name, its dungeon told) */
    const int recent = oot_dungeon_check;
    return recent >= 0 && recent < oot_check_count && hos_now_ns() - oot_dungeon_check_at < OOT_DUNGEON_CHECK_NS &&
           oot_checks[recent].owner[0] && !strcmp(oot_checks[recent].item, name);
}
static int oot_dungeon_owner(const char *name, char *owner, size_t size, float *away_out) {
    float nearest = OOT_DUNGEON_NEAR;
    owner[0] = 0;
    AcquireSRWLockShared(&oot_checks_lock);
    /* (2026-11-26: a test pin's dungeon item on a Gold Skulltula or in a pot. The check its add was just found to be
       (oot_tracker_item: the pot broken, the Skulltula nearest) says whose, before any chest near) */
    if (oot_dungeon_recent(name)) nearest = 0, snprintf(owner, size, "%s", oot_checks[oot_dungeon_check].owner);
    /* (the owner's test 2026-11-26: a Skulltula's key, its window opened before the add 8 m from the Skulltula's place, up
       a tree, said only "You found a small key!". A check that is no chest (a Skulltula's, a pot's: no .opened) is
       looked for as the tracker looks for it, within OOT_CHECK_NEAR and not yet collected; a chest within OOT_DUNGEON_NEAR) */
    float best = nearest > 0 ? 1e30f : 0;
    for (int i = 0; i < oot_check_count && nearest > 0; i++) {
        if (!oot_checks[i].owner[0] || strcmp(oot_checks[i].item, name) || !oot_banc_in_folder(oot_link_map, oot_checks[i].folder)) continue;
        const int chest = oot_checks[i].opened != 0;
        if (!chest && oot_checks[i].done == 1) continue;
        const float dx = oot_checks[i].place[0] - oot_link_place[0], dy = oot_checks[i].place[1] - oot_link_place[1],
                    dz = oot_checks[i].place[2] - oot_link_place[2];
        const float away = sqrtf(dx * dx + dy * dy + dz * dz);
        if (away < (chest ? OOT_DUNGEON_NEAR : OOT_CHECK_NEAR) && away < best) best = away, snprintf(owner, size, "%s", oot_checks[i].owner);
    }
    if (nearest > 0) nearest = owner[0] ? best : OOT_DUNGEON_NEAR;
    ReleaseSRWLockShared(&oot_checks_lock);
    if (away_out) *away_out = nearest;
    if (owner[0] && oot_banc_in_folder(oot_link_map, owner)) snprintf(oot_dungeon_own, sizeof oot_dungeon_own, "%s", owner);   /* (for a ring: oot_keyring_rest) */
    if (!owner[0] || oot_banc_in_folder(oot_link_map, owner)) return owner[0] = 0, 0;   /* (in its own dungeon: the game counts it there) */
    return 1;
}
/* (Key rings, rando_keyrings, asked 2026-11-27; tools/rando/rando_seed.py keyrings) With the setting a dungeon's small
   keys of the shuffle are one item, its ring: the seed says how many keys that is (keyrings.txt, read with the
   tracker's lists), and the dungeon's count is raised by that many where it was raised by one. Got in its own
   dungeon the game counts one itself, and the rest is added here (oot_keyring_rest). A dungeon without a line: one. */
static int oot_keyring(const char *folder) {
    for (int i = 0; i < oot_keyring_n; i++)
        if (!strcmp(oot_keyrings[i].folder, folder)) return oot_keyrings[i].keys;
    return 1;
}
static void oot_keyring_rest(Ctx *c, const char *name, const char *folder) {
    const int keys = oot_keyring(folder);
    if (strcmp(name, "Item_Dungeon_SmallKey") || keys < 2) return;
    char flag[80];
    snprintf(flag, sizeof flag, "DungeonInfo.%s.SmallKeyNum", folder);
    int32_t n = 0;
    int ok = oot_gamedata_int(c, oot_flag_hash(flag), &n, 0);
    n += keys - 1;
    ok = ok && oot_gamedata_int(c, oot_flag_hash(flag), &n, 1);
    hos_log("rando: key ring of %s got in its own dungeon: %d more keys beside the game's one: %s %s", folder, keys - 1, flag, ok ? "set" : "NOT FOUND");
}
static int oot_dungeon_item(Ctx *c, const char *name) {
    const char *field = !strcmp(name, "Item_Dungeon_Map") ? "IsGetMap" : !strcmp(name, "Item_Dungeon_Compass") ? "IsGetCompass" :
                        !strcmp(name, "Item_Dungeon_BossKey") ? "IsGetBossKey" : !strcmp(name, "Item_Dungeon_SmallKey") ? "SmallKeyNum" : NULL;
    if (!field || !hos_rando_on()) return 0;
    char owner[24];
    float nearest;
    if (oot_pickup_folder[0]) {   /* (the pick-up of a dungeon's own, from a pot: its dungeon is in its name, oot_dungeon_pickup) */
        snprintf(owner, sizeof owner, "%s", oot_pickup_folder), oot_pickup_folder[0] = 0, nearest = 0;
        if (oot_banc_in_folder(oot_link_map, owner)) return oot_keyring_rest(c, name, owner), 0;   /* (in its own dungeon: the game counts it there) */
    } else {
    if (c->x[30] != 0x828d50acULL) {   /* (0x828d50ac: a chest's add, as a shop's. Another add, a pick-up's: a Gold Skulltula's
                                          or a pot's drop whose check the tracker has just found, with a dungeon told: test pins) */
        AcquireSRWLockShared(&oot_checks_lock);
        const int from_check = oot_dungeon_recent(name);
        ReleaseSRWLockShared(&oot_checks_lock);
        if (!from_check) return 0;
    }
    oot_dungeon_own[0] = 0;
    if (!oot_dungeon_owner(name, owner, sizeof owner, &nearest)) {
        if (oot_dungeon_own[0]) oot_keyring_rest(c, name, oot_dungeon_own);   /* (its ring, in its own dungeon) */
        return 0;
    }
    }
    char flag[80];
    snprintf(flag, sizeof flag, "DungeonInfo.%s.%s", owner, field);
    int ok;
    if (!strcmp(field, "SmallKeyNum")) {
        int32_t n = 0;
        ok = oot_gamedata_int(c, oot_flag_hash(flag), &n, 0);
        n += oot_keyring(owner);   /* (one, or its ring's keys) */
        ok = ok && oot_gamedata_int(c, oot_flag_hash(flag), &n, 1);
    } else ok = oot_gamedata_set_bool(c, oot_flag_hash(flag), 1);
    hos_log("rando: %s from a check %.1f m away (0: the one just collected) belongs to %s: %s %s", name, nearest, owner, flag, ok ? "set" : "NOT FOUND");
    return ok;
}

/* (the randomizer's fork) <game folder>/rando/<name>, into out: 1, or 0 when the game's folder is not known */
static int oot_place_file(char *out, size_t size, const char *name) {
    char exe[MAX_PATH];
    const DWORD n = hos_game_path_a(exe, MAX_PATH);
    if (!n || n >= MAX_PATH) return 0;
    char *slash = strrchr(exe, '\\');
    char *other = strrchr(exe, '/');
    if (other > slash) slash = other;
    if (!slash) return 0;
    *slash = 0;
    snprintf(out, size, "%s/rando/%s", exe, name);
    return 1;
}

/* (the randomizer's fork) Skip cutscenes: the game's own skip, asked of a cutscene as soon as it plays. An event (the
   event manager's current one, +104) has a list of players (+3768, count +3760) and plays one of them (+3864): its
   flowchart, or a cutscene the flowchart started. A player's name is at +8, and a cutscene's player is of the class
   OOT_TIMELINE_PLAYER (a flowchart's is another). The skip is the game's sequence action
   SeqOneShotEventRequestForceSkip (f_832f1890): the player's +544, whose twelfth virtual function (+88) it calls.
   Only a cutscene is skipped: asked of a flowchart the skip ends the whole event before its steps have run (the event
   of Saria's goodbye started over and over, seen without a window). With a cutscene skipped its flowchart goes on: the
   talk after Saria's goodbye played and the ocarina was given. Asked again each half second while the cutscene still
   plays (the skip fades out first). Not asked of the events the game itself lets nobody skip (its three
   EventSettingComponentLists with a SkipSetting), nor of the title's and the credits'.
   HOS_OOT_SKIP_EVENTS=1 is the setting on, 2 only logs each event and the player it plays. */
#define OOT_TIMELINE_PLAYER 0x84c82d58ULL
/* (a video's player, "RecordMovieTimelineEvent": the goddesses' story in Zelda's courtyard, Dm_HrlCastle_0045, and the
   other videos of Event/Movie. Seen in the owner's log of 2026-11-15 as "not a cutscene (class 84c82c88)": it played.
   The skip asked of it does nothing (tried without a window: the video played its 40 seconds, and the buttons did
   nothing either), so it is only named in the log; the seed passes over the step that starts it, SCENE_VIDEOS) */
#define OOT_MOVIE_PLAYER 0x84c82c88ULL
int hos_rando_skip_cutscenes(void);   /* host/oot_rando.c */
static int oot_cutscene_kept(const char *name) {
    static const char *const kept[] = {"Dm_Title", "Dm_StaffCredit", "Dm_Kokiri_0000", "Dm_SY_"};
    for (size_t i = 0; i < sizeof kept / sizeof kept[0]; i++)
        if (!strncmp(name, kept[i], strlen(kept[i]))) return 1;
    return 0;
}

static void oot_skip_cutscene_locked(Ctx *c);
#define OOT_BIG_CHEST_FAST_NS 1700000000LL   /* (the big chest's opening fast forwarded this long: oot_skip_cutscene_locked) */
/* (asked from Link's update and from the gameplay camera's view each frame, hos_oot_free_view: a cutscene without Link,
   the Deku Tree's story of Ganondorf after Gohma (Dm_Kokiri_0090), was asked once at its start and played its 45 s,
   bug 30: Link's update did not run again until it ended. One caller at a time) */
static void oot_skip_cutscene(Ctx *c) {
    static SRWLOCK lock = SRWLOCK_INIT;
    if (!TryAcquireSRWLockExclusive(&lock)) return;
    oot_skip_cutscene_locked(c);
    ReleaseSRWLockExclusive(&lock);
}
static void oot_stats_event(const char *name);
static void oot_skip_cutscene_locked(Ctx *c) {
    static uint64_t was_event, was_player;
    static int64_t asked_at;
    static int env = -1;
    if (env < 0) env = getenv("HOS_OOT_SKIP_EVENTS") ? atoi(getenv("HOS_OOT_SKIP_EVENTS")) : 0;
    /* (the run's stats, oot_stats_event, read the events' names with Skip cutscenes off too: the randomizer on is enough) */
    const int skipping = env || hos_rando_skip_cutscenes();
    if (!skipping && !hos_rando_on()) return;
    const uint64_t events = oot_singleton(c, OOT_EVENTMGR_SLOT);
    const uint64_t event = events ? recomp_load64(c, events + 104) : 0;
    if (!event) {
        was_event = was_player = 0;
        return;
    }
    const uint64_t list = recomp_load64(c, event + 3768);
    const uint32_t count = recomp_load32(c, event + 3760), at = recomp_load32(c, event + 3864);
    const uint64_t player = list && at < count ? recomp_load64(c, list + 8ULL * at) : 0;
    if (!player) return;
    const uint64_t kind = recomp_load64(c, player);
    const int cutscene = kind == OOT_TIMELINE_PLAYER;
    const int is_new = event != was_event || player != was_player;
    if (!cutscene && !is_new) {
        return;
    }
    char name[64] = "";
    const uint64_t text = recomp_load64(c, player + 8);
    for (int n = 0; text && n < 63; n++) {
        name[n] = (char)recomp_load8(c, text + n), name[n + 1] = 0;
        if (!name[n]) break;
    }
    /* (every player an event starts is logged, with its class when it is not a cutscene's: a log then lists what plays
       and what is not skipped, without HOS_OOT_SKIP_EVENTS) */
    if (is_new) {
        if (cutscene) hos_log("rando: event: player %u of %u, \"%s\": a cutscene", at, count, name);
        else if (kind == OOT_MOVIE_PLAYER) hos_log("rando: event: player %u of %u, \"%s\": a video (not skipped here: the seed leaves it out)", at, count, name);
        else hos_log("rando: event: player %u of %u, \"%s\": not a cutscene (class %llx)", at, count, name,
                     (unsigned long long)recomp_load64(c, player));
    }
    was_event = event, was_player = player;
    if (is_new && hos_rando_on()) oot_stats_event(name);
    if (!skipping) return;
    /* (Willow Woods, asked 2026-11-18: the big chest's long opening. Link's heave of the lid is his own sequence for a big
       chest (Dm_SY_Treasurebox; a small chest's is Dm_SY_TreasureboxSmall), not the chest's, and no step of its flowchart
       chooses it (tried 2026-11-19: the chest's AI, AS and animations pointed at the small chest's changed nothing of its
       length). So with Skip cutscenes it plays at the fast forward's speed (host/nn_vi.c, four times) for its first
       OOT_BIG_CHEST_FAST_NS: about 6.8 s of the game's time, the heave and the rise, before the "You got" window) */
    if (is_new && !strcmp(name, "Dm_SY_Treasurebox") && hos_rando_skip_cutscenes()) {
        extern volatile int64_t hos_auto_fast_until;   /* host/nn_vi.c */
        hos_auto_fast_until = hos_now_ns() + OOT_BIG_CHEST_FAST_NS;
        hos_log("rando: a big chest opens: its opening at fast forward's speed");
    }
    if (env == 2 || !cutscene || oot_cutscene_kept(name)) return;
    const int64_t now = hos_now_ns();
    if (!is_new && now - asked_at < 500000000LL) return;
    asked_at = now;
    const uint64_t line = recomp_load64(c, player + 544);
    const uint64_t skip = line ? recomp_load64(c, recomp_load64(c, line) + 88) : 0;
    A64Fn fn = skip ? a64_lookup(skip) : 0;
    if (is_new) hos_log("rando: the cutscene %s is skipped%s", name, fn ? "" : " (no skip found: it plays)");
    if (!fn) return;
    const Ctx saved = *c;
    c->x[31] = (c->x[31] - 0x200) & ~0xfULL;
    c->x[0] = line;
    fn(c);
    *c = saved;
}

/* (the randomizer's fork) Infinite ammo (a launcher setting, asked for 2026-11-21: a stick broken, a bomb or a Bombchu
   used, an arrow or a seed shot, a nut thrown is not used up). The game's own taking was not found as one call, so the
   counts are watched instead: every OOT_AMMO_EVERY player updates each is read, and one that went down since the last
   look, Link having some, is made up again: a bag's ammunition by the bag's fill (oot_fill_start: added until the count
   stops going up, so never more than the bag holds), the Bombchus, which have no bag, by what went. What Link never had
   (a count of 0, never higher) is never added. A count read is the one of an update before (oot_fill_note): a fill
   made is looked at again only after OOT_AMMO_EVERY. With the randomizer on only. */
enum { OOT_AMMO_EVERY = 8 };
static const char *const oot_ammo_kept[] = {"Item_Bomb", "Item_Arrow_Normal", "Item_DekuSeed", "Item_DekuStick", "Item_DekuNut", "Item_Bombchu"};
enum { OOT_AMMO_KEPT = sizeof oot_ammo_kept / sizeof oot_ammo_kept[0] };
static int oot_ammo_seen[OOT_AMMO_KEPT] = {-1, -1, -1, -1, -1, -1};
int hos_rando_infinite_ammo(void);   /* host/oot_rando.c */
static void oot_infinite_ammo(Ctx *c) {
    static unsigned tick;
    if (!hos_rando_infinite_ammo() || ++tick % OOT_AMMO_EVERY) return;
    for (int k = 0; k < (int)OOT_AMMO_KEPT; k++) {
        const int now = oot_pouch_count(c, oot_ammo_kept[k]);
        if (now < 0) continue;
        const int was = oot_ammo_seen[k];
        oot_ammo_seen[k] = now;
        if (was <= 0 || now >= was) continue;
        if (!strcmp(oot_ammo_kept[k], "Item_Bombchu")) {
            const int result = oot_pouch_change(c, oot_ammo_kept[k], was - now);
            hos_log("rando: infinite ammo: %s %d -> %d, %d given back (%d)", oot_ammo_kept[k], was, now, was - now, result);
            oot_ammo_seen[k] = was;   /* (the add is counted an update later: not given twice meanwhile) */
        } else {
            hos_log("rando: infinite ammo: %s %d -> %d, the bag filled again", oot_ammo_kept[k], was, now);
            oot_fill_start(oot_ammo_kept[k], "infinite ammo");
        }
    }
}

/* (Willow Woods, asked 2026-11-25, share/todo.md) The Debug tab's Fly (HOS_OPT_CHEAT_FLY, on with the debug tools only:
   gpu/vk/vk_menu.cpp menu_fly; HOS_OOT_FLY=1/0 over the row for a test): while Jump is held (host/nn_hid.c hos_fly_jump_held)
   Link rises OOT_FLY_RISE a second, by the same change of place as no-clip flight but in height alone: where he goes
   sideways stays the game's, walls and all, and he falls as himself when Jump is let go. His height is kept here and
   raised each frame, never more than OOT_FLY_LEAD above where he is (a ceiling that holds him back does not store a
   jump). Not while no-clip flight, an event or a go-to has him. */
#define OOT_FLY_RISE 4.0f
#define OOT_FLY_LEAD 0.5f
int hos_oot_fly(void) {
    static int env = -2;
    if (env == -2) { const char *e = getenv("HOS_OOT_FLY"); env = e && *e ? *e == '1' : -1; }
    return env >= 0 ? env : rx_option(HOS_OPT_CHEAT_FLY, 0) > 0;
}
/* The height Link is put at this frame (fly_y: the height kept; *last: the time of the last frame lifted, 0 none) */
static float oot_fly_height(float *fly_y, int64_t *last, float here, int64_t now) {
    if (!*last || now - *last > 250000000LL || now < *last) *fly_y = here;   /* (a new hold: from where he is) */
    const float dt = *last && now > *last ? fminf((float)(now - *last) * 1e-9f, 0.05f) : 0.0f;
    *last = now;
    *fly_y = fmaxf(*fly_y + OOT_FLY_RISE * dt, here);   /* (a jump of his own higher: followed) */
    *fly_y = fminf(*fly_y, here + OOT_FLY_LEAD);
    return *fly_y;
}
static void oot_update_player_cheats(Ctx *c, uint64_t actor, uint64_t components) {
    int rx_option(int id, int otherwise);
    oot_skip_cutscene(c);
    oot_infinite_ammo(c);
    for (int k = 0; k < (int)OOT_FILLS; k++) {   /* (a bag found is a full bag: oot_fill_note) */
        if (__atomic_load_n(&oot_fill_wait[k], __ATOMIC_ACQUIRE) <= 0) continue;
        if (__atomic_sub_fetch(&oot_fill_wait[k], 1, __ATOMIC_RELEASE) > 0) continue;
        const char *holds = oot_fills[k][1];
        if (!oot_fill_bagged[k]) {   /* (a bow or a Slingshot with nothing to carry its ammunition in: oot_fill_bags) */
            oot_fill_bagged[k] = 1;
            int given = 0;
            for (unsigned b = 0; b < sizeof oot_fill_bags / sizeof oot_fill_bags[0] && !given; b++) {
                if (strcmp(holds, oot_fill_bags[b][0])) continue;
                int has = 0;
                for (int t = 1; t < 4; t++) has += oot_pouch_count(c, oot_fill_bags[b][t]) > 0;
                if (has) break;
                given = oot_pouch_change(c, oot_fill_bags[b][1], 1) >= 0;
                hos_log("rando: Link has nothing to carry %s in: %s is %s", holds, oot_fill_bags[b][1], given ? "given" : "NOT GIVEN");
            }
            if (given) {   /* (the fill after the carrier is in the pouch) */
                __atomic_store_n(&oot_fill_wait[k], OOT_FILL_WAIT, __ATOMIC_RELEASE);
                continue;
            }
        }
        const int now = oot_pouch_count(c, holds);
        /* (until the count stops going up: the bag is full. The first add is made whatever the count; each after it
           when the one before raised it) */
        if ((oot_fill_last[k] < 0 || now > oot_fill_last[k]) && oot_fill_adds[k] < OOT_FILL_STEPS &&
            oot_pouch_change(c, holds, strcmp(holds, OOT_FILL_RUPEES) ? OOT_FILL_STEP : 1) >= 0) {
            oot_fill_last[k] = now, oot_fill_adds[k]++;
            __atomic_store_n(&oot_fill_wait[k], OOT_FILL_APART, __ATOMIC_RELEASE);
            continue;
        }
        hos_log("rando: %s filled: Link has %d (%d adds)", holds, now, oot_fill_adds[k]);
    }
    if (__atomic_load_n(&oot_piece_back, __ATOMIC_ACQUIRE) > 0) {   /* (Heart Pieces: hos_oot_pouch_add) */
        const int left = __atomic_sub_fetch(&oot_piece_back, 1, __ATOMIC_RELEASE);
        if (!(left % 4) && oot_pouch_count(c, OOT_PIECE) > 0) {
            const int result = oot_pouch_change(c, OOT_PIECE, -1);
            __atomic_store_n(&oot_piece_back, 0, __ATOMIC_RELEASE);
            hos_log("rando: the Piece of Heart counted with the seed's item is taken out (%d)", result);
        }
    }
    oot_magic_fill_tick(c);   /* (a magic found: its meter filled, oot_magic_meter) */
    oot_infinite_magic(c);    /* (the Debug tab's Infinite magic: the meter kept full) */
    {   /* (bug 31: Link's max life followed, and a boss container's heart taken back: oot_container_back) */
        int32_t max;
        if (oot_gamedata_int(c, OOT_MAX_LIFE, &max, 0)) {
            if (max > oot_max_now && oot_max_now >= 0) oot_max_was = oot_max_now, oot_max_rose = hos_now_ns();
            oot_max_now = max;
            const int32_t keep = __atomic_load_n(&oot_container_max, __ATOMIC_RELAXED);
            if (__atomic_load_n(&oot_container_back, __ATOMIC_ACQUIRE) > 0) {
                __atomic_sub_fetch(&oot_container_back, 1, __ATOMIC_RELEASE);
                if (keep > 0 && max > keep) {
                    int32_t life, was = max, to = keep;
                    oot_gamedata_int(c, OOT_MAX_LIFE, &to, 1);
                    if (oot_gamedata_int(c, OOT_LIFE, &life, 0) && life > keep) oot_gamedata_int(c, OOT_LIFE, &to, 1);
                    oot_max_now = keep;
                    hos_log("rando: the boss's Heart Container's heart is taken back (max life %d -> %d quarters)", was, keep);
                }
            }
        }
    }
    if (env_on("HOS_OOT_PIECES")) {   /* (a test's: the count as it changes) */
        static int last = -2, turn;
        if (!(turn++ % 4)) {
            const int now = oot_pouch_count(c, OOT_PIECE);
            if (now != last) hos_log("rando: Pieces of Heart in the pouch: %d -> %d", last, now), last = now;
        }
    }
    static uint64_t flying_actor, marked_actor, marked_controller;
    static int64_t last_tick, last_player_tick, hold_until, trace_until, trace_next;
    static const char *boss_event;   /* (a boss room's fight, asked for after Link is put there: oot_boss_rooms) */
    static int64_t boss_event_at;
    /* (the randomizer's fork) the Tracker tab's Go there: a check's place and its map's folder, read from
       <game folder>/rando/goto_check.txt at the action 5. waiting: the teleport to that map was sent, and the place is
       taken once Link is in it with no event playing and no map loading for a second and a half. */
    static struct {
        float place[3];
        char folder[40], ages[8];
        int waiting;
        int64_t until, settled;
        float face[3];   /* (Willow Woods, asked 2026-11-19: the check's own place, goto_check.txt's sixth to eighth: Link turned
                            toward it while he is held where he is put; faces: 0 when the file has none, or it is where he stands) */
        int faces;
    } check;
    int go = 0, boss = -1;
    static float target[3], velocity[3], mark[3], yaw;
    int flying = rx_option(HOS_OPT_CHEAT_FLIGHT, 0) > 0;
    /* An event that takes Link (a map change he flew into, the age toggle's, a cutscene) waits for him to stand, and the
       flight holds him in the air: the screen the event had faded stayed black until the flight was switched off, and a
       second request met "waits until the current event ends". While an event plays he is let go and lands; the flight
       takes him again, from where he then stands, when it has ended. */
    if (flying && oot_event_playing(c)) flying = 0;
    if (!flying) flying_actor = 0;
    const int64_t now = hos_now_ns();
    __atomic_store_n(&flight_player_seen, now, __ATOMIC_RELAXED);
    if (marked_actor != actor || now - last_player_tick > 2000000000LL) marked_controller = 0;
    last_player_tick = now;
    int action = rx_option(HOS_OPT_CHEAT_ACTION, 0);
    if (!action) action = __atomic_exchange_n(&hos_oot_live_action, 0, __ATOMIC_RELAXED);
    int bridge_ticket = 0;   /* (the control bridge's teleport or age switch, host/control.c: what came of it is kept for its reply) */
    int bridge_adult = -1;   /* (the bridge's age switch: the age wanted, 1 the adult) */
    if (!action) {
        const int asked = oot_bridge_teleport_take(&bridge_ticket);
        if (asked & OOT_BRIDGE_AGE) action = OOT_AGE_ACTION, bridge_adult = asked & 1;
        else if (asked) action = OOT_TELEPORT_ACTION + asked - 1;
    }
    oot_teleport_followup(c);
    oot_piece_heal(c, now, recomp_load64(c, components + 800) - 0x1d50);   /* (Link's own actor: hos_oot_lift_player) */
    oot_inventory_refresh(c, now);
    oot_tracker_refresh(c, now, actor);
    oot_time_door(c, now, actor);
    oot_ganon_bridge(c, now);
    oot_open_death_mountain(c, now);
    oot_player_speed(c, components);
    oot_map_refresh(c, now);
    {   /* (a test's: HOS_OOT_CLOCK_LOG=1 logs the world's clock every 5 seconds: the object at the world manager's +0x510,
           which ExecuteWmSetTime's set call reads, its words at +0x28 (seconds in the day) and +0x2c (days): bug 81, the
           night that stood still) */
        static int on = -1;
        static int64_t next_at;
        if (on < 0) { const char *e = getenv("HOS_OOT_CLOCK_LOG"); on = e && *e == '1'; }
        if (on && now >= next_at) {
            next_at = now + 5000000000LL;
            const uint64_t singleton = recomp_load64(c, 0x84c9e898ULL);
            const uint64_t world = singleton ? recomp_load64(c, singleton) : 0;
            const uint64_t clock = world ? recomp_load64(c, world + 0x510) : 0;
            if (clock)
                hos_log("test: clock +0x20..0x3c: %d %d %d %d %d %d %d %d", (int)recomp_load32(c, clock + 0x20), (int)recomp_load32(c, clock + 0x24),
                        (int)recomp_load32(c, clock + 0x28), (int)recomp_load32(c, clock + 0x2c), (int)recomp_load32(c, clock + 0x30),
                        (int)recomp_load32(c, clock + 0x34), (int)recomp_load32(c, clock + 0x38), (int)recomp_load32(c, clock + 0x3c));
            hos_log("test: Link at %.1f %.1f %.1f", oot_link_place[0], oot_link_place[1], oot_link_place[2]);   /* (to go back there) */
        }
    }
    if (action == OOT_CHEAT_ADD_ALL) {   /* (the Inventory page's Add all: one change a frame, oot_add_all_tick) */
        hos_log("cheats: inventory: Add all");
        oot_add_all_at = 0;
    }
    oot_add_all_tick(c);
    if (action >= OOT_CHEAT_ITEM_ACTION && action < OOT_CHEAT_ITEM_ACTION + 256 * (int)OOT_ITEM_COUNT) {
        oot_inventory_edit(c, action);
    } else if (action == OOT_AGE_ACTION) {
        int child = 1;   /* (the bridge's: Link's age now, not its sample's; already the age wanted, nothing to flip) */
        if (bridge_adult >= 0 && oot_gamedata_bool(c, 0xcea220d3u, &child) && !child == bridge_adult) {
            hos_log("cheats: age toggle: Link is the %s already", child ? "child" : "adult");
            oot_bridge_teleport_done(bridge_ticket, 2);
        } else {
            const int sent = oot_toggle_age(c, actor);
            if (bridge_ticket) oot_bridge_teleport_done(bridge_ticket, sent);
        }
    } else if (action >= OOT_TELEPORT_ACTION + (int)OOT_DESTINATIONS && action < OOT_TELEPORT_ACTION + (int)(OOT_DESTINATIONS + OOT_BOSS_ROOMS)) {
        boss = action - OOT_TELEPORT_ACTION - (int)OOT_DESTINATIONS;   /* (a boss's room: taken below, as Go there) */
    } else if (action >= OOT_TELEPORT_ACTION) {
        const int sent = oot_teleport(c, actor, (unsigned)(action - OOT_TELEPORT_ACTION));
        if (bridge_ticket) oot_bridge_teleport_done(bridge_ticket, sent);
    } else if (action >= 200) {
        oot_edit_pouch(c, action);
    } else if (action == 6) {   /* (the Tracker tab's first row: forget what is collected) */
        if (hos_rando_on()) oot_tracker_forget();
    } else if (action == 7) {   /* (the Tracker tab's Return home: a child to the Kokiri Forest, an adult to the Market. The
                                   randomizer's own way out of a place with no way back, the Colossus by the Requiem alone:
                                   not a debug tool, so with the debug tools off too) */
        if (hos_rando_on()) {
            int child = 1;
            oot_gamedata_bool(c, 0xcea220d3u, &child);   /* Sequence_IsChildhood */
            const char *home = child ? "KokiriForest_Child" : "Market_Adult";
            unsigned index = 0;
            const unsigned count = sizeof oot_destinations / sizeof oot_destinations[0];
            /* (in a dungeon: its entrance, asked for 2026-11-18. A dungeon's row is one map for both ages, the Debug tab's
               teleport into it; Link's map is the dungeon's when its name is the row's, or that and "_...") */
            for (unsigned d = 0; d < count; d++) {
                const char *cb = oot_destinations[d].child_banc, *ab = oot_destinations[d].adult_banc;
                if (cb && ab && !strcmp(cb, ab) && oot_banc_in_folder(oot_link_map, cb)) {
                    home = cb, index = d;
                    break;
                }
            }
            for (; index < count; index++) {
                const char *banc = child ? oot_destinations[index].child_banc : oot_destinations[index].adult_banc;
                if (banc && !strcmp(banc, home)) break;
            }
            hos_log("rando: return home: %s (%s)", home, index == count ? "the teleport has no such map" : oot_teleport(c, actor, index) ? "sent" : "NOT SENT");
        }
    } else if (action >= 100 && action < 124) {
        oot_set_time(c, action - 100);
    }
    /* (the randomizer's tools are the randomizer's: the Tracker tab's Go there and the place in rando\goto.txt do nothing
       in the normal game or in Master Quest) */
    if ((action == 5 && hos_rando_on()) || boss >= 0) {   /* (a boss's room is a debug tool's: in any game) */
        char path[MAX_PATH + 32], current[80];
        int read = 0;
        if (boss >= 0) {
            const OotBossRoom *room = &oot_boss_rooms[boss];
            memcpy(check.place, room->place, sizeof check.place);
            snprintf(check.folder, sizeof check.folder, "%s", room->folder);
            snprintf(check.ages, sizeof check.ages, "%s", room->ages);
            read = 5;
            check.faces = 0;
            boss_event = room->event, boss_event_at = 0;
            if (room->seen) oot_gamedata_set_bool(c, room->seen, 1);
            hos_log("cheats: boss room %d: %s", boss, room->folder);
        } else {
            FILE *f = oot_place_file(path, sizeof path, "goto_check.txt") ? fopen(path, "r") : NULL;
            read = f ? fscanf(f, "%f %f %f %39s %7s %f %f %f", &check.place[0], &check.place[1], &check.place[2], check.folder, check.ages,
                              &check.face[0], &check.face[1], &check.face[2]) : 0;
            check.faces = read >= 8 && hypotf(check.face[0] - check.place[0], check.face[2] - check.place[2]) > 0.3f;
            if (read > 5) read = 5;   /* (the place's five are what the rest asks for) */
            if (f) fclose(f);
        }
        check.waiting = 0;
        int child = 1;
        oot_gamedata_bool(c, 0xcea220d3u, &child);   /* Sequence_IsChildhood */
        oot_gamedata_string(c, 0x1d6189dau, current, sizeof current);   /* Sequence_CurrentBanc */
        if (read != 5) {
            hos_log("cheats: go to a check: rando/goto_check.txt does not say one");
        } else if (!strchr(check.ages, child ? 'C' : 'A')) {
            hos_log("cheats: go to a check: %s's map of %s does not have it (change Link's age first)", child ? "the child" : "the adult", check.folder);
        } else if (oot_banc_in_folder(current, check.folder)) {
            go = 1;
        } else {
            unsigned index = 0;
            const unsigned count = sizeof oot_destinations / sizeof oot_destinations[0];
            for (; index < count; index++) {
                const char *banc = child ? oot_destinations[index].child_banc : oot_destinations[index].adult_banc;
                if (banc && oot_banc_in_folder(banc, check.folder)) break;
            }
            if (index == count) hos_log("cheats: go to a check: the teleport has no map of %s", check.folder);
            else if (oot_teleport(c, actor, index)) check.waiting = 1, check.until = now + 60000000000LL, check.settled = 0;
        }
    } else if (check.waiting) {
        char current[80];
        int loading = 0;
        oot_gamedata_string(c, 0x1d6189dau, current, sizeof current);
        oot_gamedata_bool(c, 0xef2b60c2u, &loading);   /* Sequence_IsLoadingBanc */
        if (now > check.until) {
            check.waiting = 0;
            hos_log("cheats: go to a check: Link did not arrive in %s (in \"%s\")", check.folder, current);
        } else if (!oot_banc_in_folder(current, check.folder) || loading || oot_event_playing(c)) {
            check.settled = 0;
        } else if (!check.settled) {
            check.settled = now;
        } else if (now - check.settled > (boss_event ? 5000000000LL : 1500000000LL)) {
            /* (a boss room's: five seconds, so a dungeon's arrival scene has begun and ended first. The Water Temple's,
               Goto_WaterTemple, began after a second and a half and walked Link to the entrance, which he never reached
               from Morpha's room: the camera stayed on it and Link could not be moved; the owner, 2026-11-16) */
            check.waiting = 0, go = 1;
        }
    }
    {   /* (a test's: HOS_OOT_TEST_EVENT=<event> asks for that event once, 30 s after Link is first seen, as a map's
           starter would: a scene tried without playing up to it) */
        static int64_t first; static int sent;
        const char *test_event = getenv("HOS_OOT_TEST_EVENT");
        if (!first) first = now;
        if (test_event && *test_event && !sent && now - first > 30000000000LL && !oot_event_playing(c)) {
            sent = 1;
            hos_log("test: the event %s %s", test_event, oot_event_request(c, actor, test_event) ? "asked for" : "NOT SENT");
        }
    }
    if (boss_event && boss_event_at && now >= boss_event_at && !oot_event_playing(c)) {   /* (a boss room's fight: above) */
        hos_log("cheats: boss room: the fight's event %s %s", boss_event, oot_event_request(c, actor, boss_event) ? "asked for" : "NOT SENT");
        boss_event = NULL, boss_event_at = 0;
    }
    if (now < trace_until && now >= trace_next) {   /* (where Link is, twice a second, for a while after a go-to) */
        trace_next = now + 500000000LL;
        hos_log("cheats: go-to trace: Link at %.2f %.2f %.2f%s", oot_load_float(c, actor + 796), oot_load_float(c, actor + 800),
                oot_load_float(c, actor + 804), now < hold_until ? " (held)" : "");
    }
    {   /* (Go there: once Link is let go where he was put, he is turned toward the check by a short push of the left
           stick toward it, as a player turns him: his rotation written while he is held did not stay (seen without a
           window, 2026-11-20: asked -2.47, he kept 1.94). The push is the camera's way round, as the flight reads the
           stick: world x = rx right + rz forward, z = rz right - rx forward, so right = rx x + rz z, forward = rz x - rx z) */
        static int64_t face_after, face_next;
        static int face_tries;
        if (check.faces && hold_until && now < hold_until && mark[0] == check.place[0] && mark[2] == check.place[2]) face_after = hold_until;
        if (face_after && now >= face_after) face_after = 0, face_tries = 6, face_next = now;
        /* (pushed again every 0.4 s, at most six times, until he faces it within 0.25 radians: a push while the area's
           arrival or its autosave still held him did nothing, seen without a window in Kakariko and the Graveyard) */
        if (face_tries > 0 && now >= face_next) {
            const float wx = check.face[0] - oot_load_float(c, actor + 796), wz = check.face[2] - oot_load_float(c, actor + 804);
            const float length = hypotf(wx, wz), want = atan2f(wx, wz);
            const float has = atan2f(oot_load_float(c, actor + 816), oot_load_float(c, actor + 840));
            const float off = fabsf(remainderf(want - has, 6.28318531f));
            if (length <= 0.05f || off < 0.25f) {
                hos_log("cheats: go to a check: facing asked %.2f, Link %.2f", want, has);
                face_tries = 0;
            } else if (--face_tries == 0) {
                hos_log("cheats: go to a check: facing asked %.2f, Link %.2f (not turned)", want, has);
            } else {
                const uint64_t view = oot_gameplay_view(c);
                float rx = 1, rz = 0;
                if (view && recomp_load64(c, view) == 0x84c18a88ULL) {
                    const float x = oot_load_float(c, view + 8), z = oot_load_float(c, view + 16), l = hypotf(x, z);
                    if (l > 0.01f) rx = x / l, rz = z / l;
                }
                void hos_hid_stick(int lx, int ly, int rx, int ry, int hold_ms);   /* host/nn_hid.c */
                const float right = (rx * wx + rz * wz) / length, forward = (rz * wx - rx * wz) / length;
                hos_hid_stick((int)(right * 12000), (int)(forward * 12000), 0, 0, 120);
                face_next = now + 400000000LL;
                hos_log("cheats: go to a check: Link turned toward it (the stick %.2f %.2f)", right, forward);
            }
        }
    }
    int hos_fly_jump_held(void);
    const int fly = !flying && hos_oot_fly() && hos_fly_jump_held() && !oot_event_playing(c);   /* (the Debug tab's Fly) */
    static float fly_y;
    static int64_t fly_last;
    if (!fly) fly_last = 0;
    if (!flying && !fly && action != 2 && action != 3 && !go && now >= hold_until) return;

    // Follow OneShotPhysicsCctChangePosition to Link's controller.
    const uint64_t controller = oot_player_controller(c, components);
    if (!controller || recomp_load64(c, 0x84c54f10ULL + 0xe8) != 0x806d2530ULL) return;
    A64Fn change_position = a64_lookup(0x806d2530ULL);
    if (!change_position) return;

    if (action == 2) {
        for (unsigned i = 0; i < 3; i++) {
            const uint32_t bits = recomp_load32(c, actor + 796 + i * 4);
            memcpy(&mark[i], &bits, sizeof bits);
        }
        marked_actor = actor;
        marked_controller = controller;
        hos_log("cheats: marked position %.2f %.2f %.2f", mark[0], mark[1], mark[2]);
        {   /* (the randomizer's fork) and written beside the game, <game folder>/rando/position.txt: where Link stands, in
               the map files' own coordinates, for finding what a map file has at a place */
            char path[MAX_PATH + 32];
            FILE *f = oot_place_file(path, sizeof path, "position.txt") ? fopen(path, "w") : NULL;
            if (f) fprintf(f, "%.2f %.2f %.2f\n", mark[0], mark[1], mark[2]), fclose(f);
        }
    }
    if (action == 3) {
        /* (the randomizer's fork) Return to mark goes to the place written in <game folder>/rando/goto.txt, "x y z" in the
           map files' coordinates, when that file says another place than the last one taken from it: a map's actor (a
           Business Scrub, a chest) is reached by its coordinates. A place marked after that is the mark again. */
        static char taken[96];
        char path[MAX_PATH + 32], line[96] = "";
        FILE *f = hos_rando_on() && oot_place_file(path, sizeof path, "goto.txt") ? fopen(path, "r") : NULL;
        if (f) {
            float place[3], hold = 3;
            if (fgets(line, sizeof line, f) && strcmp(line, taken) && sscanf(line, "%f %f %f %f", &place[0], &place[1], &place[2], &hold) >= 3) {
                memcpy(mark, place, sizeof mark);
                memcpy(taken, line, sizeof taken);
                marked_actor = actor;
                marked_controller = controller;
                /* A place far from where Link stood has no ground yet (seen in play: he fell out of the map and was put
                   back, a heart less): he is held there for three seconds, while the map around him is loaded. */
                hold_until = now + (int64_t)(fminf(fmaxf(hold, 0), 60) * 1e9f);
                trace_until = hold_until + 8000000000LL, trace_next = 0;
                hos_log("cheats: the mark is rando/goto.txt's place, %.2f %.2f %.2f", mark[0], mark[1], mark[2]);
            }
            fclose(f);
        }
    }
    if (go) {   /* (the check's place is the mark, and Link is held there as at a go-to) */
        memcpy(mark, check.place, sizeof mark);
        marked_actor = actor;
        marked_controller = controller;
        hold_until = now + 3000000000LL;
        trace_until = hold_until + 8000000000LL, trace_next = 0;
        hos_log("cheats: go to a check: %s, %.2f %.2f %.2f", check.folder, mark[0], mark[1], mark[2]);
        if (boss_event) boss_event_at = hold_until + 1000000000LL;   /* (the boss's event, once he has been held there) */
    }
    if (action == 2 || marked_controller != controller) hold_until = 0;
    const int returning = (action == 3 || go || now < hold_until) && marked_controller == controller;
    if (action == 3 && !returning) hos_log("cheats: no mark for this player controller");
    if (!flying && !returning && fly) {   /* (Fly: his own place, a little higher) */
        float place[3];
        for (unsigned i = 0; i < 3; i++) place[i] = oot_load_float(c, actor + 796 + i * 4);
        place[1] = oot_fly_height(&fly_y, &fly_last, place[1], now);
        const Ctx saved = *c;
        const uint64_t arg = c->x[31] - 16;
        for (unsigned i = 0; i < 3; i++) {
            uint32_t bits;
            memcpy(&bits, &place[i], sizeof bits);
            recomp_store32_sp(c, arg + i * 4, bits);
        }
        recomp_store32_sp(c, arg + 12, 0);
        c->x[31] = arg;
        c->x[0] = controller;
        c->x[1] = arg;
        change_position(c);
        *c = saved;
        return;
    }
    if (!flying && !returning) return;
    const int64_t elapsed = now - last_tick;
    if (flying_actor != actor)
        yaw = atan2f(oot_load_float(c, actor + 816), oot_load_float(c, actor + 840));
    if (returning) {
        memcpy(target, mark, sizeof target);
        memset(velocity, 0, sizeof velocity);
        flying_actor = flying ? actor : 0;
    } else if (flying_actor != actor || elapsed < 0 || elapsed > 250000000 || oot_flight_moved_away(c, actor, target)) {
        for (unsigned i = 0; i < 3; i++) target[i] = oot_load_float(c, actor + 796 + i * 4);
        memset(velocity, 0, sizeof velocity);
        flying_actor = actor;
        last_tick = now;
        return;
    } else if (elapsed == 0) {
        return;
    }
    last_tick = now;

    DWORD foreground = 0;
    GetWindowThreadProcessId(GetForegroundWindow(), &foreground);
    if (!returning) {
        const float dt = fminf((float)elapsed * 1e-9f, 0.05f);
        float desired[3] = {0};
        if (foreground == GetCurrentProcessId() && !rx_option(1, 0) && !rx_option(HOS_OPT_CHEAT_CAMERA, 0)) {
            uint64_t hos_flight_input(void);
            const uint64_t axes = hos_flight_input();
            const float right = (int16_t)axes / 32767.0f, forward = (int16_t)(axes >> 16) / 32767.0f;
            const int vertical = (GetAsyncKeyState(VK_PRIOR) < 0) - (GetAsyncKeyState(VK_NEXT) < 0);
            const uint64_t view = oot_gameplay_view(c);
            float rx = 1, rz = 0;
            if (view && recomp_load64(c, view) == 0x84c18a88ULL) {
                const float x = oot_load_float(c, view + 8), z = oot_load_float(c, view + 16);
                const float length = hypotf(x, z);
                if (length > 0.01f) rx = x / length, rz = z / length;
            }
            desired[0] = rx * right + rz * forward;
            desired[1] = vertical ? vertical : (int16_t)(axes >> 32);
            desired[2] = rz * right - rx * forward;
        }
        const float length = sqrtf(desired[0] * desired[0] + desired[1] * desired[1] + desired[2] * desired[2]);
        const float speed = 4.0f / fmaxf(1.0f, length);
        const float blend = 1.0f - expf(-12.0f * dt);
        for (unsigned i = 0; i < 3; i++) {
            velocity[i] += (desired[i] * speed - velocity[i]) * blend;
            target[i] += velocity[i] * dt;
        }
        if (hypotf(desired[0], desired[2]) > 0.08f) {
            const float delta = remainderf(atan2f(desired[0], desired[2]) - yaw, 6.28318531f);
            yaw += fmaxf(-8.0f * dt, fminf(delta, 8.0f * dt));
        }
    }

    const Ctx saved = *c;
    const uint64_t arg = c->x[31] - 16;
    for (unsigned i = 0; i < 3; i++) {
        uint32_t bits;
        memcpy(&bits, &target[i], sizeof bits);
        recomp_store32_sp(c, arg + i * 4, bits);
    }
    recomp_store32_sp(c, arg + 12, 0);
    c->x[31] = arg;
    c->x[0] = controller;
    c->x[1] = arg;
    flight_transform_yaw = yaw;
    flight_pose_actor = flying && !returning ? actor : 0;
    flight_transform_controller = flying && !returning ? controller : 0;
    change_position(c);
    flight_transform_controller = 0;
    *c = saved;
    if ((action == 3 || go) && returning) hos_log("cheats: returned to %.2f %.2f %.2f", mark[0], mark[1], mark[2]);
}
#endif

int hos_oot_player_seen(void) {
#if defined(_WIN32) || defined(__linux__)   /* (the debug tools: host/posix has what they call) */
    const int64_t seen = __atomic_load_n(&flight_player_seen, __ATOMIC_RELAXED);
    return seen && hos_now_ns() - seen < 250000000;
#else
    return 0;
#endif
}

int hos_oot_flight_shortcut_ready(void) {
    return hos_oot_player_seen();
}

#if defined(_WIN32) || defined(__linux__)   /* (the debug tools: host/posix has what they call) */
static void oot_write_flight_rotation(Ctx *c, uint64_t matrix) {
    const float s = sinf(flight_transform_yaw), co = cosf(flight_transform_yaw);
    const float rotation[3][3] = {{co, 0, s}, {0, 1, 0}, {-s, 0, co}};
    for (unsigned row = 0; row < 3; row++) {
        for (unsigned col = 0; col < 3; col++) {
            uint32_t bits;
            memcpy(&bits, &rotation[row][col], sizeof bits);
            recomp_store32(c, matrix + row * 16 + col * 4, bits);
        }
    }
}
#endif

void hos_oot_flight_rotation(Ctx *c, uint64_t controller, uint64_t matrix) {
#if defined(_WIN32) || defined(__linux__)   /* (the debug tools: host/posix has what they call) */
    if (flight_transform_controller == controller) oot_write_flight_rotation(c, matrix);
#else
    (void)c;
    (void)controller;
    (void)matrix;
#endif
}

void hos_oot_flight_pose(Ctx *c, uint64_t actor, uint64_t matrix) {
#if defined(_WIN32) || defined(__linux__)   /* (the debug tools: host/posix has what they call) */
    if (flight_pose_actor == actor) {
        flight_pose_actor = 0;
        oot_write_flight_rotation(c, matrix);
    }
#else
    (void)c;
    (void)actor;
    (void)matrix;
#endif
}

/* (the randomizer's fork) Progressive items. f_8112d570 is the pouch manager's add: x0 the manager, x1 a string view of
   the content's actor name ({the text, its room as a 32-bit number}), x2 how many (the event action
   OneShotAddOrRemovePouchContent, f_828d4a70, calls it so, and a dozen other places do). nx2/oot_patches.py calls this at
   its start. With the setting on, an upgrade of a family on its way into the pouch is made the next of the family that
   Link has not: he has the Silver Gauntlets' place in the family when he carries them or the Golden ones (a bigger one
   may take the smaller one's place in the pouch). The name is not written over where it is (it may be the game's own
   text): the call is given a view of its own, in memory that stays. What the chest's scene shows and says is the item
   it was shuffled as; what is put in the pouch is this. A name given in two spellings (the item's and the pouch's)
   is answered in the one it came in. */
/* And the Bomb Bag the game gives with bombs. A chest's bombs, when Link has no bag, are got in three adds (seen in the
   log of a game, twice): the event action adds Item_BombBag_Small (from 0x828d50ac, x4 2, x7 0), the bag is filled
   (Item_Bomb, 20), then the action adds the bundle as every chest's item is added (x4 7, x7 1). The first is the
   game's own kindness and gave the randomizer's gating item for five bombs: with the randomizer on it is not made
   (1 is returned, and the add is left at once with nothing added), so the bombs find no bag and are not kept, as
   bombs dropped by a Gold Skulltula are not. A Bomb Bag of a chest's own comes as the bundle does and is added.
   x3 is how many (20, 5, 1); x2 is not. */
int hos_rando_progressive(void);   /* host/oot_rando.c */
int hos_rando_on(void);   /* (host/oot_rando.c: the randomizer is on) */
#if defined(_WIN32) || defined(__linux__)
/* The add's content made `give`: the call is given a view of its own, in memory that stays (the name is not written
   over where it is: it may be the game's own text). Returns the view the call has now. */
static uint64_t oot_pouch_name(Ctx *c, uint64_t view, const char *give) {
    static uint64_t blocks;
    static unsigned turn;
    if (!blocks) blocks = hos_sys_alloc(8 * 256, 16);
    if (!blocks) return view;
    const uint64_t block = blocks + (uint64_t)(__atomic_fetch_add(&turn, 1, __ATOMIC_RELAXED) % 8) * 256;
    memcpy(A64_PTR(block), A64_PTR(view - 16), 64);   /* (the view as it is, with what is before it: a string object's start) */
    memcpy(A64_PTR(block + 96), give, strlen(give) + 1);
    recomp_store64(c, block + 16, block + 96);
    recomp_store32(c, block + 24, 128);
    c->x[1] = block + 16;
    return block + 16;
}
#endif
#if defined(_WIN32) || defined(__linux__)
/* With Progressive items: what a content of a family gives Link now, the next of the family he has not (by the
   spelling it was named by); NULL when it is of no family, or he has the family whole (it is given as it is). */
/* (the randomizer's fork) Magic and the fairies' gifts (rando_magic, tools/rando/rando_seed.py MAGIC_ITEM): magic is two
   items of the shuffle, the Gift of Doubled Magic twice. Found while Link has no magic meter (PlayerStatus.MPMax under
   24), it is given as Item_MagicMeter, an item of the seed's own (the gift's model and its own words) that the pouch keeps
   nothing of: its add sets the meter to 24 (oot_magic_meter). Found with the meter, it is the gift itself: 48. The spin
   attack's gift (Item_FairyBless_MP) is no tier of magic then: it is given as it is. Whatever Progressive items says */
#define OOT_MAGIC_ITEM "Item_MagicMeter"
#define OOT_MAGIC_DOUBLE "Item_FairyBless_MPDouble"
#define OOT_MAGIC_SPIN "Item_FairyBless_MP"
#define OOT_MPMAX_HASH 0x12d63a97u   /* PlayerStatus.MPMax */
#define OOT_MAGIC_FIRST 240   /* (the first meter, in tenths: the list of pouch actors' MPMax 24) */
#define OOT_MAGIC_DOUBLED 480   /* (the doubled meter: the gift's MPMax 48) */
#define OOT_MP_HASH 0x76b18200u   /* PlayerStatus.MP: the magic Link has now, in the same tenths */
#define OOT_MAGIC_JAR 120   /* (what a large magic jar fills, in tenths: a test's run 2026-11-20) */
#define OOT_MAGIC_FILL_FRAMES 3600   /* (the most a fill waits for the get's scene to end, about a minute) */
/* (frames left to fill the meter, a magic found: oot_magic_meter, oot_magic_fill_tick) */
static int oot_magic_fill_frames;
static int oot_magic_family(const char *name) {
    int hos_rando_magic(void);   /* host/oot_rando.c */
    return hos_rando_magic() && (!strcmp(name, OOT_MAGIC_DOUBLE) || !strcmp(name, OOT_MAGIC_SPIN) || !strcmp(name, OOT_MAGIC_ITEM));
}
static const char *oot_magic_give(Ctx *c, const char *name) {   /* (what is given for `name`: NULL for itself) */
    if (strcmp(name, OOT_MAGIC_DOUBLE)) return NULL;
    int32_t most = 0;
    if (!oot_gamedata_int(c, OOT_MPMAX_HASH, &most, 0)) return NULL;
    return most < OOT_MAGIC_FIRST ? OOT_MAGIC_ITEM : NULL;
}
/* (a magic found: the meter's next tier, and the meter filled (the owner's test 2026-11-19: the first came empty). No
   meter: the first, 24. The first: doubled, 48, whichever of the two items it is (two magics in one room are both made
   Item_MagicMeter when the room loads, oot_magic_give asked before either is opened: the second then did nothing).
   Doubled: filled only) */
static void oot_magic_meter(Ctx *c) {
    int32_t most = 0;
    if (!oot_gamedata_int(c, OOT_MPMAX_HASH, &most, 0)) {
        hos_log("rando: magic: PlayerStatus.MPMax not found: no meter given");
        return;
    }
    int32_t want = most < OOT_MAGIC_FIRST ? OOT_MAGIC_FIRST : most < OOT_MAGIC_DOUBLED ? OOT_MAGIC_DOUBLED : most;
    if (want != most) oot_gamedata_int(c, OOT_MPMAX_HASH, &want, 1);
    /* (the fill: the game's own magic jars, given by the frame's tick once the get's scene is over: oot_magic_fill_tick) */
    __atomic_store_n(&oot_magic_fill_frames, OOT_MAGIC_FILL_FRAMES, __ATOMIC_RELEASE);
    hos_log("rando: magic: PlayerStatus.MPMax %d -> %d, the meter to be filled", (int)most, (int)want);
}
/* (each frame after a magic found: the meter filled with the game's own large magic jars (Tbox_MagicJar_Large, 12 of
   magic each), one every 15 frames, as many as it lacks when the get's scene is over. PlayerStatus.MP written directly
   showed on the meter and was the game's again the next frame: what Link really has is kept elsewhere and copied there
   each frame (the owner's tests 2026-11-20: filled, then emptied a moment after). A jar put in the pouch fills what he
   really has (a test's run 2026-11-20: 0, 120, 240 of 480 after two, and kept). The tick waits while an event plays,
   at most OOT_MAGIC_FILL_FRAMES) */
static void oot_magic_fill_tick(Ctx *c) {
    static int jars;   /* (jars left to give for this fill; -1: not counted yet) */
    int left = __atomic_load_n(&oot_magic_fill_frames, __ATOMIC_ACQUIRE);
    if (left <= 0) return;
    __atomic_store_n(&oot_magic_fill_frames, left - 1, __ATOMIC_RELEASE);
    if (left == OOT_MAGIC_FILL_FRAMES) jars = -1;
    if (jars == 0 || (oot_event_playing(c) && jars < 0)) return;
    if (jars < 0) {
        int32_t most = 0, now = 0;
        if (!oot_gamedata_live_int(c, OOT_MPMAX_HASH, &most, 0, NULL) || most <= 0 || !oot_gamedata_live_int(c, OOT_MP_HASH, &now, 0, NULL)) return;
        jars = now < most ? (most - now + OOT_MAGIC_JAR - 1) / OOT_MAGIC_JAR : 0;
        hos_log("rando: magic: %d of %d: %d large magic jar(s) to fill it", (int)now, (int)most, jars);
        left = 15;
    }
    if (jars > 0 && left % 15 == 0) {
        oot_pouch_change(c, "Tbox_MagicJar_Large", 1);
        jars--;
    }
}

/* (Willow Woods, asked 2026-11-23, share/todo.md) Infinite magic: the Debug tab's row (HOS_OPT_CHEAT_MAGIC, on with the
   debug tools only, gpu/vk/vk_menu.cpp menu_infinite_magic), or HOS_OOT_INFINITE_MAGIC=1 for a test. Every
   OOT_MAGIC_KEEP_EVERY player updates the meter is read (PlayerStatus.MP and MPMax, oot_gamedata_live_int); below its top
   it gets one of the game's own large magic jars, as oot_magic_fill_tick fills a meter found (written directly, the
   magic was the player's own again a frame later). A spell or a magic arrow is so made up within a few frames; the Lens
   of Truth's drain never shows. No meter (MPMax 0): nothing. Not while an event plays, nor while a found magic's fill runs. */
#define OOT_MAGIC_KEEP_EVERY 8
int hos_oot_infinite_magic(void) {
    int rx_option(int id, int otherwise);
    static int env = -2;
    if (env == -2) { const char *e = getenv("HOS_OOT_INFINITE_MAGIC"); env = e && *e ? *e == '1' : -1; }
    return env >= 0 ? env : rx_option(HOS_OPT_CHEAT_MAGIC, 0) > 0;
}
static void oot_infinite_magic(Ctx *c) {
    static unsigned tick;
    if (++tick % OOT_MAGIC_KEEP_EVERY || !hos_oot_infinite_magic()) return;
    if (__atomic_load_n(&oot_magic_fill_frames, __ATOMIC_ACQUIRE) > 0 || oot_event_playing(c)) return;
    int32_t most = 0, now = 0;
    if (!oot_gamedata_live_int(c, OOT_MPMAX_HASH, &most, 0, NULL) || most <= 0 || !oot_gamedata_live_int(c, OOT_MP_HASH, &now, 0, NULL) ||
        now >= most) return;
    static int logged;
    if (logged++ < 8) hos_log("infinite magic: %d of %d: a large magic jar", (int)now, (int)most);
    oot_pouch_change(c, "Tbox_MagicJar_Large", 1);
}

static const char *oot_progressive_give(Ctx *c, const char *name) {
    if (oot_magic_family(name)) return oot_magic_give(c, name);   /* (rando_magic: the magic's own tiers) */
    int spelling = 0;
    const int f = oot_family_of(name, &spelling);
    if (f < 0) return NULL;
    int tiers = 0;
    while (tiers < 3 && oot_families[f][tiers][0]) tiers++;
    int level = 0;   /* (how many of the family Link has: the highest he carries, and all under it) */
    for (int t = tiers - 1; t >= 0 && !level; t--)
        for (int a = 0; a < 2; a++)
            if (oot_families[f][t][a] && oot_pouch_count(c, oot_families[f][t][a]) > 0) level = t + 1;
    if (level >= tiers) return NULL;
    return oot_families[f][level][spelling] ? oot_families[f][level][spelling] : oot_families[f][level][0];
}
#endif

/* (the randomizer's fork) Progressive items, what a chest shows and says. f_80bf1c00 is handed an actor as it is made
   (x0, a drop's component; x1, what the actor is made with) and reads the actor's Drop__DropActor (a chest's content)
   from the actor's list of parameters (x1+0x40, +0x270, then [0]: the list at +0x10, its count of names at +0, the
   names at +8, its count of values at +0x10, the values at +0x18, all pointers) into the component's own name (+0x48,
   its size the 32 bits at +0x50). The chest's scene (Dm_SY_Treasurebox) shows, names and adds its ContentName, which
   is not that copy: seen without a window 2026-11-16, the copy made the family's next, the scene still said "a bigger
   Deku-nut bag". So the value in the list is pointed at the family's next too, a string of the host's own that stays,
   for what reads the list after. Called as f_80bf1c00 returns (nx2/oot_patches.py patch_drop_name). Seen in play
   2026-11-15: a Bomb Bag in Mido's house with no bag had said "bigger bomb bag". HOS_OOT_DROP_NAME=0 turns it off. */
#if defined(_WIN32) || defined(__linux__)
static uint64_t oot_kept_name(const char *give) {   /* (a string in the game's memory that stays, one per name) */
    static struct { char name[48]; uint64_t at; } kept[32];
    static int count;
    for (int i = 0; i < count; i++)
        if (!strcmp(kept[i].name, give)) return kept[i].at;
    if (count >= 32 || strlen(give) >= sizeof kept[0].name) return 0;
    const uint64_t at = hos_sys_alloc(64, 16);
    if (!at) return 0;
    memcpy(A64_PTR(at), give, strlen(give) + 1);
    snprintf(kept[count].name, sizeof kept[count].name, "%s", give);
    kept[count].at = at;
    count++;
    return at;
}
#endif

/* (characters' looks, tools/rando/rando_cosmetics.py) Link shown as another character: his code asks the model for his own
   bones by name (where his sword and shield hang, his straps), which the other model has not; f_801d3620 then answers -1
   and its callers used that unasked (seen in play 2026-11-16: the shield on the ground, the game fell when it was raised).
   The cosmetics write <game>/mods/zz-cosmetics-models/bone_fallbacks.txt, "<Link's bone>=<the nearest of its parents the
   other model has>", read here once; f_801d3620 (nx2/oot_patches.py patch_bone_fallback) asks again with that name when its
   own is not found. No file (no look of Link's chosen): nothing changes. Returns the other name's string in the game's
   memory, or 0. */
uint64_t hos_oot_bone_fallback(Ctx *c, uint64_t name) {
#if defined(_WIN32) || defined(__linux__)
    static SRWLOCK lock = SRWLOCK_INIT;
    static int loaded;
    static struct { char from[64]; uint64_t to; } *table;
    static int count;
    if (!name) return 0;
    AcquireSRWLockExclusive(&lock);
    if (!loaded) {
        loaded = 1;
        char path[MAX_PATH + 64];
        FILE *f = oot_game_file(path, sizeof path, "mods/zz-cosmetics-models/bone_fallbacks.txt") ? fopen(path, "rb") : NULL;
        if (f) {
            char line[160];
            static struct { char name[64]; uint64_t at; } names[64];
            int nnames = 0;
            table = calloc(1024, sizeof *table);
            while (table && count < 1024 && fgets(line, sizeof line, f)) {
                line[strcspn(line, "\r\n")] = 0;
                char *eq = strchr(line, '=');
                if (!eq || eq == line || !eq[1] || strlen(line) >= 64 || strlen(eq + 1) >= 64) continue;
                *eq = 0;
                uint64_t to = 0;
                for (int i = 0; i < nnames && !to; i++)
                    if (!strcmp(names[i].name, eq + 1)) to = names[i].at;
                if (!to && nnames < 64 && (to = hos_sys_alloc(64, 16)) != 0) {
                    memcpy(A64_PTR(to), eq + 1, strlen(eq + 1) + 1);
                    snprintf(names[nnames].name, sizeof names[nnames].name, "%s", eq + 1);
                    names[nnames++].at = to;
                }
                if (!to) continue;
                snprintf(table[count].from, sizeof table[count].from, "%s", line);
                table[count++].to = to;
            }
            fclose(f);
            hos_log("rando: characters' looks: %d of Link's bones answered by another (bone_fallbacks.txt)", count);
        }
    }
    uint64_t to = 0;
    if (count) {
        char want[64];
        int i = 0;
        for (; i < 63; i++) {
            want[i] = (char)recomp_load8(c, name + i);
            if (!want[i]) break;
        }
        want[i] = 0;
        for (int k = 0; k < count && !to; k++)
            if (!strcmp(table[k].from, want)) to = table[k].to;
    }
    ReleaseSRWLockExclusive(&lock);
    return to;
#else
    (void)c; (void)name;
    return 0;
#endif
}

/* (the randomizer's fork) The day's 15:00 cap, bug 58: the world's clock stops at 15:00 until the cutscene Dm_HrlField_0020
   (Zelda's escape, the Door of Time's story) has played, and a shuffle reaches it late or never: the owner stood five
   minutes in Hyrule Field at fast forward and the day never ended (seen without a window: the clock's seconds climbed
   to 54000 and stayed). f_803edf70 asks this after the scene's flag (nx2/oot_patches.py patch_clock_cap): with the
   randomizer on, no limit. HOS_OOT_CLOCK_CAP=1 keeps the game's cap. */
int hos_oot_field_clock_free(void) {
    static int keep = -1;
    if (keep < 0) { const char *e = getenv("HOS_OOT_CLOCK_CAP"); keep = e && *e == '1'; }
    return !keep && hos_rando_on();
}

/* (the randomizer's fork) The R item wheel, bug 57: the game opens it only with more than one item the age can use
   (f_8331efa0, SeqQueryIsOpenableShortCut's calculate: nx2/oot_patches.py patch_wheel_fewest asks this for the count
   compared with). A shuffle can leave a child one (the owner's run: the Hookshot on ZR, R did nothing). With the
   randomizer on, more than 0. HOS_OOT_WHEEL_TWO=1 keeps the game's two. */
int hos_oot_wheel_fewest(void) {
    static int keep = -1;
    if (keep < 0) { const char *e = getenv("HOS_OOT_WHEEL_TWO"); keep = e && *e == '1'; }
    return keep || !hos_rando_on() ? 1 : 0;
}

/* (Willow Woods, bug 91) The Water Temple's gate switch by Lake Hylia. The ring above the door turns on for a hit of
   the Hookshot's damage type only (its AI: QueryDamageCalculatorIsOnDamageTypeAny, then ...IsOnDamageType with type 16,
   both read the damage calculator's mask of this frame's damage types). In this build the tip reaches the ring and no hit
   is recorded: the mask stays 0, the tip bounces off, the gate's cutscene never plays (traced 2026-11-22 without a
   window, the gate shut on a copy of the owner's save; why the tip's attack sensor never meets the ring's hit sensor is
   not found). What does arrive is the tip's area sensor (layer 25) in the ring's hit sensor's contacts, from the shot on;
   so the tip counts as there when that sensor's body is within 0.9 of the hit sensor's (the tip stops 0.6 from the
   ring's middle; on its way it is metres off).

   oot_hook_tip_at: whether a Hookshot's or Longshot's tip (the actor Shootable_Hook, Shootable_HookLong) is at the hit
   sensor of this SensorHit component. The way there, as the game's own sifting walks it (f_800c6940): the component's
   actor (+0x18), its parts (+0x270), the physics part (+0x50, its +0x20), the hit sensor's contact collection (the
   component's +0x99 says which of +0x38 at +0x40), its bodies (+0x10 at +0x18, 0x18 apart, the body at +8), a body's
   contacts (+0x158: +8 how many, +0x28 the entries, 0x10 apart, a contact's two bodies at +0x60 and +0x68). The other
   body's layer is the low 6 bits of its +0x150's +8, its place the floats at +0x8c, +0x9c, +0xac, and its actor behind
   its +0x108's handle (+0x20 the slot, whose +0x48 must be the handle's own number at +0x28 and whose +0x40 is the
   actor; the actor's name at its +0x260). */
static int oot_hook_tip_at(Ctx *c, uint64_t sensor) {
    const uint64_t owner = recomp_load64(c, sensor + 0x18), parts = owner ? recomp_load64(c, owner + 0x270) : 0;
    const uint64_t p50 = parts ? recomp_load64(c, parts + 0x50) : 0, ph = p50 ? recomp_load64(c, p50 + 0x20) : 0;
    const int which = (int8_t)recomp_load8(c, sensor + 0x99);
    if (!ph || which < 0 || which >= (int)recomp_load32(c, ph + 0x38)) return 0;
    const uint64_t entry = recomp_load64(c, recomp_load64(c, ph + 0x40) + 8ULL * (unsigned)which), cc = entry ? recomp_load64(c, entry + 8) : 0;
    const uint32_t bodies = cc ? recomp_load32(c, cc + 0x10) : 0;
    for (uint32_t j = 0; j < bodies && j < 4; j++) {
        const uint64_t rb = recomp_load64(c, recomp_load64(c, cc + 0x18) + 0x18ULL * j + 8), holder = rb ? recomp_load64(c, rb + 0x158) : 0;
        const uint32_t count = holder ? recomp_load32(c, holder + 8) : 0;
        const uint64_t entries = holder ? recomp_load64(c, holder + 0x28) : 0;
        for (uint32_t k = 0; entries && k < count && k < 16; k++) {
            const uint64_t contact = recomp_load64(c, entries + 0x10ULL * k);
            if (!contact) continue;
            const uint64_t b0 = recomp_load64(c, contact + 0x60), b1 = recomp_load64(c, contact + 0x68);
            if ((b0 == rb) == (b1 == rb)) continue;   /* (not this sensor's and another's: an entry left from before) */
            const uint64_t other = b0 == rb ? b1 : b0, layer = other ? recomp_load64(c, other + 0x150) : 0;
            if (!layer || (recomp_load32(c, layer + 8) & 0x3f) != 25) continue;
            const float dx = oot_load_float(c, other + 0x8c) - oot_load_float(c, rb + 0x8c), dy = oot_load_float(c, other + 0x9c) - oot_load_float(c, rb + 0x9c),
                        dz = oot_load_float(c, other + 0xac) - oot_load_float(c, rb + 0xac);
            if (!(dx * dx + dy * dy + dz * dz <= 0.9f * 0.9f)) continue;
            const uint64_t user = recomp_load64(c, other + 0x108), slot = user ? recomp_load64(c, user + 0x20) : 0;
            if (!slot || recomp_load32(c, slot + 0x48) != recomp_load32(c, user + 0x28)) continue;
            const uint64_t shooter = recomp_load64(c, slot + 0x40), name = shooter ? recomp_load64(c, shooter + 0x260) : 0;
            char text[16] = {0};
            for (int i = 0; name && i < 14; i++) text[i] = (char)recomp_load8(c, name + (unsigned)i);
            if (!strcmp(text, "Shootable_Hook")) return 1;   /* (the name's first 14 letters: Shootable_HookLong too) */
        }
    }
    return 0;
}

/* The two queries' first step (nx2/oot_patches.py patch_hook_switch; any: 1 from ...IsOnDamageTypeAny, 0 from
   ...IsOnDamageType). x0 is the query's node: its actor's parts at node +8, +8, +0x1f0, +0x270, as the queries read
   them; the parts' +0x2b8 the damage calculator (its +0x2c0 the mask), +0x3b8 the SensorHit component; the type asked for
   at the node's +0x20 (a pointer with flags in its low 2 bits). A switch that asks for type 16 with the tip at its sensor
   has the Hookshot's bit set, and is held so for a fifth of a second: the AI asks "any" before the type, so the frame the
   tip arrives the "any" has already said no, and the tip is gone from the sensor two frames on. HOS_OOT_NO_HOOK_HIT=1
   leaves the mask to the game (a test's). */
/* (Rekarina's ringpost, 2026-11-22) One of the game's lock-free queue writers was about to end the game (a full ring, or the
   reader swapped it while this writer copied: nx2/oot_patches.py patch_ring_post): 1, return instead, the record dropped
   or read a frame later. The first 16 and then every 1000th are logged, with the writer's return address.
   HOS_OOT_RING_ABORT=1 keeps the game's abort (a test's). */
int hos_oot_ring_post(Ctx *c) {
    static int keep = -1;
    static volatile LONG dropped;
    if (keep < 0) keep = env_on("HOS_OOT_RING_ABORT");
    if (keep) return 0;
    const LONG n = InterlockedIncrement(&dropped);
    if (n <= 16 || n % 1000 == 0)
        hos_log("oot: a game queue's late writer returned instead of ending the game (%ld so far; lr %#llx)", (long)n,
                (unsigned long long)c->x[30]);
    return 1;
}
void hos_oot_hook_switch(Ctx *c, int any) {
    static int off = -1;
    static uint64_t held;           /* (the damage calculator given the hit) */
    static long long held_until;
    if (off < 0) off = env_on("HOS_OOT_NO_HOOK_HIT");
    if (off) return;
    const uint64_t node = c->x[0], actor = recomp_load64(c, recomp_load64(c, node + 8) + 8);
    const uint64_t parts = recomp_load64(c, recomp_load64(c, actor + 0x1f0) + 0x270);
    const uint64_t dc = parts ? recomp_load64(c, parts + 0x2b8) : 0;
    if (!dc) return;
    const long long now = hos_now_ns();
    if (!any && recomp_load32(c, recomp_load64(c, node + 0x20) & ~3ULL) == 16) {
        const uint64_t sensor = recomp_load64(c, parts + 0x3b8);
        if (sensor && oot_hook_tip_at(c, sensor)) {
            static int said;
            if ((__atomic_load_n(&held, __ATOMIC_RELAXED) != dc || now >= __atomic_load_n(&held_until, __ATOMIC_RELAXED)) && said++ < 8)
                hos_log("rando: the Hookshot's tip is at a switch that asks for its hit: the hit given");
            __atomic_store_n(&held, dc, __ATOMIC_RELAXED);
            __atomic_store_n(&held_until, now + 200000000LL, __ATOMIC_RELAXED);
        }
    }
    if (__atomic_load_n(&held, __ATOMIC_RELAXED) == dc && now < __atomic_load_n(&held_until, __ATOMIC_RELAXED))
        recomp_store32(c, dc + 0x2c0, recomp_load32(c, dc + 0x2c0) | (1u << 16));
}

void hos_oot_drop_name(Ctx *c, uint64_t self, uint64_t made) {
#if defined(_WIN32) || defined(__linux__)
    static int on = -1;
    if (on < 0) { const char *e = getenv("HOS_OOT_DROP_NAME"); on = !(e && *e == '0'); }
    int hos_rando_magic(void);   /* host/oot_rando.c (rando_magic: its tiers whatever Progressive items says) */
    if (!on || !self || !made || !hos_rando_on() || (!hos_rando_progressive() && !hos_rando_magic())) return;
    /* (bug 114, the owner's run 2026-11-23: a Gold Skulltula's drop is the named actor made in the world, and the family's
       next was no pick-up there (Armor_Adult_Gauntlet_Silver, a pouch's name) or none the seed made: the Golden Gauntlets
       and a Slingshot could not be taken. A Skulltula's drop keeps the seed's item; the pouch's add of it gives the
       family's next (hos_oot_pouch_add), as any check's does. The dropping actor's name is at its +0x260, as
       oot_hook_tip_at reads a shooter's. HOS_OOT_DROP_SKULLTULA=1 renames those too, as before) */
    static int skull_too = -1;
    if (skull_too < 0) { const char *e = getenv("HOS_OOT_DROP_SKULLTULA"); skull_too = e && *e == '1'; }
    const uint64_t owner = recomp_load64(c, made + 0x40);
    int skull = 0;   /* (a Skulltula's drop: renamed only to a tier the seed made a pick-up, below) */
    if (owner && !skull_too) {
        const uint64_t at = recomp_load64(c, owner + 0x260);
        char who[24] = {0};
        for (int i = 0; at && i < (int)sizeof who - 1; i++) {
            who[i] = (char)recomp_load8(c, at + (unsigned)i);
            if (!who[i]) break;
        }
        static int said;
        if (said < 12) said++, hos_log("rando: progressive: a drop's actor is %s", who[0] ? who : "(no name read)");
        skull = !strncmp(who, "Enemy_Skulltula", 15);   /* (Enemy_Skulltula_Gold and its kin) */
    }
    /* (the list, as f_80bf1c00 finds it) */
    uint64_t list = owner;
    if (list) list = recomp_load64(c, list + 0x270);
    if (list) list = recomp_load64(c, list);
    if (list) list = recomp_load64(c, list + 0x10);
    if (!list) return;
    const int names = (int)recomp_load32(c, list), values = (int)recomp_load32(c, list + 0x10);
    const uint64_t name_at = recomp_load64(c, list + 8), value_at = recomp_load64(c, list + 0x18);
    if (!name_at || !value_at || names <= 0 || names > 4096) return;
    {   /* (a test's: HOS_OOT_DROP_TRACE=1 logs the dropping actor's name and its list's keys and texts, the first 40 drops; 2 the pots' only) */
        static int trace = -1, told;
        if (trace < 0) { const char *e = getenv("HOS_OOT_DROP_TRACE"); trace = e && *e >= '1' && *e <= '2' ? *e - '0' : 0; }
        char line[1024], text[48] = "";
        const uint64_t who_at = owner ? recomp_load64(c, owner + 0x260) : 0;
        for (int i = 0; trace && who_at && i < 47; i++) if (!(text[i] = (char)recomp_load8(c, who_at + (unsigned)i))) break;
        text[47] = 0;
        if (trace && told < 40 && (trace != 2 || !strncmp(text, "Obj_PotR", 8))) {   /* (2: the pots only) */
            told++;
            int at = 0;
            char own[48] = "-";
            const uint64_t self_text = recomp_load64(c, self + 0x48);
            for (int i = 0; self_text && i < 47; i++) if (!(own[i] = (char)recomp_load8(c, self_text + (unsigned)i))) break;
            own[47] = 0;
            at += snprintf(line + at, sizeof line - at, "drop trace: %s (self %#llx, its text %s, made %#llx):", who_at ? text : "-",
                           (unsigned long long)self, own, (unsigned long long)made);
            for (int i = 0; i < names && i < values && i < 16 && at < (int)sizeof line - 100; i++) {
                const uint64_t k = recomp_load64(c, name_at + 8ULL * i), v = recomp_load64(c, value_at + 8ULL * i);
                char kt[48] = "-", vt[48] = "-";
                for (int j = 0; k && j < 47; j++) if (!(kt[j] = (char)recomp_load8(c, k + j))) break;
                kt[47] = 0;
                int printable = v > 0x100000;
                for (int j = 0; printable && j < 47; j++) {
                    const char ch = (char)recomp_load8(c, v + j);
                    if (!ch) { vt[j] = 0; break; }
                    if (ch < 32 || ch > 126) { printable = 0; strcpy(vt, "?"); break; }
                    vt[j] = ch, vt[j + 1] = 0;
                }
                vt[47] = 0;
                at += snprintf(line + at, sizeof line - at, " %s=%s", kt, vt);
            }
            hos_log("%s", line);
        }
    }
    static const char key[] = "Drop__DropActor";
    int found = -1;
    for (int i = 0; i < names && i < values && found < 0; i++) {
        const uint64_t k = recomp_load64(c, name_at + 8ULL * i);
        if (!k) continue;
        int same = 1;
        for (int j = 0; j < (int)sizeof key && same; j++) same = (char)recomp_load8(c, k + j) == key[j];
        if (same) found = i;
    }
    if (found < 0) return;
    const uint64_t value = recomp_load64(c, value_at + 8ULL * found);
    if (!value) return;
    char name[96];
    int length = 0;
    for (; length + 1 < (int)sizeof name; length++) {
        name[length] = (char)recomp_load8(c, value + length);
        if (!name[length]) break;
    }
    name[length] = 0;
    if (oot_family_of(name, NULL) < 0 || (!hos_rando_progressive() && !oot_magic_family(name))) return;
    uint64_t saved[31];
    memcpy(saved, c->x, sizeof saved);   /* (oot_pouch_count calls the game: the registers are given back as they were) */
    const char *give = oot_progressive_give(c, name);
    memcpy(c->x, saved, sizeof saved);
    if (!give) return;
    /* (the owner's run 2026-11-24: a Skulltula's Golden Gauntlets showed the gauntlets and gave the Goron Bracelet. A
       Skulltula's drop is shown as the family's next only when the seed made that a pick-up: it names those tiers in
       mods/rando-seed/skull_tiers.txt (tools/rando/rando_seed.py SKULL_TIERS); else the seed's item stays, as bug 114 left
       every one: a tier that is no pick-up could not be taken) */
    if (skull) {
        char path[MAX_PATH + 48], line[96];
        int made_one = 0;
        FILE *f = oot_game_file(path, sizeof path, "mods/rando-seed/skull_tiers.txt") ? fopen(path, "r") : NULL;
        while (f && !made_one && fgets(line, sizeof line, f)) {
            line[strcspn(line, "\r\n")] = 0;
            made_one = line[0] != '#' && !strcmp(line, give);
        }
        if (f) fclose(f);
        if (!made_one) return;
        if (!strcmp(give, name)) return;
        const uint64_t kept = oot_kept_name(give);
        if (!kept) return;
        recomp_store64(c, value_at + 8ULL * found, kept);
        const uint64_t text = recomp_load64(c, self + 0x48);
        const int size = (int)recomp_load32(c, self + 0x50);
        if (text && size > (int)strlen(give) && size <= 4096) {
            const size_t n = strlen(give);
            for (size_t i = 0; i <= n; i++) recomp_store8(c, text + i, (uint8_t)give[i]);
        }
        hos_log("rando: progressive: a Gold Skulltula's %s shows and gives %s", name, give);
        return;
    }
    for (size_t i = 0; i < sizeof oot_show_as / sizeof oot_show_as[0]; i++)
        if (!strcmp(give, oot_show_as[i][0])) give = oot_show_as[i][1];
    for (size_t i = 0; i < sizeof oot_no_show / sizeof oot_no_show[0]; i++)
        if (!strcmp(give, oot_no_show[i])) {
            hos_log("rando: progressive: a chest's %s gives %s, which has no words of its own: it shows its own", name, give);
            return;
        }
    if (!strcmp(give, name)) return;
    const uint64_t kept = oot_kept_name(give);
    if (!kept) return;
    recomp_store64(c, value_at + 8ULL * found, kept);   /* (the list's value: what reads it after) */
    const uint64_t text = recomp_load64(c, self + 0x48);   /* (the component's own copy) */
    const int size = (int)recomp_load32(c, self + 0x50);
    if (text && size > (int)strlen(give) && size <= 4096) {
        const size_t n = strlen(give);
        for (size_t i = 0; i <= n; i++) recomp_store8(c, text + i, (uint8_t)give[i]);
    }
    hos_log("rando: progressive: a chest's %s shows and gives %s", name, give);
#else
    (void)c; (void)self; (void)made;
#endif
}

/* (the randomizer's fork) Progressive items, what a gift or a shop's sale shows and says. A character's gift, a
   Business Scrub's sale, a quest's reward and a shop's sale name their item in their event (the seed's rewrite of the
   flow: GetInEvent_<...>(ActorName "Item_...")), and the scene's steps take it from there: Link holds up the item of
   that name (Player_Event's EventCreateShowItemFromActorFileName: the AI node ExecuteEventCreateShowItem, f_826ca590,
   its name's input at +0x38 when the numbers at +0x28 and +0x30 are -1), and the window's words are those of the String64
   flag UI_MessageTargetActorName, set before it opens (PouchSystemActor's EventTriggerSetForGetWindow: the AI node
   OneShotSetNonStructGameDataString64, f_8295a4b0, the flag's name's input at +0x30, its value's at +0x40). The pouch's
   add (hos_oot_pouch_add) gives the family's next. Each input is a pointer (its two low bits a tag) to where the name's
   string pointer is kept; that is pointed at a kept string with the family's next, in the spelling a chest shows
   (oot_show_as, oot_no_show), so the steps after read it too. What is shown is chosen once an event (the event manager's
   current event): a step after the add would otherwise show the tier after. kind 0 the flag's node, 1 the show item's.
   Called at the nodes' start (nx2/oot_patches.py patch_get_name). HOS_OOT_GET_NAME=0 turns it off. */
#if defined(_WIN32) || defined(__linux__)
static int oot_guest_string(Ctx *c, uint64_t at, char *out, int size) {
    int n = 0;
    if (!at) return 0;
    for (; n + 1 < size; n++) {
        out[n] = (char)recomp_load8(c, at + n);
        if (!out[n]) break;
    }
    out[n] = 0;
    return n + 1 < size;
}
#endif

void hos_oot_get_name(Ctx *c, uint64_t node, int kind) {
#if defined(_WIN32) || defined(__linux__)
    static int on = -1;
    if (on < 0) { const char *e = getenv("HOS_OOT_GET_NAME"); on = !(e && *e == '0'); }
    if (!on || !node || !hos_rando_on()) return;
    uint64_t slot = 0;
    char name[96];
    if (kind == 0) {
        const uint64_t key_slot = recomp_load64(c, node + 0x30) & ~3ULL;
        char key[64];
        if (!key_slot || !oot_guest_string(c, recomp_load64(c, key_slot), key, sizeof key)) return;
        const int window = !strcmp(key, "UI_MessageTargetActorName"), shop = !strcmp(key, "Shop_SelectItemName");
        if (!window && !shop) return;
        slot = recomp_load64(c, node + 0x40) & ~3ULL;
        if (!slot || !oot_guest_string(c, recomp_load64(c, slot), name, sizeof name)) return;
        static char last[2][96];   /* (each value once in the log, to learn what the shops set) */
        if (strcmp(last[shop], name)) {
            snprintf(last[shop], sizeof last[shop], "%s", name);
            hos_log("rando: progressive: %s set to %s", key, name);
        }
        if (shop) return;
        /* (bug 141, the owner's run 2026-11-25: a small key found in Kokiri Forest said "You found a small key!", not whose.)
           A dungeon item of a chest away from its dungeon: the window's words are the seed's for that dungeon's item,
           "<item>_<dungeon>" (rando_seed.py DUNGEON_WORDS: "You found a small key for the Water Temple!"), when the seed
           has them (dungeon_words.txt). Link stands at the chest as the window opens, before the add (oot_dungeon_item) */
        if (oot_dungeon_words && (!strcmp(name, "Item_Dungeon_SmallKey") || !strcmp(name, "Item_Dungeon_BossKey") ||
                                  !strcmp(name, "Item_Dungeon_Map") || !strcmp(name, "Item_Dungeon_Compass"))) {
            char owner[24], word[64];
            if (!oot_dungeon_owner(name, owner, sizeof owner, NULL)) return;
            snprintf(word, sizeof word, "%s_%s", name, owner);
            const uint64_t kept = oot_kept_name(word);
            if (kept) recomp_store64(c, slot, kept);
            hos_log("rando: a %s's window names its dungeon: %s%s", name, word, kept ? "" : " (NOT DONE: no kept name)");
            return;
        }
        /* (a Piece of Heart lying in the world, or a boss's Heart Container, that the seed made another item: the window
           names that item, as the add gives it (oot_piece_gives; with Progressive items the family's next), in the
           spelling with "You got" words. Seen without a window 2026-11-20: Zora's River's piece of a Gold Skulltula
           token said "You got a Piece of Heart!" and "Four pieces form one container". The piece itself is still what
           Link holds up: it is the world's actor) */
        if (oot_is_piece(name) || !strcmp(name, OOT_PIECE_VALLEY) || oot_is_container(name) || oot_is_sun(name)) {
            char gives[64];
            if (!oot_piece_gives(gives, sizeof gives, oot_is_container(name))) return;
            const char *word = gives;
            if (hos_rando_progressive() || oot_magic_family(gives)) {
                uint64_t saved[31];
                memcpy(saved, c->x, sizeof saved);   /* (oot_pouch_count calls the game) */
                const char *next = oot_progressive_give(c, gives);
                memcpy(c->x, saved, sizeof saved);
                if (next) word = next;
            }
            for (size_t i = 0; i < sizeof oot_show_as / sizeof oot_show_as[0]; i++)
                if (!strcmp(word, oot_show_as[i][0])) word = oot_show_as[i][1];
            for (size_t i = 0; i < sizeof oot_no_show / sizeof oot_no_show[0]; i++)
                if (!strcmp(word, oot_no_show[i])) return;
            const uint64_t kept = oot_kept_name(word);
            if (kept) recomp_store64(c, slot, kept);
            hos_log("rando: a %s's window names the seed's %s%s", name, word, kept ? "" : " (NOT DONE: no kept name)");
            return;
        }
    } else {
        const uint64_t a = recomp_load64(c, node + 0x28) & ~3ULL, b = recomp_load64(c, node + 0x30) & ~3ULL;
        if (env_on("HOS_OOT_SHOW_LOG")) {   /* (a test's: every show item asked for, before the checks below) */
            const uint64_t s = recomp_load64(c, node + 0x38) & ~3ULL;
            char seen[96] = "";
            if (s) oot_guest_string(c, recomp_load64(c, s), seen, sizeof seen);
            hos_log("rando: show item asked: a %d b %d name '%s'", a ? (int32_t)recomp_load32(c, a) : -999, b ? (int32_t)recomp_load32(c, b) : -999, seen);
        }
        if (!a || !b || (int32_t)recomp_load32(c, a) != -1 || (int32_t)recomp_load32(c, b) != -1) return;
        slot = recomp_load64(c, node + 0x38) & ~3ULL;
        if (!slot || !oot_guest_string(c, recomp_load64(c, slot), name, sizeof name)) return;
    }
    if (!hos_rando_progressive() && !oot_magic_family(name)) return;   /* (rando_magic's tiers whatever Progressive items says) */
    int spelling = 0;
    const int family = oot_family_of(name, &spelling);
    if (family < 0) return;
    /* (once an event: the family's choice kept with the event it was made in) */
    static struct { uint64_t event; int family; const char *give; } chosen[4];
    const uint64_t events = oot_singleton(c, OOT_EVENTMGR_SLOT);
    const uint64_t event = events ? recomp_load64(c, events + 104) : 0;
    const char *give = NULL;
    int found = 0;
    for (int i = 0; i < 4 && !found; i++)
        if (event && chosen[i].event == event && chosen[i].family == family) give = chosen[i].give, found = 1;
    if (!found) {
        uint64_t saved[31];
        memcpy(saved, c->x, sizeof saved);   /* (oot_pouch_count calls the game) */
        give = oot_progressive_give(c, name);
        memcpy(c->x, saved, sizeof saved);
        if (give)
            for (size_t i = 0; i < sizeof oot_show_as / sizeof oot_show_as[0]; i++)
                if (!strcmp(give, oot_show_as[i][0])) give = oot_show_as[i][1];
        if (give)
            for (size_t i = 0; i < sizeof oot_no_show / sizeof oot_no_show[0]; i++)
                if (!strcmp(give, oot_no_show[i])) give = NULL;
        if (event) {
            static int turn;
            chosen[turn].event = event, chosen[turn].family = family, chosen[turn].give = give;
            turn = (turn + 1) % 4;
        }
        hos_log("rando: progressive: %s's %s %s", kind ? "a show item" : "a get window", name,
                give ? (strcmp(give, name) ? "is shown as the family's next" : "is the family's next") : "is shown as it is");
        if (give && strcmp(give, name)) hos_log("rando: progressive: shown: %s", give);
    }
    /* (bugs 54, 55, 56: the item Link holds up is shown by the Item_ spelling. The Armor_ spellings (oot_show_as) have the
       "You got" words, but are the pieces Link wears: held up, nothing showed (the bracelet from a chest, the Silver
       Gauntlets bought). Both spellings' packs name the same model; the game's own bracelet scene, Dm_Goron_0030, holds
       up Item_Gauntlet_Goron. The window's words keep the Armor_ spelling.
       The Weapon_ spellings the same (bug 73, the owner's run 2026-11-18): the Potion Shop keeper's gift, the seed's Fairy
       Slingshot, held up as Weapon_Range_SlingShot made no show item, and the game read the one it had not made: a crash
       (guest lr 0x829630ac, a null actor's +0x270 read in f_80994de0). Every spelling of oot_show_as is held up by its
       Item_ one; a chest's Bow held up as the weapon was also upside down and off-centre, bug 71) */
    if (kind == 1) {
        const char *shown = give ? give : name;
        for (size_t i = 0; i < sizeof oot_show_as / sizeof oot_show_as[0]; i++)
            if (!strcmp(shown, oot_show_as[i][1])) {
                if (strcmp(give ? give : "", oot_show_as[i][0]))
                    hos_log("rando: progressive: a show item's %s is held up as %s", shown, oot_show_as[i][0]);
                give = oot_show_as[i][0];
            }
    }
    if (!give || !strcmp(give, name)) return;
    const uint64_t kept = oot_kept_name(give);
    if (kept) recomp_store64(c, slot, kept);
    (void)spelling;
#else
    (void)c; (void)node; (void)kind;
#endif
}

/* (the randomizer's fork) Progressive items, what a shelf shows. A shelf's look, name and the keeper's words are its
   actor's, which its map file names; the seed writes a shop's map once for each choice of tiers of its shelves of a
   family, and lists them in <seed>/shelf_tiers.txt ("<the map's path>|<item>,<item>...": the items the shuffle put on
   those shelves, in the order of the versions' names; tools/rando/rando_seed.py SHELF_FAMILIES). As the game opens such a
   map (host/mods.c hos_mods_romfs) it is given <seed>/shelf_tiers/<the map's path>.<k>_<k>..., k the tier of each shelf:
   the family's next for what Link has, or the shelf's own item when he has the family whole. What he has is what
   oot_inventory_refresh last read (every half second, a save loaded). The game keeps a map it has opened (seen: the
   Kokiri Forest's was not opened again after the Lost Woods and back), and opens the first one before anything here has
   read the pouch: the levels last read are kept in <user>/<save folder>/family_levels.txt for it. So a shelf shows what
   Link had when the map was first opened in a session; it still gives what the pouch's add gives.
   HOS_OOT_SHELF_TIERS=0 turns it off. */
static volatile int oot_family_level[OOT_FAMILIES + 1] = {[0 ... OOT_FAMILIES] = -1};

static void oot_family_levels_path(char *out, size_t cap) {
    extern const char *hos_user_dir;
    const char *hos_save_folder(void);
    snprintf(out, cap, "%s/%s/family_levels.txt", hos_user_dir ? hos_user_dir : "user", hos_save_folder());
}

static void oot_family_levels_refresh(Ctx *c) {
    int changed = 0, loading = 0;
    /* (not while an event plays or a map loads: the pouch is then the game's to change, and a count read half way
       would be kept for the maps opened next. A precaution: nothing wrong was seen) */
    if (oot_event_playing(c) || (oot_gamedata_bool(c, 0xef2b60c2u, &loading) && loading)) return;   /* (Sequence_IsLoadingBanc) */
    for (int f = 0; f < OOT_FAMILIES; f++) {
        int tiers = 0, level = 0;
        while (tiers < 3 && oot_families[f][tiers][0]) tiers++;
        for (int t = tiers - 1; t >= 0 && !level; t--)
            for (int a = 0; a < 2 && !level; a++)
                if (oot_families[f][t][a] && oot_pouch_count(c, oot_families[f][t][a]) > 0) level = t + 1;
        changed |= __atomic_exchange_n(&oot_family_level[f], level, __ATOMIC_RELAXED) != level;
    }
    if (changed && hos_rando_on() && hos_rando_progressive()) {
        char path[MAX_PATH + 64], line[OOT_FAMILIES + 2];
        oot_family_levels_path(path, sizeof path);
        for (int f = 0; f < OOT_FAMILIES; f++) line[f] = (char)('0' + __atomic_load_n(&oot_family_level[f], __ATOMIC_RELAXED));
        line[OOT_FAMILIES] = 10, line[OOT_FAMILIES + 1] = 0;   /* (a line's end) */
        FILE *out = fopen(path, "wb");
        if (out) fputs(line, out), fclose(out);
    }
}

#if defined(_WIN32) || defined(__linux__)
/* (bug 69) A shelf of a family showed the tier of its map's first opening in a session: the game opens a map file once
   a session and keeps it, so the version given then (hos_oot_shelf_map) stays (the owner's run, 2026-11-17: the Silver
   Scale bought in the Zora shop, the Market's shelf still showed it). But the game reads the kept map's actors again at
   each entry into the area: f_805d7660 reads each actor's name (Gyaml) from it, and asks here with the name's place
   (nx2/oot_patches.py patch_shelf_actor). A shelf's tiers are its actors (tools/rando/rando_seed.py SHELF_FAMILIES): the
   shuffled item's is the shelf's own, <shelf>, each other tier k <shelf>_<k>; the seed lists the shelves in
   shelf_tiers.txt's third field. Any of a shelf's names is answered with the one for what Link has now, a string of the
   host's own in guest memory that stays. The place on the shelf stays the version's given at the opening (each tier had
   its own: a model may sit a little off). HOS_OOT_SHELF_TIERS=0 turns it off with the maps' versions. */
static struct { char actor[48]; int family, own; } oot_tier_shelves[64];
static int oot_tier_shelf_count;
static void oot_tier_shelf_add(const char *actor, const char *item) {
    const int f = oot_family_of(item, NULL);
    if (f < 0 || oot_tier_shelf_count >= (int)(sizeof oot_tier_shelves / sizeof oot_tier_shelves[0]) ||
        strlen(actor) + 3 >= sizeof oot_tier_shelves[0].actor)
        return;
    int tiers = 0, own = 0;
    while (tiers < 3 && oot_families[f][tiers][0]) tiers++;
    for (int t = 0; t < tiers; t++)
        for (int a = 0; a < 2; a++)
            if (oot_families[f][t][a] && !strcmp(oot_families[f][t][a], item)) own = t;
    for (int i = 0; i < oot_tier_shelf_count; i++)   /* (a shelf in two maps' lines: a map's adult and child copies) */
        if (!strcmp(oot_tier_shelves[i].actor, actor)) return;
    snprintf(oot_tier_shelves[oot_tier_shelf_count].actor, sizeof oot_tier_shelves[0].actor, "%s", actor);
    oot_tier_shelves[oot_tier_shelf_count].family = f, oot_tier_shelves[oot_tier_shelf_count].own = own;
    __atomic_store_n(&oot_tier_shelf_count, oot_tier_shelf_count + 1, __ATOMIC_RELEASE);
}
/* which of the shelves `name` is a tier of (-1 none), and that tier in *tier */
static int oot_tier_shelf_of(const char *name, int *tier) {
    const int count = __atomic_load_n(&oot_tier_shelf_count, __ATOMIC_ACQUIRE);
    for (int i = 0; i < count; i++) {
        const size_t n = strlen(oot_tier_shelves[i].actor);
        if (strncmp(name, oot_tier_shelves[i].actor, n)) continue;
        if (!name[n]) { *tier = oot_tier_shelves[i].own; return i; }
        if (name[n] == '_' && name[n + 1] >= '0' && name[n + 1] <= '2' && !name[n + 2]) { *tier = name[n + 1] - '0'; return i; }
    }
    return -1;
}
/* the tier a shelf shows for what Link has now (-1: not read yet) */
static int oot_tier_shelf_want(int i) {
    const int f = oot_tier_shelves[i].family;
    const int level = __atomic_load_n(&oot_family_level[f], __ATOMIC_RELAXED);
    if (level < 0) return -1;
    int tiers = 0;
    while (tiers < 3 && oot_families[f][tiers][0]) tiers++;
    return level < tiers ? level : oot_tier_shelves[i].own;
}
#endif
/* (Pots, 2026-11-25) Each pot taking part is an actor of its own, coloured, dropping its check's item (tools/rando/rando_seed.py
   POT_ACTOR: Obj_PotR000...); <seed>/pot_looks.txt lists them in order, "<actor>|<its hash>|<the game's pot it was>". Once
   its check is collected (the record's: oot_checks[].broken is the pot's hash), its name read as its map is read is
   answered with the game's pot: red again, and its drop table "None" the game's, which drops nothing. (0: not one) */
#define OOT_POT_LOOK_MAX 1024
static struct { uint64_t hash; char game[40], bagged[24]; uint64_t slot, bagged_slot; } oot_pot_looks[OOT_POT_LOOK_MAX];
static int oot_bundle_holder(const char *name, const char *const **sizes);
static int oot_pot_look_count = -1;
/* (POT_BAGGED) Whether Link holds one of a bundle's bags (sizes: smallest first). The pouch, else (as a map is read with a save
   just loaded, the pouch not there yet: its count -1) the save's IsGet.<bag> flags; not known: not held, so the pot drops the
   bundle that gives the bag. Reported 2026-11-25: a save loaded in the Market had its stick pots read with the pouch not yet
   there, taken as a bag held: the game's own sticks, a green rupee with no bag, and no bag ever given. */
static int oot_pot_bag_held(Ctx *c, const char *const *sizes) {
    int known = 0;
    for (int i = 0; i < 3; i++) {
        const int n = oot_pouch_count(c, sizes[i]);
        if (n > 0) return 1;
        if (n == 0) known++;
    }
    if (known == 3) return 0;
    for (int i = 0; i < 3; i++) {
        char flag[64];
        int got = 0;
        snprintf(flag, sizeof flag, "IsGet.%s", sizes[i]);
        if (oot_gamedata_bool(c, oot_flag_hash(flag), &got) && got) return 1;
    }
    return 0;
}
#if defined(_WIN32) || defined(__linux__)
static int oot_text_is(Ctx *c, uint64_t at, const char *text) {
    if (!at) return 0;
    for (int i = 0;; i++) {
        const char ch = (char)recomp_load8(c, at + (unsigned)i);
        if (ch != text[i]) return 0;
        if (!ch) return 1;
    }
}
static int oot_pot_index(const char *name, int *bagged) {   /* (k of "Obj_PotR<k>" or "Obj_PotR<k>B", else -1) */
    if (strncmp(name, "Obj_PotR", 8) || strlen(name) < 11) return -1;
    int k = 0;
    for (int i = 8; i < 11; i++) {
        if (name[i] < '0' || name[i] > '9') return -1;
        k = k * 10 + name[i] - '0';
    }
    *bagged = name[11] == 'B' && !name[12];
    return name[11] && !*bagged ? -1 : k;
}
#endif
/* (POT_BAGGED, bug 139, reported 2026-11-25: the Deku Nuts and Sticks still played their get scene until Link left the area.)
   A pot read as its bag-giving actor ("Obj_PotR<k>B", oot_pot_look_answer: no bag when its area was read) drops its bundle
   by its own drop table, named in its list of values (Drop__DropTable "None", Drop__DropActor empty). The game's f_80bf1c00
   reads that list into the pot's drop both as the pot is made and again as it breaks; this is called just before it reads
   (nx2/oot_patches.py patch_drop_name, with the same self and made as hos_oot_drop_name). When Link holds the bag by then,
   the list is made a grass's first: Drop__DropActor the game's own pick-up (Obj_DekuNut, Obj_DekuStick: POT_WORLD's) and no
   table, so the pot breaks into plain ones with no scene. Nothing is kept between calls: the list is the one the game is
   about to read. (Before: the lists were noted as the pots were made and rewritten from Link's update once the bag was
   held; the notes were thrown away when Link's map name changed, which comes after a new area's pots are made, so in play
   only a pot's own break noted it again, after its drop was read. The owner's log, 2026-11-25.) The registers are given
   back as they were (oot_pouch_count calls the game). */
void hos_oot_drop_list(Ctx *c, uint64_t self, uint64_t made) {
#if defined(_WIN32) || defined(__linux__)
    if (!self || !made || !hos_rando_on()) return;
    const uint64_t owner = recomp_load64(c, made + 0x40);
    const uint64_t at = owner ? recomp_load64(c, owner + 0x260) : 0;
    char name[24] = "";
    for (int i = 0; at && i < (int)sizeof name - 1; i++)
        if (!(name[i] = (char)recomp_load8(c, at + (unsigned)i))) break;
    name[sizeof name - 1] = 0;
    int bagged = 0;
    const int k = oot_pot_index(name, &bagged);
    if (k < 0 || !bagged || k >= oot_pot_look_count) return;
    uint64_t list = recomp_load64(c, owner + 0x270);
    if (list) list = recomp_load64(c, list);
    if (list) list = recomp_load64(c, list + 0x10);
    if (list + 1 < 2) return;   /* (none: the game reads its own empty one) */
    const int names = (int)recomp_load32(c, list), count = (int)recomp_load32(c, list + 0x10);
    const uint64_t keys = recomp_load64(c, list + 8), values = recomp_load64(c, list + 0x18);
    if (!keys || !values || names <= 0 || names > 64 || count < names) return;
    int table = -1, actor = -1;
    for (int i = 0; i < names; i++) {
        const uint64_t key = recomp_load64(c, keys + 8ULL * i);
        if (oot_text_is(c, key, "Drop__DropTable")) table = i;
        else if (oot_text_is(c, key, "Drop__DropActor")) actor = i;
    }
    if (table < 0 || actor < 0) return;
    char item[48] = "";
    AcquireSRWLockShared(&oot_checks_lock);
    for (int i = 0; i < oot_check_count; i++)
        if (oot_checks[i].pot && oot_checks[i].broken == oot_pot_looks[k].hash) {
            snprintf(item, sizeof item, "%s", oot_checks[i].item);
            break;
        }
    ReleaseSRWLockShared(&oot_checks_lock);
    const char *plain = !strcmp(item, "TBox_DekuNutBundle") ? "Obj_DekuNut" : !strcmp(item, "Item_DekuStickBundle_Small") ? "Obj_DekuStick" : NULL;
    const char *const *sizes = NULL;
    if (!plain || oot_bundle_holder(item, &sizes) != 1) return;
    if (oot_text_is(c, recomp_load64(c, values + 8ULL * actor), plain)) return;   /* (made plain at an earlier call) */
    uint64_t saved[31];
    memcpy(saved, c->x, sizeof saved);
    const int held = oot_pot_bag_held(c, sizes);
    memcpy(c->x, saved, sizeof saved);
    if (!held) return;
    const uint64_t kept = oot_kept_name(plain), none = oot_kept_name("");
    if (!kept || !none) return;
    recomp_store64(c, values + 8ULL * actor, kept);
    recomp_store64(c, values + 8ULL * table, none);
    static int told;
    if (told++ < 40) hos_log("rando: pots: %s drops %s: the bag is held (its list made plain before the game reads it)", name, plain);
#else
    (void)c; (void)self; (void)made;
#endif
}
static uint64_t oot_pot_look_answer(Ctx *c, uint64_t name_at) {
    static const char head[] = "Obj_PotR";
    for (int i = 0; head[i]; i++)
        if ((char)recomp_load8(c, name_at + i) != head[i]) return 0;
    int k = 0;
    for (int i = 0; i < 3; i++) {
        const char d = (char)recomp_load8(c, name_at + sizeof head - 1 + i);
        if (d < '0' || d > '9') return 0;
        k = k * 10 + d - '0';
    }
    if ((char)recomp_load8(c, name_at + sizeof head - 1 + 3)) return 0;
    static SRWLOCK lock = SRWLOCK_INIT;
    AcquireSRWLockExclusive(&lock);
    if (oot_pot_look_count < 0) {
        oot_pot_look_count = 0;
        char path[MAX_PATH], line[160];
        FILE *f = oot_game_file(path, sizeof path, "mods/rando-seed/pot_looks.txt") ? fopen(path, "rb") : NULL;
        while (f && fgets(line, sizeof line, f) && oot_pot_look_count < OOT_POT_LOOK_MAX) {
            char actor[40], hash[24], game[40], bagged[24] = "";
            if (line[0] == '#' || sscanf(line, "%39[^|]|%23[^|]|%39[^|\r\n]|%23[^|\r\n]", actor, hash, game, bagged) < 3) continue;
            oot_pot_looks[oot_pot_look_count].hash = strtoull(hash, NULL, 16);
            snprintf(oot_pot_looks[oot_pot_look_count].bagged, sizeof oot_pot_looks[0].bagged, "%s", bagged);
            snprintf(oot_pot_looks[oot_pot_look_count].game, sizeof oot_pot_looks[0].game, "%s", game);
            oot_pot_look_count++;
        }
        if (f) fclose(f);
        if (oot_pot_look_count) hos_log("rando: pots: %d actors of their own (pot_looks.txt)", oot_pot_look_count);
    }
    uint64_t answer = 0;
    /* (the seed's checks not read yet: the first map of a save just loaded is read before the Tracker's first refresh, a second
       later, and a pot was then no check's: its default actor, the game's own Deku Nuts or Sticks with no bag, and never the
       game's pot once collected. Reported 2026-11-25. Read here, as oot_tracker_refresh does) */
    AcquireSRWLockExclusive(&oot_checks_lock);
    if (oot_check_count < 0) {
        char stamp[sizeof oot_checks_seed];
        oot_tracker_stamp(stamp, sizeof stamp);
        oot_tracker_load(stamp);
        hos_log("rando: pots: the seed's checks read as the first map is read (%d)", oot_check_count);
    }
    ReleaseSRWLockExclusive(&oot_checks_lock);
    if (k < oot_pot_look_count) {
        int done = 0, found = -1;
        char item[48] = "";
        AcquireSRWLockShared(&oot_checks_lock);
        for (int i = 0; i < oot_check_count && found < 0; i++)
            if (oot_checks[i].pot && oot_checks[i].broken == oot_pot_looks[k].hash)
                found = i, done = oot_checks[i].done == 1, snprintf(item, sizeof item, "%s", oot_checks[i].item);
        ReleaseSRWLockShared(&oot_checks_lock);
        /* (a new game of the seed, its own flag still true: none of the record's pots is this game's, oot_pot_progress) */
        int is_new = 0;
        const uint32_t fresh = oot_new_game_flag();
        if (done && fresh && oot_gamedata_bool(c, fresh, &is_new) && is_new) done = 0;
        /* (FIXES 100, POT_BAGGED: a pot holding Deku Nuts or Sticks, Link with no such bag: the actor dropping the bundle
           itself, whose pick-up gives the bag, the game's supply drop being a green rupee then) */
        const char *const *sizes;
        if (!done && found >= 0 && oot_pot_looks[k].bagged[0] && oot_bundle_holder(item, &sizes) == 1 && !oot_pot_bag_held(c, sizes)) {
            if (!oot_pot_looks[k].bagged_slot && (oot_pot_looks[k].bagged_slot = hos_sys_alloc(32, 16)) != 0)
                snprintf((char *)A64_PTR(oot_pot_looks[k].bagged_slot), 32, "%s", oot_pot_looks[k].bagged);
            answer = oot_pot_looks[k].bagged_slot;
            if (answer) hos_log("rando: pots: Obj_PotR%03d holds %s and Link has no bag for it: read as %s", k, item, oot_pot_looks[k].bagged);
        }
        if (done && !answer) {
            if (!oot_pot_looks[k].slot && (oot_pot_looks[k].slot = hos_sys_alloc(64, 16)) != 0)
                snprintf((char *)A64_PTR(oot_pot_looks[k].slot), 64, "%s", oot_pot_looks[k].game);
            answer = oot_pot_looks[k].slot;
            if (answer) hos_log("rando: pots: Obj_PotR%03d is collected: read as %s", k, oot_pot_looks[k].game);
        }
    }
    ReleaseSRWLockExclusive(&lock);
    return answer;
}
/* The Door of Time's name read: the actor to answer it with, NULL the door's own. A save made in the temple loads its map
   before the game's thread first asks for the song (oot_time_door, each second in play): the owner's run 2026-11-26, the
   door was back behind an adult who saved there, Link shut in. So when the door is not known open yet the song and the
   ocarina are asked for here, as the map is read */
static const char *oot_door_answer(Ctx *c, const char *test) {
    int hos_rando_open_door(void);   /* host/oot_rando.c */
    if (test && *test) return test;
    if (__atomic_load_n(&oot_door_song_open, __ATOMIC_ACQUIRE)) return OOT_DOOR_STAND_IN;
    if (hos_rando_open_door() != 2 || !oot_door_song_held(c)) return NULL;
    __atomic_store_n(&oot_door_song_open, 1, __ATOMIC_RELEASE);
    hos_log("rando: Link holds the Song of Time and an ocarina, read as the temple's map is: the Door of Time is open");
    return OOT_DOOR_STAND_IN;
}
uint64_t hos_oot_shelf_actor(Ctx *c, uint64_t name_at) {
#if defined(_WIN32) || defined(__linux__)
    static const char head[] = "Shop_Rando_";
    if (name_at && hos_rando_on()) {   /* (Pots: a collected pot's actor read as the game's pot) */
        const uint64_t pot = oot_pot_look_answer(c, name_at);
        if (pot) return pot;
    }
    {   /* (the Door of Time by the Song of Time: its name answered with a stand-in once open, oot_time_door; a test's
           HOS_OOT_DOOR_AS=<actor> answers it with that actor's whatever the setting) */
        static const char door[] = "Obj_TimeTemple_Door_A_01";
        static const char *test = (const char *)1;
        if (test == (const char *)1) test = getenv("HOS_OOT_DOOR_AS");
        if (name_at) {
            int same = 1;
            for (int i = 0; same && i < (int)sizeof door; i++) same = (char)recomp_load8(c, name_at + i) == door[i];
            const char *as = same ? oot_door_answer(c, test) : NULL;
            if (as) {
                static uint64_t slot;
                if (!slot && (slot = hos_sys_alloc(64, 16)) != 0) snprintf((char *)A64_PTR(slot), 64, "%s", as);
                if (slot) {
                    hos_log("rando: the Door of Time's actor read: answered as %s", as);
                    return slot;
                }
            }
        }
    }
    if (!name_at || !__atomic_load_n(&oot_tier_shelf_count, __ATOMIC_ACQUIRE)) return name_at;
    for (int i = 0; head[i]; i++)
        if ((char)recomp_load8(c, name_at + i) != head[i]) return name_at;
    char name[64];
    size_t n = 0;
    for (; n + 1 < sizeof name; n++)
        if (!(name[n] = (char)recomp_load8(c, name_at + n))) break;
    name[n] = 0;
    if (n + 1 >= sizeof name) return name_at;
    int tier = 0;
    const int i = oot_tier_shelf_of(name, &tier);
    const int want = i >= 0 ? oot_tier_shelf_want(i) : -1;
    static int trace = -1;   /* (a test's: HOS_OOT_SHELF_TRACE=1 logs every shop shelf's name read, and its tier) */
    if (trace < 0) { const char *e = getenv("HOS_OOT_SHELF_TRACE"); trace = e && *e == '1'; }
    if (trace) hos_log("rando: progressive: map actor %s: shelf %d, tier %d, wanted %d", name, i, tier, want);
    if (want < 0 || want == tier) return name_at;
    static uint64_t names;   /* (a slot of 64 bytes for each shelf's tier: written once, then the same each time) */
    if (!names) names = hos_sys_alloc(sizeof oot_tier_shelves / sizeof oot_tier_shelves[0] * 3 * 64, 16);
    if (!names) return name_at;
    const uint64_t at = names + ((uint64_t)i * 3 + (uint64_t)want) * 64;
    char *slot = (char *)A64_PTR(at);
    if (!slot[0]) {
        if (want == oot_tier_shelves[i].own) snprintf(slot, 64, "%s", oot_tier_shelves[i].actor);
        else snprintf(slot, 64, "%s_%d", oot_tier_shelves[i].actor, want);
    }
    static char told[64][4];
    if (!told[i][want]) told[i][want] = 1, hos_log("rando: progressive: shelf %s shows tier %d now (was %s)", oot_tier_shelves[i].actor, want, name);
    return at;
#else
    (void)c;
    return name_at;
#endif
}

int hos_oot_shelf_map(const char *rel, char *out, size_t cap) {
#if defined(_WIN32) || defined(__linux__)
    static SRWLOCK lock = SRWLOCK_INIT;
    static int loaded, on = -1, count;
    static struct { char rel[160]; char items[3][40]; int n; } maps[64];
    if (on < 0) { const char *e = getenv("HOS_OOT_SHELF_TIERS"); on = !(e && *e == '0'); }
    if (!on || !rel || _strnicmp(rel, "Banc/", 5) || !hos_rando_on() || !hos_rando_progressive()) return 0;
    AcquireSRWLockExclusive(&lock);
    if (!loaded) {
        loaded = 1;
        char path[MAX_PATH + 64], line[512];
        FILE *f = oot_game_file(path, sizeof path, "mods/rando-seed/shelf_tiers.txt") ? fopen(path, "rb") : NULL;
        while (f && count < 64 && fgets(line, sizeof line, f)) {
            line[strcspn(line, "\r\n")] = 0;
            char *bar = strchr(line, '|');
            if (!bar || bar - line >= (int)sizeof maps[0].rel) continue;
            *bar = 0;
            snprintf(maps[count].rel, sizeof maps[count].rel, "%s", line);
            char *actors = strchr(bar + 1, '|');   /* (the shelves' actors: a seed from bug 69's fix on) */
            if (actors) *actors++ = 0;
            int n = 0;
            for (char *item = strtok(bar + 1, ","); item && n < 3; item = strtok(NULL, ","))
                snprintf(maps[count].items[n++], sizeof maps[count].items[0], "%s", item);
            maps[count].n = n;
            int k = 0;
            for (char *actor = actors ? strtok(actors, ",") : NULL; actor && k < n; actor = strtok(NULL, ","), k++)
                oot_tier_shelf_add(actor, maps[count].items[k]);
            /* (a map named twice is left as the seed's own: a seed made before fixes 39 listed the Market once for each
               of its two shops, whose versions had overwritten each other, and the game stayed black entering it) */
            int twice = 0;
            for (int i = 0; i < count; i++)
                if (!_stricmp(maps[i].rel, maps[count].rel)) maps[i].n = 0, twice = 1;
            if (twice) hos_log("rando: progressive: %s is listed twice in shelf_tiers.txt: the seed's own map is used", maps[count].rel);
            if (n && !twice) count++;
        }
        if (f) fclose(f);
        if (count) hos_log("rando: progressive: %d shop map(s) with shelves of a family (shelf_tiers.txt)", count);
        oot_family_levels_path(path, sizeof path);   /* (the last levels read, for a map opened before the pouch is read) */
        f = count && __atomic_load_n(&oot_family_level[0], __ATOMIC_RELAXED) < 0 ? fopen(path, "rb") : NULL;
        const char *test = getenv("HOS_OOT_FAMILY_LEVELS");   /* (a test's: those digits in place of the file's) */
        if (test && strlen(test) < sizeof line) snprintf(line, sizeof line, "%s", test);
        if (((test && *test) || (f && fgets(line, sizeof line, f))) && strspn(line, "0123") >= (size_t)OOT_FAMILIES) {
            for (int k = 0; k < OOT_FAMILIES; k++) __atomic_store_n(&oot_family_level[k], line[k] - '0', __ATOMIC_RELAXED);
            hos_log("rando: progressive: the families' levels last read, until the pouch is read: %.*s", OOT_FAMILIES, line);
        }
        if (f) fclose(f);
    }
    int found = -1;
    for (int i = 0; i < count && found < 0; i++)
        if (maps[i].n && !_stricmp(maps[i].rel, rel)) found = i;
    char combo[16] = "";
    int ok = found >= 0;
    for (int k = 0; ok && k < maps[found].n; k++) {
        const int f = oot_family_of(maps[found].items[k], NULL);
        const int level = f >= 0 ? __atomic_load_n(&oot_family_level[f], __ATOMIC_RELAXED) : -1;
        if (level < 0) { ok = 0; break; }
        int tiers = 0, own = 0;
        while (tiers < 3 && oot_families[f][tiers][0]) tiers++;
        for (int t = 0; t < tiers; t++)
            for (int a = 0; a < 2; a++)
                if (oot_families[f][t][a] && !strcmp(oot_families[f][t][a], maps[found].items[k])) own = t;
        const size_t used = strlen(combo);
        snprintf(combo + used, sizeof combo - used, "%s%d", k ? "_" : "", level < tiers ? level : own);
    }
    int given = 0;
    if (ok) {
        char tail[260];
        snprintf(tail, sizeof tail, "mods/rando-seed/shelf_tiers/%s.%s", maps[found].rel, combo);
        if (oot_game_file(out, cap, tail) && GetFileAttributesA(out) != INVALID_FILE_ATTRIBUTES) given = 1;
        hos_log("rando: progressive: the shop's map %s %s its shelves' tiers %s", rel, given ? "is given with" : "has no file for", combo);
    } else if (found >= 0) {
        hos_log("rando: progressive: the shop's map %s is the seed's own (what Link has not read yet)", rel);
    }
    ReleaseSRWLockExclusive(&lock);
    return given;
#else
    (void)rel; (void)out; (void)cap;
    return 0;
#endif
}

#if defined(_WIN32) || defined(__linux__)
/* (bug 42) A bomb added while Link has no Bomb Bag: bombs (Item_Bomb), a chest's bundle (Item_BombBundle_*), a bomb
   lying in the world (Obj_Bomb: not a bomb flower, Obj_BombFlower_*). Not Bombchus, which need no bag, nor an add as a
   save is loaded. 1: it is to add nothing */
static int oot_bombs_bagless(Ctx *c, const char *name) {
    if ((int32_t)c->x[3] <= 0 || c->x[30] == 0x8112d4b8ULL) return 0;
    if (strcmp(name, "Item_Bomb") && strncmp(name, "Item_BombBundle_", 16) && strcmp(name, "Obj_Bomb")) return 0;
    static const char *const bags[3] = {"Item_BombBag_Small", "Item_BombBag_Medium", "Item_BombBag_Large"};
    for (int i = 0; i < 3; i++)
        if (oot_pouch_count(c, bags[i]) != 0) return 0;   /* (-1, not known: as if he had one) */
    return 1;
}

/* (the randomizer's fork, bug 87: the owner's run 2026-11-19) A Gold Skulltula's bundle with nothing to carry it in: a
   pick-up touched asks the game whether the pouch has room (f_80a94ea0, from the touch update: nx2/oot_patches.py
   ROOM_HOOK), and with no holder the answer was no: a Deku Nut bundle with no nut bag stayed where it fell, and its
   Skulltula was back when the area was entered again. What the seed may put on a Skulltula that needs a holder
   (tools/rando/rando_seed.py SKULLTULA_ITEMS): 1, the holder may be given (sizes: smallest first), the nuts and sticks,
   whose bags no rule asks for; 2, the holder is one the logic counts (a Bomb Bag, a quiver with the bow, a bullet bag
   with the Slingshot): the bundle is taken and nothing given, as a chest's bombs are without a bag (bug 42). 0: none.
   Bombchus need no bag. tests/test_rando_skulltula_bagless.py */
static int oot_bundle_holder(const char *name, const char *const **sizes) {
    static const char *const nuts[3] = {"Item_NutBag_Small", "Item_NutBag_Medium", "Item_NutBag_Large"};
    static const char *const sticks[3] = {"Item_StickBag_Small", "Item_StickBag_Medium", "Item_StickBag_Large"};
    static const char *const bombs[3] = {"Item_BombBag_Small", "Item_BombBag_Medium", "Item_BombBag_Large"};
    static const char *const arrows[3] = {"Item_Quiver_Small", "Item_Quiver_Medium", "Item_Quiver_Large"};
    static const char *const seeds[3] = {"Item_BulletBag_Small", "Item_BulletBag_Medium", "Item_BulletBag_Large"};
    static const struct { const char *name; const char *const *sizes; int rule; } bundles[] = {
        {"TBox_DekuNutBundle", nuts, 1}, {"Item_DekuStickBundle_Small", sticks, 1}, {"Item_BombBundle_Small", bombs, 2},
        {"TBox_ArrowBundle_Medium", arrows, 2}, {"TBox_ArrowBundle_Large", arrows, 2}, {"Item_ScrubBusinessSeed", seeds, 2},
    };
    for (unsigned i = 0; i < sizeof bundles / sizeof bundles[0]; i++)
        if (!strcmp(name, bundles[i].name)) {
            *sizes = bundles[i].sizes;
            return bundles[i].rule;
        }
    *sizes = NULL;
    return 0;
}

/* (a check of the seed not yet collected that gives this, in the map Link is in and near him: the pick-up is a
   Skulltula's drop, not one of the world's own) */
static int oot_drop_check_near(const char *name) {
    int found = 0;
    AcquireSRWLockShared(&oot_checks_lock);
    for (int i = 0; i < oot_check_count && !found; i++) {
        if (oot_checks[i].done == 1 || strcmp(oot_checks[i].item, name) || !oot_banc_in_folder(oot_link_map, oot_checks[i].folder))
            continue;
        const float dx = oot_checks[i].place[0] - oot_link_place[0], dy = oot_checks[i].place[1] - oot_link_place[1],
                    dz = oot_checks[i].place[2] - oot_link_place[2];
        found = dx * dx + dy * dy + dz * dz <= OOT_CHECK_NEAR * OOT_CHECK_NEAR;
    }
    ReleaseSRWLockShared(&oot_checks_lock);
    return found;
}
static int oot_holder_giving;   /* (a holder the host gives just now: not a check's item for the tracker's record) */
#endif

/* 1: the pick-up is to be got with nothing given (w0 1 in the game's answer); 0: the game answers, with a holder given
   first when Link had none (an add is counted an update later: the touch is answered no this time and yes the next).
   (bug 136, 2026-11-25) A check's pick-up (a Gold Skulltula's drop near its place, or a pot's whose pot is broken and not
   yet collected: oot_pot_open) is got with a full bag too: the game answered no, and it stayed there, lifted and thrown
   (seen in play: Deku Nut and Stick bundles from the Market guard house's pots, after the first; the first was got by its
   get scene, which asks nothing). Got, the add follows with what fits (seen: "pouch add Item_DekuNut x0"). */
static int oot_pot_open(Ctx *c, const char *name, int *broken);
/* (fixes 102, tools/rando/rando_seed.py POT_FALL_AS) A pot's unique item is an actor of its own that falls to the ground,
   "<the item>_Fall", and the game names the pick-up and the pouch's add by the actor: the name is made the item's again
   (1), so everything after goes by the seed's item as it did. 0: not such a name, left as it is. */
#define OOT_POT_FALL "_Fall"
/* (tools/rando/rando_seed.py POT_AS, asked 2026-11-25) A pick-up the seed made for an item that has no chest's item of its
   own, and the item it stands for: the Master Sword's (MASTER_PICKUP, made from the Biggoron's item), and an ocarina's
   that a character hands over (OCARINA_HELD, bug 162: Link held up the ocarina he plays and the game fell; the add is
   by the held item's name, seen without a window, and is made the ocarina's here) */
static const char *const oot_pot_as[][2] = {{"Item_Sword_Master", "Weapon_Sword_Master"}, {"Item_HeldOcarina_Fairy", "Item_Ocarina_Fairy"}, {"Item_HeldOcarina_Time", "Item_Ocarina_Time"}};
/* (tools/rando/rando_seed.py DUNGEON_PICKUP, asked 2026-11-26) A pot's dungeon item is a pick-up of its dungeon's own,
   "<the item>_<its dungeon>": the get scene's words are the seed's for that name, and the add here is made the item's again,
   its dungeon kept for oot_dungeon_item (oot_pickup_folder). Two pots broken by one swing, each with a small key of another
   dungeon, named one dungeon twice when it was chosen by the nearest pot (the owner's test). 1 when the name was one */
static int oot_dungeon_pickup(char *name, char *folder, size_t size) {
    static const char *const items[] = {"Item_Dungeon_SmallKey", "Item_Dungeon_BossKey", "Item_Dungeon_Map", "Item_Dungeon_Compass"};
    for (unsigned i = 0; i < sizeof items / sizeof items[0]; i++) {
        const size_t n = strlen(items[i]);
        if (strncmp(name, items[i], n) || name[n] != '_' || !name[n + 1]) continue;
        const char *rest = name + n + 1;
        for (const char *k = rest; *k; k++)
            if (!((*k >= 'A' && *k <= 'Z') || (*k >= 'a' && *k <= 'z'))) return 0;
        if (strlen(rest) >= size) return 0;
        snprintf(folder, size, "%s", rest);
        name[n] = 0;
        return 1;
    }
    return 0;
}
static int oot_pot_fall(char *name) {
    const size_t length = strlen(name), tail = sizeof OOT_POT_FALL - 1;
    int changed = 0;
    if (length > tail && !strcmp(name + length - tail, OOT_POT_FALL)) name[length - tail] = 0, changed = 1;
    for (unsigned i = 0; i < sizeof oot_pot_as / sizeof oot_pot_as[0]; i++)
        if (!strcmp(name, oot_pot_as[i][0])) {   /* (both names are shorter than any buffer this is given: 96) */
            strcpy(name, oot_pot_as[i][1]);
            changed = 1;
        }
    return changed;
}
int hos_oot_pickup_room(Ctx *c) {
#if defined(_WIN32) || defined(__linux__)
    if (!hos_rando_on()) return 0;
    char name[96];
    uint64_t text = c->x[1] ? recomp_load64(c, c->x[1]) : 0;   /* (a name as the pouch's add has it: a pointer to the text) */
    if (!text || text < 0x80000000ULL) text = c->x[1];        /* (else the text itself) */
    size_t length = 0;
    for (; text && length + 1 < sizeof name; length++) {
        name[length] = (char)recomp_load8(c, text + length);
        if (!name[length]) break;
    }
    name[length] = 0;
    oot_pot_fall(name);   /* (a pot's falling pick-up: its item) */
    {
        char folder[24];
        oot_dungeon_pickup(name, folder, sizeof folder);   /* (a dungeon's own: the item's name, DUNGEON_PICKUP) */
    }
    const char *const *sizes;
    const int rule = oot_bundle_holder(name, &sizes);
    int broken_pots = 0;   /* (a junk pot's bundle: its pot is collected when it breaks, so any broken pot giving it, POT_BAGGED) */
    if (!oot_drop_check_near(name) && oot_pot_open(c, name, &broken_pots) < 0 && !(broken_pots && oot_pot_junk(name))) return 0;   /* (no check's: the game's answer) */
    int holder = !rule;
    for (int i = 0; i < 3 && !holder; i++)
        if (oot_pouch_count(c, sizes[i]) != 0) holder = 1;   /* (he has one, or it is not known) */
    if (holder) {
        static int64_t said_at;
        const int64_t now = hos_now_ns();
        if (!said_at || now - said_at > 2000000000LL) hos_log("rando: %s is a check's: got whatever the bag holds", name), said_at = now;
        return 1;
    }
    if (rule == 2) {
        hos_log("rando: a Gold Skulltula's %s with no %s: taken, nothing given", name, sizes[0]);
        return 1;
    }
    static int64_t given_at;   /* (the holder's add is counted an update later: not given twice meanwhile) */
    const int64_t now = hos_now_ns();
    if (given_at && now - given_at < 3000000000LL) return 0;
    given_at = now;
    oot_holder_giving = 1;
    const int result = oot_pouch_change(c, sizes[0], 1);
    oot_holder_giving = 0;
    hos_log("rando: a Gold Skulltula's %s with no holder: %s %s", name, sizes[0], result >= 0 ? "given first" : "could not be given");
#else
    (void)c;
#endif
    return 0;
}
int hos_oot_pouch_add(Ctx *c) {
#if defined(_WIN32) || defined(__linux__)
    if (!hos_rando_on()) return 0;
    uint64_t view = c->x[1];
    const uint64_t text = view ? recomp_load64(c, view) : 0;
    if (!text) return 0;
    char name[96];
    size_t length = 0;
    for (; length + 1 < sizeof name; length++) {
        name[length] = (char)recomp_load8(c, text + length);
        if (!name[length]) break;
    }
    name[length] = 0;
    oot_pickup_folder[0] = 0;
    oot_piece_chosen = -1;
    if (oot_pot_fall(name)) {   /* (a pot's falling pick-up, POT_FALL_AS: the add is its item's) */
        if (oot_dungeon_pickup(name, oot_pickup_folder, sizeof oot_pickup_folder))
            hos_log("rando: pots: the pick-up is %s's own", oot_pickup_folder);
        hos_log("rando: pots: a pot's pick-up (or an item of the seed's own) is the seed's %s: that is added", name);
        view = oot_pouch_name(c, view, name);
    } else if (oot_dungeon_pickup(name, oot_pickup_folder, sizeof oot_pickup_folder)) {   /* (a Gold Skulltula's drop of a dungeon's own) */
        hos_log("rando: a Gold Skulltula's drop is %s's own %s: that is added", oot_pickup_folder, name);
        view = oot_pouch_name(c, view, name);
    }
    /* (every content added, with where the call came from and its other arguments: the game gives a Bomb Bag with a
       chest's bombs when Link has none, seen in play, and that add is to be told from a chest's own Bomb Bag) */
    hos_log("rando: pouch add %s x%d (lr %#llx, x2 %#llx x4 %#llx x5 %#llx x6 %#llx x7 %#llx)", name, (int)(int32_t)c->x[3],
            (unsigned long long)c->x[30], (unsigned long long)c->x[2], (unsigned long long)c->x[4], (unsigned long long)c->x[5],
            (unsigned long long)c->x[6], (unsigned long long)c->x[7]);
    oot_fill_quiet = c->x[30] == 0x828d50acULL && (uint32_t)c->x[4] == 2 && !(c->x[7] & 1);   /* (the game's own bag: oot_fill_note) */
    if (!strcmp(name, "Item_BombBag_Small") && c->x[30] == 0x828d50acULL && (uint32_t)c->x[4] == 2 && !(c->x[7] & 1)) {
        hos_log("rando: the Bomb Bag the game gives with bombs is not given");
        return 1;
    }
    /* (an item given: the tracker's record. Not the pouch as a save is loaded (from 0x8112d4b8), an add inside another (a bag
       filled, a bundle's own: from 0x8112f998 and 0x8112e19c), nor the debug inventory's (x4 9)) */
    static int debug_counts = -1;   /* (a test's: HOS_OOT_TRACK_DEBUG=1 has the debug inventory's adds marked too) */
    if (debug_counts < 0) { const char *e = getenv("HOS_OOT_TRACK_DEBUG"); debug_counts = e && *e == '1'; }
    if ((int32_t)c->x[3] > 0 && c->x[30] != 0x8112d4b8ULL && c->x[30] != 0x8112f998ULL && c->x[30] != 0x8112e19cULL &&
        ((uint32_t)c->x[4] != 9 || debug_counts)) {
        /* (Heart Pieces: a piece lying in the world that the seed made another item gives that item) */
        char gives[64];
        if ((oot_is_piece(name) || !strcmp(name, OOT_PIECE_VALLEY)) && c->x[30] != 0x828d50acULL &&
            oot_piece_gives(gives, sizeof gives, 0)) {
            hos_log("rando: the Piece of Heart lying here is the seed's %s: that is given", gives);
            /* (and the piece's heal is not: bug 4, oot_piece_heal) */
            __atomic_store_n(&oot_life_held, __atomic_load_n(&oot_life_seen, __ATOMIC_RELAXED), __ATOMIC_RELAXED);
            __atomic_store_n(&oot_no_heal_until, hos_now_ns() + OOT_PIECE_NO_HEAL, __ATOMIC_RELEASE);
            /* (the piece is counted all the same, by its own taking and not by this add: see oot_piece_gives. The
               valley's has been counted by now, the others are counted after it. One piece is taken out again: now
               when Link has one, so that the count to come cannot make the fourth of three; else when it has come) */
            const int has = oot_pouch_count(c, OOT_PIECE);
            const int valley = !strcmp(name, OOT_PIECE_VALLEY);
            int result = -2;
            if (has > 0) result = oot_pouch_change(c, OOT_PIECE, -1);
            else if (!valley) __atomic_store_n(&oot_piece_back, OOT_PIECE_WAIT, __ATOMIC_RELEASE);
            hos_log("rando: Link had %d Pieces of Heart at the add: %s", has,
                    has > 0 ? (result >= 0 ? "one is taken out" : "one could not be taken out") :
                    valley ? "none is taken out (the piece made a heart of three)" : "the one to come is taken out");
            view = oot_pouch_name(c, view, gives);
            snprintf(name, sizeof name, "%s", gives);
        } else if (oot_is_container(name) && c->x[30] != 0x828d50acULL && oot_piece_gives(gives, sizeof gives, 1)) {
            /* (bug 31: a boss's Heart Container that the seed made another item gives that item. The container's add
               gives its heart by itself and the pouch keeps none, so the add renamed gives no heart: nothing to take back) */
            hos_log("rando: the boss's Heart Container here is the seed's %s: that is given", gives);
            /* (and the heart its taking makes is taken back: before the add when it rose just now, else after it) */
            const int recent = oot_max_was >= 0 && hos_now_ns() - oot_max_rose < OOT_MAX_RECENT;
            __atomic_store_n(&oot_container_max, recent ? oot_max_was : oot_max_now, __ATOMIC_RELAXED);
            __atomic_store_n(&oot_container_back, OOT_PIECE_WAIT, __ATOMIC_RELEASE);
            hos_log("rando: Link's max life %d quarters at the add%s: kept at %d", oot_max_now, recent ? " (it rose just now)" : "",
                    recent ? oot_max_was : oot_max_now);
            view = oot_pouch_name(c, view, gives);
            snprintf(name, sizeof name, "%s", gives);
        } else if (oot_is_sun(name) && c->x[30] != 0x828d50acULL && oot_piece_gives(gives, sizeof gives, 0) && strcmp(gives, name)) {
            /* (Lake Hylia's Fire Arrows that the seed made another item give that item, SUN_ARROWS) */
            hos_log("rando: the Fire Arrows lying here are the seed's %s: that is given", gives);
            view = oot_pouch_name(c, view, gives);
            snprintf(name, sizeof name, "%s", gives);
        }
        oot_pot_chosen = -1;
        if (c->x[30] != 0x828d50acULL && oot_pot_again(c, name)) return 1;   /* (Pots: a pot back after a day gives nothing again; before the record) */
        if (!oot_holder_giving) {   /* (a holder given for a Skulltula's bundle is no check's: bug 87) */
            const int shop = c->x[30] == 0x828d50acULL && (uint32_t)c->x[4] == 5;   /* (a shop's sale: oot_tracker_item) */
            int32_t price = -1;
            if (shop && !oot_gamedata_int(c, 0x07a1b798u, &price, 0)) price = -1;   /* Shop_SelectItemPrice */
            if (shop) hos_log("rando: tracker: %s bought in a shop (price %d)", name, (int)price);
            oot_tracker_item(c, name, shop, price, c->x[30] != 0x828d50acULL);
        }
    }
    if (oot_dungeon_item(c, name)) return 1;   /* (a dungeon's map or compass got in another place: its dungeon's flag) */
    /* (bug 42: with no Bomb Bag, the bombs that follow the bag the game is not let give made the inventory's bombs at
       0/0, a slot that can't be used: a bomb added while Link has no bag adds nothing. Here, after the tracker's record
       and a piece's or a container's item named: a check that gave bombs is still a check got) */
    if (oot_bombs_bagless(c, name)) {
        hos_log("rando: %s x%d with no Bomb Bag: nothing is added", name, (int)(int32_t)c->x[3]);
        return 1;
    }
    oot_pickup_qol(c, name);   /* (Ammo pick-ups, Rupees fill the wallet) */
    if ((int32_t)c->x[3] <= 0) return 0;
    if (oot_magic_family(name)) {   /* (rando_magic: the first magic found is the meter, oot_magic_give) */
        if (!strcmp(name, OOT_MAGIC_ITEM)) {
            oot_magic_meter(c);
            return 0;
        }
        const char *give = oot_magic_give(c, name);
        if (give) {
            hos_log("rando: magic: %s found: %s given", name, give);
            oot_magic_meter(c);
            oot_pouch_name(c, view, give);
        } else if (!strcmp(name, OOT_MAGIC_DOUBLE)) {
            oot_magic_meter(c);   /* (the second magic, as the gift: doubled and filled) */
        }
        return 0;
    }
    if (!hos_rando_progressive()) {
        oot_fill_note(name);   /* (a bag found is a full bag) */
        return 0;
    }
    if (oot_family_of(name, NULL) >= 0) {
        const char *give = oot_progressive_give(c, name);
        if (!give) {   /* (he has them all: the one found is given as it is) */
            oot_fill_note(name);
            return 0;
        }
        hos_log("rando: progressive: %s found: %s given", name, give);
        oot_fill_note(give);
        if (!strcmp(give, name)) return 0;
        oot_pouch_name(c, view, give);
        return 0;
    }
    oot_fill_note(name);   /* (not an upgrade of a family: a holder all the same, or nothing) */
    return 0;
#else
    (void)c;
    return 0;
#endif
}

/* The new-game opening, build e0f3ccfaf50065ae4ea01eb5aeb13b1a45da3348. Sequence/Opening.module.ainb requests
   Opening_Introduction and Opening_LoadingKokiriForest (SeqOneShotRequestEvent, f_80d9a820; the event name is the
   pointer at the request arg + 6800, which that function reads). Opening_Introduction's flowchart writes the state
   on both paths: the clock at 6:00, Meet_DekuTree's challenge Step01, the forest terrain pin, then
   EventTransition of the timeline Dm_Kokiri_0030. Its own skip query (IsEventSkipedMostRecent, f_80de6cb0) then
   takes the short edge: Navi warped to the position that edge names, the in-game music, Navi's talked flag, the
   camera handed back, and an autosave. Opening_LoadingKokiriForest's flowchart plays the timeline Dm_Kokiri_0000
   and then waits until the forest banc has loaded. Neither timeline writes save data. Meet_DekuTree is a later
   flow and is not one of these names.

   With Skip opening on, the request is still sent, so the flowchart applies that edge. The two timelines are not
   started: f_83b5bfb0 is their only starter (EventTransition at 0x80eaba00). Leaving bit 0 of the timeline player
   + 0xf25 clear makes that caller take its own exit at 0x80eac5e0, which finishes the action node, instead of the
   exit at 0x80eac640 that leaves the timeline running. The skip query is answered yes only while one of these two
   requests is the current one, so the short edge runs and a title demo that uses the same query does not. The
   cutscene frame counter is not moved. mode 0 observes a request, 1 a timeline start (return 1: do not start it),
   2 the skip query (return 1: x0 is 1), 3 Link is updating and no event is playing (the opening has let him go). */
int hos_oot_opening(Ctx *c, int mode) {
    int rx_option(int id, int otherwise);
    static int armed;
    static char logged[64];
    char name[80];
    uint64_t p = 0;
    if (mode == 3) {
        armed = 0;
        logged[0] = 0;
        return 0;
    }
    if (!c || rx_option(HOS_OPT_SKIP_OPENING, 0) <= 0) {
        armed = 0;
        return 0;
    }
    name[0] = 0;
    if (mode == 0) {
        const uint64_t arg = c->x[1];
        p = arg ? recomp_load64(c, arg + 6800) : 0;
    } else if (mode == 1 && c->x[1]) {
        p = recomp_load64(c, c->x[1]);   /* EventTransition passes a pointer to the timeline's name */
    }
    if (p) {
        size_t i = 0;
        for (; i + 1 < sizeof name; i++) {
            name[i] = (char)recomp_load8(c, p + i);
            name[i + 1] = 0;
            if (!name[i]) break;
        }
    }
    if (mode == 0) {
        if (!strcmp(name, "Opening_Introduction") || !strcmp(name, "Opening_LoadingKokiriForest")) {
            armed = 1;
            if (strcmp(logged, name)) {
                size_t i = 0;
                for (; name[i] && i + 1 < sizeof logged; i++) logged[i] = name[i];
                logged[i] = 0;
                hos_log("opening skip: %s request sent", name);
            }
        } else if (name[0]) {
            /* a different event (Meet_DekuTree included) is not skipped and drops the arm */
            armed = 0;
            logged[0] = 0;
        }
        return 0;   /* the request is still sent */
    }
    if (!armed) return 0;
    if (mode == 2) {
        c->x[0] = 1;
        return 1;
    }
    if (mode == 1 && (!strcmp(name, "Dm_Kokiri_0000") || !strcmp(name, "Dm_Kokiri_0030"))) {
        const uint64_t player = c->x[0];
        if (player) recomp_store8(c, player + 0xf25, recomp_load8(c, player + 0xf25) & ~(uint64_t)1);
        return 1;
    }
    return 0;
}

void hos_oot_lift_player(Ctx *c, uint64_t actor) {
#if defined(_WIN32) || defined(__linux__)   /* (the debug tools: host/posix has what they call) */
    flight_pose_actor = 0;
    if (recomp_load64(c, actor) != 0x84b45e18ULL) return;
    const uint64_t components = recomp_load64(c, actor + 624);
    const uint64_t movement = components ? recomp_load64(c, components + 800) : 0;
    if (movement < HOS_HEAP_BASE + 0x1d50 || recomp_load64(c, movement + 24) != actor ||
        !hos_oot_is_player(c, movement - 0x1d50)) return;
    if (!oot_event_playing(c)) hos_oot_opening(c, 3);   /* the opening has let Link go: later events keep their own skip */
    void hos_oot_note_link(uint64_t components);   /* host/oot_high_fps.c: his driven body's target above 60 fps (here, in the
                                                     debug tools' block, as the player's other hooks: built on both) */
    hos_oot_note_link(components);
    {   /* (Item buttons, host/oot_wheel.c: what Link has in his hand. His item record is at his components' +0x358, +0x7c0
           (f_827ff39c reads it so); its +0x18 the item in hand, -1 none (f_83034d30), its +0x110 his actor) */
        int hos_oot_slots_link(int hand, int forced);   /* (its +0x1c: an item forced on him, used in place of ZR's) */
        const uint64_t record = recomp_load64(c, components + 0x358);
        if (record >= HOS_HEAP_BASE && hos_guest_range(record + 0x7c0, 0x118) && recomp_load64(c, record + 0x7c0 + 0x110) == actor) {
            const int hand = (int32_t)recomp_load32(c, record + 0x7c0 + 0x18);
            const int force = hos_oot_slots_link(hand >= 0 && hand < 64 ? hand : -1, (int32_t)recomp_load32(c, record + 0x7c0 + 0x1c));
            if (force >= -1) recomp_store32(c, record + 0x7c0 + 0x1c, (uint32_t)force);
        }
    }

    // Link can be updated by different guest workers on successive frames.
    static SRWLOCK cheats_lock = SRWLOCK_INIT;
    if (!TryAcquireSRWLockExclusive(&cheats_lock)) return;
    oot_update_player_cheats(c, actor, components);
    void hos_oot_state_tap(uint64_t actor);   /* the control bridge's copied snapshot and per-connection samples */
    hos_oot_state_tap(actor);
    ReleaseSRWLockExclusive(&cheats_lock);
#else
    (void)c;
    (void)actor;
#endif
}

#if defined(_WIN32) || defined(__linux__)   /* (the debug tools: host/posix has what they call) */
static void oot_build_free_view(Ctx *c, uint64_t view, uint64_t out) {
    int rx_option(int id, int otherwise);
    static uint64_t active_view;
    static int64_t last_tick;
    static double eye[3], yaw, pitch;
    const int64_t now = hos_now_ns();
    const int64_t elapsed = now - last_tick;

    if (!view) {
        active_view = 0;
        return;
    }
    if (active_view != view || elapsed > 500000000) {
        double target[3];
        memcpy(eye, A64_PTR(view + 96), sizeof eye);
        memcpy(target, A64_PTR(view + 120), sizeof target);
        const double x = eye[0] - target[0], y = eye[1] - target[1], z = eye[2] - target[2];
        yaw = atan2(x, z);
        pitch = atan2(y, hypot(x, z));
        active_view = view;
        hos_log("cheats: free camera at %.2f %.2f %.2f", eye[0], eye[1], eye[2]);
    }
    last_tick = now;
    DWORD foreground = 0;
    GetWindowThreadProcessId(GetForegroundWindow(), &foreground);
    const double dt = elapsed > 0 && elapsed < 100000000 ? (double)elapsed * 1e-9 : 0;
    const int control = foreground == GetCurrentProcessId() && !rx_option(1, 0);
    int height = 0;
    uint64_t hos_free_camera_input(int *height);
    const uint64_t input = control ? hos_free_camera_input(&height) : 0;
    if (control) {
        yaw -= 1.6 * dt * (int16_t)(input >> 32) / 32767.0;
        pitch -= 1.2 * dt * (int16_t)(input >> 48) / 32767.0;
        pitch = fmax(-1.55, fmin(1.55, pitch));
    }
    const double sy = sin(yaw), cy = cos(yaw), sp = sin(pitch), cp = cos(pitch);
    const double axes[3][3] = {{cy, 0, -sy}, {-sp * sy, cp, -sp * cy}, {cp * sy, sp, cp * cy}};
    if (control) {
        const double step = dt * (GetAsyncKeyState(VK_CONTROL) < 0 ? 30.0 : 8.0);
        const double right = (int16_t)input / 32767.0;
        const double forward = (int16_t)(input >> 16) / 32767.0;
        const int key_height = (GetAsyncKeyState(VK_PRIOR) < 0) - (GetAsyncKeyState(VK_NEXT) < 0);
        eye[1] += step * (key_height ? key_height : height);
        for (int i = 0; i < 3; i++)
            eye[i] += step * (right * axes[0][i] - forward * axes[2][i]);
    }
    for (int row = 0; row < 3; row++) {
        const double *axis = axes[row];
        const float values[4] = {(float)axis[0], (float)axis[1], (float)axis[2],
            (float)-(axis[0] * eye[0] + axis[1] * eye[1] + axis[2] * eye[2])};
        for (int col = 0; col < 4; col++) {
            uint32_t bits;
            memcpy(&bits, &values[col], sizeof bits);
            recomp_store32(c, out + (row * 4 + col) * 4, bits);
        }
    }
}
#endif

/* The Health bars row (asked 2026-11-23): the enemies hit lately, OOT_HEALTH_SLOTS of them (oot_health_hit, from hos_oot_hit),
   each with its life's address (the life component's, as the hit's write had it), the most life seen (the life before its
   first hit: its whole life, as a boss is first hit at full), its boss's place in OOT_BOSSES, and when it was last hit. Each
   gameplay frame (oot_health_tick, from hos_oot_free_view) a slot sends where its bar goes, its life and its kind; it is
   let go when the life is 0, the actor is no longer the same (its vtable and resource record changed: gone from the map),
   or OOT_HEALTH_KEEP_NS passed since its last hit (a boss's is kept while it lives). */
#define OOT_HEALTH_KEEP_NS 8000000000LL
#define OOT_HEALTH_ABOVE 1.0f
static const char *const oot_boss_actors[] = {
#define OOT_BOSS_ACTOR(actor, name) actor,
    OOT_BOSSES(OOT_BOSS_ACTOR)
#undef OOT_BOSS_ACTOR
};
static struct { uint64_t actor, vtable, resource, life; uint32_t max; int boss; int64_t hit_ns; } oot_health[OOT_HEALTH_SLOTS];
static int oot_health_sent[OOT_HEALTH_SLOTS];   /* (a slot the renderer was told is in use) */

static void oot_health_hit(Ctx *c, uint64_t actor, uint64_t life, uint32_t old, uint32_t next, const char *name) {
    if (!life) return;
    int k = 0;
    for (; k < OOT_HEALTH_SLOTS && oot_health[k].actor != actor; k++) {}
    if (k == OOT_HEALTH_SLOTS) {   /* (a new one: a free slot, else the one hit longest ago) */
        k = 0;
        for (int i = 0; i < OOT_HEALTH_SLOTS; i++) {
            if (!oot_health[i].actor) { k = i; break; }
            if (oot_health[i].hit_ns < oot_health[k].hit_ns) k = i;
        }
        oot_health[k].actor = actor, oot_health[k].vtable = recomp_load64(c, actor), oot_health[k].resource = recomp_load64(c, actor + 16);
        oot_health[k].max = 0, oot_health[k].boss = 0;
        for (int b = 0; b < (int)(sizeof oot_boss_actors / sizeof oot_boss_actors[0]); b++)
            if (!strcmp(name, oot_boss_actors[b])) oot_health[k].boss = b + 1;
    }
    oot_health[k].life = life;
    if (old > oot_health[k].max) oot_health[k].max = old;
    oot_health[k].hit_ns = hos_now_ns();
    (void)next;
}

static void oot_health_tick(Ctx *c) {
    void rx_option_set(int id, int value);
    const int64_t now = hos_now_ns();
    for (int k = 0; k < OOT_HEALTH_SLOTS; k++) {
        const uint64_t actor = oot_health[k].actor;
        uint32_t life = 0;
        if (actor && recomp_load64(c, actor) == oot_health[k].vtable && recomp_load64(c, actor + 16) == oot_health[k].resource)
            life = recomp_load32(c, oot_health[k].life);
        if (actor && (!life || life > 0xffff || (!oot_health[k].boss && now - oot_health[k].hit_ns > OOT_HEALTH_KEEP_NS))) {
            memset(&oot_health[k], 0, sizeof oot_health[k]);
            life = 0;
        }
        if (!oot_health[k].actor) {
            if (oot_health_sent[k]) rx_option_set(OOT_HEALTH_LIFE + k, 0), oot_health_sent[k] = 0;
            continue;
        }
        if (life > oot_health[k].max) oot_health[k].max = life;   /* (healed past what was seen: the most is the most) */
        float place[3];
        const uint64_t body = recomp_load64(c, actor + 0x18);
        for (int i = 0; i < 3; i++) place[i] = body ? oot_load_float(c, body + 0x31c + 4 * i) : 0;
        place[1] += OOT_HEALTH_ABOVE;
        rx_option_set(OOT_HEALTH_AT + k, body ? oot_damage_screen(c, place) : -1);
        rx_option_set(OOT_HEALTH_KIND + k, oot_health[k].boss);
        rx_option_set(OOT_HEALTH_LIFE + k, (int)(life | (oot_health[k].max > 0x7fff ? 0x7fff : oot_health[k].max) << 16));
        oot_health_sent[k] = 1;
    }
}

void hos_oot_free_view(Ctx *c, uint64_t view) {
#if defined(_WIN32) || defined(__linux__)   /* (the debug tools: host/posix has what they call) */
    int rx_option(int id, int otherwise);
    if (!view || recomp_load64(c, view) != 0x84c18a88ULL) return;

    // Camera zero supplies the gameplay view. The same matrix routine also serves other cameras.
    if (oot_gameplay_view(c) != view) return;
    oot_skip_cutscene(c);   /* (the randomizer's fork: Skip cutscenes, also while Link isn't updated) */
    oot_health_tick(c);   /* (the Health bars row: the enemies hit lately, each frame) */

    static SRWLOCK lock = SRWLOCK_INIT;
    AcquireSRWLockExclusive(&lock);
    const int enabled = rx_option(HOS_OPT_CHEAT_CAMERA, 0);
    oot_build_free_view(c, enabled ? view : 0, view + 8);
    ReleaseSRWLockExclusive(&lock);
#else
    (void)c;
    (void)view;
#endif
}

float hos_aspect_ratio = 0;   /* (the window's default shape: host/display.c) */
/* (nx2/oot_wide.py) read by the widescreen patches in the game's code; 0: the game's own 16:9 */
volatile uint64_t hos_wide_out, hos_wide_scene;
volatile float hos_wide_ratio, hos_wide_squeeze, hos_wide_margin;
volatile uint32_t hos_wide_keep_mask = 0xf;   /* (nx2/oot_wide.py KEEP_VTABLES: the screens that keep the whole picture, a bit each; MkwVkHost.wide_menus) */
/* (issues 1241, 2838) Swap can keep a small Linux PC from running out of backing storage without keeping it responsive.
   Warn below the existing 10 GiB floor in physical RAM there too; this is not a promise that 10 GiB is enough.
   The game starts anyway, and headless runs only log the warning. Windows keeps its commit-limit check. */
#define HOS_MEMORY_NEEDED_MB 10240ull
static int memory_notice_text(unsigned long long ram_mb, unsigned long long swap_mb, char *out, size_t cap) {
#if defined(__linux__) && !defined(_WIN32)
    if (ram_mb < HOS_MEMORY_NEEDED_MB) {
        snprintf(out, cap,
                 "This PC has %.1f GiB of RAM and %.1f GiB of swap. Hookshot recommends 16 GB of RAM or more; "
                 "the game alone can use more than 13 GiB.\n\n"
                 "Swap can prevent an out-of-memory exit, but heavy swapping can make the game and desktop unresponsive. "
                 "Close other programs before playing. More swap is not a replacement for RAM. The game starts anyway.",
                 ram_mb / 1024.0, swap_mb / 1024.0);
        return 1;
    }
#endif
    if (ram_mb + swap_mb >= HOS_MEMORY_NEEDED_MB) return 0;
    snprintf(out, cap,
             "This PC has %.1f GB of memory and %.1f GB of swap (the page file on Windows). The game needs about %llu GB of the "
             "two together; with less it can close by itself while it loads.\n\nClose other programs, or add swap (on Windows: "
             "let it manage the page file's size), then start the game again. It starts now anyway.",
             ram_mb / 1024.0, swap_mb / 1024.0, HOS_MEMORY_NEEDED_MB / 1024);
    return 1;
}
#ifndef A64_MEM_ZERO
static void memory_notice(void) {
    unsigned long long ram = 0, swap = 0;   /* (MB) */
#ifdef _WIN32
    MEMORYSTATUSEX m = {sizeof m};
    if (!GlobalMemoryStatusEx(&m)) return;
    ram = m.ullTotalPhys >> 20;
    swap = m.ullTotalPageFile > m.ullTotalPhys ? (m.ullTotalPageFile - m.ullTotalPhys) >> 20 : 0;   /* (the commit limit: RAM and page file) */
#elif defined(__linux__)
    struct sysinfo si;
    if (sysinfo(&si)) return;
    ram = ((unsigned long long)si.totalram * si.mem_unit) >> 20, swap = ((unsigned long long)si.totalswap * si.mem_unit) >> 20;
#else
    return;
#endif
#ifdef _WIN32
    /* (Triforce v0.8.4) the last run ran out of memory (mkw_glue.c oom_mark): said now, once, before play, with this PC's RAM
       and page file. The mark is removed when said (a run without a window leaves it for the player's next start) */
    {
        char mark[MAX_PATH];
        const DWORD len = hos_game_path_a(mark, MAX_PATH);
        char *slash = len ? strrchr(mark, '\\') : NULL;
        if (slash) {
            snprintf(slash + 1, (size_t)(mark + MAX_PATH - slash - 1), "%s", HOS_OOM_MARK);
            FILE *f = fopen(mark, "r");
            if (f) {
                fclose(f);
                hos_log("boot: the last run ran out of memory (%llu MB of memory, %llu MB of page file): said once now (%s)", ram, swap, mark);
                if (!env_on("HOS_HEADLESS")) {
                    char said[900];
                    snprintf(said, sizeof said,
                             "The last time the game ran, Windows ran out of memory for it: this PC's RAM (%.1f GB) and page file "
                             "(%.1f GB) were full. That is what closed or froze the game.\n\nTo fix it, let Windows size the page "
                             "file: search \"Adjust the appearance and performance of Windows\", Advanced tab, Virtual memory: "
                             "Change, tick \"Automatically manage paging file size for all drives\", OK, then restart the PC. "
                             "Closing other programs while playing helps too.",
                             ram / 1024.0, swap / 1024.0);
                    MessageBoxA(NULL, said, "Hookshot: out of memory last time", MB_OK | MB_ICONWARNING);
                    remove(mark);
                }
            }
        }
    }
#endif
    char text[512];
    if (!memory_notice_text(ram, swap, text, sizeof text)) {
        hos_log("boot: %llu MB of memory, %llu MB of swap", ram, swap);
        return;
    }
#if defined(__linux__) && !defined(_WIN32)
    hos_log("boot: LOW MEMORY: %llu MB of memory, %llu MB of swap; below %llu MB of physical RAM: heavy swapping can make "
            "the game and desktop unresponsive (16 GB RAM or more recommended)", ram, swap, HOS_MEMORY_NEEDED_MB);
#else
    hos_log("boot: LOW MEMORY: %llu MB of memory, %llu MB of swap, below the ~%llu MB the game needs", ram, swap, HOS_MEMORY_NEEDED_MB);
#endif
    if (env_on("HOS_HEADLESS")) return;
#ifndef _WIN32
    int hos_sdl_load(void);
    hos_sdl_load();   /* (host/posix MessageBoxA shows it through the SDL already loaded) */
#endif
    MessageBoxA(NULL, text, "Hookshot", MB_OK | MB_ICONWARNING);
}
#endif
/* (hookshot, linux) What driver_env_choose did with the driver's environment, said again in the game's own log once it is open
   (it runs before, when stderr is still the launcher's) */
static char driver_env_said[1024];
static void driver_env_log(void) {
    if (driver_env_said[0]) hos_log("%s", driver_env_said);
}
#ifdef _WIN32
/* (hookshot) On laptops with two GPUs, the drivers run a program on the dedicated one when it exports these (NVIDIA Optimus, AMD
   PowerXpress): without them a laptop could put the game on its integrated GPU, 5 fps (issue 176) */
__declspec(dllexport) unsigned long NvOptimusEnablement = 1;
__declspec(dllexport) int AmdPowerXpressRequestHighPerformance = 1;

/* (hookshot) The game's paths are UTF-8 char strings through Windows' A functions and fopen: its manifest (nx2/win_manifest.py)
   makes the process's code page UTF-8, from Windows 10 1903 on. Before that, or with the manifest missing, those take the system's
   ANSI code page, and a folder name it cannot spell (Japanese on a Western Windows, an emoji) comes back as "?": nothing opens and
   the game closed with no window and no log. The exe's own path through GetModuleFileNameA must name the exe (a name past MAX_PATH
   bytes fails the same way); when it does not, a message says why (none for the builder's --prepare-shaders run: its log has it). */
static int narrow_paths_ok(int argc, char **argv) {
    char a[MAX_PATH];
    const DWORD n = GetModuleFileNameA(NULL, a, MAX_PATH);
    if (n && n < MAX_PATH && GetFileAttributesA(a) != INVALID_FILE_ATTRIBUTES) return 1;
    wchar_t w[MAX_PATH * 2] = L"";
    GetModuleFileNameW(NULL, w, MAX_PATH * 2);
    fprintf(stderr, "hookshot: this folder's path cannot be opened (code page %u, %s): move the game to a folder with a plain name\n",
            GetACP(), n >= MAX_PATH ? "too long" : "has characters the code page lacks");
    int quiet = env_on("HOS_HEADLESS");
    for (int i = 1; i < argc; i++) quiet |= !strcmp(argv[i], "--prepare-shaders");
    if (!quiet) {
        wchar_t text[MAX_PATH * 2 + 640];
        _snwprintf(text, sizeof text / sizeof text[0],
                   L"Hookshot can't open its files in this folder:\n\n%ls\n\n"
                   L"%ls\n\nMove the game folder somewhere with a shorter name of plain letters and digits (for example C:\\Games\\Hookshot), "
                   L"or update Windows.",
                   w, GetACP() == CP_UTF8 ? L"The path is too long."
                                          : L"Its name has characters this Windows can only give the game from Windows 10 version 1903 on.");
        text[sizeof text / sizeof text[0] - 1] = 0;
        MessageBoxW(NULL, text, L"Hookshot", MB_OK | MB_ICONERROR | MB_SETFOREGROUND);
    }
    return 0;
}

int main(int argc, char **argv) {
#else
static int game_main(int argc, char **argv) {
#endif
#ifdef _WIN32
    {   /* (hookshot) the crash window's helper of this run (host/hos_crash_dialog.c): first, so it starts nothing of the game */
        int hos_crash_helper_main(int argc, char **argv);
        const int helper = hos_crash_helper_main(argc, argv);
        if (helper >= 0) return helper;
    }
    if (!narrow_paths_ok(argc, argv)) return 1;
    hos_game_layout();   /* (the game folder's cache/ and logs/, before anything writes there: host/game_layout.c) */
    {
        void hos_relaunch_keep_env(void);   /* (host/hos_relaunch.c: the environment before the file's lines, for a restart) */
        hos_relaunch_keep_env();
    }
    load_hookshot_env();
    hos_profiling_env();   /* (HOS_PROFILE=1, host/profiling.c: after the file, which may set it) */
#endif
    /* (the settings file, in the user folder: chosen before the crash window's helper, the Discord status and the renderer read
       it, and after hookshot_env.txt, which may set HOS_OPTIONS_FILE; Linux's main chose it already: host/options_path.c) */
    hos_options_choose(argc, argv);
    {   /* (the heap retry's test switches, read once before the game's threads: host/oot_heap_retry.c) */
        void hos_oot_heap_test_init(void);
        hos_oot_heap_test_init();
    }
    {
        const char *protect_hearts = getenv("HOS_OOT_PROTECT_HEARTS");
        hos_oot_protect_hearts = protect_hearts && !strcmp(protect_hearts, "1");
    }
#ifdef _WIN32
    {   // (the whole process, not only the window's thread: the renderer asks the window's size from its own, and on a 4K screen at 150%
        // Windows answered such a thread 2560 x 1440: the picture was that size, in the corner of the window. Hookshot issues 15, 18, 20)
        typedef BOOL(WINAPI * SetAware)(void *);
        SetAware set = (SetAware)(void *)GetProcAddress(GetModuleHandleA("user32.dll"), "SetProcessDpiAwarenessContext");
        if (set && !env_on("HOS_DPI_UNAWARE")) set((void *)(intptr_t)-4);
    }
#endif
    void hos_crash_record_prepare(const char *log_path);
    int hos_log_redact_file(const char *path, const char *run_id);   /* (host/log_redact.h) */
    {   // (started from its icon the game has nowhere to log to: hookshot_log.txt in the game folder's logs/ (host/game_layout.c), for players to send in)
#ifdef _WIN32
        {   /* (started again by the Insert menu's Restart now (host/hos_relaunch.c): the run before still has its log open until
               it exits, so wait for it (up to 10 s) before the log moves to .1, or the move fails and its log is overwritten) */
            const char *of = getenv("HOS_RESTART_OF");
            if (of && *of) {
                HANDLE before = OpenProcess(SYNCHRONIZE, FALSE, (DWORD)strtoul(of, NULL, 10));
                if (before) WaitForSingleObject(before, 10000), CloseHandle(before);
                SetEnvironmentVariableA("HOS_RESTART_OF", NULL);   /* (not passed on: a later restart sets its own) */
                _putenv("HOS_RESTART_OF=");
            }
        }
#endif
        HANDLE err = GetStdHandle(STD_ERROR_HANDLE);
        if (!err || err == INVALID_HANDLE_VALUE || GetFileType(err) == FILE_TYPE_UNKNOWN) {
            char path[MAX_PATH + 32];
            DWORD n = hos_game_path_a(path, MAX_PATH);
            while (n && path[n - 1] != 92 && path[n - 1] != 47) n--;
            if (n && n + 5 < MAX_PATH) {   /* (its logs/, which hos_game_layout made; else beside the game, as before) */
                memcpy(path + n, "logs", 5);
                if (GetFileAttributesA(path) != INVALID_FILE_ATTRIBUTES) path[n + 4] = path[n - 1], n += 5;
            }
            memcpy(path + n, "hookshot_log.txt", 17);
            hos_crash_record_prepare(path);   /* recovery before rotation; keep this run's actual destination */
            /* (the four runs before stay as hookshot_log.1.txt (the last) to .4.txt: a player who started the game again after a
               crash sent in the new run's log, and the crash was gone) */
            char from[MAX_PATH + 32], to[MAX_PATH + 32];
            for (int k = 4; k >= 1; k--) {
                if (k == 1) memcpy(from + n, "hookshot_log.txt", 17), memcpy(from, path, n);
                else memcpy(from, path, n), snprintf(from + n, 32, "hookshot_log.%d.txt", k - 1);
                memcpy(to, path, n), snprintf(to + n, 32, "hookshot_log.%d.txt", k);
                MoveFileExA(from, to, MOVEFILE_REPLACE_EXISTING);
            }
            /* (hookshot) the run before's log without the player's user name: its own lines were written so, and what wrote to
               stderr itself (the Vulkan loader, SDL) is redacted here when its crash watch did not (host/log_redact.h) */
            hos_log_redact_file(to, NULL);
#if !defined(_WIN32) && !defined(A64_MEM_ZERO)
            startup_stderr = fcntl(STDERR_FILENO, F_DUPFD_CLOEXEC, 0);
#endif
            /* (opened first: freopen closes stderr when it cannot open the file, and the next file opened would take its
               descriptor. A log that cannot be written leaves the stderr the game was started with) */
            FILE *log = fopen(path, "w");
            if (log) {
                fclose(log);
                if (freopen(path, "w", stderr)) setvbuf(stderr, NULL, _IONBF, 0);
            }
        } else hos_crash_record_prepare(NULL);   /* an externally supplied stderr, not the game's log */
    }
    hos_log("hookshot %s", HOOKSHOT_VERSION);   /* (the log's first line: which build a report comes from) */
    const char *hos_report_run_id(void);
    hos_log("run_id: %s", hos_report_run_id());
    hos_game_layout_log();
    driver_env_log();
    void hos_crash_record_log_notes(void);
    hos_crash_record_log_notes();
    removed_switch_notes();
    void hos_control_start(const char *version);
    hos_control_start(HOOKSHOT_VERSION);   /* (HOS_CONTROL=<socket>: the control bridge, host/control.c) */
    /* (hookshot) the window after a crash: a helper that waits for this run to end (host/hos_crash_dialog.c), started before
       the guest, the renderer, the sound and the input; none for --prepare-shaders, HOS_HEADLESS or HOS_CRASH_WATCH=0 */
    void hos_crash_watch_start(int argc, char **argv);
    hos_crash_watch_start(argc, argv);
    const char *image = NULL;
    /* (hookshot) --compile-shaders all or most: what a preparation of this run builds (gpu/vk/vk_draw.cpp compile_all), over
       compile_shaders= in hookshot_options.ini; as RX_VK_COMPILE_SHADERS, set before --prepare-shaders runs, wherever it stands */
    for (int i = 1; i + 1 < argc; i++)
        if (!strcmp(argv[i], "--compile-shaders")) {
#ifdef _WIN32
            char set[64];
            snprintf(set, sizeof set, "RX_VK_COMPILE_SHADERS=%s", argv[i + 1]);
            _putenv(set);
#else
            setenv("RX_VK_COMPILE_SHADERS", argv[i + 1], 1);
#endif
        }
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--romfs") && i + 1 < argc) hos_romfs_dir = argv[++i];
        else if (!strcmp(argv[i], "--compile-shaders") && i + 1 < argc) i++;   /* (taken above) */
        else if (!strcmp(argv[i], "--user") && i + 1 < argc) hos_user_dir = argv[++i];
        else if (!strcmp(argv[i], "--trace")) hos_trace = 1;
        else if (!strcmp(argv[i], "--prepare-shaders")) {   /* (hookshot) a build's last step: no game */
#ifdef _WIN32
            _putenv("HOOKSHOT_PREPARE_ONLY=1");
#else
            setenv("HOOKSHOT_PREPARE_ONLY", "1", 1);
#endif
            int rx_prepare_shaders(void);
            if (rx_prepare_shaders()) {
                printf("@@done shaders\n");
                return 0;
            }
            printf("@@error no usable Vulkan here: the game prepares its shaders at its first start\n");
            return 3;
        }
        else if (!image) image = argv[i];
    }
#ifdef _WIN32
    {   /* (hookshot) the Discord status (discord_rpc.c), a game run only (a --prepare-shaders run returned above). Linux starts
           it in its own main, below; on Windows it was never started: no status and no "discord:" line in any log */
        void hos_discord_start(void);
        hos_discord_start();
    }
#endif
    static char beside_image[MAX_PATH], beside_romfs[MAX_PATH], beside_user[MAX_PATH];
    if (!image) {   /* (hookshot) started with nothing, as a game is: everything beside the executable (the builder's folder) */
        char dir[MAX_PATH];
        const DWORD len = hos_game_path_a(dir, MAX_PATH);
        char *slash = len ? strrchr(dir, SEP) : NULL;
        if (slash) {
            *slash = 0;
            SetCurrentDirectoryA(dir);
            snprintf(beside_image, MAX_PATH, "%s" SEP_S "image.bin", dir);
            snprintf(beside_romfs, MAX_PATH, "%s" SEP_S "romfs", dir);
            snprintf(beside_user, MAX_PATH, "%s" SEP_S "user", dir);
            if (GetFileAttributesA(beside_image) != INVALID_FILE_ATTRIBUTES) {
                image = beside_image;
                if (!hos_romfs_dir) hos_romfs_dir = beside_romfs;
#ifndef _WIN32
                if (!hos_user_dir) hos_user_dir = saves_dir(beside_user);
#else
                if (!hos_user_dir) hos_user_dir = beside_user;
#endif
            }
        }
    }
    if (!image) {
        fprintf(stderr, "usage: %s [image.bin] [--romfs <dir>] [--user <dir>] [--trace] [--prepare-shaders] [--compile-shaders all|most]\n",
                argv[0]);
        return 2;
    }
    if (env_on("HOS_TRACE")) hos_trace = 1;
    if (env_on("HOS_HLE_STATS")) {
        void hos_hle_stats_start(void);
        hos_hle_stats_start();
    }
    if (!hos_user_dir) hos_user_dir = "user";
    recover_writes();   /* (what a write of a setting that a kill cut left: before anything reads the settings) */
    CreateDirectoryA(hos_user_dir, NULL);
#ifdef _WIN32
    if (beside_user[0] && hos_user_dir == beside_user && !env_on("HOS_NO_SAVE_FOLDER")) {   /* (sharkiix version) */
        char game_dir[MAX_PATH];
        snprintf(game_dir, sizeof game_dir, "%s", beside_user);
        char *slash = strrchr(game_dir, SEP);
        if (slash) *slash = 0, save_folder_import(game_dir, hos_user_dir);
    }
#endif
    hos_options_carry();   /* (a game folder's settings from before into the user folder, once: host/options_path.c) */
    if (!reserve_guest()) {
        fprintf(stderr, "cannot reserve the guest window\n");
        return 1;
    }
    void hos_crash_test_arm(void);
    hos_crash_test_arm();   /* (HOS_CRASH_TEST: a crash on purpose, once the crash handlers are set up: host/hos_crash_dialog.c) */
#ifdef A64_MEM_ZERO
    web_fs_init(NULL, hos_romfs_dir);
    /* (the whole file, no range: the server sends it brotli-compressed, 85 -> 26 MB) */
    const int got = web_fetch_all(image, A64_MEM + IMAGE_BASE, GUEST_SPACE - IMAGE_BASE);
    if (got < 0) {
        fprintf(stderr, "cannot fetch %s\n", image);
        return 1;
    }
    size_t n = (size_t)got;
#else
    FILE *f = fopen(image, "rb");
    if (!f) {
        fprintf(stderr, "cannot open %s\n", image);
        return 1;
    }
    /* exactly the file's size: a read into "the rest of the guest window" (~4 GB) made Windows commit physical memory
       for ~2 GB of it before the game ran (the whole heap was resident from the start, ~1.3 GB of it never used) */
    fseek(f, 0, SEEK_END);
    const long long file_size = _ftelli64(f);
    fseek(f, 0, SEEK_SET);
    if (file_size > 0) hos_commit(IMAGE_BASE, (uint64_t)file_size);
    size_t n = file_size > 0 && (uint64_t)file_size <= GUEST_SPACE - IMAGE_BASE
                   ? fread(A64_MEM + IMAGE_BASE, 1, (size_t)file_size, f) : 0;
    fclose(f);
#endif
    if (IMAGE_BASE + n != hos_image_end) {
        fprintf(stderr, "%s: %zu bytes, the lifted code expects %#llx: lift and image do not match\n", image, n,
                (unsigned long long)(hos_image_end - IMAGE_BASE));
        return 1;
    }
    hos_mem_init(hos_image_end);
    {   /* (hookshot) Widescreen and ultrawide (nx2/oot_wide.py): HOS_ASPECT=<ratio> (2.3889 for 3440x1440), else the Insert menu's
           Aspect ratio (on unless it says 0) takes the main monitor's shape. The game's picture takes that shape at its own height (the
           world wider at the sides on an ultrawide screen, narrower on a 16:10 or 4:3 one), its 16:9 cameras the picture's ratio.
           An output that is not 16:9 takes precedence over both HOS_ASPECT and the Aspect ratio, matching the menu's picture. Wider
           than 16:9 the HUD, menus and movies keep the middle 16:9; narrower they fill the picture's width. Until now the one 16:9
           constant in the game's data was changed and the 16:9 picture stretched to the window. */
        const char *e = getenv("HOS_ASPECT");
        float want = e ? (float)atof(e) : 0.0f;
        if (!e) {
            int saved = -1, version = 0;   /* (the Aspect ratio's ultrawide= and options_version=, -1 / 0 without them) */
            FILE *o = fopen(hos_options_file(), "r");
            if (o) {
                char line[80];
                while (fgets(line, sizeof line, o)) {
                    if (!strncmp(line, "ultrawide=", 10)) saved = atoi(line + 10) != 0;
                    if (!strncmp(line, "options_version=", 16)) version = atoi(line + 16);
                }
                fclose(o);
            }
            void hos_monitor_prepare(void);
            int hos_monitor_screen_size(int *,int *);
            hos_monitor_prepare();
            int sw=0,sh=0;
            if (!hos_monitor_screen_size(&sw,&sh)) {
                sw=GetSystemMetrics(SM_CXSCREEN); sh=GetSystemMetrics(SM_CYSCREEN);
            }
            /* (no line: the monitor's shape; an older file's 16:9 on a screen narrower than 16:9 too: hos_aspect_on) */
            const int on = hos_aspect_on(saved, version, sw, sh);
            if (on && sh > 0) want = (float)sw / (float)sh;
        }
        extern volatile uint64_t hos_wide_out, hos_wide_scene;
        extern volatile float hos_wide_ratio, hos_wide_squeeze, hos_wide_margin;
        uint32_t hos_output_size(int height);
        const uint32_t output_w = hos_output_size(0), output_h = hos_output_size(1);
        /* An output of a shape of its own (the Insert menu's Aspect ratio: 21:9, 16:10, 4:3, a 32:9 surround...) asks for that
           shape, over HOS_ASPECT and Ultrawide, even if the OS reports one monitor (host/hos_wide_size.h) */
        if (hos_output_own_shape(output_w, output_h)) want = (float)output_w / (float)output_h;
        const double game = 16.0 / 9.0;
        /* (a screen narrower than 16:9 too, 16:10 to 5:4: the picture keeps the game's height and is narrower, the
           cameras take its ratio, and the HUD fills its width instead of a middle 16:9 wider than the screen. A 4:3 CRT
           at the 1440 output: picture 1920 x 1440, scene 1440 x 1080, HUD 100%) */
        if (want > game * 1.01 || (want > 1.0f && want < game * 0.99)) {
            const double r = hos_wide_clamp(want);
            /* (the height kept, the width at the screen's ratio, at most hos_wide_max_px() pixels (5120 x 2160's, a 21:9 screen's
               native at the 4K output) with the shape kept: host/hos_wide_size.h, which the Insert menu's Output and Render
               resolution rows share; issue 1031) */
            unsigned ow, oh;
            hos_wide_size(output_h, r, hos_wide_max_px(), &ow, &oh);
            const unsigned sh = oh * 3 / 4, sw = (unsigned)(ow * 0.75 / 8 + 0.5) * 8;   /* (the scene, 3/4 of the picture as shipped) */
            hos_wide_out = (uint64_t)oh << 32 | ow;
            hos_wide_scene = (uint64_t)sh << 32 | sw;
            hos_wide_ratio = (float)ow / (float)oh;
            hos_wide_squeeze = (float)fmin(1.0, game / ((double)ow / oh));   /* (a narrower screen: the whole width) */
            hos_wide_margin = (1.0f - hos_wide_squeeze) / 2.0f;
            hos_aspect_ratio = hos_wide_ratio;
            hos_log("boot: widescreen: picture %ux%u, scene %ux%u, camera ratio %.4f, HUD and movies in the middle %.1f%%", ow, oh, sw, sh,
                    (double)hos_wide_ratio, hos_wide_squeeze * 100.0);
        } else if (want > 1.0f) {
            hos_log("boot: widescreen: a %.4f screen is 16:9: the game's own picture", (double)want);
        }
    }
    hos_log("boot: image %zu MB at %#llx, %llu MB of memory for the game", n >> 20, IMAGE_BASE,
            (unsigned long long)(hos_total_memory >> 20));
#ifndef A64_MEM_ZERO
    memory_notice();
#endif
    void hos_mods_init(const char *image_path);
    hos_mods_init(image);   /* mods.c: <exe folder>\mods (RomFS files) */
    void hos_rando_init(void);
    hos_rando_init();   /* oot_rando.c: the launcher's Randomizer page's seed and settings */

    Ctx *c = hos_boot_main_thread(hos_main_stack_size);
    uint64_t sp = c->x[31];
    void hos_prof_start(void);
    hos_prof_start();   /* HOS_PROFILE_EVERY=<seconds>, the samplers, HOS_PROFILE=1 */
    void hos_chain_start(void);
    hos_chain_start();  /* HOS_CHAIN=<path> */
#ifdef _WIN32
    timeBeginPeriod(1);   /* 1 ms timer resolution: the 60 Hz vsync and the game's frame pacing sleep in short steps */
    no_power_throttling();
#endif
    void hos_display_start(void);
    hos_display_start();  /* the game's window; HOS_HEADLESS=1 for none */
    /* nn::init::Start's order (sdk+0xfa060), with rtld's three callbacks done here: f1 only marks rtld initialized,
       f2 is every module's DT_INIT, f3 the DT_FINIs (not needed: we never return from nnMain to unload). */
    call_guest(c, hos_entry_init_libc0, sp, "_init_libc0");
    c->x[0] = hos_thread_handle(hos_self());   /* the main thread's handle */
    c->x[1] = 0;                               /* program arguments: none (an unmapped address) */
    call_guest_args(c, hos_entry_nnosInitialize, sp, "nnosInitialize");
    void hos_thread_adopt_guest(HosThread *t);
    hos_thread_adopt_guest(hos_self());
    call_guest(c, hos_entry_init_libc1, sp, "_init_libc1");
    /* nninitInitializeSdkModule (sdk+0xfa000) only opens the SDK's service clients (sm:, diag, oe, aoc, err, fs,
       pctl) over IPC; the HLE stands in for every one of them, so it is not run. */
    call_guest(c, hos_entry_nninitStartup, sp, "nninitStartup");
    call_guest(c, hos_entry_init_libc2, sp, "_init_libc2");
    for (int i = 0; i < hos_module_count; i++) {
        char what[64];
        snprintf(what, sizeof what, "%s DT_INIT", hos_module_name[i]);
        call_guest(c, hos_module_init[i], sp, what);
    }
    call_guest(c, hos_entry_nnMain, sp, "nnMain");
    hos_log("nnMain returned");
    void hos_crash_clean_end(void);
    hos_crash_clean_end();
    return 0;
}

#ifndef _WIN32
/* (linux) The window belongs on the process's main thread (SDL), so the game runs on a thread of its own, with the
   stack the guest main thread's lifted code needs (the main thread has the system's 8 MB): host/posix/display_sdl.c */
static int game_argc;
static char **game_argv;
static DWORD WINAPI game_thread(void *p) {
    (void)p;
    const UINT result = (UINT)game_main(game_argc, game_argv);
    void hos_crash_clean_end(void);
    hos_crash_clean_end();
    ExitProcess(result);
}
/* (hookshot, linux) Room in the drivers' own shader caches for what the preparation builds. The pipelines the notes predict (~43,000
   in OoT, vk_draw.cpp predict_run) are built into the driver's disk cache alone, not into hookshot_vk_pipelines.bin, which is read in whole
   at every start. NVIDIA's cache holds 1 GiB by default and cleans itself down to that as it is written: a full preparation filled
   it to the limit (1026 MB) and the pipelines it dropped were compiled again in play. Mesa's (RADV, ANV) has the same 1 GiB default.
   Raised for this process only, before anything loads Vulkan; a value the player set (or hookshot_env.txt) is kept. Windows: the
   NVIDIA driver takes its size from the control panel's Shader Cache Size, which a program cannot set (readme) */
static void driver_cache_room(void) {
    setenv("__GL_SHADER_DISK_CACHE_SIZE", "10737418240", 0);   /* (10 GiB, bytes) */
    setenv("MESA_SHADER_CACHE_MAX_SIZE", "10G", 0);
}
#include <errno.h>
#include <sys/stat.h>
/* (hookshot, linux) NVIDIA's driver keeps no shader cache at all when __GL_SHADER_DISK_CACHE_PATH names a folder that does not exist:
   it neither creates it nor falls back to ~/.cache/nvidia, and every start compiles every pipeline again (a test of 300 pipelines:
   7.9 ms each at the first start and at the second, against 0.06 ms from the cache; driver 620.70). The folder a player or a
   launcher named is made here, before anything loads Vulkan. Mesa makes its own (MESA_SHADER_CACHE_DIR, parents too). Not needed:
   NVIDIA files the cache by the program's file name alone (bin/hookshot), not its folder, bytes or date, nor VkApplicationInfo, so
   an update in place, a folder moved or copied and every Hookshot folder on the PC share one cache (a cache of another driver or
   GPU is the driver's to drop) */
static void driver_cache_folder(void) {
    const char *dir = getenv("__GL_SHADER_DISK_CACHE_PATH");
    if (!dir || !*dir || strlen(dir) >= 4096) return;
    char path[4096];
    strcpy(path, dir);
    for (char *p = path + 1;; p++) {   /* (each parent, then the folder itself: mkdir -p) */
        const char c = *p;
        if (c != '/' && c) continue;
        *p = 0;
        if (mkdir(path, 0700) != 0 && errno != EEXIST) {
            fprintf(stderr, "vk: __GL_SHADER_DISK_CACHE_PATH %s: cannot make %s (%s): NVIDIA's driver keeps no shader cache\n", dir,
                    path, strerror(errno));
            return;
        }
        if (!c) {   /* (a file already at that name counts as made for mkdir, but the driver can't use it) */
            struct stat st;
            if (stat(path, &st) != 0 || !S_ISDIR(st.st_mode))
                fprintf(stderr, "vk: __GL_SHADER_DISK_CACHE_PATH %s: cannot make it, a file has that name: NVIDIA's driver keeps no shader cache\n", dir);
            return;
        }
        *p = '/';
    }
}
/* (hookshot, linux) RADV_FORCE_VRS_CONFIG_FILE dropped before anything loads Vulkan. The Steam Deck's Game Mode sets it for
   Steam and everything it starts, naming a file it writes the Half Rate Shading rate to (/tmp/radv_vrs.<random>, "1x1" when
   off). When that file exists, RADV forces VRS for the device and puts that into every graphics pipeline's key, so nothing
   built without it is found, in the driver's cache or in ours: measured on a Steam Deck OLED (RADV, Mesa 26.2.0-devel), the
   same install compiled its 32,438 noted pipelines at about 20 a second (25-30 minutes) with the variable naming a file, empty
   or "1x1", and loaded them in 22 s without it or with it naming no file. The preparation (the Builder, a first start from the
   desktop) runs without it, so every start from Game Mode compiled again what it built. Dropped only when it names a file that
   exists, which is when RADV reads it; no other driver reads it. RX_VK_HALF_RATE_SHADING=1 keeps it: Steam's Half Rate Shading
   works for Hookshot then (little: RADV leaves a fragment program that reads its position at full rate, and nearly all of
   ours do), and the starts in Game Mode compile their own pipelines. RADV_FORCE_VRS, a rate someone set by hand, is kept.
   The variable is named in HOOKSHOT_DRIVER_ENV_SET for the renderer's driver cache line. A restart (hos_relaunch.c) starts
   again from the first environment and drops it again */
static void driver_env_choose(void) {
    const char *file = getenv("RADV_FORCE_VRS_CONFIG_FILE");
    struct stat st;
    if (!file || !*file || stat(file, &st) != 0) return;
    const char *keep = getenv("RX_VK_HALF_RATE_SHADING");
    if (keep && !strcmp(keep, "1")) {
        snprintf(driver_env_said, sizeof driver_env_said,
                 "vk: RADV_FORCE_VRS_CONFIG_FILE kept (RX_VK_HALF_RATE_SHADING=1): Steam's Half Rate Shading reaches the game, "
                 "and RADV gives every graphics pipeline another key than the preparation's, so they are compiled again");
    } else {
        snprintf(driver_env_said, sizeof driver_env_said,
                 "vk: RADV_FORCE_VRS_CONFIG_FILE=%.300s dropped: with it RADV gives every graphics pipeline another key than the "
                 "preparation's and compiles them all again; Steam's Half Rate Shading has no effect on Hookshot "
                 "(RX_VK_HALF_RATE_SHADING=1 keeps it)", file);
        unsetenv("RADV_FORCE_VRS_CONFIG_FILE");
        setenv("HOOKSHOT_DRIVER_ENV_SET", "RADV_FORCE_VRS_CONFIG_FILE", 1);
    }
    fprintf(stderr, "%s\n", driver_env_said);
}
int main(int argc, char **argv) {
    {   /* (hookshot) the crash window's helper of this run (host/hos_crash_dialog.c): first, so it starts nothing of the game */
        int hos_crash_helper_main(int argc, char **argv);
        const int helper = hos_crash_helper_main(argc, argv);
        if (helper >= 0) return helper;
    }
    int hos_display_init(void);
    void hos_display_loop(void);
    hos_game_layout();   /* (the game folder's cache/ and logs/, before anything writes there, --prepare-shaders too: host/game_layout.c) */
    load_hookshot_env();
    hos_profiling_env();   /* (HOS_PROFILE=1, host/profiling.c: after the file, which may set it) */
    hos_options_choose(argc, argv);   /* (before the Discord status reads it, below: host/options_path.c) */
    driver_cache_room();
    driver_cache_folder();
    driver_env_choose();
    game_argc = argc, game_argv = argv;
    int prepare_shaders = 0;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--prepare-shaders")) prepare_shaders = 1;
        else if (!strcmp(argv[i], "--romfs") || !strcmp(argv[i], "--user") || !strcmp(argv[i], "--compile-shaders")) i++;
    }
    /* The builder's preparation worker needs Vulkan, but no SDL display. */
    const int window = prepare_shaders ? 0 : hos_display_init();
    if (window < 0) {
        hos_log_flush();
        return 1;
    }
    if (!prepare_shaders) {   /* (hookshot) the Discord status (discord_rpc.c): only a game run */
        void hos_discord_start(void);
        hos_discord_start();
    }
    HANDLE t = CreateThread(NULL, 64u << 20, game_thread, NULL, 0, NULL);
    if (!t) {
        fprintf(stderr, "cannot start the game's thread\n");
        return 1;
    }
    SetThreadDescription(t, L"Game");
    if (window) hos_display_loop();   /* (does not return: the window's events until the process ends) */
    WaitForSingleObject(t, INFINITE);
    return 0;
}
#endif
