// Orchestrator: wires the reader, the /generate backend, and the Strudel player.
//
// Reading is per-paragraph (the gutter line tracks your position), but MUSIC is
// per SECTION: paragraphs are grouped into ~1-minute chunks, and the music only
// swaps when you cross into a new section — so it doesn't change every paragraph.
// Each section's whole text is sent to the model, with the previous section's
// code for continuity, and the next section is prefetched while you read.

import { splitParagraphs, groupParagraphs, renderParagraphs, setHighlight } from './reader.js';
import * as player from './player.js';

// Same-origin when served by uvicorn; fall back to localhost when opened as a file.
const API = location.protocol === 'file:' ? 'http://localhost:8000' : '';

// Roughly a minute of reading at ~200 words/min. Tune to taste.
const WORDS_PER_SECTION = 200;

const els = {
  start: document.getElementById('start'),
  prev: document.getElementById('prev'),
  next: document.getElementById('next'),
  stop: document.getElementById('stop'),
  status: document.getElementById('status'),
  paragraphs: document.getElementById('paragraphs'),
  textInput: document.getElementById('text-input'),
  fileInput: document.getElementById('file-input'),
  load: document.getElementById('load'),
};

let paragraphs = [];
let paraEls = [];
let groups = [];
let groupOf = [];
let current = -1; // paragraph index (reading position)
let playingGroup = -1; // section index whose music is playing
const codeCache = new Map(); // section index -> Promise<string>

function status(msg) {
  els.status.textContent = msg;
}

function playingStatus(g) {
  return `Playing section ${g + 1}/${groups.length}  ·  paragraph ${current + 1}/${paragraphs.length}`;
}

// Generate (or reuse) the Strudel code for a section. Uses the previous section's
// code as context when it's already cached (cheap continuity).
function getCode(g) {
  if (codeCache.has(g)) return codeCache.get(g);
  const promise = (async () => {
    const previous_code = codeCache.has(g - 1) ? await codeCache.get(g - 1) : '';
    const res = await fetch(`${API}/generate`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ paragraph: groups[g].text, previous_code }),
    });
    if (!res.ok) throw new Error(`/generate failed: ${res.status}`);
    return (await res.json()).code;
  })();
  codeCache.set(g, promise);
  return promise;
}

// Warm the cache for a section without blocking.
function prefetch(g) {
  if (g >= 0 && g < groups.length) getCode(g).catch(() => {});
}

const MAX_ATTEMPTS = 3; // the small model occasionally emits invalid Strudel; regenerate

// Generate + swap in the music for section `g` (with retry), then prefetch the next.
async function playGroup(g) {
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    const composing = !codeCache.has(g);
    const retry = attempt > 1 ? ` (retry ${attempt - 1})` : '';
    status(`${composing ? 'Composing' : 'Cueing'} section ${g + 1}/${groups.length}…${retry}`);

    let code;
    try {
      code = await getCode(g);
    } catch (err) {
      status(`Couldn't reach the composer for section ${g + 1}: ${err.message}`);
      return;
    }
    if (groupOf[current] !== g) return; // reader moved to a different section

    try {
      await player.play(code); // shows the code in the editor + throws if it doesn't parse
      status(playingStatus(g));
      prefetch(g + 1);
      return;
    } catch (err) {
      codeCache.delete(g); // bad code — drop it and try a fresh generation
      if (attempt === MAX_ATTEMPTS) {
        status(`Section ${g + 1}: couldn't produce valid music (${err.message})`);
      }
    }
  }
}

// Move the reading position to a paragraph. Music only changes at section borders.
async function goTo(paraIndex) {
  if (paraIndex < 0 || paraIndex >= paragraphs.length) return;
  current = paraIndex;
  const g = groupOf[paraIndex];
  setHighlight(paraEls, current, groups[g].indices);
  updateNav();

  if (g === playingGroup) {
    status(playingStatus(g)); // same section — music keeps playing
    prefetch(g + 1);
    return;
  }
  playingGroup = g;
  await playGroup(g);
}

function updateNav() {
  const playing = player.isReady();
  els.prev.disabled = !playing || current <= 0;
  els.next.disabled = !playing || current >= paragraphs.length - 1;
  els.stop.disabled = !playing;
}

function loadText(text) {
  paragraphs = splitParagraphs(text);
  ({ groups, groupOf } = groupParagraphs(paragraphs, WORDS_PER_SECTION));
  codeCache.clear();
  current = -1;
  playingGroup = -1;
  paraEls = renderParagraphs(els.paragraphs, paragraphs, (i) => {
    if (player.isReady()) goTo(i);
  });
  els.start.disabled = paragraphs.length === 0;
  els.start.textContent = '▶ Start';
  status(
    paragraphs.length
      ? `${paragraphs.length} paragraphs in ${groups.length} section(s). Press Start.`
      : 'No paragraphs found.',
  );
  updateNav();
}

// --- wiring ---------------------------------------------------------------

els.load.addEventListener('click', () => loadText(els.textInput.value));

els.fileInput.addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const text = await file.text();
  els.textInput.value = text;
  loadText(text);
});

els.start.addEventListener('click', async () => {
  els.start.disabled = true;
  status('Starting audio…');
  try {
    await player.init(); // must happen inside this click (gesture)
  } catch (err) {
    status(`Error: ${err.message}`);
    els.start.disabled = false;
    return;
  }
  els.start.textContent = '▶ Started';
  await goTo(0);
});

els.prev.addEventListener('click', () => goTo(current - 1));
els.next.addEventListener('click', () => goTo(current + 1));
els.stop.addEventListener('click', () => {
  player.stop();
  status('Stopped.');
});

document.addEventListener('keydown', (e) => {
  if (!player.isReady()) return;
  if (e.key === 'ArrowRight') goTo(current + 1);
  if (e.key === 'ArrowLeft') goTo(current - 1);
});

// Best-effort: pre-load the bundled sample so there's something to play immediately.
fetch(`${API}/sample`)
  .then((r) => (r.ok ? r.text() : Promise.reject()))
  .then((text) => {
    els.textInput.value = text;
    loadText(text);
  })
  .catch(() => status('Paste text or choose a file, then Load.'));
