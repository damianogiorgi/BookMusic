"""LLM transport — the only module that knows how we talk to a model.

`call_llm(system, user)` is the single seam to swap providers. Today it speaks to
a local Ollama instance; the `BOOKMUSIC_LLM` env var selects the backend so adding
Bedrock later is one new branch here — no class hierarchy, no changes elsewhere.
"""

import os

# Model + sampling params proven in the spike. think=False is what kills the
# 120-180s reasoning delay; the low temperature and token cap keep output tight.
OLLAMA_MODEL = os.environ.get("BOOKMUSIC_OLLAMA_MODEL", "qwen3.5:4b")
TEMPERATURE = 0.3
NUM_PREDICT = 400


def _call_ollama(system: str, user: str) -> str:
    from ollama import Client

    client = Client()  # defaults to http://localhost:11434
    resp = client.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        think=False,
        options={"temperature": TEMPERATURE, "num_predict": NUM_PREDICT},
    )
    return resp["message"]["content"].strip()


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
