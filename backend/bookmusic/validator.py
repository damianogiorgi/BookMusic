"""Static validation of LLM-generated Strudel code.

Pure-Python, no LLM and no Strudel runtime: a set of lint-style checks that
mirror the HARD RULES / KEEP IT PLEASANT sections of prompt.txt. The whitelists
below must be kept in sync with the prompt.

`validate(code)` returns a list of human-readable issues (empty = valid), so it
can back both the pytest suite and, later, a reject-and-retry guardrail in the
/generate endpoint.

Heuristic assumption: the model writes one layer per line (as every prompt
example does), so per-line checks like "sawtooth needs .lpf" are line-scoped.
"""

import re

# --- Whitelists (keep in sync with prompt.txt) -------------------------------

MELODIC_SOUNDS = {
    "sine", "triangle", "sawtooth",
    "gm_synth_strings_1", "gm_pad_warm", "gm_epiano1",
    "piano", "gm_acoustic_guitar_nylon", "gm_electric_guitar_jazz",
    "gm_vibraphone", "gm_celesta", "gm_music_box",
    "gm_flute", "gm_clarinet", "gm_ocarina", "gm_choir_aahs", "gm_reed_organ",
    "gm_string_ensemble_1", "gm_brass_section", "gm_french_horn", "gm_timpani",
    "gm_acoustic_bass",
}
DRUM_SOUNDS = {"bd", "sd", "hh", "rim", "cp", "crackle"}
ALLOWED_SOUNDS = MELODIC_SOUNDS | DRUM_SOUNDS

ALLOWED_METHODS = {
    "sound", "gain", "room", "lpf", "lpq", "delay", "attack", "release",
    "pan", "vowel", "scale", "slow", "range", "bank",
}
ALLOWED_CALLS = {"setcpm", "stack", "note", "n", "sound"}

GAIN_MAX = 0.6
CPM_MIN, CPM_MAX = 14, 50
CPM_MAX_WITH_BEAT = 28  # a bd-driven beat means one cycle = one bar
MAX_LINES = 16
MIN_LAYERS, MAX_LAYERS = 3, 5
MAX_OCTAVE = 5
MAX_SCALE_DEGREE = 9
LPQ_MAX = 6
MAX_HAT_MULT = 8
MIN_MODULATIONS = 2

# A code line starts with setcpm/stack/a pattern source, or is a closer/continuation.
_CODE_LINE = re.compile(r"^\s*(setcpm\(|stack\(|note\(|n\(|sound\(|[)\],.])")


def _strings(code: str) -> list[str]:
    return re.findall(r'"([^"]*)"', code)


def _split_top_level(s: str) -> list[str]:
    """Split mini-notation items on whitespace, ignoring spaces inside [ ]."""
    items, depth, cur = [], 0, ""
    for ch in s:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if ch.isspace() and depth == 0:
            if cur:
                items.append(cur)
            cur = ""
        else:
            cur += ch
    if cur:
        items.append(cur)
    return items


def _count_stack_layers(code: str) -> int:
    """Count top-level comma-separated entries inside stack(...)."""
    start = code.find("stack(")
    if start == -1:
        return 0
    depth, layers, in_string = 0, 1, False
    for ch in code[start + len("stack("):]:
        if ch == '"':
            in_string = not in_string
        if in_string:
            continue
        if ch in "([":
            depth += 1
        elif ch in ")]":
            if depth == 0:
                break
            depth -= 1
        elif ch == "," and depth == 0:
            layers += 1
    return layers


