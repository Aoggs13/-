# ZhubaiSlide — handoff for the next developer / AI

> Бұл файлды жобамен бірге басқа ЖИ-ге беріңіз: онда бәрі түсіндірілген. API кілттерді чатқа жазбаңыз —
> оларды тек Railway → Variables ішіне қойыңыз.

## What it is
A website: the user types a topic, picks 5 / 8 / 10 / 15 / 20 / 25 slides, Kazakh or Russian and a design,
and gets a designed PowerPoint (PPTX) with an in-browser preview of every slide, a live countdown and photos
of the real subject. No Telegram bot (the owner's explicit wish). The audience is non-technical ("so that my
mom understands"): a simple 4-question form; everything else sits under «Қосымша баптаулар».

- Live: https://zhubislide-production.up.railway.app
- Code: GitHub `Aoggs13/-`, branch `zhubislide`, folder `zhubislide/`. (The `main` branch is a different
  project, a Telegram photo bot.)

## Code map
- `app/main.py` — FastAPI: `/api/meta`, `/api/estimate`, `/api/jobs` (create, status, deck JSON, images, PPTX
  download), rate limits, the AI key check at startup, optional photo self-test.
- `app/content.py` — AI text. Providers: Anthropic, OpenAI, Gemini (via its OpenAI-compatible endpoint).
  Phase 1: outline (design, title, slide plan, cover subject); phase 2: slide text in parallel batches.
  JSON-schema output, model fallback, error codes that the UI explains.
- `app/jobs.py` — job queue; files in `DATA_DIR/jobs/<id>`; time estimates learned per provider
  (`DATA_DIR/stats.json`); photos are fetched while the text is still being written.
- `app/builder.py` — PPTX builder: 5 styles × 7 palettes × 8 fonts; layouts cover, image_left/right, article,
  cards, stats, quote, two_column, timeline, thanks; simulated word wrap so long text always fits; portraits
  are framed, never stretched.
- `app/themes.py` — palettes, fonts, styles and the automatic choice by topic.
- `app/images.py` — photos (see below).
- `static/` — the single-page site (`index.html`, `app.js` — its renderer mirrors the builder for the preview,
  `style.css`), UI in Kazakh and Russian.
- `tests/` — 54 tests, no network: `python -m pytest -q tests`.

## Run locally
```bash
pip install -r requirements.txt
export GEMINI_API_KEY=...            # or ANTHROPIC_API_KEY / OPENAI_API_KEY; never commit it
uvicorn app.main:app --reload        # http://localhost:8000
python -m pytest -q tests
```
All settings are listed in README.md → Environment.

## AI keys (state in October 2026)
- Keys live only in Railway → service `zhubislide` → Variables. Never in code, files, commits or chats.
- `OPENAI_API_KEY` is set, but its account has no API balance (429 insufficient_quota), so it is skipped.
- `GEMINI_API_KEY` (free tier) generates the decks: about 20 requests per model per day. The app walks the
  Flash models (newest first, then -flash-lite) and skips overloaded (503) and used-up ones. When all are used
  up the site shows a "daily limit" message and works again the next day.
- For reliable service, add billing to one provider's **API** (console.anthropic.com, platform.openai.com or
  Google AI Studio). Chat subscriptions (Claude Pro, ChatGPT Plus) do not include API usage.
- Keys that were pasted into chats should be revoked and replaced; put the new key only in Railway Variables.

## Photos (`app/images.py`)
1. A slide about a specific person, place or event: the AI gives `image_subject` =
   "English Wikipedia title | title in the deck language" (`cover_subject` for the whole deck). The photo is
   that article's image (English, deck-language, then Russian Wikipedia), then more photos of it from
   Wikimedia Commons. Example: a deck about Ахмет Байтұрсынұлы shows him, not a stranger.
2. Other slides (`image_query`, 2–4 English nouns): Pexels / Unsplash if a key is set → Openverse → Commons
   file search (JPEG only) → Wikipedia search, where an article counts only if the head noun of its title is a
   query word ("Optical fiber" yes, "Food desert" no). From Railway, Openverse times out: it gets 8 s and is
   then skipped for 10 minutes. A shortened 2-word query does not use the Commons search.
3. Nothing on topic → abstract art in the theme colours, never a random person.

To see the picks on the server, set `ZS_PHOTO_SELFTEST="Akhmet Baitursynuly | Ахмет Байтұрсынұлы; q:kazakh
steppe horses"`. The startup logs then show each source's result and the chosen files. Clear it afterwards.

## Deployment (Railway)
- Project "Sulba Heritage" (the free plan did not allow a new project), service `zhubislide`, volume at
  `/data`, the domain above. Variables: `PORT=8000`, `DATA_DIR=/data`, `DAILY_LIMIT=100`, `ZS_VERSION`, AI keys.
- Railway's GitHub app has no access to this repo. So the service runs the image `python:3.13-slim` with a
  custom start command: base64 of `deploy/railway_boot.py`, which downloads a pinned commit of this public repo,
  pip-installs `requirements.txt` and starts uvicorn. Deployed now: commit `b3cd2a2` (same app code as the
  branch head).

### Ship an update
1. Push to branch `zhubislide`.
2. `python deploy/make_start_command.py $(git rev-parse HEAD)` → paste the output into Railway → service →
   Settings → Deploy → Custom Start Command.
3. Change the `ZS_VERSION` variable (e.g. to the short SHA). That starts a deployment with the new command; a
   plain "Redeploy" may reuse the old one.
4. The deploy logs should show `ZhubaiSlide started` and `AI check ok: provider=...`.

### Simpler alternative
Give Railway's GitHub app access to `Aoggs13/-` (GitHub → Settings → Applications → Installed GitHub Apps →
Railway → Configure). Then set the service source to repo `Aoggs13/-`, branch `zhubislide`, Root Directory
`zhubislide` (Dockerfile builder, see `railway.json`), and clear the custom start command. After that, every
push deploys automatically.

## Not verified
After the last photo changes, only the unit tests and the server photo self-test were run. No full deck was
generated, to save the free Gemini quota.
