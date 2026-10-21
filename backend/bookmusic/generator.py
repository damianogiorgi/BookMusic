"""Generate ambient Strudel code for a paragraph of prose.

Experiment B: heuristic mood pick → STYLE/KEY/ENERGY/MOOD slots + one injected
style card + truncated PASSAGE. System prompt stays slim (no 9-example dump).

Invalid or near-duplicate replies get 1–2 feedback regenerations (reject+retry,
no aggressive sanitizing).
"""

from difflib import SequenceMatcher
from pathlib import Path

from .llm import call_llm
from .mood import pick_mood
from .style_cards import style_card
from .validate import validation_issues

# Load the system prompt relative to this file so cwd doesn't matter.
SYSTEM_PROMPT = (Path(__file__).parent / "prompt.txt").read_text()

# Above this SequenceMatcher ratio vs previous_code, regenerate with feedback.
SIMILARITY_THRESHOLD = 0.85

# Truncate passage evidence after slots (Experiment B: ~400–600 chars).
PASSAGE_MAX_CHARS = 500

# First attempt + up to this many feedback regenerations.
MAX_FEEDBACK_RETRIES = 2

_ENERGY_LABELS = {
    1: "barely-there background",
    2: "very calm background",
    3: "gentle background",
    4: "present but still soft",
    5: "fuller background (still not foreground)",
}


def _normalize_code(code: str) -> str:
    return " ".join(code.split()).lower()


def _too_similar(code: str, previous_code: str) -> bool:
    if not code or not previous_code:
        return False
    ratio = SequenceMatcher(
        None, _normalize_code(code), _normalize_code(previous_code)
    ).ratio()
    return ratio > SIMILARITY_THRESHOLD


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


def _feedback_suffix(issues: list[str]) -> str:
    listed = "; ".join(issues[:6])
    return (
        f"\n\nPREVIOUS ATTEMPT was invalid: {listed}. "
        "Output ONLY valid Strudel starting with setcpm( then stack(. "
        "Chain with .method() only (never comma-separate calls). "
        "Balance () [] <>. Notes like c3/eb3/bb2 only (octaves 1-5). "
        "No prose, labels, backticks, or HTML. Code only."
    )


def generate(paragraph: str, previous_code: str = "", debug: bool = False) -> str:
    """Return Strudel code for the mood of `paragraph`.

    Mood is chosen heuristically (no extra LLM call). The model receives compact
    slots + one style card. Invalid syntax / prompt echoes / near-copies trigger
    up to MAX_FEEDBACK_RETRIES regenerations with a short issue list — the code
    is never aggressively stripped.
    """
    user = _build_user_message(paragraph, previous_code)
    if debug:
        mood = pick_mood(paragraph, previous_code)
        print("MOOD PICK:", mood)
        print("SYSTEM PROMPT:", SYSTEM_PROMPT)
        print("USER PROMPT:", user)

    code = call_llm(SYSTEM_PROMPT, user)

    for attempt in range(MAX_FEEDBACK_RETRIES):
        issues = list(validation_issues(code))
        if previous_code and _too_similar(code, previous_code):
            issues.insert(0, "too similar to previous code")
        if not issues:
            break
        suffix = _feedback_suffix(issues)
        if debug:
            print(f"VALIDITY RETRY {attempt + 1}/{MAX_FEEDBACK_RETRIES}:", issues)
            print("RETRY SUFFIX:", suffix.strip())
        code = call_llm(SYSTEM_PROMPT, user + suffix)

    return code


if __name__ == "__main__":
    sample = Path(__file__).parent.parent / "samples" / "sample.txt"
    print(generate(sample.read_text(), debug=True))
