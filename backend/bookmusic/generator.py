"""Generate ambient Strudel code for a paragraph of prose.

Provider-agnostic: it assembles the system + user messages exactly as the spike
did and hands them to `llm.call_llm`. The `previous_code` argument feeds the
prompt's CONTINUITY mechanism so consecutive paragraphs evolve rather than jump.
A lightweight similarity guard retries once with feedback when the model clones
the previous section's code.
"""

from difflib import SequenceMatcher
from pathlib import Path

from .llm import call_llm

# Load the system prompt relative to this file so cwd doesn't matter.
SYSTEM_PROMPT = (Path(__file__).parent / "prompt.txt").read_text()

# Above this SequenceMatcher ratio vs previous_code, regenerate once with feedback.
SIMILARITY_THRESHOLD = 0.85

_SIMILAR_RETRY_SUFFIX = (
    "\n\nPREVIOUS ATTEMPT was too similar to PREVIOUS CODE. "
    "Write fresh notes/harmony/root/tempo and density. Code only."
)
_SHAPE_RETRY_SUFFIX = (
    "\n\nPREVIOUS ATTEMPT was invalid or incomplete. "
    "Output only Strudel starting with setcpm( and a stack(...)."
)


def _normalize_code(code: str) -> str:
    return " ".join(code.split()).lower()


def _too_similar(code: str, previous_code: str) -> bool:
    if not code or not previous_code:
        return False
    ratio = SequenceMatcher(
        None, _normalize_code(code), _normalize_code(previous_code)
    ).ratio()
    return ratio > SIMILARITY_THRESHOLD


def _looks_like_strudel(code: str) -> bool:
    """Minimal shape check — full parse happens in the browser player."""
    cleaned = code.replace("```", "").strip().lower()
    return "setcpm(" in cleaned and "stack(" in cleaned


def generate(paragraph: str, previous_code: str = "", debug: bool = False) -> str:
    """Return Strudel code for the mood of `paragraph`.

    If `previous_code` is given, the model keeps the same timbre/style and evolves it.
    When the reply is nearly identical to `previous_code` (or missing basic Strudel
    shape), one regenerate runs with an explicit feedback suffix — not the same prompt.
    """
    user = (f"PREVIOUS CODE:\n{previous_code}\n\n" if previous_code else "") + \
           f"PARAGRAPH: {paragraph}"
    if debug:
        print("SYSTEM PROMPT:", SYSTEM_PROMPT)
        print("USER PROMPT:", user)
    code = call_llm(SYSTEM_PROMPT, user)

    similar = bool(previous_code) and _too_similar(code, previous_code)
    bad_shape = not _looks_like_strudel(code)
    if similar or bad_shape:
        # Prefer the similarity message when cloning previous; otherwise ask for shape.
        suffix = _SIMILAR_RETRY_SUFFIX if similar else _SHAPE_RETRY_SUFFIX
        retry_user = user + suffix
        if debug:
            print("RETRY USER PROMPT:", retry_user)
        code = call_llm(SYSTEM_PROMPT, retry_user)

    return code


if __name__ == "__main__":
    print(generate((Path(__file__).parent / "samples/sample.txt").read_text(), debug=True))
