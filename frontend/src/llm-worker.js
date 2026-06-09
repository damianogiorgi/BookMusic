// In-browser "composer": runs the same small Qwen model the Python backend uses,
// but entirely in the browser via transformers.js + WebGPU — no Ollama, no /generate.
//
// This is a MODULE web worker (spawned with { type: 'module' }) so it can `import`
// transformers.js from a CDN and, crucially, keep the ~hundreds-of-ms-per-token
// inference OFF the main thread — the reader can keep scrolling and Strudel can
// keep scheduling audio while a section is being composed.
//
// Protocol (postMessage):
//   main -> worker  { type: 'init', systemPrompt }
//   worker -> main  { type: 'progress', status, progress }   // model download %
//   worker -> main  { type: 'ready' } | { type: 'init-error', error }
//   main -> worker  { type: 'generate', id, paragraph, previousCode }
//   worker -> main  { type: 'result', id, code } | { type: 'error', id, error }

import {
  env,
  AutoTokenizer,
  AutoModelForCausalLM,
  TextGenerationPipeline,
} from 'https://cdn.jsdelivr.net/npm/@huggingface/transformers@4.2.0';

// Same family as the backend's ollama `qwen3.5:0.8b` — verified working end-to-end
// (downloads, runs on WebGPU, emits valid playing Strudel).
//
// NOTE: 'onnx-community/Qwen3-0.6B-ONNX' was tried as a lighter/faster option but
// would NOT run on WebGPU in testing (Chrome/Electron 146): dtype 'q4f16' threw an
// ONNX Runtime buffer error / crashed the renderer, and dtype 'q4' OOM'd
// (std::bad_alloc). The 0.8B q4f16 ran fine. Revisit the 0.6B if a newer
// transformers.js / onnxruntime-web fixes its WebGPU graph.
const MODEL_ID = 'onnx-community/Qwen3.5-0.8B-ONNX';
const DTYPE = 'q4f16';

// Match the backend sampling (backend/bookmusic/llm.py): low temp + 512-token cap.
const TEMPERATURE = 0.5;
const MAX_NEW_TOKENS = 512;

let systemPrompt = '';
let tokenizer = null;
let model = null;
let pipe = null;

// One GPU, and transformers.js generation isn't safe to call concurrently — so we
// serialize: every `generate` request is appended to this promise chain.
let queue = Promise.resolve();

// transformers.js caches model files in the browser Cache Storage after the first
// download. Let it use the default Hugging Face Hub.
env.allowLocalModels = false;

async function loadModel() {
  const progress_callback = (p) => {
    // p: { status, file, progress, loaded, total }
    if (p.status === 'progress' && p.total) {
      self.postMessage({
        type: 'progress',
        status: `Downloading model (${p.file || ''})`,
        progress: p.progress, // 0..100
      });
    } else if (p.status === 'ready' || p.status === 'done') {
      self.postMessage({ type: 'progress', status: 'Preparing model…' });
    }
  };

  tokenizer = await AutoTokenizer.from_pretrained(MODEL_ID, { progress_callback });
  model = await AutoModelForCausalLM.from_pretrained(MODEL_ID, {
    device: 'webgpu',
    dtype: DTYPE,
    progress_callback,
  });
  pipe = new TextGenerationPipeline({ task: 'text-generation', model, tokenizer });
}

// Reproduce the backend's user message exactly (backend/bookmusic/generator.py):
//   PREVIOUS CODE:\n<code>\n\n  (only if there was previous code)
//   PARAGRAPH: <text>
function buildUserMessage(paragraph, previousCode) {
  const prev = previousCode ? `PREVIOUS CODE:\n${previousCode}\n\n` : '';
  return `${prev}PARAGRAPH: ${paragraph}`;
}

async function generate(paragraph, previousCode) {
  const messages = [
    { role: 'system', content: systemPrompt },
    { role: 'user', content: buildUserMessage(paragraph, previousCode) },
  ];

  // Qwen3.x is a hybrid reasoning model. We must disable "thinking" (the backend
  // does this with Ollama's think:false) — otherwise the small model spends its
  // 512-token budget on a <think> ramble and emits no usable code. We apply the
  // chat template ourselves so we can pass enable_thinking:false.
  const prompt = tokenizer.apply_chat_template(messages, {
    tokenize: false,
    add_generation_prompt: true,
    enable_thinking: false,
  });

  const t0 = performance.now();
  const out = await pipe(prompt, {
    max_new_tokens: MAX_NEW_TOKENS,
    do_sample: true,
    temperature: TEMPERATURE,
    return_full_text: false, // give us only the newly generated text
  });
  const ms = Math.round(performance.now() - t0);

  let text = out?.[0]?.generated_text ?? '';
  if (typeof text !== 'string') {
    // Some builds return the chat array; take the last assistant turn's content.
    text = Array.isArray(text) ? (text.at(-1)?.content ?? '') : String(text);
  }
  // Defensive, like the backend: strip any stray <think>…</think>. Markdown fences
  // are stripped later in player.js before evaluation.
  const code = text.replace(/<think>[\s\S]*?<\/think>/g, '').trim();
  return { code, ms };
}

self.addEventListener('message', async (e) => {
  const msg = e.data;

  if (msg.type === 'init') {
    systemPrompt = msg.systemPrompt || '';
    try {
      await loadModel();
      self.postMessage({ type: 'ready' });
    } catch (err) {
      self.postMessage({ type: 'init-error', error: String(err?.message || err) });
    }
    return;
  }

  if (msg.type === 'generate') {
    const { id, paragraph, previousCode } = msg;
    // Chain onto the queue so generations run one at a time, in order.
    queue = queue.then(async () => {
      try {
        const { code, ms } = await generate(paragraph, previousCode);
        self.postMessage({ type: 'result', id, code, ms });
      } catch (err) {
        self.postMessage({ type: 'error', id, error: String(err?.message || err) });
      }
    });
  }
});
