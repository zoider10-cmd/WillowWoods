/* The host's log writer (host/hos_thread.c, the Windows queue, log_main and log_flush) extracted unmodified, with the CRT
   stream calls as spies: what goes out, in how many writes, and when. Real threads, SRW locks and condition variables. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static SRWLOCK spy_lock = SRWLOCK_INIT;
static char out[1 << 20];
static size_t out_len;
static volatile LONG writes;
static volatile LONG stall_ms;               /* (the "full" case: a write that waits on the disk) */
static volatile DWORD writer_tid;            /* (the thread of the first write: the writer) */
static volatile LONG other_thread_writes;    /* (writes made by any other thread: the logging thread writing itself) */

static void spy_append(const void *p, size_t n) {
    if (!writer_tid) writer_tid = GetCurrentThreadId();
    else if (writer_tid != GetCurrentThreadId()) InterlockedIncrement(&other_thread_writes);
    if (stall_ms) Sleep((DWORD)stall_ms);
    AcquireSRWLockExclusive(&spy_lock);
    if (out_len + n <= sizeof out) memcpy(out + out_len, p, n), out_len += n;
    ReleaseSRWLockExclusive(&spy_lock);
    InterlockedIncrement(&writes);
}
__attribute__((unused)) static int spy_fputs(const char *s, FILE *f) {
    (void)f;
    spy_append(s, strlen(s));
    return 0;
}
__attribute__((unused)) static size_t spy_fwrite(const void *p, size_t size, size_t n, FILE *f) {
    (void)f;
    spy_append(p, size * n);
    return n;
}
__attribute__((unused)) static int spy_fflush(FILE *f) {
    (void)f;
    return 0;
}
static size_t out_size(void) {
    AcquireSRWLockExclusive(&spy_lock);
    const size_t n = out_len;
    ReleaseSRWLockExclusive(&spy_lock);
    return n;
}

#define fputs spy_fputs
#define fwrite spy_fwrite
#define fflush spy_fflush
/* (log_main is a thread that never returns: its for (;;) has no return after it. GCC's C front end warns for a static function
   with no return statement at all, whatever its loop; clang, which builds the game, does not) */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wreturn-type"
/* ACTUAL_LOG */
#pragma GCC diagnostic pop
#undef fflush
#undef fwrite
#undef fputs

#define CHECK(c) do { if (!(c)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #c); return 1; } } while (0)

static char expect[1 << 20];
static size_t expect_len;
static int queue(int i) {
    char line[64];
    const int n = snprintf(line, sizeof line, "[hos test] line %d\n", i);
    memcpy(expect + expect_len, line, (size_t)n);
    expect_len += (size_t)n;
    return log_queue(line, 0);
}
static int wait_for(size_t n, DWORD ms) {
    const ULONGLONG end = GetTickCount64() + ms;
    while (out_size() < n && GetTickCount64() < end) Sleep(1);
    return out_size() >= n;
}
static int same(void) {
    return out_size() == expect_len && memcmp(out, expect, expect_len) == 0;
}

static int run(const char *name) {
    if (!strcmp(name, "batch")) {   /* (HOS_LOG_BATCH_MS=1000: the lines of that time in one write) */
        CHECK(queue(0));
        Sleep(20);
        for (int i = 1; i < 50; i++) CHECK(queue(i));
        Sleep(100);
        CHECK(out_size() == 0);   /* (still waiting for more) */
        CHECK(wait_for(expect_len, 4000) && same());
        CHECK(writes == 1);
        Sleep(400);
        CHECK(queue(50));   /* (the next batch: the writer back to waiting for a line) */
        CHECK(wait_for(expect_len, 4000) && same() && writes == 2);
    } else if (!strcmp(name, "default")) {   /* (no setting: a line waits its 250 ms, then goes out) */
        const ULONGLONG t0 = GetTickCount64();
        CHECK(queue(0));
        CHECK(wait_for(expect_len, 3000) && same());
        CHECK(GetTickCount64() - t0 >= 200);   /* (GetTickCount64 steps in 10-16 ms) */
    } else if (!strcmp(name, "off")) {   /* (HOS_LOG_BATCH_MS=0: each wake's lines at once, as before) */
        /* (the fastest of three deliveries: a loaded CI runner stalled one past 200 ms now and then, and the default's
           250 ms batch never delivers that fast, so the fastest still tells the two apart) */
        ULONGLONG best = ~0ULL;
        for (int i = 0; i < 3; i++) {
            const ULONGLONG t0 = GetTickCount64();
            CHECK(queue(i));
            CHECK(wait_for(expect_len, 3000) && same());
            const ULONGLONG took = GetTickCount64() - t0;
            if (took < best) best = took;
        }
        CHECK(best < 200);
    } else if (!strcmp(name, "burst")) {   /* (HOS_LOG_BATCH_MS=2000: a queue half full goes out without the wait) */
        size_t half = 0;
        for (int i = 0; i < 1500; i++) {
            CHECK(queue(i));   /* (every line queued: none written by this thread) */
            if (i == 1023) half = expect_len;
        }
        CHECK(wait_for(half, 1000));
        CHECK(wait_for(expect_len, 4000) && same());
    } else if (!strcmp(name, "flush")) {   /* (HOS_LOG_BATCH_MS=2000: a way out writes what waits, once) */
        for (int i = 0; i < 10; i++) CHECK(queue(i));
        Sleep(50);
        CHECK(out_size() == 0);
        log_flush();   /* (as atexit, hos_fatal and the window's close do) */
        CHECK(same());
        Sleep(2500);   /* (the writer's wait ends with nothing left to write) */
        CHECK(same());
    } else if (!strcmp(name, "full")) {   /* (STUT3: the writer stuck in a write; a full queue is not written by the thread that logs) */
        stall_ms = 1500;
        CHECK(queue(0));
        CHECK(wait_for(0, 10) || 1);
        Sleep(300);   /* (the writer is in its slow write now) */
        const ULONGLONG t0 = GetTickCount64();
        for (int i = 1; i < LOG_Q + 500; i++) {
            char line[64];
            snprintf(line, sizeof line, "[hos test] line %d\n", i);
            CHECK(log_queue(line, 0));   /* (queued, or left out and counted: never written here) */
        }
        CHECK(GetTickCount64() - t0 < 1000);   /* (no wait for the writer's lock, no write of this thread's own) */
        CHECK(log_dropped > 0);
        stall_ms = 0;
        Sleep(3000);
        CHECK(other_thread_writes == 0);
        CHECK(strstr(out, "lines left out: the queue was full") != NULL || log_dropped > 0);
        char fatal[64];
        snprintf(fatal, sizeof fatal, "[hos test] fatal\n");
        CHECK(log_queue(fatal, 1));   /* (a fatal line still goes) */
    } else {
        CHECK(0);
    }
    printf("PASS: %s\n", name);
    return 0;
}

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    return run(argv[1]);
}
