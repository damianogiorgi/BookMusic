"""Generate ambient Strudel code for a paragraph of prose.

Provider-agnostic: it assembles the system + user messages exactly as the spike
did and hands them to `llm.call_llm`. The `previous_code` argument feeds the
prompt's CONTINUITY mechanism so consecutive paragraphs evolve rather than jump.

Post-checks: similarity vs previous code, basic Strudel shape, and prompt-label
echoes (e.g. literal PARAGRAPH). One regenerate with feedback when needed; always
sanitize before returning so residual labels never reach the player.
"""

import re
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
    "Output only Strudel starting with setcpm( and a stack(...). "
    "No labels, no prose."
)
_ECHO_RETRY_SUFFIX = (
    "\n\nPREVIOUS ATTEMPT echoed prompt labels (e.g. PARAGRAPH / CODE / "
    "PREVIOUS CODE). Output only Strudel code starting with setcpm( — "
    "no labels, no prose."
)

# Labeled lines the tiny model sometimes copies from the user message / few-shots.
# Use [^\S\n] (horizontal whitespace only) after the label so we never swallow the
# following setcpm(...) line — bare \s would match the newline and eat it.
_LABEL_LINE_RE = re.compile(
    r"^\s*(?:PARAGRAPH|PREVIOUS\s+CODE|PREVIOUS\s+ATTEMPT|CODE|STYLE|"
    r"PASSAGE|SCENE|MOOD)\b[^\S\n]*:?[^\n]*$",
    re.IGNORECASE | re.MULTILINE,
)
_BARE_ECHO_LINE_RE = re.compile(
    r"^\s*(?:PARAGRAPH|PREVIOUS\s+CODE|CODE|STYLE|PASSAGE|SCENE)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_ECHO_TOKEN_RE = re.compile(
    r"\b(?:PARAGRAPH|PASSAGE|PREVIOUS\s+CODE)\b|^\s*CODE\s*:?[^\n]*$",
    re.IGNORECASE | re.MULTILINE,
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


def _has_prompt_echo(code: str) -> bool:
    """True if the model leaked prompt labels into the reply."""
    if not code:
        return False
    return bool(_ECHO_TOKEN_RE.search(code) or _LABEL_LINE_RE.search(code))


def _looks_like_strudel(code: str) -> bool:
    """Minimal shape check — full parse happens in the browser player."""
    cleaned = code.replace("```", "").strip().lower()
    return "setcpm(" in cleaned and "stack(" in cleaned


def _sanitize_code(code: str) -> str:
    """Strip fences, prompt-label echoes, and preamble before setcpm(."""
    text = (code or "").strip()
    if not text:
        return text

    text = re.sub(r"^```(?:[a-z]*)\s*\n?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\n?```\s*$", "", text)

    text = _LABEL_LINE_RE.sub("", text)
    text = _BARE_ECHO_LINE_RE.sub("", text)

    # Drop any prose preamble; keep from the first setcpm( onward.
    match = re.search(r"(?im)^\s*setcpm\s*\(", text)
    if match:
        text = text[match.start() :]

    # Residual bare tokens sometimes land inside stack(...) argument lists.
    text = re.sub(r",\s*\bPARAGRAPH\b\s*", ", ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bPARAGRAPH\b\s*,\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bPARAGRAPH\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r",\s*\bPASSAGE\b\s*", ", ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bPASSAGE\b\s*,\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bPASSAGE\b", "", text, flags=re.IGNORECASE)

    text = re.sub(r",\s*,", ",", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def generate(paragraph: str, previous_code: str = "", debug: bool = False) -> str:
    """Return Strudel code for the mood of `paragraph`.

    If `previous_code` is given, the model keeps the same timbre/style and evolves it.
    When the reply is nearly identical to `previous_code`, missing basic Strudel
    shape, or echoes prompt labels, one regenerate runs with feedback — not the
    same prompt. The returned string is always sanitized.
    """
    # PASSAGE: (not PARAGRAPH:) — few-shots used to teach "PARAGRAPH" as a label
    # the model sometimes pasted into the code.
    user = (f"PREVIOUS CODE:\n{previous_code}\n\n" if previous_code else "") + \
           f"PASSAGE: {paragraph}"
    if debug:
        print("SYSTEM PROMPT:", SYSTEM_PROMPT)
        print("USER PROMPT:", user)
    code = call_llm(SYSTEM_PROMPT, user)

    similar = bool(previous_code) and _too_similar(code, previous_code)
    has_echo = _has_prompt_echo(code)
    bad_shape = not _looks_like_strudel(code)
    if similar or has_echo or bad_shape:
        if similar:
            suffix = _SIMILAR_RETRY_SUFFIX
        elif has_echo:
            suffix = _ECHO_RETRY_SUFFIX
        else:
            suffix = _SHAPE_RETRY_SUFFIX
        retry_user = user + suffix
        if debug:
            print("RETRY USER PROMPT:", retry_user)
        code = call_llm(SYSTEM_PROMPT, retry_user)

    return _sanitize_code(code)


if __name__ == "__main__":
    print(generate((Path(__file__).parent / "samples/sample.txt").read_text(), debug=True))
