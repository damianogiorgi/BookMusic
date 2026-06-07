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

// Same-origin when served by uvicorn; fall back to localhost when opened as a file.
const API = location.protocol === 'file:' ? 'http://localhost:8000' : '';

const WORDS_PER_SECTION = 200; // ~1 minute of reading at ~200 words/min
const PAGES_PER_RANGE = 10; // how many PDF pages to render at once

const els = {
  start: document.getElementById('start'),
  prev: document.getElementById('prev'),
  next: document.getElementById('next'),
  stop: document.getElementById('stop'),
  status: document.getElementById('status'),
  reading: document.getElementById('reading'),
  paragraphs: document.getElementById('paragraphs'),
  textInput: document.getElementById('text-input'),
  fileInput: document.getElementById('file-input'),
  load: document.getElementById('load'),
  pdfControls: document.getElementById('pdf-controls'),
  pdfFrom: document.getElementById('pdf-from'),
  pdfTo: document.getElementById('pdf-to'),
  pdfLoad: document.getElementById('pdf-load'),
  pdfPrev: document.getElementById('pdf-prev-range'),
  pdfNext: document.getElementById('pdf-next-range'),
  pdfInfo: document.getElementById('pdf-info'),
};

let paragraphs = [];
let groups = [];
let groupOf = [];
let view = { setCurrent() {} }; // active view (text or pdf)
let current = -1; // paragraph index (reading position)
let playingGroup = -1; // section index whose music is playing
const codeCache = new Map(); // section index -> Promise<string>

let pdfDoc = null; // current PDFDocumentProxy (pdf mode only)

function status(msg) {
  els.status.textContent = msg;
}

function playingStatus(g) {
  return `Playing section ${g + 1}/${groups.length}  ·  paragraph ${current + 1}/${paragraphs.length}`;
}

// --- music / section engine (view-agnostic) -------------------------------

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

// Move the reading position. Music only changes at section borders.
async function goTo(paraIndex) {
  if (paraIndex < 0 || paraIndex >= paragraphs.length) return;
  current = paraIndex;
  const g = groupOf[paraIndex];
  view.setCurrent(current, groups[g].indices);
  updateNav();

  if (g === playingGroup) {
    status(playingStatus(g));
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
    status(`${paragraphs.length} paragraphs in ${groups.length} section(s). Press Start.`);
  }
}

// --- views ----------------------------------------------------------------

function loadText(text) {
  els.pdfControls.hidden = true;
  pdfDoc = null;
  const paras = splitParagraphs(text);
  const paraEls = renderParagraphs(els.paragraphs, paras, (i) => { if (player.isReady()) goTo(i); });
  setDocument(paras, { setCurrent: (i, gi) => setHighlight(paraEls, i, gi) });
}

async function loadPdfRange(from, to) {
  from = Math.max(1, from);
  to = Math.min(pdfDoc.numPages, to);
  els.pdfFrom.value = from;
  els.pdfTo.value = to;
  els.pdfInfo.textContent = `of ${pdfDoc.numPages}`;
  els.pdfPrev.disabled = from <= 1;
  els.pdfNext.disabled = to >= pdfDoc.numPages;
  status(`Rendering pages ${from}–${to}…`);
  try {
    const { paragraphs: paras, overlayEls, hasText } = await renderRange(
      pdfDoc, from, to, els.paragraphs, (i) => { if (player.isReady()) goTo(i); },
    );
    if (!hasText) status('This PDF has no extractable text (a scanned image?).');
    setDocument(paras, { setCurrent: (i, gi) => setHighlight(overlayEls, i, gi) });
  } catch (err) {
    status(`Couldn't render the PDF: ${err.message}`);
  }
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
  await loadPdfRange(1, Math.min(PAGES_PER_RANGE, pdfDoc.numPages));
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

// Page-range controls
els.pdfLoad.addEventListener('click', () => {
  if (pdfDoc) loadPdfRange(Number(els.pdfFrom.value), Number(els.pdfTo.value));
});
els.pdfPrev.addEventListener('click', () => {
  if (!pdfDoc) return;
  const size = Number(els.pdfTo.value) - Number(els.pdfFrom.value) + 1;
  const from = Math.max(1, Number(els.pdfFrom.value) - size);
  loadPdfRange(from, from + size - 1);
});
els.pdfNext.addEventListener('click', () => {
  if (!pdfDoc) return;
  const size = Number(els.pdfTo.value) - Number(els.pdfFrom.value) + 1;
  const from = Number(els.pdfTo.value) + 1;
  loadPdfRange(from, from + size - 1);
});

// Drag & drop a .pdf or .txt onto the reading area
['dragenter', 'dragover'].forEach((ev) =>
  els.reading.addEventListener(ev, (e) => { e.preventDefault(); els.reading.classList.add('dragover'); }));
['dragleave', 'drop'].forEach((ev) =>
  els.reading.addEventListener(ev, (e) => { e.preventDefault(); if (ev === 'dragleave' && els.reading.contains(e.relatedTarget)) return; els.reading.classList.remove('dragover'); }));
els.reading.addEventListener('drop', (e) => handleFile(e.dataTransfer.files[0]));

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
