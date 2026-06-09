// Orchestrator: wires the reader (text OR pdf view), the /generate backend, and
// the Strudel player.
//
// Reading is per-paragraph (the gutter line tracks your position), but MUSIC is
// per SECTION: paragraphs are grouped into ~1-minute chunks, and the music only
// swaps when you cross into a new section. The section/music engine below is
// view-agnostic — it calls `view.setCurrent(index, groupIndices)`, which both the
// text view (DOM paragraphs) and the PDF view (overlay divs on rendered pages)
// implement via the same setHighlight().

import { splitParagraphs, groupParagraphs, renderParagraphs, setHighlight } from './reader.js';
import { openPdf, renderRange } from './pdfdoc.js';
import * as player from './player.js';
import * as llmLocal from './llm-local.js';

// Same-origin when served by uvicorn; fall back to localhost when opened as a file.
const API = location.protocol === 'file:' ? 'http://localhost:8000' : '';

const WORDS_PER_SECTION = 200; // ~1 minute of reading at ~200 words/min
const PAGES_PER_RANGE = 10; // how many PDF pages to render at once

const els = {
  start: document.getElementById('start'),
  prev: document.getElementById('prev'),
  next: document.getElementById('next'),
  stop: document.getElementById('stop'),
  follow: document.getElementById('follow'),
  engineLocal: document.getElementById('engine-local'),
  status: document.getElementById('status'),
  reading: document.getElementById('reading'),
  paragraphs: document.getElementById('paragraphs'),
  textInput: document.getElementById('text-input'),
  fileInput: document.getElementById('file-input'),
  load: document.getElementById('load'),
  pdfControls: document.getElementById('pdf-controls'),
  pdfInfo: document.getElementById('pdf-info'),
  pdfMore: document.getElementById('pdf-more'),
  pdfJump: document.getElementById('pdf-jump'),
  pdfJumpGo: document.getElementById('pdf-jump-go'),
};

let paragraphs = [];
let groups = [];
let groupOf = [];
let view = { setCurrent() {} }; // active view (text or pdf)
let viewEls = []; // the active view's paragraph elements (for scroll-follow)
let current = -1; // paragraph index (reading position)
let playingGroup = -1; // section index whose music is playing
const codeCache = new Map(); // section index -> Promise<string>
let useLocal = false; // compose music in-browser (WebGPU) instead of via the backend

// Scroll-follow: the current paragraph tracks the one crossing this line.
const READING_LINE = 0.38; // fraction down the viewport
let followScroll = true; // auto-advance the reading position as you scroll
let suppressFollow = false; // true while a manual-nav scroll animates (no feedback loop)
let suppressTimer = null;
let scrollThrottle = null;
let musicTimer = null; // debounce: only generate the section you settle on

// PDF mode state
let pdfDoc = null; // current PDFDocumentProxy
let pdfFrom = 1; // first loaded page
let pdfLoadedTo = 0; // last loaded page
let pdfOverlayEls = []; // growing array of paragraph overlay divs (the pdf view's elements)
let appending = false; // an append batch is in flight
let pdfObserver = null; // IntersectionObserver that auto-loads more pages near the bottom

function status(msg) {
  els.status.textContent = msg;
}

function playingStatus(g) {
  return `Playing section ${g + 1}/${groups.length}  ·  paragraph ${current + 1}/${paragraphs.length}`;
}

// --- music / section engine (view-agnostic) -------------------------------

// Backend composer: POST the section text to the Python /generate endpoint.
async function composeBackend(text, previousCode) {
  const res = await fetch(`${API}/generate`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ paragraph: text, previous_code: previousCode }),
  });
  if (!res.ok) throw new Error(`/generate failed: ${res.status}`);
  return (await res.json()).code;
}

// Boot the in-browser model on demand (first local generation). Idempotent; shows
// download/preparation progress in the status line.
function ensureLocalEngine() {
  return llmLocal.init((p) => {
    const pct = typeof p.progress === 'number' ? ` ${Math.round(p.progress)}%` : '';
    status(`${p.status || 'Loading model…'}${pct}`);
  });
}

function getCode(g) {
  if (codeCache.has(g)) return codeCache.get(g);
  const promise = (async () => {
    const previousCode = codeCache.has(g - 1) ? await codeCache.get(g - 1) : '';
    if (useLocal) {
      await ensureLocalEngine();
      return llmLocal.generate(groups[g].text, previousCode);
    }
    return composeBackend(groups[g].text, previousCode);
  })();
  codeCache.set(g, promise);
  return promise;
}

