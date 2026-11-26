# Copyright (C) 2026 Sacrappy

"""STUT3: nn::fs's calls that change the disk give the virtual core up while the host's call runs, as OpenFile, ReadFile, WriteFile
and FlushFile already do (tests/test_vcore_fs_open.py, test_vcore_fs_write.py).

On the PC 3050, with the system's commit at its limit and the page file growing, the game's ARes loaders sat 2-6.2 s in CloseHandle
(ZwClose) holding cores 4 and 5, and every thread that wanted those cores ran without one after 2 s. By the text of host/nn_fs.c:
CloseFile, SetFileSize, CreateFile, DeleteFile, RenameFile, DeleteDirectoryRecursively, GetFileSize, CreateDirectory, GetEntryType
and OpenDirectory call hos_vcore_away() before the host's
call and hos_vcore_back() after it, on every way out; and the handle is looked up (guest memory) before the core is given up.

python -I -B tests/test_vcore_fs_close.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def block(source, marker):
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


CALLS = {
    "_ZN2nn2fs9CloseFileENS0_10FileHandleE": "CloseHandle(fh->h);",
    "_ZN2nn2fs11SetFileSizeENS0_10FileHandleEl": "SetEndOfFile(fh->h);",
    "_ZN2nn2fs10CreateFileEPKcl": "CreateFileA(path, GENERIC_WRITE",
    "_ZN2nn2fs10DeleteFileEPKc": "DeleteFileA(path)",
    "_ZN2nn2fs10RenameFileEPKcS2_": "MoveFileExA(a, b, MOVEFILE_REPLACE_EXISTING)",
    "_ZN2nn2fs26DeleteDirectoryRecursivelyEPKc": "delete_tree(path);",
    "_ZN2nn2fs11GetFileSizeEPlNS0_10FileHandleE": "GetFileSizeEx(h, &sz);",
    "_ZN2nn2fs15CreateDirectoryEPKc": "CreateDirectoryA(path, NULL)",
    "_ZN2nn2fs12GetEntryTypeEPNS0_18DirectoryEntryTypeEPKc": "GetFileAttributesA(path);",
    "_ZN2nn2fs13OpenDirectoryEPNS0_15DirectoryHandleEPKci": "FindFirstFileA(pat, &dh->fd);",
}


def main():
    src = (ROOT / "host/nn_fs.c").read_text(encoding="utf-8")
    for name, call in CALLS.items():
        body = block(src, "HLE(%s) {" % name)
        assert "const int away = hos_vcore_away();" in body, "%s keeps the core through the host's call" % name
        i_away, i_call = body.index("hos_vcore_away()"), body.index(call)
        i_back = body.index("if (away) hos_vcore_back();", i_call)
        assert i_away < i_call < i_back, "%s: the call is not between the core's release and its return" % name
        # every RET after the release comes after the core is back
        for m in re.finditer(r"RET\(", body[i_away:]):
            at = i_away + m.start()
            assert at > i_back or body.rfind("hos_vcore_back()", i_away, at) > i_away, "%s returns without its core" % name
        if "get_handle(" in body:
            assert body.index("get_handle(") < i_away, "%s reads guest memory without its core" % name
    print("PASS nn::fs's close, size, create, delete, rename, tree delete, file size, directory create, entry type and directory open give the core up")


if __name__ == "__main__":
    main()
