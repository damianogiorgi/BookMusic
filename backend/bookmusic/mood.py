"""Heuristic mood → STYLE / KEY / ENERGY for Experiment B.

Regex/keyword lexicon pilot — no extra LLM call. Keeps the tiny model to a
single code-generation request with compressed slots in the user message.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Canonical style ids used in style cards + user slots.
STYLES = (
    "AMBIENT",
    "LOFI",
    "CHILLHOP",
    "WARM_PIANO",
    "DREAMY",
    "TENSE",
    "HAPPY",
    "EPIC",
    "ANGER",
)

# (style, weight, keywords) — each keyword is matched as a whole word / stem.
# Higher weight = stronger signal per hit. First match of each keyword scores once.
_STYLE_LEXICON: list[tuple[str, int, tuple[str, ...]]] = [
    (
        "ANGER",
        4,
        ("fury", "furious", "rage", "anger", "angry", "violent", "slammed", "hate", "wrath", "raging"),
    ),
    (
        "TENSE",
        3,
        (
            "tense", "fear", "fearful", "danger", "dangerous", "dread", "threat",
            "creeping", "hush", "terror", "afraid", "uneasy", "suspicious", "ominous",
        ),
    ),
    (
        "EPIC",
        3,
        (
            "heroic", "triumphant", "army", "kingdom", "empire", "awe", "magnificent",
            "glory", "crested", "vast", "legendary", "conquest",
        ),
    ),
    (
        "DREAMY",
        3,
        (
            "wonder", "magic", "magical", "surreal", "dream", "dreamy", "dreaming",
            "mirror", "shimmer", "ethereal", "fairy", "enchant", "starlight", "unreal",
        ),
    ),
    (
        "HAPPY",
        3,
        (
            "happy", "cheerful", "cheer", "laugh", "laughing", "laughter", "joy",
            "joyful", "playful", "sunshine", "upbeat", "carefree", "celebrate", "delight",
        ),
    ),
    (
        "WARM_PIANO",
        3,
        (
            "tender", "intimate", "grief", "photograph", "reflective", "melancholy",
            "longing", "remember", "remembered", "mourning", "sorrowful",
        ),
    ),
    (
        "LOFI",
        2,
        (
            "rain", "rainy", "cafe", "coffee", "cozy", "nostalgic", "nostalgia",
            "everyday", "bittersweet", "window", "comfortable", "drizzle", "apartment",
        ),
    ),
    (
        "CHILLHOP",
        2,
        (
            "jazz", "city", "late-night", "wistful", "bar", "neon", "midnight",
            "urban", "streetlight", "smoky",
        ),
    ),
    (
        "AMBIENT",
        2,
        (
            "calm", "lonely", "alone", "dusk", "quiet", "atmosphere", "mist",
            "fog", "stillness", "distant", "empty",
        ),
    ),
]

_MODE_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("phrygian", ("tense", "danger", "fear", "rage", "fury", "dark")),
    ("lydian", ("wonder", "magic", "surreal", "dream", "shimmer")),
    ("minor", ("sad", "sorrow", "grief", "lonely", "melancholy", "cry")),
    ("dorian", ("mystery", "mysterious", "shadow", "forest", "mist")),
    ("major", ("happy", "joy", "sunshine", "cheer", "laugh", "warm")),
]

_DEFAULT_KEY = {
    "AMBIENT": "G minor",
    "LOFI": "D minor",
    "CHILLHOP": "D dorian",
    "WARM_PIANO": "A minor",
    "DREAMY": "C lydian",
    "TENSE": "C phrygian",
    "HAPPY": "C major",
    "EPIC": "C major",
    "ANGER": "C phrygian",
}

_ROOTS = ("C", "D", "E", "F", "G", "A", "Bb")


@dataclass(frozen=True)
class MoodPick:
    style: str
    key: str
    energy: int  # 1–5
    mood_line: str
    scores: dict[str, int]


def _word_hit(text: str, keyword: str) -> bool:
    """Match keyword as a word; allow simple prefixes (enchant→enchanted)."""
    if keyword == "late-night":
        return bool(re.search(r"\blate[\s-]?night\b", text, re.IGNORECASE))
    # Stem-ish: keyword as prefix of a word, min length 4 to avoid 'a'/'joy' false flex
    if len(keyword) >= 4:
        return bool(re.search(rf"\b{re.escape(keyword)}\w*\b", text, re.IGNORECASE))
    return bool(re.search(rf"\b{re.escape(keyword)}\b", text, re.IGNORECASE))


def score_styles(paragraph: str) -> tuple[dict[str, int], list[str]]:
    text = paragraph or ""
    scores = {s: 0 for s in STYLES}
    matched: list[str] = []
    for style, weight, keywords in _STYLE_LEXICON:
        for kw in keywords:
            if _word_hit(text, kw):
                scores[style] += weight
                if kw not in matched:
                    matched.append(kw)
    return scores, matched


def infer_style_from_code(previous_code: str) -> str | None:
    """Best-effort style from instruments in PREVIOUS CODE (for continuity)."""
    if not previous_code:
        return None
    code = previous_code.lower()
    if "gm_electric_guitar_jazz" in code or "gm_acoustic_guitar_nylon" in code:
        return "CHILLHOP"
    if "gm_vibraphone" in code or "gm_celesta" in code or "gm_music_box" in code:
        return "DREAMY"
    if "gm_brass_section" in code or "gm_string_ensemble_1" in code or "gm_french_horn" in code:
        return "EPIC"
    if re.search(r'\.sound\(["\']piano["\']\)', code):
        return "WARM_PIANO"
    if "gm_epiano1" in code:
        if re.search(r'scale\(["\'][^"\']*major', code):
            return "HAPPY"
        return "LOFI"
    if "sawtooth" in code:
        if "bd ~ bd ~" in code:
            return "ANGER"
        return "TENSE"
    if "gm_pad_warm" in code or "gm_synth_strings_1" in code:
        return "AMBIENT"
    return None


def _pick_key(style: str, paragraph: str) -> str:
    text = paragraph or ""
    mode = None
    for mode_name, keywords in _MODE_HINTS:
        if any(_word_hit(text, kw) for kw in keywords):
            mode = mode_name
            break
    default = _DEFAULT_KEY.get(style, "C major")
    root = _ROOTS[sum(map(ord, text[:80])) % len(_ROOTS)]
    if style in ("TENSE", "ANGER"):
        return f"{root} phrygian"
    if style == "DREAMY":
        return f"{root} lydian"
    if mode is None:
        mode_part = default.split(None, 1)[-1] if " " in default else "minor"
        return f"{root} {mode_part}"
    return f"{root} {mode}"


def _pick_energy(style: str, paragraph: str, style_score: int) -> int:
    text = paragraph or ""
    energy = {
        "AMBIENT": 2,
        "LOFI": 2,
        "CHILLHOP": 3,
        "WARM_PIANO": 2,
        "DREAMY": 2,
        "TENSE": 3,
        "HAPPY": 4,
        "EPIC": 4,
        "ANGER": 4,
    }.get(style, 2)
    if any(_word_hit(text, w) for w in ("whisper", "softly", "gentle", "still", "slow")):
        energy = max(1, energy - 1)
    if any(_word_hit(text, w) for w in ("rush", "race", "slam", "shout", "explode", "frantic")):
        energy = min(5, energy + 1)
    if style_score >= 8:
        energy = min(5, energy + 1)
    return energy


def pick_mood(paragraph: str, previous_code: str = "") -> MoodPick:
    """Return STYLE / KEY / ENERGY / short mood line for the passage."""
    scores, matched = score_styles(paragraph)
    best_style = max(STYLES, key=lambda s: scores[s])
    if scores[best_style] == 0:
        best_style = "AMBIENT"

    prev_style = infer_style_from_code(previous_code)
    if prev_style and prev_style in scores:
        # Keep previous timbre unless the new text strongly votes elsewhere.
        if scores[best_style] < scores[prev_style] + 4:
            best_style = prev_style

    key = _pick_key(best_style, paragraph)
    energy = _pick_energy(best_style, paragraph, scores[best_style])
    mood_line = ", ".join(matched[:8]) if matched else "calm background reading"
    return MoodPick(
        style=best_style,
        key=key,
        energy=energy,
        mood_line=mood_line,
        scores=scores,
    )
