"""A sparse texture's upload that runs out of staging memory binds the blocks it queued before it gives up
(gpu/vk/vk_texture.cpp upload_inner; the fix is HeyListen a3a7b102, Hookshot #3031). No game, no GPU.

The upload queues the sparse binds of each run of rows into sparse_binds, one list shared by every texture, and
texture_resident_flush binds the whole list into ONE image. When staging failed part-way, upload_inner returned with the
earlier rows' binds still queued: their tiles were marked bound with no memory behind them, and the next flush, another
texture's, bound that memory into the other texture's image. Staging runs out on a card short of memory. Checked: after
the staging call, no way out of the rows' loop returns false without flushing this texture's binds first.

    python -I -B tests/test_sparse_staging_failure.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from srccut import block   # noqa: E402


def main():
    source = (ROOT / "gpu" / "vk" / "vk_texture.cpp").read_text(encoding="utf-8")
    body = block(source, "bool upload_inner(Texture& tex, const Ranges* dirty) {")
    if "texture_resident_queue(&tex" not in body or "const Staging st = staging((out_bytes" not in body:
        sys.exit("FAIL: upload_inner no longer queues sparse binds or takes staging as this check reads it: bring the check up to date")
    if "if (!st.buffer) return false;" in body:
        sys.exit("FAIL: a staging failure returns without binding the sparse blocks queued by the rows before it")
    # (from the staging call to the next rows' binds being queued: every "return false" there has the flush just before it,
    #  in its own braces)
    rows = body[body.index("const Staging st = staging((out_bytes"):]
    rows = rows[:rows.index("texture_resident_queue(&tex")] if "texture_resident_queue(&tex" in rows else rows
    at, seen = 0, 0
    while True:
        at = rows.find("return false;", at)
        if at < 0:
            break
        braces = rows[rows.rfind("{", 0, at):at]
        if "texture_resident_flush(&tex);" not in braces:
            sys.exit("FAIL: a sparse upload that fails part-way leaves its queued binds for another texture's flush")
        seen += 1
        at += 1
    if not seen:
        sys.exit("FAIL: the staging failure's way out was not found: bring the check up to date")
    print("PASS: a sparse upload that fails part-way binds what it queued")


if __name__ == "__main__":
    main()