function prefetch(g) {
  if (g >= 0 && g < groups.length) getCode(g).catch(() => {});
}

const MAX_ATTEMPTS = 3; // the small model occasionally emits invalid Strudel; regenerate

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
      await player.play(code);
      status(playingStatus(g));
      prefetch(g + 1);
      return;
    } catch (err) {
      codeCache.delete(g);
      if (attempt === MAX_ATTEMPTS) status(`Section ${g + 1}: couldn't produce valid music (${err.message})`);
    }
  }
}

// Update highlight + reading position (no music). Manual nav scrolls it to the
// reading line; scroll-follow passes scroll:false (it's already there).
function setReadingPosition(i, scroll) {
  current = i;
  const g = groupOf[i];
  view.setCurrent(i, groups[g].indices);
  if (scroll) scrollToReadingLine(viewEls[i]);
  updateNav();
  return g;
}

// Scroll an element so its top sits at the reading line. Suppress scroll-follow
// during the animation so it doesn't fight the manual jump.
function scrollToReadingLine(el) {
  if (!el) return;
  const top = window.scrollY + el.getBoundingClientRect().top - window.innerHeight * READING_LINE;
  suppressFollow = true;
  clearTimeout(suppressTimer);
  suppressTimer = setTimeout(() => { suppressFollow = false; }, 700);
  window.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
}

// Manual navigation (buttons / arrows / click): jump here and play the section now.
async function goTo(i, { scroll = true } = {}) {
  if (i < 0 || i >= paragraphs.length) return;
  clearTimeout(musicTimer);
  const g = setReadingPosition(i, scroll);
  if (g === playingGroup) {
    status(playingStatus(g));
    prefetch(g + 1);
    return;
  }
  playingGroup = g;
  await playGroup(g);
}

// Scroll-follow: move the highlight now; play its section once you settle there
// (debounced, so scrolling fast through many sections doesn't thrash the generator).
function followTo(i) {
  if (i === current) return;
  const g = setReadingPosition(i, false);
  status(playingStatus(g));
  clearTimeout(musicTimer);
  musicTimer = setTimeout(() => {
    const gg = groupOf[current];
    if (gg !== playingGroup) { playingGroup = gg; playGroup(gg); }
    else prefetch(gg + 1);
  }, 300);
}

// Find the paragraph crossing the reading line (elements are in reading order).
function updateCurrentFromScroll() {
  const vh = window.innerHeight;
  const line = vh * READING_LINE;
  let candidate = -1;
  for (let i = 0; i < viewEls.length; i++) {
    const r = viewEls[i].getBoundingClientRect();
    if (r.bottom < 0) continue; // above the viewport
    if (r.top > vh) break; // below the viewport
    if (r.top <= line) candidate = i; // last paragraph whose top is above the line
    else { if (candidate === -1) candidate = i; break; }
  }
  if (candidate !== -1) followTo(candidate);
}

function onScroll() {
  if (!followScroll || suppressFollow || !player.isReady() || !viewEls.length) return;
  if (scrollThrottle) return; // throttle to ~8/s while scrolling
  scrollThrottle = setTimeout(() => { scrollThrottle = null; updateCurrentFromScroll(); }, 120);
}
window.addEventListener('scroll', onScroll, { passive: true });

function updateNav() {
  const playing = player.isReady();
  els.prev.disabled = !playing || current <= 0;
  els.next.disabled = !playing || current >= paragraphs.length - 1;
  els.stop.disabled = !playing;
}

// Start the audio engine if needed. MUST run inside a user gesture (a button or
// paragraph click) — that's what lets the browser start Web Audio.
async function ensureStarted() {
  if (player.isReady()) return true;
  els.start.disabled = true;
  status('Starting audio…');
  try {
    await player.init();
  } catch (err) {
    status(`Error: ${err.message}`);
    els.start.disabled = false;
    return false;
  }
  els.start.textContent = '▶ Started';
  updateNav();
  return true;
}

// Clicking a paragraph starts from there (so you can resume mid-book, not only
// from the beginning). On the first click it also boots the audio engine.
async function selectParagraph(i) {
  if (await ensureStarted()) goTo(i, { scroll: false }); // you clicked it — don't jump
}

