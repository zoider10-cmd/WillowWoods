"""nn::fs's file and directory handles are allocated with the waiting allocators (Triforce 86170247).

At Windows' commit limit a bare calloc in OpenFile answered NULL and the next write crashed the game as "write 0" with no
word of memory. OpenFile's and OpenDirectory's handles and the mods' entry array use hos_xcalloc / hos_xrealloc
(host/mkw_glue.c: they wait at the commit limit, then stop the game saying why), and OpenFile logs a file of a writable
mount that is there but would not open, with the error taken before the virtual core is taken back.
"""
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from srccut import block  # noqa: E402

SRC = Path(__file__).resolve().parents[1] / "host" / "nn_fs.c"


def main():
    src = SRC.read_text(encoding="utf-8")
    bad = []
    open_file = block(src, "HLE(_ZN2nn2fs8OpenFileEPNS0_10FileHandleEPKci) {")
    open_dir = block(src, "HLE(_ZN2nn2fs13OpenDirectoryEPNS0_15DirectoryHandleEPKci) {")
    add_extra = block(src, "static void add_extra(void *arg, const char *name, int is_dir, uint64_t size) {")
    for name, body in (("OpenFile", open_file), ("OpenDirectory", open_dir), ("add_extra", add_extra)):
        if re.search(r"(?<![\w])(calloc|realloc|malloc)\s*\(", body):
            bad.append(f"{name} allocates with a bare calloc/realloc/malloc: use hos_xcalloc/hos_xrealloc")
    if "hos_xcalloc(1, sizeof *fh" not in open_file:
        bad.append("OpenFile's handle is not from hos_xcalloc")
    if "hos_xcalloc(1, sizeof *dh" not in open_dir:
        bad.append("OpenDirectory's handle is not from hos_xcalloc")
    if "hos_xrealloc(dh->extras" not in add_extra:
        bad.append("add_extra's array is not from hos_xrealloc")
    err = open_file.find("GetLastError()")
    back = open_file.find("if (away) hos_vcore_back();", open_file.find("CreateFileA("))
    if err < 0 or back < 0 or err > back:
        bad.append("OpenFile must take GetLastError() before hos_vcore_back (the core's take can change it)")
    if "is there but could not be opened" not in open_file:
        bad.append("OpenFile no longer logs a writable file that is there but would not open")
    for b in bad:
        print("FAIL:", b)
    if bad:
        sys.exit(1)
    print("PASS: nn::fs handles from the waiting allocators; a file there but refused is logged")


if __name__ == "__main__":
    main()
