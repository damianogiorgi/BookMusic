# BookMusic 🎴🎶

**Generate ambient background music for whatever you're reading — live, from a small local LLM, played in the browser with [Strudel](https://strudel.cc).**

Open a text file or a PDF, start reading, and BookMusic composes a gentle ~1‑minute
"score" for each section of the page, evolving the mood as the story does — lofi for a
rainy café, warm piano for a tender moment, dark phrygian for danger, swelling strings
for an epic dawn. As you scroll, the highlight follows you and the music advances on its
own.

> [!IMPORTANT]
> **This is an experiment / showcase, not a product.** The interesting idea here is the
> *approach*: instead of burning a lot of compute to synthesize audio with a large
> generative-audio model, we ask a **tiny** language model to write a few lines of
> [Strudel](https://strudel.cc) (a live‑coding music language) and let the browser
> synthesize the sound for free. The "music model" is ~1 line of code per layer. It's
> cheap, it runs on a laptop, and it's surprisingly evocative. Treat the output as
> *mood lighting*, not a soundtrack.

---

## Why this approach

Generating music as raw audio (diffusion/transformer audio models) is expensive and slow.
But background reading music doesn't need to be elaborate — it needs to be **calm,
evolving, and fit the mood**. That's a great fit for **algorithmic** music:

- A small LLM (≈0.8B–4B params, running locally via [Ollama](https://ollama.com)) is more
  than capable of writing a short, valid **Strudel** pattern when given a tight prompt.
- **Strudel** (a JS port of [TidalCycles](https://tidalcycles.org)) turns those few lines
  into real sound in the browser via the Web Audio API — soundfonts, drum samples, pads,
  the works — at zero inference cost.

So the "generation" is a few hundred tokens of text, and the "synthesis" is free. The
result is a hands‑free reading companion you can run entirely on your own machine.

Read the complete story on my [blog](https://damianogiorgi.it/articles/2026/06/a-tiny-llm-that-writes-music---the-story-of-bookmusic/)
---

## What it does

- 📄 **Reads text or PDFs.** Paste text, drop a `.txt`, or open a PDF (rendered page by
  page, in the browser, with [pdf.js](https://mozilla.github.io/pdf.js/) — nothing is
  uploaded).
- ✂️ **Groups paragraphs into ~1‑minute "sections."** Music changes per section, not per
  paragraph — books don't switch mood every sentence.
- 🎚️ **Composes per section.** Each section's text → a small LLM → a few lines of Strudel →
  played in the browser. The previous section's code is passed along so the mood *evolves*
  rather than jumps.
- 🪄 **Follows your reading.** A blue/purple gutter line marks where you are; scroll and the
  highlight + music advance automatically (toggle: *Follow scroll*). Click any paragraph to
  start/resume there. Long PDFs auto‑load more pages as you scroll.
- 🔁 **Prefetches & swaps.** The next section is generated while you read; on a section
  boundary the new pattern is swapped in (cycle‑aligned, with reverb tails covering the
  seam). Every generation is **validated server‑side and regenerated if it breaks the
  rules** (see [Quality](#quality-keeping-the-music-pleasant-and-tested) below); the
  frontend still retries as a last resort if code doesn't parse.

---

## Architecture

A **static browser frontend** (the reader + the Strudel engine) and a **thin Python
backend** whose only job is to turn a chunk of prose into Strudel code via a local LLM.
The backend is deliberately tiny and swappable (local Ollama today; AWS API Gateway +
Lambda + Bedrock later).

```mermaid
flowchart TB
  user(["Reader"])

  subgraph browser["Browser — static frontend (no build step)"]
    direction TB
    doc["PDF or text"]
    pdfjs["pdf.js<br/>render pages + paragraph boxes"]
    reader["reader.js<br/>split into paragraphs,<br/>group into ~1-min sections"]
    app["app.js orchestrator<br/>scroll-follow · prefetch · swap"]
    strudel["@strudel/repl engine<br/>evaluate() → Web Audio"]
    doc --> pdfjs --> reader
    doc --> reader
    reader --> app
    app -->|play Strudel code| strudel
  end

  subgraph backend["Backend — FastAPI (local now, Lambda later)"]
    direction TB
    api["POST /generate<br/>{ section text, previous_code }"]
    gen["generator.py + prompt.txt"]
    llm["llm.py call_llm<br/>think:false"]
    api --> gen --> llm
  end

  ollama["Ollama<br/>gemma4 / qwen3.5 (local LLM)"]
  cdn["CDN: @strudel/repl, pdf.js,<br/>soundfonts + samples"]

  app -->|"section + previous code"| api
  llm <-->|chat| ollama
  llm -->|Strudel code| api
  api -->|Strudel code| app
  cdn -.->|loaded at runtime| browser
  user -->|"open + scroll"| browser
  strudel -.->|background music| user
```

### Layout

```
backend/                     # Python — turns prose into Strudel code
  server.py                  # FastAPI: POST /generate, serves the frontend in dev
  bookmusic/
    prompt.txt               # the system prompt (the heart of the project)
    generator.py             # builds the messages, calls the model, validate-retry loop
    llm.py                   # the only transport seam (Ollama now; Bedrock stub)
    validator.py             # static lint for generated Strudel (mirrors prompt rules)
  tests/                     # pytest suite (validator + generator, no LLM needed)
  evals/eval_prompt.py       # LLM scorecard: real generations, scored per mood
  samples/sample.txt         # demo document
  pyproject.toml             # uv-managed
frontend/                    # static JS, no build step
  index.html
  src/
    reader.js                # paragraph split + ~1-min section grouping + highlight
    pdfdoc.js                # pdf.js page rendering + paragraph bounding boxes
    player.js                # drives the @strudel/repl engine (setCode/evaluate/stop)
    app.js                   # orchestrator: scroll-follow, prefetch, section swap
    style.css
LICENSE                      # AGPL-3.0
```

### How a few key pieces work

- **Sectioning** (`reader.js`): split into paragraphs (blank lines; a wall of text is
  auto‑chunked on sentence boundaries), then group consecutive paragraphs to ~200 words
  (`WORDS_PER_SECTION`, ≈1 minute at ~200 wpm). Reading position is per‑paragraph; **music
  is per section**.
- **The engine** (`player.js`): we drive the **full `@strudel/repl`** web component (not the
  bare `@strudel/web`) so it loads the *same* sounds as strudel.cc — GM soundfonts, drum
  samples, piano. It also doubles as the live "Now playing" editor that highlights the
  active events.
- **PDF** (`pdfdoc.js`): pages are rendered to `<canvas>`, the text layer is grouped into
  paragraphs with bounding boxes, and a transparent overlay `<div>` per paragraph carries
  the gutter line — so the same highlight/section code works on a rendered page.
- **Scroll‑follow** (`app.js`): the current paragraph tracks whichever crosses a "reading
  line" ~38% down the viewport; the section's music is generated *debounced* (so fast
  scrolling doesn't thrash the generator) and swaps when you settle.

---

## The prompt (the actual "music model")

Almost all of the quality lives in [`backend/bookmusic/prompt.txt`](backend/bookmusic/prompt.txt).
It is a tightly‑constrained system prompt that teaches a small model to emit a **valid,
calm, background** subset of Strudel. Highlights of how it's tuned:

- **A restricted Strudel vocabulary** — only the sounds/effects that exist and sound good
  for reading (pads, soft synths, gm_ soundfonts, gentle drums, slow filter/pan
  modulation). The model is told never to invent functions.
- **Mood → STYLE → code.** A cheat‑sheet maps the passage's mood to one of several styles
  (AMBIENT, LOFI, CHILLHOP/JAZZY, WARM PIANO, DREAMY, TENSE, HAPPY/POP, EPIC/ORCHESTRAL,
  ANGER), and **each style has one labeled example** to copy. Without per‑style examples,
  small models collapse everything into "strings or a synth guitar."
- **Continuity.** The previous section's code is passed in as context, so the model evolves
  the same timbre instead of jumping at every boundary.
- **Develops over a minute.** Since each piece plays ~1 minute, the prompt pushes slow
  modulation (`.lpf(sine.range(...).slow(16))`, `.pan(...)`) rather than busy notes.

### Lessons learned (worth knowing if you tinker)

- **Disable "thinking."** Recent Ollama (0.30.x) defaults Qwen‑style *thinking* **on**, and
  the `ollama-python` `think=False` flag is **not honored** by the server — the
  chain‑of‑thought floods the reply and there's no usable code. The fix is to `POST`
  `/api/chat` directly with top‑level `"think": false` (see [`llm.py`](backend/bookmusic/llm.py)).
  This was the single biggest "it broke on another machine" gotcha.
- **Keep sampling minimal.** The custom Qwen Modelfiles bake in an aggressive
  `presence_penalty`; stacking our own `repeat_penalty` on top pushed the model into
  token‑salad. Just `temperature` + `num_predict`.
- **Small models need small, labeled examples.** 2–3 layer examples per style, an explicit
  anti‑repetition rule (small models love to loop a chord group until the token cap), and a
  **client‑side retry** when the generated Strudel doesn't parse.
- **Bigger model = steadier.** ~0.8B is fast and often good; 2B/4B follow the styles and
  stay valid more reliably. Pick via `BOOKMUSIC_OLLAMA_MODEL`. The current default is
  **gemma4:e4b-it-qat** (6.1 GB QAT quant — the plain `e4b` tag is 9.6 GB and does *not*
  fit comfortably in 16 GB of unified memory), which beat qwen3.5:4b head‑to‑head on the
  eval below. Some models drop the last closing paren of the piece — a deterministic
  `repair()` step appends it rather than burning a retry.

---

## Quality: keeping the music pleasant (and tested)

"It works" and "it's nice to read to" are different bars. After living with the app for a
while, the music that *did* validate still sometimes failed in three specific ways, and
the prompt + a validation pipeline now target exactly those:

| Failure mode | What it sounded like | What the prompt demands now |
|---|---|---|
| **Repetitive / static** | a 4‑second loop going nowhere for a minute | at least **two slow modulations** on *different* layers at *different* speeds (`.lpf(sine.range(...).slow(16))` + `.pan(...slow(10))`), and a `< >` progression of **4+ chords** |
| **Harsh / clashing** | piercing highs, dissonant layers, clicks | a *KEEP IT PLEASANT* rule block: one key per piece (bass on chord roots), nothing above octave 5, sawtooth always low‑pass‑filtered with low resonance, soft attacks on pads, `pan` kept in 0–1 |
| **Thin / empty** | two quiet layers, technically fine, no character | **3–4 layers** (chords + bass + beat *or* sparse melody), 7th‑chord voicings, and an explicit `.gain()` on every layer (Strudel's default is *loud*) |

Two structural lessons baked in: **examples beat rules** for small models (every style
example in the prompt demonstrates all of the above, because a 4B model imitates far more
than it obeys), and a **final numbered checklist** at the very end of the prompt catches
more slips than a rule buried in the middle.

### The validation pipeline

Three lines of defense, from cheap to last‑resort:

1. **Static validator** ([`validator.py`](backend/bookmusic/validator.py)) — a pure‑Python
   lint, no LLM and no Strudel runtime. `validate(code)` returns a list of issues (empty =
   good): shape (starts with `setcpm`, balanced brackets, *well‑formed quoted pattern
   strings* — a dropped quote can fool bracket counting, we learned the hard way), a
   whitelisted vocabulary (catches invented `gm_*` sounds and functions), loudness caps,
   structure (3–5 layers, a varied `< >` sequence, ≥2 slow modulations), and the
   pleasantness rules above. The whitelists mirror `prompt.txt` — keep them in sync.
2. **Server‑side retry** ([`generator.py`](backend/bookmusic/generator.py)) — every model
   reply is validated; rejected code is regenerated up to 3 times (temperature makes
   retries productive). If nothing fully passes, the attempt with the fewest issues is
   returned rather than blocking playback.
3. **Frontend parse guard** ([`player.js`](frontend/src/player.js)) — if code still fails
   to *evaluate* in the Strudel engine, the section is re‑requested.

### Test suite (fast, no LLM required)

```bash
cd backend
uv run pytest            # ~40 tests, runs in milliseconds
```

- **Self‑consistency invariant:** every style example embedded in `prompt.txt` must pass
  the validator. If you tweak the prompt or tighten the validator and they drift apart,
  the suite fails before the model ever produces rejected code.
- **Defect catalog:** ~25 parametrized cases, each verifying one specific bad pattern is
  caught (prose in the output, invented sounds, gain too hot, missing modulation, sawtooth
  without a filter, truncated code, …).
- **Generator tests:** prompt assembly (continuity via `previous_code`) and the retry loop
  (valid on first try = one call; invalid‑then‑valid retries once; all‑fail returns the
  least‑broken attempt), with the LLM stubbed out.

### LLM eval scorecard (slow, real model)

```bash
cd backend
uv run python evals/eval_prompt.py             # 1 run per mood, ~1 min total
uv run python evals/eval_prompt.py --runs 3    # steadier numbers
uv run python evals/eval_prompt.py --mood lofi anger --show-code
```

Sends one **fresh** paragraph per style (deliberately *not* the ones embedded in the
prompt) through a **raw single‑shot** model call — bypassing the retry loop on purpose, so
the numbers measure the *prompt*, not the guardrail. Each reply is scored on **rules**
(the static validator) and **style match** (expected instrument family, beat
presence/absence, scale flavor), ending in a per‑mood table plus a histogram of the most
common issues. It's a scorecard, not a pass/fail test: run it before and after a prompt
tweak (or when trying a new model) and compare. Baseline at `--runs 2`:
**gemma4:e4b-it-qat rules 16/18, style 15/18** vs qwen3.5:4b rules 10/18, style 14/18 —
which is why Gemma is the default (the retry guardrail absorbs the remaining misses in
actual use).

**Workflow when touching `prompt.txt`:** `uv run pytest` (instant — catches
prompt/validator drift) → `evals/eval_prompt.py --runs 3` (minutes — tells you whether
the music actually got better) → listen to a couple of sections anyway; ears outrank
regexes.

---

## Run it locally

### Prerequisites
- [**Ollama**](https://ollama.com) running locally with a small **instruct** model pulled.
  The default is `ollama pull gemma4:e4b-it-qat` (6.1 GB; fits 16 GB Macs). Qwen3‑class
  models (~0.8B–4B) also work — set `BOOKMUSIC_OLLAMA_MODEL` to whatever you have.
- [**uv**](https://docs.astral.sh/uv/) for the Python backend.
- A modern browser (Web Audio + ES modules).

### Start
```bash
cd backend
uv sync
uv run uvicorn server:app --reload --port 8000
```
Open <http://localhost:8000>. The bundled sample text pre‑loads. **Click a paragraph** (or
press **Start**) to begin — the first click is what lets the browser start audio. Drop a
`.pdf`/`.txt` anywhere on the page to read your own.

> The backend serves the static `frontend/` in dev, so it's one command. In production the
> frontend is just static files and `/generate` becomes a small serverless endpoint.

### Configuration (env vars)
| Variable | Default | Purpose |
|---|---|---|
| `BOOKMUSIC_OLLAMA_MODEL` | `gemma4:e4b-it-qat` | Which Ollama model to use |
| `BOOKMUSIC_LLM` | `ollama` | Backend selector (`ollama` now; `bedrock` is a stub) |
| `OLLAMA_HOST` | `http://localhost:11434` | Where Ollama is listening |

A few tunables live as constants: `WORDS_PER_SECTION` and `PAGES_PER_RANGE`
([`app.js`](frontend/src/app.js)), and `TEMPERATURE` / `NUM_PREDICT`
([`llm.py`](backend/bookmusic/llm.py)).

---

## Missing features / roadmap

This is a sketch, so plenty is intentionally left undone:

- **PDF**: multi‑column layouts, scanned/image PDFs (needs OCR), running header/footer
  stripping, and true music continuity across page‑range jumps.
- **Transitions**: a real cross‑fade between sections (today it's a cycle‑aligned swap that
  leans on reverb tails). A dual‑scheduler/gain crossfade would be smoother.
- **No backend at all**: run the LLM fully in the browser (WebGPU / `transformers.js`) so
  the whole thing is static — a spike exists.
- **Cloud**: API Gateway + Lambda + Bedrock (the `bedrock` branch in `llm.py` is a stub).
- **More styles & smarter mood detection**, and per‑user tempo/volume controls.

---

## Contributing

Ideas and PRs are very welcome — this is meant to be played with. Especially:

- 🎼 **New genres/styles.** Add a labeled `### STYLE` block (description + one clean example)
  to [`prompt.txt`](backend/bookmusic/prompt.txt) and a line to the mood cheat‑sheet. Keep
  examples short (3–4 layers) so small models can copy them — and run `uv run pytest`:
  every example embedded in the prompt must pass the static validator.
- 🧪 **Prompt evolution.** Better mood→style mapping, richer-but-valid Strudel, fewer
  retries on tiny models. Measure with `evals/eval_prompt.py` before/after.
- 📚 **Better document handling.** PDF paragraph segmentation, EPUB, multi‑column.
- 💡 **New ideas.** Reading‑speed‑aware sections, per‑chapter themes, a "vibe" override, …

If you find a prompt tweak that makes a small model noticeably more reliable, that's
gold — open a PR with a before/after example.

---

## License

**[GNU AGPL‑3.0](LICENSE).** BookMusic is a web app built on **Strudel, which is itself
AGPL‑3.0** — so AGPL is the natural, consistent choice: anyone who modifies BookMusic *and
runs it as a network service* must make their source available. If you fork and host it,
share your changes. 🙂

### Acknowledgments / third‑party
- [**Strudel**](https://strudel.cc) — AGPL‑3.0 — the live‑coding engine that makes the sound.
- [**pdf.js**](https://mozilla.github.io/pdf.js/) — Apache‑2.0 — in‑browser PDF rendering.
- [**Ollama**](https://ollama.com) (MIT) + your chosen LLM (e.g. **Qwen**) — local generation.
- [**FastAPI**](https://fastapi.tiangolo.com) / **uvicorn** / **httpx** — the backend.
- Soundfonts & drum samples are loaded at runtime by Strudel from its community sample banks
  (various open licenses).
