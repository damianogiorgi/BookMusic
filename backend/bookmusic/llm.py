"""LLM transport — the only module that knows how we talk to a model.

`call_llm(system, user)` is the single seam to swap providers. Today it speaks to
a local Ollama instance; the `BOOKMUSIC_LLM` env var selects the backend so adding
Bedrock later is one new branch here — no class hierarchy, no changes elsewhere.
"""

import os

# Model + sampling params proven in the spike. think=False is what kills the
# 120-180s reasoning delay; the low temperature and token cap keep output tight.
# repeat_penalty + repeat_last_n stop the small model from looping a chord group
# forever (which overruns the token cap and yields truncated, invalid code). The
# loop alternates two chord groups, so the window must be wide enough to see it.
OLLAMA_MODEL = os.environ.get("BOOKMUSIC_OLLAMA_MODEL", "qwen3.5:0.8b")
TEMPERATURE = 0.5
NUM_PREDICT = 400
REPEAT_PENALTY = 1.4
REPEAT_LAST_N = 256


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
        options={
            "temperature": TEMPERATURE,
            "num_predict": NUM_PREDICT,
            "repeat_penalty": REPEAT_PENALTY,
            "repeat_last_n": REPEAT_LAST_N,
        },
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
