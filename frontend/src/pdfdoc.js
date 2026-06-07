// PDF reading view: render PDF pages to <canvas>, extract paragraphs + their
// bounding boxes from the text layer, and lay a transparent ".pdf-para" overlay
// <div> over each paragraph. Those overlay divs are what the shared setHighlight()
// marks (.current = gutter line, .in-group = section tint), so the music/section
// engine in app.js is reused unchanged. Single-column, digitally-generated PDFs.

const PDFJS_VERSION = '5.7.284';
const CDN = `https://cdn.jsdelivr.net/npm/pdfjs-dist@${PDFJS_VERSION}/build`;

let pdfjsLib = null;

async function loadPdfjs() {
  if (pdfjsLib) return pdfjsLib;
  pdfjsLib = await import(/* @vite-ignore */ `${CDN}/pdf.min.mjs`);
  pdfjsLib.GlobalWorkerOptions.workerSrc = `${CDN}/pdf.worker.min.mjs`;
  return pdfjsLib;
}

// Open a File/Blob and return a PDFDocumentProxy.
export async function openPdf(file) {
  const lib = await loadPdfjs();
  const data = await file.arrayBuffer();
  return lib.getDocument({ data }).promise;
}

// Render pages [from..to] into `container` (cleared first). Returns:
//   { paragraphs: string[], overlayEls: HTMLDivElement[], hasText: boolean }
// `onSelect(index)` fires when a paragraph overlay is clicked.
export async function renderRange(pdfDoc, from, to, container, onSelect) {
  const lib = await loadPdfjs();
  container.innerHTML = '';
  const targetW = Math.max(320, container.clientWidth || 700);

  const paragraphs = [];
  const overlayEls = [];
  let hasText = false;

  for (let n = from; n <= to; n++) {
    const page = await pdfDoc.getPage(n);
    const base = page.getViewport({ scale: 1 });
    const scale = Math.min(2, targetW / base.width);
    const viewport = page.getViewport({ scale });

    const wrap = document.createElement('div');
    wrap.className = 'pdf-page';
    wrap.style.width = `${Math.floor(viewport.width)}px`;
    wrap.style.height = `${Math.floor(viewport.height)}px`;

    const canvas = document.createElement('canvas');
    canvas.width = Math.floor(viewport.width);
    canvas.height = Math.floor(viewport.height);
    wrap.appendChild(canvas);

    const overlay = document.createElement('div');
    overlay.className = 'pdf-overlay';
    wrap.appendChild(overlay);
    container.appendChild(wrap);

    await page.render({ canvasContext: canvas.getContext('2d'), viewport }).promise;

    const tc = await page.getTextContent();
    if (tc.items.some((i) => i.str && i.str.trim())) hasText = true;

    for (const para of extractParagraphs(tc, viewport, lib)) {
      const div = document.createElement('div');
      div.className = 'pdf-para';
      div.style.left = `${para.bbox.x}px`;
      div.style.top = `${para.bbox.y}px`;
      div.style.width = `${para.bbox.w}px`;
      div.style.height = `${para.bbox.h}px`;
      const index = paragraphs.length;
      div.addEventListener('click', () => onSelect && onSelect(index));
      overlay.appendChild(div);
      paragraphs.push(para.text);
      overlayEls.push(div);
    }
  }
  return { paragraphs, overlayEls, hasText };
}

// --- text-layer heuristics ------------------------------------------------

// Turn a page's text items into paragraphs with viewport-space bounding boxes.
function extractParagraphs(textContent, viewport, lib) {
  // 1) place each item in viewport (CSS px) space
  const items = [];
  for (const it of textContent.items) {
    if (!it.str || !it.str.trim()) continue;
    const t = lib.Util.transform(viewport.transform, it.transform);
    const fontH = Math.hypot(t[2], t[3]) || (it.height || 10) * viewport.scale;
    const x = t[4];
    const bottom = t[5];
    items.push({ str: it.str, x, top: bottom - fontH, bottom, h: fontH, w: (it.width || 0) * viewport.scale, right: x + (it.width || 0) * viewport.scale });
  }
  if (!items.length) return [];

  // 2) group items into lines by vertical position (items arrive in reading order)
  const lines = [];
  let cur = null;
  for (const it of items) {
    if (cur && Math.abs(it.top - cur.top) <= cur.h * 0.6) {
      cur.items.push(it);
      cur.top = Math.min(cur.top, it.top);
      cur.bottom = Math.max(cur.bottom, it.bottom);
      cur.left = Math.min(cur.left, it.x);
      cur.right = Math.max(cur.right, it.right);
      cur.h = Math.max(cur.h, it.h);
    } else {
      cur = { items: [it], top: it.top, bottom: it.bottom, left: it.x, right: it.right, h: it.h };
      lines.push(cur);
    }
  }
  for (const ln of lines) ln.text = joinLine(ln.items);

  // 3) group lines into paragraphs by vertical gap
  const heights = lines.map((l) => l.bottom - l.top).sort((a, b) => a - b);
  const medianH = heights[Math.floor(heights.length / 2)] || 12;
  const paras = [];
  let p = null;
  let prev = null;
  for (const ln of lines) {
    if (!ln.text || /^\d+$/.test(ln.text)) continue; // skip blanks + page numbers
    const gap = prev ? ln.top - prev.bottom : 0;
    if (!p || gap > medianH * 0.9) {
      p = { lines: [], left: ln.left, top: ln.top, right: ln.right, bottom: ln.bottom };
      paras.push(p);
    }
    p.lines.push(ln);
    p.left = Math.min(p.left, ln.left);
    p.top = Math.min(p.top, ln.top);
    p.right = Math.max(p.right, ln.right);
    p.bottom = Math.max(p.bottom, ln.bottom);
    prev = ln;
  }

  // 4) build paragraph text (de-hyphenating line-end hyphens) + bbox
  return paras
    .map((pp) => ({
      text: dehyphenate(pp.lines.map((l) => l.text)),
      bbox: { x: pp.left, y: pp.top, w: pp.right - pp.left, h: pp.bottom - pp.top },
    }))
    .filter((pp) => pp.text.length > 0);
}

// Join the items of one line, inserting a space across notable x-gaps.
function joinLine(lineItems) {
  lineItems.sort((a, b) => a.x - b.x);
  let s = '';
  let prev = null;
  for (const it of lineItems) {
    if (prev && it.x - prev.right > prev.h * 0.25 && !/\s$/.test(s) && !/^\s/.test(it.str)) s += ' ';
    s += it.str;
    prev = it;
  }
  return s.replace(/\s+/g, ' ').trim();
}

// Join lines into one string; if a line ends with a hyphen, glue the next word on.
function dehyphenate(lineTexts) {
  let text = '';
  lineTexts.forEach((t, i) => {
    if (i === 0) { text = t; return; }
    if (/[-­]$/.test(text)) text = text.replace(/[-­]$/, '') + t;
    else text += ` ${t}`;
  });
  return text.replace(/\s+/g, ' ').trim();
}
