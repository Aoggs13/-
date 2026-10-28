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

## ZhubiSlide (folder `zhubislide/`, branch `zhubislide`)
Website (no Telegram bot): topic → designed PPTX, 5–25 slides, kk/ru, auto topic design + presets, 8 fonts,
full text, live countdown. Tests: `cd zhubislide && python -m pytest -q tests` (32 pass, no network).
Railway: service `zhubislide` in project **Sulba Heritage** (free plan blocked a new project), volume `/data`,
https://zhubislide-production.up.railway.app, vars PORT=8000, DATA_DIR=/data, DAILY_LIMIT=100.
Railway's GitHub app has no access to this repo, so the service runs image `python:3.13-slim` with a start
command that downloads a **pinned commit** tarball of this (public) repo, pip-installs and starts uvicorn
(boot script is base64 in the start command). To ship a new version: push, then update the start command
with the new commit SHA (`update-service startCommand`) — the service redeploys.
AI keys: any of ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY; the startup check picks the first that
works and logs `AI check ok|failed`. OPENAI_API_KEY is set but its account has no API balance (429
insufficient_quota). Claude Pro / ChatGPT Plus subscriptions do not include API usage.
Pending: user tops up an API balance or adds a free GEMINI_API_KEY (never put keys in code/files/commits).
