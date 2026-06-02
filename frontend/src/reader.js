// Document model + rendering: split prose into paragraphs, group them into
// ~1-minute reading sections, and draw them — marking the current paragraph with
// the blue/purple gutter line (.para.current) and tinting the rest of its
// section (.para.in-group) so you can see which paragraphs share the music.

// Split on blank lines; collapse hard-wrapped lines inside a block into one line.
export function splitParagraphs(text) {
  return text
    .split(/\n\s*\n/)
    .map((block) => block.replace(/\s*\n\s*/g, ' ').trim())
    .filter((block) => block.length > 0);
}

function wordCount(s) {
  return (s.match(/\S+/g) || []).length;
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
