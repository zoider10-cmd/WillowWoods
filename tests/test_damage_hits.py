"""Damage numbers, step one (asked 2026-11-23, share/damage-values.md): every life loss at the life component's write tells
the host (nx2/oot_patches.py patch_life_hits -> host/hos_main.c hos_oot_hit), before patch_life's own guard may change
the new life, on a file patch_life made already as on a new one; once. Without a game dump."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nx2"))
import oot_patches as patches  # noqa: E402


def main():
    source = '#include "a64.h"\n' + patches.LIFE_HEAD + patches.LIFE_CAS + '\n' + patches.LIFE_CAS + '\n}\n'
    for name, start in (("new", source), ("made by patch_life", patches.patch_life(source))):
        made = patches.patch_life_hits(start)
        assert made and made.count("hos_oot_hit(") == 2, name   # (the call and its extern)
        assert patches.patch_life_hits(made) == made, "%s: twice adds it twice" % name
        body = made.split(patches.LIFE_HEAD)[1]
        hit, cas = body.index(patches.LIFE_HIT), body.index(patches.LIFE_CAS)
        assert hit < cas, "%s: the hit is not told before the damage write" % name
        if "hos_oot_damage(" in body:
            assert hit < body.index("hos_oot_damage("), "the hit is not told before patch_life's guard changes it"
        assert body.count(patches.LIFE_HIT) == 1, "%s: the healing write tells a hit too" % name
    # (a file made with the first form, before the health bars, without the life's address: brought up to this one)
    first = patches.patch_life_hits(source).replace(patches.LIFE_HIT, patches.LIFE_HIT_FIRST).replace(patches.LIFE_HIT_DECL, patches.LIFE_HIT_DECL_FIRST)
    assert patches.LIFE_HIT_FIRST in first and patches.patch_life_hits(first) == patches.patch_life_hits(source), "the first form is not brought up"
    assert "c->x[13]);" in patches.LIFE_HIT, "the life's own address is not passed"
    # (both orders end the same: patch_file runs patch_life first)
    assert patches.patch_life_hits(patches.patch_life(source)) == patches.patch_file(source, "authored.c", protect_hearts=True)[0]
    assert patches.patch_file(source, "authored.c", protect_hearts=False)[0] == source
    assert patches.patch_life_hits(source.replace(patches.LIFE_CAS, "", 1)) is None
    host = (ROOT / "host" / "hos_main.c").read_text(encoding="utf-8")
    fn = host[host.index("void hos_oot_hit(Ctx *c, uint64_t actor, uint32_t old, uint32_t next, uint32_t hit, uint64_t life) {"):]
    fn = fn[:fn.index("\n}\n")]
    assert "hos_oot_is_player(c, actor)) return;" in fn and "resource + 88 + (unsigned)i" in fn and 'env_on("HOS_OOT_DAMAGE_LOG")' in fn
    print("PASS: damage numbers' hits reach the host")
    return 0


if __name__ == "__main__":
    sys.exit(main())
