"""A run that ran out of memory says so at the next start (host/mkw_glue.c oom_mark, host/hos_main.c memory_notice; Triforce
v0.8.4). Read from the source: no game, and no PC is filled up.

The out-of-memory notice at the moment is under a full-screen game and often not seen. Checked:
- the first out-of-memory of a run leaves the mark beside the game, in the branch that is taken once, on Windows;
- the next start looks for the mark before its low-memory check, logs it, shows a notice with this PC's RAM and page file and
  the page file's advice, and removes the mark only when the notice was shown (a run without a window leaves it);
- both sides name the same file.

    python -I -B tests/test_oom_next_start.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from srccut import block   # noqa: E402


def check(ok, why):
    if not ok:
        print("FAIL: %s" % why)
        sys.exit(1)


def main():
    glue = (ROOT / "host" / "mkw_glue.c").read_text(encoding="utf-8")
    main_c = (ROOT / "host" / "hos_main.c").read_text(encoding="utf-8")
    head = (ROOT / "host" / "hos.h").read_text(encoding="utf-8")
    check('#define HOS_OOM_MARK "hookshot_out_of_memory.txt"' in head, "hos.h no longer names the mark's file")
    mark = block(glue, "static void oom_mark(void) {")
    check("hos_game_path_a(path, MAX_PATH)" in mark and "HOS_OOM_MARK" in mark and 'fopen(path, "w")' in mark and "#ifdef _WIN32" in mark,
          "the mark is not written beside the game, on Windows")
    oom = block(glue, "void hos_out_of_memory(int wait) {")
    once = oom[oom.index("if (InterlockedCompareExchange(&oom_state, 1, 0) == 0) {"):oom.index("while (wait")]
    check("oom_mark();" in once, "running out of memory no longer leaves the mark, or not in the branch taken once")
    notice = block(main_c, "static void memory_notice(void) {")
    at = notice.index("HOS_OOM_MARK")
    check(at < notice.index("if (!memory_notice_text(ram, swap, text, sizeof text)) {"), "the mark is looked for after the low-memory check, which returns on a PC with enough")
    said = notice[at:notice.index("char text[512];")]
    check('fopen(mark, "r")' in said and "hos_log(" in said and "MessageBoxA(NULL, said," in said and "ram / 1024.0, swap / 1024.0" in said and
          "Automatically manage paging file size" in said, "the next start does not say it with this PC's memory and the page file's advice")
    shown = said[said.index('if (!env_on("HOS_HEADLESS")) {'):]
    check("remove(mark);" in shown and "remove(mark);" not in said[:said.index('if (!env_on("HOS_HEADLESS")) {')],
          "the mark is removed without the notice having been shown")
    print("PASS: a run that ran out of memory says so at the next start, once")


if __name__ == "__main__":
    main()
