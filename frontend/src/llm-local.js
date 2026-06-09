// Frontend-only "composer" provider: mirrors the backend's
// (paragraph, previous_code) -> code contract, but generates in the browser via a
// WebGPU model (see llm-worker.js). app.js picks this over the /generate fetch when
// the "Run in browser" toggle / ?local=1 is on.
//
// All the heavy lifting (model download + inference) happens in the worker; this
// module is just the main-thread handle: capability check, lazy init with progress,
// and request/reply correlation by id.

let worker = null;
let readyPromise = null; // resolves once the model is loaded (init is idempotent)
let nextId = 1;
const pending = new Map(); // id -> { resolve, reject }

// WebGPU is the hard requirement. Cheap synchronous check first; callers can also
// await the adapter probe below for a more reliable answer.
export function isSupported() {
  return typeof navigator !== 'undefined' && 'gpu' in navigator;
}

// Best-effort confirmation that an adapter is actually obtainable (some browsers
// expose navigator.gpu but fail to hand out an adapter).
export async function probe() {
  if (!isSupported()) return false;
  try {
    return !!(await navigator.gpu.requestAdapter());
  } catch {
    return false;
  }
}

function handleMessage(e) {
  const msg = e.data;
  if (msg.type === 'result') {
    pending.get(msg.id)?.resolve(msg.code);
    pending.delete(msg.id);
  } else if (msg.type === 'error') {
    pending.get(msg.id)?.reject(new Error(msg.error));
    pending.delete(msg.id);
  }
}

// Spin up the worker and load the model. `onProgress({ status, progress })` is
// called with download/preparation updates so the UI can show "Downloading… 42%".
// Idempotent: repeated calls return the same in-flight/settled promise.
export function init(onProgress = () => {}) {
  if (readyPromise) return readyPromise;

  readyPromise = (async () => {
    const systemPrompt = await fetch('prompt.txt').then((r) => {
      if (!r.ok) throw new Error(`couldn't load prompt.txt: ${r.status}`);
      return r.text();
    });

    worker = new Worker(new URL('./llm-worker.js', import.meta.url), { type: 'module' });

    await new Promise((resolve, reject) => {
      const onInit = (e) => {
        const msg = e.data;
        if (msg.type === 'progress') {
          onProgress(msg);
        } else if (msg.type === 'ready') {
          worker.removeEventListener('message', onInit);
          worker.addEventListener('message', handleMessage); // switch to per-request routing
          resolve();
        } else if (msg.type === 'init-error') {
          worker.removeEventListener('message', onInit);
          reject(new Error(msg.error));
        }
      };
      worker.addEventListener('message', onInit);
      worker.addEventListener('error', (err) => reject(new Error(err.message || 'worker error')));
      worker.postMessage({ type: 'init', systemPrompt });
    });
  })();

  // If init fails, clear the cached promise so a later retry can start over.
  readyPromise.catch(() => { readyPromise = null; worker = null; });
  return readyPromise;
}

// Generate Strudel code for one section. Returns a Promise<string>, matching what
// app.js's getCode() expects from the backend path.
export async function generate(paragraph, previousCode = '') {
  if (!readyPromise) throw new Error('local composer not initialised — call init() first');
  await readyPromise;
  const id = nextId++;
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    worker.postMessage({ type: 'generate', id, paragraph, previousCode });
  });
}