// Install a new document (text or pdf) and reset playback state.
function setDocument(paras, viewObj) {
  paragraphs = paras;
  ({ groups, groupOf } = groupParagraphs(paragraphs, WORDS_PER_SECTION));
  view = viewObj;
  codeCache.clear();
  current = -1;
  playingGroup = -1;
  if (!player.isReady()) {
    els.start.disabled = paragraphs.length === 0;
    els.start.textContent = '▶ Start';
  }
  updateNav();
  if (!paragraphs.length) {
    status('No readable text found.');
  } else if (player.isReady()) {
    goTo(0); // already playing — start the new document right away
  } else {
    status(`${paragraphs.length} paragraphs in ${groups.length} section(s). Press Start, or click where you want to begin.`);
  }
}

// --- views ----------------------------------------------------------------

function loadText(text) {
  els.pdfControls.hidden = true;
  pdfDoc = null;
  if (pdfObserver) pdfObserver.disconnect();
  const paras = splitParagraphs(text);
  const paraEls = renderParagraphs(els.paragraphs, paras, selectParagraph);
  viewEls = paraEls;
  setDocument(paras, { setCurrent: (i, gi) => setHighlight(paraEls, i, gi) });
}

const onPdfSelect = (i) => selectParagraph(i);

function updatePdfHeader() {
  els.pdfInfo.textContent = `Pages ${pdfFrom}–${pdfLoadedTo} of ${pdfDoc.numPages}`;
  els.pdfMore.disabled = pdfLoadedTo >= pdfDoc.numPages;
}

// Fresh load (open / jump-to-page): replace everything, starting at `from`.
async function loadPdfRange(from) {
  from = Math.min(Math.max(1, from), pdfDoc.numPages);
  const to = Math.min(pdfDoc.numPages, from + PAGES_PER_RANGE - 1);
  status(`Rendering pages ${from}–${to}…`);
  try {
    const { paragraphs: paras, overlayEls, hasText } =
      await renderRange(pdfDoc, from, to, els.paragraphs, onPdfSelect);
    if (!hasText) status('This PDF has no extractable text (a scanned image?).');
    pdfFrom = from;
    pdfLoadedTo = to;
    pdfOverlayEls = overlayEls;
    viewEls = pdfOverlayEls;
    setDocument(paras, { setCurrent: (i, gi) => setHighlight(pdfOverlayEls, i, gi) });
    setupSentinel();
    updatePdfHeader();
  } catch (err) {
    status(`Couldn't render the PDF: ${err.message}`);
  }
}

// Append the next batch of pages below — continuous reading, no reset of playback.
async function appendBatch() {
  if (!pdfDoc || appending || pdfLoadedTo >= pdfDoc.numPages) return;
  appending = true;
  els.pdfMore.disabled = true;
  const from = pdfLoadedTo + 1;
  const to = Math.min(pdfDoc.numPages, pdfLoadedTo + PAGES_PER_RANGE);
  try {
    const { overlayEls: newEls, paragraphs: newParas } = await renderRange(
      pdfDoc, from, to, els.paragraphs, onPdfSelect, { append: true, indexOffset: paragraphs.length },
    );
    const oldCount = paragraphs.length;
    pdfOverlayEls.push(...newEls);
    paragraphs.push(...newParas);
    extendGroups(newParas, oldCount);
    pdfLoadedTo = to;
    updateNav();
    updatePdfHeader();
    setupSentinel(); // keep the sentinel below the new pages
  } catch (err) {
    status(`Couldn't load more pages: ${err.message}`);
  } finally {
    appending = false;
  }
}

// Group freshly-appended paragraphs into NEW sections so existing section indices
// (and codeCache) stay valid — a section boundary just falls at the batch edge.
function extendGroups(newParas, oldCount) {
  const { groups: ng, groupOf: ngo } = groupParagraphs(newParas, WORDS_PER_SECTION);
  const baseG = groups.length;
  for (const g of ng) groups.push({ indices: g.indices.map((i) => i + oldCount), text: g.text });
  for (let i = 0; i < ngo.length; i++) groupOf[oldCount + i] = baseG + ngo[i];
}

