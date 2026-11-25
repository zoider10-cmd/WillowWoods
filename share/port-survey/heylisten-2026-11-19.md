# HeyListen, 2026-11-19 (504f8362..539d20ad, 70 commits; read only)

Nothing taken. What it changed, and where we stand:
- 710a70b3 Gohma reaches her ceiling above 60 fps: a port of Hookshot 93a8bff3, which ours has ("the saved steering rate
  above 60 fps" in our build's patch log). 843bf072 Epona's fences and the barge: taken today from Longshot directly.
- 62b2cb69 then 539d20ad: they gave AMD's retired and idle imports back on Windows (ReLink's rule), then went back to
  keeping them by default (RX_VK_AMD_GIVE_BACK=1 for the give-back). Ours gives retired ones back after a wait and keeps
  idle ones: between the two, and no missing ground reported here. Leave as is.
- Translation storm hold, job steal (d85e5132, 48693a43, 9f1b060f, bea549d9): experiments they turned off by default again.
- Shader translator fixes of 11-09..11-15 (fb9ee832, 80470aa9, 8bcc8e66, ...): ports from Hookshot and Fritchii; a change
  to the translator re-prepares every shader. Not looked at one by one: a later pass if a glitch points there.
- fb483ede an Off choice in the Upscaler row; 9f725aa1 a texture's re-upload takes only its own submission's copies (their
  issue 66): worth a look later.
