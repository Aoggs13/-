# ZhubaiSlide

Website that turns a topic into a designed PowerPoint deck (5–25 slides, Kazakh or Russian).

- **Five design styles** — modern, classic, bold, clean, playful (backgrounds, titles, photo frames, cards and
  numbers differ, not just colours). "Авто" lets the AI pick style, palette, ornament and font for the topic;
  colours are corrected server-side so text is always readable. 7 palettes and 8 fonts (Times New Roman, Arial,
  Calibri, Cambria, Segoe UI, Verdana, Tahoma, Courier New) can be chosen instead — also after generation.
- **Photos of the real subject**: for a slide about a specific person, place or event the AI names it
  (`image_subject`, "English title | local title"); its Wikipedia page image and Commons photos are used, so a
  deck about Akhmet Baitursynuly shows him, not a stranger. Portraits are framed, never stretched.
- **Full, understandable text**: lead sentence + explanatory bullets; three text amounts. Every text box is
  fitted (simulated word wrap) so long text stays inside the design.
- **Real time estimate**: shown per slide count before starting, learned from real runs (stored in
  `/data/stats.json`); during generation the countdown is re-estimated from the observed speed.
- Other slides get a stock photo: Pexels / Unsplash if a key is set, else Openverse, then Wikimedia Commons,
  then the lead photo of an English Wikipedia article about the thing (a failing optional API is skipped for
  10 minutes). Photos are fetched while the text is still being written; speaker notes; PPTX download;
  in-browser preview of every slide.

## Run locally
```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...        # or OPENAI_API_KEY; never commit it
uvicorn app.main:app --reload
python -m pytest -q tests           # 48 tests, no network needed
```

## Environment
| Variable | Default | |
|---|---|---|
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` or `GEMINI_API_KEY` | — | **at least one**, set in Railway → Variables. At startup a tiny request checks each key; the first one whose balance works is used (Anthropic → OpenAI → Gemini, or `AI_PROVIDER` first) |
| `CLAUDE_MODEL`, `CLAUDE_EFFORT` | `claude-opus-5-5`, `low` | |
| `OPENAI_MODEL`, `OPENAI_REASONING_EFFORT` | newest `gpt-N.M` the key can use, `low` | |
| `GEMINI_MODEL` | newest `gemini-N.M-flash` (free tier) | via Gemini's OpenAI-compatible API |
| `PEXELS_API_KEY`, `UNSPLASH_ACCESS_KEY` | — | optional, better photos |
| `DATA_DIR` | `/data` in Docker | mount a Railway volume here |
| `RATE_LIMIT_PER_HOUR` | `12` | decks per IP per hour |
| `MAX_PARALLEL` | `3` | decks generated at the same time |
| `SLIDES_PER_BATCH`, `BATCHES_PARALLEL` | `4`, `4` | parallel text generation |
| `KEEP_DAYS` | `14` | how long decks are kept |
| `ZS_PHOTO_SELFTEST` | — | "English \| local; q:stock query; …": at startup, log which photo each subject or stock query gets (diagnostics) |

## Railway
Service from this repo with **Root Directory = `zhubislide`** (Dockerfile builder, see `railway.json`),
a volume mounted at `/data`, variable `ANTHROPIC_API_KEY`, and a generated domain.
