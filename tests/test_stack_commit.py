"""A thread's stack page refused at the commit limit waits for commit, and the thread goes on (host/mkw_glue.c
stack_on_touch; HeyListen 1e732fb6, from Longshot 96caf2f23). Read from the source: no game, and no PC is filled up.

With RAM and the page file full, Windows can't commit the next page of a thread's stack and raises a stack overflow with
nearly all of the stack unused: the game died with "stack overflow". Checked:
- the handler takes only a stack overflow, only while the stack's reservation has room left (a real overflow goes on to the
  crash report), and only when the commit was refused at the commit limit;
- it commits the room as guard pages (Windows hands them to the stack as its own) and lets the thread go on;
- before that room is committed it calls nothing that needs a stack: no log line until after the loop, or after the spare
  is given back;
- when commit never comes back, the spare committed at the start is given back for the room, the out-of-memory notice is
  shown and the crash report follows;
- it is a first handler, registered before the crash report's, and the spare is committed at the start.

    python -I -B tests/test_stack_commit.py
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
    src = (ROOT / "host" / "mkw_glue.c").read_text(encoding="utf-8")
    body = block(src, "static LONG CALLBACK stack_on_touch(EXCEPTION_POINTERS *info) {")
    check("if (info->ExceptionRecord->ExceptionCode != EXCEPTION_STACK_OVERFLOW) return EXCEPTION_CONTINUE_SEARCH;" in body,
          "the handler takes more than a stack overflow")
    check("if (left < 2 * STACK_ROOM) return EXCEPTION_CONTINUE_SEARCH;" in body and "mbi.State != MEM_RESERVE) return EXCEPTION_CONTINUE_SEARCH;" in body,
          "a stack that really ran out is not left to the crash report")
    check("if (GetLastError() != ERROR_COMMITMENT_LIMIT) return EXCEPTION_CONTINUE_SEARCH;" in body, "a refusal that is not the commit limit's is waited for")
    check(body.count("VirtualAlloc(room, STACK_ROOM, MEM_COMMIT, PAGE_READWRITE | PAGE_GUARD)") == 2 and "return EXCEPTION_CONTINUE_EXECUTION;" in body,
          "the room is not committed as guard pages, or the thread does not go on")
    loop = body[body.index("while (!VirtualAlloc(room"):]
    first_log = body.index("hos_log(")
    check(first_log > body.index("InterlockedExchangePointer((void *volatile *)&stack_spare, NULL)") and
          "hos_log(" not in body[:body.index("while (!VirtualAlloc(room")], "a log line is written before the stack has room for it")
    spare = loop[:loop.index("Sleep(50);")]
    check("if (ms == 5000) {" in spare and "VirtualFree(spare, 0, MEM_RELEASE)" in spare and "hos_out_of_memory(1);" in spare and
          spare.index("VirtualFree(spare, 0, MEM_RELEASE)") < spare.index("hos_out_of_memory(1);") and
          spare.index("hos_out_of_memory(1);") < spare.rindex("return EXCEPTION_CONTINUE_SEARCH;"),
          "commit that never comes back: the spare is not given back before the notice, or the crash report does not follow")
    init = block(src, "void hos_commit_init(void) {")
    check("stack_spare = VirtualAlloc(NULL, STACK_SPARE, MEM_COMMIT, PAGE_READWRITE);" in init and
          init.index("AddVectoredExceptionHandler(1, stack_on_touch);") < init.index("AddVectoredExceptionHandler(0, report_fatal);"),
          "the handler is not a first one registered before the crash report's, or the spare is not committed at the start")
    print("PASS: a thread's stack page refused at the commit limit waits for commit")


if __name__ == "__main__":
    main()
