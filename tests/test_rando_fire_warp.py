"""The owner's run 2026-11-23: after Volvagia's blue warp Link stood frozen in Kakariko. The Fire Temple's way out
plays Dm_Kakariko_0025 on arrival and then reserves the change to the Chamber of Sages; with the video passed over
(SCENE_VIDEOS) that change never came. The video plays again (SCENE_VIDEOS_KEPT, fixes 76). No game files.

python -I -B tests/test_rando_fire_warp.py
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools", "rando"))
import rando_seed as R  # noqa: E402


def main():
    ok = "Dm_Kakariko_0025" not in R.SCENE_VIDEOS and "Dm_Kakariko_0025" in R.SCENE_VIDEOS_KEPT and R.FIXES_VERSION >= 76
    print("PASS: the Fire Temple's way out keeps its Kakariko video" if ok else
          "FAIL: Dm_Kakariko_0025 is still passed over (Link frozen in Kakariko after Volvagia), or FIXES_VERSION not past 75")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
