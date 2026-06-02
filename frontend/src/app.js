// Orchestrator: wires the reader, the /generate backend, and the Strudel player.
//
// Flow: load text -> render paragraphs -> Start (user gesture) plays paragraph 0
// and prefetches 1 -> Next/Prev swap the music, reusing cached code and prefetching
// the neighbour. Continuity: each request passes the previous paragraph's code so
// the model evolves the same timbre rather than jumping.

import { splitParagraphs, renderParagraphs, setCurrent } from './reader.js';
import * as player from './player.js';

// Same-origin when served by uvicorn; fall back to localhost when opened as a file.
const API = location.protocol === 'file:' ? 'http://localhost:8000' : '';

const els = {
  start: document.getElementById('start'),
  prev: document.getElementById('prev'),
  next: document.getElementById('next'),
  stop: document.getElementById('stop'),
  status: document.getElementById('status'),
  paragraphs: document.getElementById('paragraphs'),
  code: document.getElementById('code'),
  textInput: document.getElementById('text-input'),
  fileInput: document.getElementById('file-input'),
  load: document.getElementById('load'),
};

let paragraphs = [];
let paraEls = [];
let current = -1;
const codeCache = new Map(); // index -> Promise<string>

function status(msg) {
  els.status.textContent = msg;
}

// Generate (or reuse) the Strudel code for a paragraph. Uses the previous
// paragraph's code as context when it's already cached (cheap continuity).
function getCode(index) {
  if (codeCache.has(index)) return codeCache.get(index);
  const promise = (async () => {
    const previous_code = codeCache.has(index - 1) ? await codeCache.get(index - 1) : '';
    const res = await fetch(`${API}/generate`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ paragraph: paragraphs[index], previous_code }),
    });
    if (!res.ok) throw new Error(`/generate failed: ${res.status}`);
    return (await res.json()).code;
  })();
  codeCache.set(index, promise);
  return promise;
}

// Warm the cache for a paragraph without blocking.
function prefetch(index) {
  if (index >= 0 && index < paragraphs.length) getCode(index).catch(() => {});
}

const MAX_ATTEMPTS = 3; // the small model occasionally emits invalid Strudel; regenerate

async function goTo(index) {
  if (index < 0 || index >= paragraphs.length) return;
  current = index;
  setCurrent(paraEls, index);
  updateNav();

  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    const composing = !codeCache.has(index);
    const retry = attempt > 1 ? ` (retry ${attempt - 1})` : '';
    status(`${composing ? 'Composing' : 'Cueing'} paragraph ${index + 1}…${retry}`);

    let code;
    try {
      code = await getCode(index);
    } catch (err) {
      status(`Couldn't reach the composer for paragraph ${index + 1}: ${err.message}`);
      return;
    }
    if (current !== index) return; // user moved on while we were generating
    els.code.textContent = code;

    try {
      await player.play(code); // throws if the generated code doesn't parse
      status(`Playing paragraph ${index + 1} / ${paragraphs.length}`);
      prefetch(index + 1); // read-ahead so Next is instant
      return;
    } catch (err) {
      codeCache.delete(index); // bad code — drop it and try a fresh generation
      if (attempt === MAX_ATTEMPTS) {
        status(`Paragraph ${index + 1}: couldn't produce valid music (${err.message})`);
      }
    }
  }
}

function updateNav() {
  const playing = player.isReady();
  els.prev.disabled = !playing || current <= 0;
  els.next.disabled = !playing || current >= paragraphs.length - 1;
  els.stop.disabled = !playing;
}

function loadText(text) {
  paragraphs = splitParagraphs(text);
  codeCache.clear();
  current = -1;
  els.code.textContent = '—';
  paraEls = renderParagraphs(els.paragraphs, paragraphs, (i) => {
    if (player.isReady()) goTo(i);
  });
  els.start.disabled = paragraphs.length === 0;
  els.start.textContent = '▶ Start';
  status(paragraphs.length ? `${paragraphs.length} paragraphs loaded. Press Start.` : 'No paragraphs found.');
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
