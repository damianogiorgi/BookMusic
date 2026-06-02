// Thin wrapper around the @strudel/web globals (initStrudel / evaluate / hush).
// Phase 2 uses a "simple swap": evaluate() replaces the running pattern, Strudel
// aligns it to the next cycle, and the pads' long release + reverb tails cover the
// seam. The optional master-gain dip is left as a hook for later refinement.

let ready = false;

// Must be called from within a user gesture (Web Audio autoplay policy).
export async function init() {
  if (ready) return;
  if (typeof window.initStrudel !== 'function') {
    throw new Error('@strudel/web not loaded (window.initStrudel missing)');
  }
  await window.initStrudel();
  ready = true;
}

export function isReady() {
  return ready;
}

// @strudel/web (v1) doesn't expose setcpm/setcps as globals the way the full REPL
// does, so the model's leading `setcpm(N)` line throws "setcpm is not defined".
// Rewrite it into an equivalent chained `.cpm(N)` / `.cps(N)` on the pattern,
// which @strudel/web does support — preserving the tempo the model chose.
export function normalizeCode(code) {
  code = code.replace(/```[a-z]*\n?/gi, '').trim(); // strip any stray markdown fences
  let cpm = null;
  let cps = null;
  code = code.replace(/^[ \t]*setcpm\(\s*([\d.]+)\s*\)\s*;?[ \t]*\n?/m, (_, n) => { cpm = n; return ''; });
  code = code.replace(/^[ \t]*setcps\(\s*([\d.]+)\s*\)\s*;?[ \t]*\n?/m, (_, n) => { cps = n; return ''; });
  code = code.trim();
  if (cpm !== null) code = `(${code}).cpm(${cpm})`;
  else if (cps !== null) code = `(${code}).cps(${cps})`;
  return code;
}

// Swap the currently-playing pattern for `code`.
export async function play(code) {
  if (!ready) throw new Error('player not initialised — call init() first');
  await window.evaluate(normalizeCode(code));
}

export function stop() {
  if (ready && typeof window.hush === 'function') window.hush();
}
