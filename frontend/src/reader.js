// Document model + rendering: split prose into paragraphs, group them into
// ~1-minute reading sections, and draw them — marking the current paragraph with
// the blue/purple gutter line (.para.current) and tinting the rest of its
// section (.para.in-group) so you can see which paragraphs share the music.

// A block longer than this (words) is treated as lacking paragraph structure and
// re-chunked into ~TARGET_BLOCK_WORDS pseudo-paragraphs on sentence boundaries.
const MAX_BLOCK_WORDS = 120;
const TARGET_BLOCK_WORDS = 50;

function wordCount(s) {
  return (s.match(/\S+/g) || []).length;
}

// Fallback for punctuation-free text: hard-split a run of words into ~target chunks.
function chunkByWords(text, target) {
  const words = text.match(/\S+/g) || [];
  if (words.length <= target) return [text.trim()];
  const chunks = [];
  for (let i = 0; i < words.length; i += target) chunks.push(words.slice(i, i + target).join(' '));
  return chunks;
}

// Break a long block of prose into ~target-word pseudo-paragraphs, splitting on
// sentence ends so we never cut mid-sentence (with a word-based fallback).
function splitLongBlock(text, target = TARGET_BLOCK_WORDS) {
  const sentences = text.match(/[^.!?]+[.!?]+["')\]]*\s*|[^.!?]+$/g) || [text];
  const blocks = [];
  let cur = '';
  let curWords = 0;
  const flush = () => { if (cur.trim()) blocks.push(cur.trim()); cur = ''; curWords = 0; };
  for (const s of sentences) {
    if (wordCount(s) > target * 2) {       // very long / punctuation-free sentence
      flush();
      chunkByWords(s, target).forEach((c) => blocks.push(c.trim()));
      continue;
    }
    cur += s;
    curWords += wordCount(s);
    if (curWords >= target) flush();
  }
  flush();
  return blocks;
}

// Split prose into reading blocks. Uses blank-line paragraphs when present, but
// auto-splits any block that lacks paragraph structure (a wall of text, or one
// very long paragraph) into ~50-word pseudo-paragraphs on sentence boundaries.
export function splitParagraphs(text) {
  const rawBlocks = text
    .split(/\n\s*\n/)
    .map((block) => block.replace(/\s*\n\s*/g, ' ').trim())
    .filter((block) => block.length > 0);
  const blocks = [];
  for (const b of rawBlocks) {
    if (wordCount(b) > MAX_BLOCK_WORDS) blocks.push(...splitLongBlock(b));
    else blocks.push(b);
  }
  return blocks;
}

// Group consecutive paragraphs into sections of ~`wordsPerGroup` words (about a
// minute of reading). Returns { groups, groupOf } where groups[g] = { indices, text }
// and groupOf[paragraphIndex] = its section index. A single paragraph longer than
// the target becomes its own section.
export function groupParagraphs(paragraphs, wordsPerGroup = 200) {
  const groups = [];
  const groupOf = new Array(paragraphs.length);
  let indices = [];
  let words = 0;
  const flush = () => {
    if (!indices.length) return;
    groups.push({ indices, text: indices.map((i) => paragraphs[i]).join('\n\n') });
    indices = [];
    words = 0;
  };
  paragraphs.forEach((p, i) => {
    groupOf[i] = groups.length; // the index this section will get once flushed
    indices.push(i);
    words += wordCount(p);
    if (words >= wordsPerGroup) flush();
  });
  flush();
  return { groups, groupOf };
}

// Render paragraphs into `container`. `onSelect(index)` fires when one is clicked.
// Returns the array of created elements.
export function renderParagraphs(container, paragraphs, onSelect) {
  container.innerHTML = '';
  return paragraphs.map((text, index) => {
    const el = document.createElement('div');
    el.className = 'para';
    el.textContent = text;
    el.addEventListener('click', () => onSelect(index));
    container.appendChild(el);
    return el;
  });
}

// Mark the current paragraph (gutter line) and tint the rest of its section.
export function setHighlight(elements, currentIndex, groupIndices = []) {
  const inGroup = new Set(groupIndices);
  elements.forEach((el, i) => {
    el.classList.toggle('current', i === currentIndex);
    el.classList.toggle('in-group', inGroup.has(i) && i !== currentIndex);
  });
  elements[currentIndex]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
}
