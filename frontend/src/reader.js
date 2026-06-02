// Document model + rendering: split prose into paragraphs and draw them, marking
// the current one with the blue/purple gutter line (CSS .para.current).

// Split on blank lines; collapse hard-wrapped lines inside a block into one line.
export function splitParagraphs(text) {
  return text
    .split(/\n\s*\n/)
    .map((block) => block.replace(/\s*\n\s*/g, ' ').trim())
    .filter((block) => block.length > 0);
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

// Move the highlight to `index` and scroll it into view.
export function setCurrent(elements, index) {
  elements.forEach((el, i) => el.classList.toggle('current', i === index));
  elements[index]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
}
