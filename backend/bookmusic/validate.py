"""Conservative Strudel validity checks for tiny-LLM output.

Reject-only: list short issue strings. Do NOT mutate/sanitize the code — the
generator regenerates with feedback, then falls back to a known-good style-card
example if retries still fail (returning the last invalid blob caused broken pages).
"""

from __future__ import annotations

import re

# Prompt labels / HTML-ish junk the model sometimes pastes after or into code.
_ECHO_PATTERNS: list[tuple[str, str]] = [
    (r"\bPARAGRAPH\b", "contains PARAGRAPH"),
    (r"\bPASSAGE\b", "contains PASSAGE"),
    (r"\bSTYLE\s*:", "contains STYLE:"),
    (r"\bPREVIOUS\b", "contains PREVIOUS"),
    (r"\bKEY\s*:", "contains KEY:"),
    (r"\bENERGY\s*:", "contains ENERGY:"),
    (r"\bMOOD\s*:", "contains MOOD:"),
    (r"</", "contains </"),
    (r"```", "contains markdown backticks"),
]

# Invented / JS-ish APIs and non-chaining that show up in bad generations.
_BAD_API_PATTERNS: list[tuple[str, str]] = [
    (r"\bpanning\s*\(", "invented API panning( — use .pan(...)"),
    (r"['\"]cutoff['\"]", "invented cutoff argument"),
    (r"=\s*\.", "JS-style = . assignment"),
    # ).sound("x"), gain(  — must be .gain(  (commas between stack layers like
    # ),\n  note( / sound( are fine and must NOT match here)
    (
        r"\)\s*,\s*(?:gain|room|lpf|lpq|pan|delay|attack|release|bank|vowel|scale)\s*\(",
        "comma between calls — chain with .method()",
    ),
]

# Doubled pitch letters (bb = flat, OK) and absurd octaves.
_JUNK_NOTE_RE = re.compile(
    r"\b(?:aa|cc|dd|ee|ff|gg)\d+\b"  # dd4, ee3, …
    r"|\b[a-g][#b]?[6-9]\b"  # c6, g7, …
    r"|\b[a-g][#b]?[1-9]\d+\b",  # c10, …
    re.IGNORECASE,
)

_NOTE_OR_N_CALL_RE = re.compile(
    r"\b(?:note|n)\s*\(\s*(['\"])",
    re.IGNORECASE,
)


def _scan_matching_paren(code: str, open_idx: int) -> int:
    """Return index of ')' matching code[open_idx]=='(', or -1."""
    if open_idx < 0 or open_idx >= len(code) or code[open_idx] != "(":
        return -1
    depth = 0
    in_str: str | None = None
    i = open_idx
    n = len(code)
    while i < n:
        ch = code[i]
        if in_str:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in ("'", '"'):
            in_str = ch
            i += 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _balance_issues(code: str) -> list[str]:
    """Check (), [], <> balance; []/<> count inside musical strings too."""
    paren = bracket = angle = 0
    i = 0
    n = len(code)
    in_str: str | None = None
    while i < n:
        ch = code[i]
        if in_str:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == in_str:
                in_str = None
            elif ch == "[":
                bracket += 1
            elif ch == "]":
                bracket -= 1
                if bracket < 0:
                    return ["unbalanced []"]
            elif ch == "<":
                angle += 1
            elif ch == ">":
                angle -= 1
                if angle < 0:
                    return ["unbalanced <>"]
            i += 1
            continue
        if ch in ("'", '"'):
            in_str = ch
            i += 1
            continue
        if ch == "(":
            paren += 1
        elif ch == ")":
            paren -= 1
            if paren < 0:
                return ["unbalanced ()"]
        elif ch == "[":
            bracket += 1
        elif ch == "]":
            bracket -= 1
            if bracket < 0:
                return ["unbalanced []"]
        elif ch == "<":
            angle += 1
        elif ch == ">":
            angle -= 1
            if angle < 0:
                return ["unbalanced <>"]
        i += 1
    issues: list[str] = []
    if paren != 0:
        issues.append("unbalanced ()")
    if bracket != 0:
        issues.append("unbalanced []")
    if angle != 0:
        issues.append("unbalanced <>")
    return issues


def _pattern_string_issues(code: str) -> list[str]:
    """note("/n(" strings must close; <…> mini-notation must not close with ]."""
    issues: list[str] = []
    for match in _NOTE_OR_N_CALL_RE.finditer(code):
        quote = match.group(1)
        start = match.end()
        j = start
        closed = False
        while j < len(code):
            c = code[j]
            if c == "\\" and j + 1 < len(code):
                j += 2
                continue
            if c == quote:
                closed = True
                body = code[start:j]
                stripped = body.lstrip()
                if stripped.startswith("<") and ">" not in stripped:
                    # Classic failure: note("<c1 b1 a1]") — < opened, ] used as closer.
                    if "]" in stripped:
                        issues.append('note/n has <…] mismatch (expected >)')
                    else:
                        issues.append('note/n opened with < but missing >')
                break
            j += 1
        if not closed:
            issues.append('unclosed note("...") or n("...")')
            break
    return issues


def _junk_note_issues(code: str) -> list[str]:
    bodies: list[str] = []
    for m in re.finditer(
        r"\b(?:note|n)\s*\(\s*(['\"])(.*?)(?:\1)", code, re.IGNORECASE | re.DOTALL
    ):
        bodies.append(m.group(2))
    if not bodies:
        bodies = [code]
    for body in bodies:
        hit = _JUNK_NOTE_RE.search(body)
        if hit:
            return [f"junk/out-of-range note {hit.group(0)!r}"]
    return []


def _hash_comment_issues(code: str) -> list[str]:
    """Reject # commentary (model dumps '# Note sequence…' after the stack)."""
    in_str: str | None = None
    i = 0
    n = len(code)
    while i < n:
        ch = code[i]
        if in_str:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in ("'", '"'):
            in_str = ch
            i += 1
            continue
        if ch == "#":
            return ["contains # comment"]
        i += 1
    return []


def _trailing_after_stack_issues(code: str) -> list[str]:
    """Any non-whitespace after the closing ) of stack(...) is junk."""
    match = re.search(r"\bstack\s*\(", code, re.IGNORECASE)
    if not match:
        return []
    open_idx = match.end() - 1
    close_idx = _scan_matching_paren(code, open_idx)
    if close_idx < 0:
        return ["unclosed stack("]
    trailing = code[close_idx + 1 :]
    if trailing.strip():
        return ["trailing junk after stack"]
    return []


def validation_issues(code: str) -> list[str]:
    """Return a short list of problems, or [] if OK enough to return to the client."""
    text = (code or "").strip()
    if not text:
        return ["empty output"]

    issues: list[str] = []
    lower = text.lower()
    if "setcpm(" not in lower:
        issues.append("missing setcpm(")
    if "stack(" not in lower:
        issues.append("missing stack(")

    for pat, msg in _ECHO_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            issues.append(msg)

    for pat, msg in _BAD_API_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            issues.append(msg)

    issues.extend(_hash_comment_issues(text))
    issues.extend(_balance_issues(text))
    issues.extend(_pattern_string_issues(text))
    issues.extend(_junk_note_issues(text))
    issues.extend(_trailing_after_stack_issues(text))

    # De-dupe preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for item in issues:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def is_valid_strudel(code: str) -> bool:
    return not validation_issues(code)