def validate(code: str) -> list[str]:
    """Return a list of issues with `code`; empty list means it passed."""
    issues: list[str] = []
    code = code.strip()
    if not code:
        return ["empty output"]

    lines = [l for l in code.splitlines() if l.strip()]

    # --- shape: code only, setcpm first, balanced, short --------------------
    if "```" in code:
        issues.append("contains markdown fences")
    for line in lines:
        if not _CODE_LINE.match(line):
            issues.append(f"non-code line: {line.strip()[:60]!r}")
    if len(lines) > MAX_LINES:
        issues.append(f"too long: {len(lines)} lines (max {MAX_LINES})")

    m = re.match(r"setcpm\((\d+(?:\.\d+)?)\)$", lines[0].strip())
    if not m:
        issues.append("does not start with setcpm(N) on its own line")
        cpm = None
    else:
        cpm = float(m.group(1))
        if not CPM_MIN <= cpm <= CPM_MAX:
            issues.append(f"tempo {cpm:g} outside {CPM_MIN}-{CPM_MAX} cpm")

    for open_ch, close_ch in ("()", "[]", "<>"):
        if code.count(open_ch) != code.count(close_ch):
            issues.append(f"unbalanced {open_ch}{close_ch}")

    # Every pattern source must be a simple quoted string: note("..."), n("..."),
    # sound("..."). A dropped quote shifts all later quote pairing, which the
    # bracket counts above can miss entirely.
    for m in re.finditer(r"\b(?:note|n|sound)\(", code):
        if not re.match(r'\s*"[^"\n]*"\s*\)', code[m.end():]):
            snippet = code[m.start():m.start() + 40]
            issues.append(f"malformed pattern call: {snippet!r}")

    # --- vocabulary: only known sounds, methods, calls -----------------------
    sound_args = re.findall(r'sound\("([^"]*)"\)', code)
    used_sounds = set()
    for arg in sound_args:
        used_sounds |= set(re.findall(r"[a-z_][a-z0-9_]*", arg))
    for s in sorted(used_sounds - ALLOWED_SOUNDS):
        issues.append(f"unknown sound: {s!r}")

    for meth in set(re.findall(r"\.([A-Za-z_]\w*)\(", code)) - ALLOWED_METHODS:
        issues.append(f"unknown method: .{meth}()")
    for call in set(re.findall(r"(?<![\w.])([A-Za-z_]\w*)\(", code)) - ALLOWED_CALLS:
        issues.append(f"unknown function: {call}()")

    # --- loudness ------------------------------------------------------------
    for g in re.findall(r"\.gain\(\s*(\d*\.?\d+)\s*\)", code):
        if float(g) > GAIN_MAX:
            issues.append(f"gain {g} too loud (max {GAIN_MAX})")
    for g in re.findall(
        r"\.gain\(\s*(?:sine|perlin)\.range\(\s*[\d.]+\s*,\s*(\d*\.?\d+)", code
    ):
        if float(g) > GAIN_MAX:
            issues.append(f"gain range peaks at {g} (max {GAIN_MAX})")
    for line in lines:
        if re.match(r"\s*(note|n|sound)\(", line) and ".gain(" not in line:
            issues.append(
                f"layer without .gain() — defaults loud: {line.strip()[:60]!r}"
            )

    # --- structure: layered, varied, evolving --------------------------------
    layers = _count_stack_layers(code)
    if layers == 0:
        issues.append("no stack(...) of layers")
    elif layers < MIN_LAYERS:
        issues.append(f"only {layers} layers (min {MIN_LAYERS}) — sounds thin")
    elif layers > MAX_LAYERS:
        issues.append(f"{layers} layers (max {MAX_LAYERS}) — too busy")

    groups = re.findall(r"<([^<>]+)>", code)
    if not any(len(set(_split_top_level(g))) >= 3 for g in groups):
        issues.append("no <...> sequence with 3+ distinct items — will loop statically")

    modulations = len(re.findall(r"(?:sine|perlin)\.range\(", code))
    if modulations < MIN_MODULATIONS:
        issues.append(
            f"only {modulations} slow modulation(s) (need {MIN_MODULATIONS}) — won't evolve"
        )
    for s in re.findall(r"\.slow\(\s*(\d*\.?\d+)\s*\)", code):
        if float(s) < 4:
            issues.append(f".slow({s}) is too fast for background modulation (min 4)")

    # --- pleasantness: soft, low, tamed ---------------------------------------
    note_strings = " ".join(re.findall(r'\bnote\(\s*"([^"]*)"', code))
    degree_strings = " ".join(re.findall(r'\bn\(\s*"([^"]*)"', code))
    for name, octave in re.findall(r"\b([a-g][#b]?)(\d)\b", note_strings):
        if int(octave) > MAX_OCTAVE:
            issues.append(f"note {name}{octave} above octave {MAX_OCTAVE} — piercing")
    for root, octave in re.findall(r'\.scale\("([a-gA-G][#b]?)(\d)', code):
        if int(octave) > MAX_OCTAVE:
            issues.append(f"scale root {root}{octave} above octave {MAX_OCTAVE}")
    for d in re.findall(r"-?\d+", degree_strings):
        if int(d) > MAX_SCALE_DEGREE:
            issues.append(f"scale degree {d} too high (max {MAX_SCALE_DEGREE})")

    for line in lines:
        if 'sound("sawtooth")' in line and ".lpf(" not in line:
            issues.append("sawtooth layer without .lpf() — harsh")
    for q in re.findall(r"\.lpq\(\s*(\d*\.?\d+)\s*\)", code):
        if float(q) > LPQ_MAX:
            issues.append(f"lpq {q} too resonant (max {LPQ_MAX})")
    for mult in re.findall(r"hh\*(\d+)", code):
        if int(mult) > MAX_HAT_MULT:
            issues.append(f"hh*{mult} too busy (max hh*{MAX_HAT_MULT})")

    pan_values = re.findall(r"\.pan\(\s*(-?\d*\.?\d+)\s*\)", code)
    pan_values += [
        v
        for pair in re.findall(
            r"\.pan\(\s*(?:sine|perlin)\.range\(\s*(-?\d*\.?\d+)\s*,\s*(-?\d*\.?\d+)", code
        )
        for v in pair
    ]
    for p in pan_values:
        if not 0 <= float(p) <= 1:
            issues.append(f"pan value {p} outside 0-1")

    if cpm is not None and "bd" in used_sounds and cpm > CPM_MAX_WITH_BEAT:
        issues.append(
            f"tempo {cpm:g} with a drum beat (max {CPM_MAX_WITH_BEAT} — beats will race)"
        )

    return issues


def is_valid(code: str) -> bool:
    return not validate(code)
