"""LLM transport — the only module that knows how we talk to a model.

`call_llm(system, user)` is the single seam to swap providers. Today it speaks to
a local Ollama instance; the `BOOKMUSIC_LLM` env var selects the backend so adding
Bedrock later is one new branch here — no class hierarchy, no changes elsewhere.
"""

import os

# Sampling params. Keep options MINIMAL: the Qwen3.x Modelfiles already bake in
# a presence_penalty, and adding our own repeat_penalty on top pushes the model
# into token-salad. Disabling "thinking" (in _call_ollama) is what actually keeps
# the reply to clean code; a low temperature + token cap keep it tight.
OLLAMA_MODEL = os.environ.get("BOOKMUSIC_OLLAMA_MODEL", "qwen3.5:0.8b")
TEMPERATURE = 0.5
NUM_PREDICT = 512


def _call_ollama(system: str, user: str) -> str:
    # We POST to /api/chat directly instead of using the ollama-python client,
    # because the client's think=False is NOT honored by newer Ollama servers
    # (0.30.x default Qwen3 "thinking" ON). When thinking leaks it floods the
    # reply with rambling prose and the code is unusable. The top-level
    # "think": false below reliably disables it.
    import re

    import httpx

    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    if not host.startswith("http"):
        host = "http://" + host
    body = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "think": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "options": {
            "temperature": TEMPERATURE,
            "num_predict": NUM_PREDICT,
        },
    }
    resp = httpx.post(f"{host.rstrip('/')}/api/chat", json=body, timeout=180)
    resp.raise_for_status()
    content = resp.json()["message"]["content"]
    # Defensive: drop any stray <think>…</think> if a model ignores think=false.
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S)
    return content.strip()


def _call_bedrock(system: str, user: str) -> str:
    # Future: API Gateway + Lambda + Bedrock. Wire boto3 bedrock-runtime here and
    # map system/user onto the chosen model's request shape.
    raise NotImplementedError("Bedrock backend not implemented yet")


_BACKENDS = {
    "ollama": _call_ollama,
    "bedrock": _call_bedrock,
}


def call_llm(system: str, user: str) -> str:
    """Send a system+user prompt to the configured model, return the raw reply."""
    backend = os.environ.get("BOOKMUSIC_LLM", "ollama").lower()
    try:
        impl = _BACKENDS[backend]
    except KeyError:
        raise ValueError(
            f"Unknown BOOKMUSIC_LLM={backend!r}; expected one of {sorted(_BACKENDS)}"
        )
    return impl(system, user)
