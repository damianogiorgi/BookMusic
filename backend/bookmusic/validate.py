"""Conservative Strudel validity checks for tiny-LLM output.

Reject-only: list short issue strings. Do NOT mutate/sanitize the code — the
generator regenerates with feedback instead (aggressive stripping wiped output
in an earlier experiment).
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
    (r"</\s*stack\s*>", "contains </stack>"),
    (r"</\s*[a-zA-Z]", "contains HTML-like close tag"),
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

_NOTE_CALL_RE = re.compile(
    r"\bnote\s*\(\s*(['\"])",
    re.IGNORECASE,
)


def _balance_issues(code: str) -> list[str]:
    """Check (), [], <> balance outside of… actually whole text (mini-notation uses them)."""
    issues: list[str] = []
    # Track strings so quotes inside note("...") don't break paren scan for ()
    # but [] <> inside strings still count toward musical bracket balance.
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
    if paren != 0:
        issues.append("unbalanced ()")
    if bracket != 0:
        issues.append("unbalanced []")
    if angle != 0:
        issues.append("unbalanced <>")
    return issues


def _unclosed_note_issues(code: str) -> list[str]:
    """note(\"...\") must close; if the string starts with < it must contain >."""
    issues: list[str] = []
    for match in _NOTE_CALL_RE.finditer(code):
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
                if body.lstrip().startswith("<") and ">" not in body:
                    issues.append('note("...") missing closing >')
                break
            j += 1
        if not closed:
            issues.append('unclosed note("...")')
            break
    return issues


def _junk_note_issues(code: str) -> list[str]:
    # Only inspect musical string bodies of note(...) / n(...) to avoid false hits.
    bodies: list[str] = []
    for m in re.finditer(r"\b(?:note|n)\s*\(\s*(['\"])(.*?)(?:\1)", code, re.IGNORECASE | re.DOTALL):
        bodies.append(m.group(2))
    if not bodies:
        # Fallback: whole code (still cheap).
        bodies = [code]
    for body in bodies:
        hit = _JUNK_NOTE_RE.search(body)
        if hit:
            return [f"junk/out-of-range note {hit.group(0)!r}"]
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

    issues.extend(_balance_issues(text))
    issues.extend(_unclosed_note_issues(text))
    issues.extend(_junk_note_issues(text))

    # Trailing prose / junk after the last closing paren of what should be the stack.
    last_close = text.rfind(")")
    if last_close != -1:
        trailing = text[last_close + 1 :].strip()
        if trailing and (
            re.search(r"[A-Za-z]{3,}", trailing)
            or "<" in trailing
            or ">" in trailing
        ):
            issues.append("trailing prose after code")

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