// A sentinel at the bottom of the rendered pages; when it nears the viewport
// (IntersectionObserver) we auto-append the next batch.
function setupSentinel() {
  let sentinel = document.getElementById('pdf-sentinel');
  if (!sentinel) {
    sentinel = document.createElement('div');
    sentinel.id = 'pdf-sentinel';
  }
  els.paragraphs.appendChild(sentinel); // always the last child
  if (!pdfObserver) {
    pdfObserver = new IntersectionObserver(
      (entries) => { if (entries.some((e) => e.isIntersecting)) appendBatch(); },
      { rootMargin: '600px' },
    );
  }
  pdfObserver.disconnect();
  pdfObserver.observe(sentinel);
}

async function openPdfFile(file) {
  status('Opening PDF…');
  try {
    pdfDoc = await openPdf(file);
  } catch (err) {
    status(`Couldn't open PDF: ${err.message}`);
    return;
  }
  els.pdfControls.hidden = false;
  els.pdfJump.max = pdfDoc.numPages;
  await loadPdfRange(1);
}

// Route a dropped/picked file to the right loader.
async function handleFile(file) {
  if (!file) return;
  const isPdf = file.type === 'application/pdf' || /\.pdf$/i.test(file.name);
  if (isPdf) await openPdfFile(file);
  else loadText(await file.text());
}

// --- wiring ---------------------------------------------------------------

els.load.addEventListener('click', () => loadText(els.textInput.value));
els.fileInput.addEventListener('change', (e) => handleFile(e.target.files[0]));

// Page controls (live in the sticky header). "Load next" appends; the next batch
// also auto-loads as you scroll near the bottom. "Go to page" jumps (replaces).
els.pdfMore.addEventListener('click', () => appendBatch());
const jumpToPage = () => { if (pdfDoc && els.pdfJump.value) loadPdfRange(Number(els.pdfJump.value)); };
els.pdfJumpGo.addEventListener('click', jumpToPage);
els.pdfJump.addEventListener('keydown', (e) => { if (e.key === 'Enter') jumpToPage(); });

// Drag & drop a .pdf or .txt onto the reading area
['dragenter', 'dragover'].forEach((ev) =>
  els.reading.addEventListener(ev, (e) => { e.preventDefault(); els.reading.classList.add('dragover'); }));
['dragleave', 'drop'].forEach((ev) =>
  els.reading.addEventListener(ev, (e) => { e.preventDefault(); if (ev === 'dragleave' && els.reading.contains(e.relatedTarget)) return; els.reading.classList.remove('dragover'); }));
els.reading.addEventListener('drop', (e) => handleFile(e.dataTransfer.files[0]));

els.start.addEventListener('click', async () => { if (await ensureStarted()) goTo(0); });

els.prev.addEventListener('click', () => goTo(current - 1));
els.next.addEventListener('click', () => goTo(current + 1));
els.stop.addEventListener('click', () => {
  player.stop();
  status('Stopped.');
});

followScroll = els.follow.checked;
els.follow.addEventListener('change', () => { followScroll = els.follow.checked; });

// Engine selection (backend vs in-browser WebGPU). Validates WebGPU support, keeps
// the checkbox/localStorage in sync, and re-composes the current section so the
// switch takes effect immediately. The model itself loads lazily on first generation.
async function setEngine(local) {
  if (local && !(await llmLocal.probe())) {
    status('WebGPU not available in this browser — staying on backend mode (try Chrome/Edge).');
    local = false;
  }
  useLocal = local;
  els.engineLocal.checked = local;
  localStorage.setItem('bm-engine', local ? 'local' : 'backend');
  codeCache.clear(); // entries were made by the other engine
  if (player.isReady() && current >= 0) {
    playingGroup = -1; // force playGroup() to re-compose this section
    goTo(current, { scroll: false });
  }
}
els.engineLocal.addEventListener('change', () => setEngine(els.engineLocal.checked));

// Pick the engine on load: ?local=1 / ?engine=local override, else the saved choice.
const engineParams = new URLSearchParams(location.search);
const wantLocal = engineParams.has('local')
  ? engineParams.get('local') !== '0'
  : engineParams.get('engine') === 'local' || localStorage.getItem('bm-engine') === 'local';
if (wantLocal) setEngine(true);

document.addEventListener('keydown', (e) => {
  if (!player.isReady() || e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
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
  .catch(() => status('Paste text, choose a file, or drop a .pdf / .txt here.'));
