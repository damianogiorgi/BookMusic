# BookMusic

Generate ambient **background reading music** from prose. A paragraph of text is
sent to a local LLM (Ollama `qwen3.5:4b`) which writes [Strudel](https://strudel.cc)
code; the browser plays it and swaps the music as you advance through the document.

```
backend/    Python — FastAPI API + Ollama call (the "composer")
frontend/   Static JS — reader UI + Strudel playback in the browser
```

## Prerequisites

- [Ollama](https://ollama.com) running locally with the model pulled:
  `ollama pull qwen3.5:4b`
- [uv](https://docs.astral.sh/uv/) for the Python backend.

## Run

```bash
cd backend
uv sync
uv run uvicorn server:app --reload --port 8000
```

Open <http://localhost:8000>. The bundled sample text pre-loads — press **Start**
(needed for browser audio), then use **Next / Prev** (or ←/→) to move through
paragraphs. The current paragraph is marked with a purple gutter line; the music
for the next paragraph is prefetched while you read and swaps in when you advance.

You can also paste your own text or load a `.txt` file from the top of the page.

## How it works

- `backend/bookmusic/prompt.txt` — the system prompt that constrains the model to
  calm, valid Strudel (synth pads, slow modulation, low gain).
- `backend/bookmusic/generator.py` — assembles the prompt and passes the previous
  paragraph's code as context so consecutive paragraphs evolve rather than jump.
- `backend/bookmusic/llm.py` — the single transport seam. `BOOKMUSIC_LLM` selects
  the backend (`ollama` today; a `bedrock` branch is stubbed for the future).
- `frontend/src/player.js` — wraps `@strudel/web` (`initStrudel` / `evaluate` /
  `hush`). It rewrites the model's `setcpm(N)` into a chained `.cpm(N)` (that build
  doesn't expose `setcpm` globally) and retries generation if a paragraph's code
  doesn't parse.

## Status / roadmap

- ✅ Backend API, browser playback, paragraph reader, prefetch + simple swap.
- ⬜ PDF mode: render with pdf.js and draw the gutter line beside the real
  paragraph on the page (`frontend/src/pdf-glue.js`).
- ⬜ Cloud: API Gateway + Lambda + Bedrock (swap `llm.py`); true crossfade.
