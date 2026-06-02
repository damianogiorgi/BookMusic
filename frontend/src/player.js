// Drives the official Strudel REPL engine via the @strudel/repl <strudel-editor>
// web component.
//
// We use the full REPL — not the bare @strudel/web bundle — because @strudel/web
// only registers basic synths (sine/sawtooth/…). The REPL auto-loads the same
// sound set as strudel.cc: the gm_* soundfonts, drum samples (bd/hh/rim), piano,
// orchestral samples, etc. That's what makes the music here sound the same as
// when the code is pasted into strudel.cc. The editor UI is hidden; we only use
// its engine (setCode + evaluate + stop), which also supports setcpm natively.

let editor = null;
let ready = false;

// Must be called from within a user gesture (Web Audio autoplay policy).
export async function init() {
  if (ready) return;
  // Resume the audio context inside the calling gesture, just in case the
  // component's own first-click handler hasn't fired yet.
  try { window.getAudioContext && window.getAudioContext().resume(); } catch (e) { /* ignore */ }

  await customElements.whenDefined('strudel-editor');
  const el = document.getElementById('strudel-engine');
  if (!el) throw new Error('<strudel-editor id="strudel-engine"> not found');

  // The StrudelMirror instance (and its repl) appears asynchronously after the
  // element connects; wait for it.
  for (let i = 0; i < 200 && !(el.editor && el.editor.repl); i++) {
    await new Promise((r) => setTimeout(r, 50));
  }
  if (!el.editor) throw new Error('Strudel engine failed to initialise');
  editor = el.editor;
  ready = true;
}

export function isReady() {
  return ready;
}

// Replace the playing pattern with `code`. The REPL records parse errors in
// repl.state rather than throwing, so we surface them as a throw — letting the
// caller retry on the small model's occasional invalid output.
export async function play(code) {
  if (!ready) throw new Error('player not initialised — call init() first');
  const clean = code.replace(/```[a-z]*\n?/gi, '').trim(); // strip stray markdown fences
  editor.setCode(clean);
  await editor.evaluate();
  const state = editor.repl && editor.repl.state;
  const err = state && (state.evalError || state.error);
  if (err) throw new Error(String(err));
}

export function stop() {
  if (ready && editor) editor.stop();
}
