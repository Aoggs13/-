# Enhance Bot — context for Claude

- Talk to the user in **Kazakh**, briefly. Never fabricate results.
- The Telegram bot token must **never** be put in code, logs, files, commits or ZIPs. The user sets `BOT_TOKEN` themselves in Railway → Variables.

## What this is
Telegram bot (aiogram 3.31, Python 3.13, CPU-only, onnxruntime):
- photo → Real-ESRGAN x4 + GPEN faces + vivid/crisp grade, up to 4K, sent as file + before/after;
- video (≤ 15 s, ≤ 20 MB) → per-frame SPAN x4 + grade, minterpolate to 120 fps in parallel slices, ≤ 50 MB.
Models (~450 MB) download on first start into `MODELS_DIR` (`/data/models` in Docker).
Tests: `python -m pytest -q tests` (9 pass; model-dependent ones skip without models).

## Pending task: deploy to Railway (Railway connector should be attached in this session)
1. Create a new Railway project/service from GitHub repo `Aoggs13/-` (branch `main`), builder = Dockerfile (see `railway.json`).
2. Add a volume mounted at `/data`.
3. Ask the user to add `BOT_TOKEN` in the service Variables (do not ask them to paste it in chat).
4. Deploy, watch logs for `bot started`, then ask the user to send `/start` and a photo.
5. Remind the user to rotate the token in @BotFather (/revoke) afterwards — the old one was pasted in chat once.

## Second bot: `evoskin_bot/` (evoworld.io reaper skin animator)
- User sends a reaper skin (standard pose) → bot returns idle 6 / fly 5 / attack 8 frames posed like the black reaper (frames sheet + ZIP of PNG frames and layers). **No GIFs** — the user does not want animations, only the frames.
- User's quality bar: hands complete, hidden areas filled like the original, nothing "eaten" (smudged); compare every frame zoomed before claiming done.
- Rig measured from `evoskin_bot/tools/black_reaper/*.png`; tests: `cd evoskin_bot && python -m pytest -q tests` (10 pass).
- Each job runs in a child process (`python -m evoskin.worker`), 2 threads, retried without LaMa if it dies; jobs cut by a restart get a message on next start (`/data/state`). Peak ~0.66 GB with LaMa.
- Arms: back sleeve moves with the back hand; front sleeve is lifted in attack_2/3/4 as a tube textured from the skin's robe; robe edge under a sleeve = the skin's sleeve line.
- Railway (account aidosmaksatuli): project `EvoSkinBot`, service `evoskin-animator`, image `python:3.13-slim`, volume `/data`, 1 GB RAM limit. Its start command downloads branch `claude/t-f02kb7` from GitHub (public repo) on every start, so deploying = push + restart the service. `BOT_TOKEN` is set in its Variables; never write it anywhere else.
