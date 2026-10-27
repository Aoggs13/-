# EvoSkin bot

Telegram bot: send an evoworld.io reaper skin in the standard pose (like the black reaper idle
frame) and get back the **idle (6) / fly (5) / attack (8)** frames, posed exactly like the black
reaper animation.

How it works (`evoskin/`):

1. `imageio` – decode, cut a flat background when the image has no transparency.
2. `register` – find the skull (two eye sockets) and place the black reaper rig on the skin.
3. `segment` – GrabCut, seeded from the rig, splits the skin into head, body (tail and other
   extras go with it), back hand, front hand and scythe; the handle axis and the hand that
   holds it are found from the image itself.
4. `layers` – fills what moving parts used to cover: the robe under the hands (LaMa inpainting,
   outline redrawn), the handle hidden behind the robe/hand (repeats the visible piece).
5. `animate` – applies the per-frame rigid transforms measured on the black reaper
   (`assets/rig.json`, built by `tools/`), draw order per frame, synthesized raised sleeve;
   writes PNG frames, GIF previews and a ZIP.

Run locally: `python -m evoskin skin.png out_dir`. Tests: `python -m pytest -q tests`.

Deploy (Railway): service root directory `evoskin_bot`, Dockerfile builder, volume at `/data`
(keeps the ~90 MB LaMa model), variable `BOT_TOKEN`. The token is read only from the
environment and is redacted from logs.
