"""Generate ambient Strudel code for a paragraph of prose.

Experiment B: heuristic mood pick → STYLE/KEY/ENERGY/MOOD slots + one injected
style card + truncated PASSAGE. System prompt stays slim (no 9-example dump).
Similarity / shape retry from try-first (A+C) is unchanged.
"""

from difflib import SequenceMatcher
from pathlib import Path

from .llm import call_llm
from .mood import pick_mood
from .style_cards import style_card

# Load the system prompt relative to this file so cwd doesn't matter.
SYSTEM_PROMPT = (Path(__file__).parent / "prompt.txt").read_text()

# Above this SequenceMatcher ratio vs previous_code, regenerate once with feedback.
SIMILARITY_THRESHOLD = 0.85

# Truncate passage evidence after slots (Experiment B: ~400–600 chars).
PASSAGE_MAX_CHARS = 500

_ENERGY_LABELS = {
    1: "barely-there background",
    2: "very calm background",
    3: "gentle background",
    4: "present but still soft",
    5: "fuller background (still not foreground)",
}

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


def _truncate_passage(paragraph: str, limit: int = PASSAGE_MAX_CHARS) -> str:
    text = (paragraph or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    # Prefer a sentence boundary near the end of the window.
    for sep in (". ", "! ", "? ", "\n"):
        idx = cut.rfind(sep)
        if idx >= int(limit * 0.5):
            return cut[: idx + 1].strip()
    # Fall back to last whitespace so we don't chop mid-word.
    idx = cut.rfind(" ")
    if idx > 0:
        return cut[:idx].strip() + "…"
    return cut.strip() + "…"


def _build_user_message(paragraph: str, previous_code: str = "") -> str:
    mood = pick_mood(paragraph, previous_code)
    energy_note = _ENERGY_LABELS.get(mood.energy, "calm background")
    passage = _truncate_passage(paragraph)
    prev_block = (
        f"PREVIOUS CODE:\n{previous_code}"
        if previous_code
        else "PREVIOUS CODE: (none)"
    )
    return "\n".join(
        [
            f"STYLE: {mood.style}",
            f"KEY: {mood.key}",
            f"ENERGY: {mood.energy}/5 ({energy_note})",
            f"MOOD: {mood.mood_line}",
            "",
            style_card(mood.style),
            "",
            prev_block,
            "",
            f"PASSAGE:\n{passage}",
            "",
            "Output Strudel code only, starting with setcpm(",
        ]
    )


def generate(paragraph: str, previous_code: str = "", debug: bool = False) -> str:
    """Return Strudel code for the mood of `paragraph`.

    Mood is chosen heuristically (no extra LLM call). The model receives compact
    slots + one style card. When the reply is nearly identical to `previous_code`
    (or missing basic Strudel shape), one regenerate runs with feedback.
    """
    user = _build_user_message(paragraph, previous_code)
    if debug:
        mood = pick_mood(paragraph, previous_code)
        print("MOOD PICK:", mood)
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
    sample = Path(__file__).parent.parent / "samples" / "sample.txt"
    print(generate(sample.read_text(), debug=True))
