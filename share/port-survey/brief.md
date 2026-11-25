# Brief: survey HeyListen for our build (read only)

Our project: C:\Users\beerc\Hookshot, branch amd-fix-sharkiix-version — a fork of Hookshot (a static recompiler of
the Switch 2 Ocarina of Time remake with a Vulkan back end) by way of Mako 4.1.1, plus picks from Longshot and
ProjectReLink, plus a randomizer. The owner's PC: AMD Radeon RX 9070 XT on Windows 11.

HeyListen (https://github.com/Sacrappy/HeyListen, GPL-3.0-or-later like ours) is another Hookshot fork. A partial
clone is at C:\Users\beerc\AppData\Local\Temp\claude\c8d5bd0e01f2723b\08dd94cd-2b55-4534-9893-754c5d5cc16a\scratchpad\src\heylisten
(no checkout: read files with `git show HEAD:engine/<path>`, diffs with `git show <hash>` / `git diff a2e65052 HEAD:engine -- <path>`).
Its `engine/` is Hookshot imported by subtree at Hookshot commit a2e65052, which OUR tree also contains (our tree has
1172 commits since it, HeyListen 670 engine commits; list in ..\hl_commits.txt). HeyListen's docs/tickets and
docs/benchmarks hold each change's measured numbers (mostly NVIDIA: RTX 3050, RTX 5070).

Rules: read only. Build, run or install nothing from HeyListen; don't edit our repo. Nothing leaves the PC.

For your area, find HeyListen's changes worth bringing to our build. For each candidate:
- what it does, in a sentence or two; HeyListen commit hashes and files;
- the gain HeyListen measured (numbers, hardware, the doc), or "unmeasured";
- whether OUR tree already has it or an equivalent (search our files for the code or its idea; many of HeyListen's
  commits are picks from Longshot or later Hookshot that we may already hold: their subjects often name "Longshot xxx"
  or "Hookshot xxx");
- hardware: does it depend on NVIDIA (NVML, DLSS), mesh shaders, a PCIe width, Linux; could it hurt an AMD card, low
  VRAM, or a low-end CPU; is it behind a switch, and its default;
- how it would port: size (lines/files), conflicts with our changed files, and whether it touches the randomizer's own
  code (nx2/oot_patches.py, host/oot_*.c, host/hos_oot*, tools/rando, the launcher's rando settings) or the lift
  (nx2/), where a change could alter game behaviour;
- risk (correctness, crashes) and your score: worth porting first / later / skip, with a reason.

Also list user-visible settings or features in your area that we lack.

Write the result as markdown to the file named in your task, candidates ranked best first, then a short "skipped"
list with one-line reasons. Report back a 10-line summary of the top items.
