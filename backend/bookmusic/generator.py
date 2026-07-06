"""Generate ambient Strudel code for a paragraph of prose.

Provider-agnostic: it assembles the system + user messages exactly as the spike
did and hands them to `llm.call_llm`. The `previous_code` argument feeds the
prompt's CONTINUITY mechanism so consecutive paragraphs evolve rather than jump.

Every reply goes through `validator.validate`; rejected code is regenerated up
to MAX_ATTEMPTS times (temperature makes retries productive). If nothing fully
passes, the attempt with the fewest issues is returned — player.js still guards
against outright parse errors on the frontend.
"""

import logging
from pathlib import Path

from .llm import call_llm
from .validator import repair, validate

log = logging.getLogger(__name__)

# Load the system prompt relative to this file so cwd doesn't matter.
SYSTEM_PROMPT = (Path(__file__).parent / "prompt.txt").read_text()

MAX_ATTEMPTS = 3


def generate(paragraph: str, previous_code: str = "", debug: bool = False) -> str:
    """Return Strudel code for the mood of `paragraph`.

    If `previous_code` is given, the model keeps the same timbre/style and evolves it.
    """
    user = (f"PREVIOUS CODE:\n{previous_code}\n\n" if previous_code else "") + \
           f"PARAGRAPH: {paragraph}"
    if debug:
        print("SYSTEM PROMPT:", SYSTEM_PROMPT)
        print("USER PROMPT:", user)

    best_code, best_issues = "", None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        code = repair(call_llm(SYSTEM_PROMPT, user))
        issues = validate(code)
        if not issues:
            return code
        log.warning("attempt %d/%d rejected: %s", attempt, MAX_ATTEMPTS, issues)
        if best_issues is None or len(issues) < len(best_issues):
            best_code, best_issues = code, issues
    log.warning(
        "no fully valid code after %d attempts; returning best with %d issue(s)",
        MAX_ATTEMPTS, len(best_issues),
    )
    return best_code


if __name__ == "__main__":
    print(generate((Path(__file__).parent / "samples/sample.txt").read_text(), debug=True))
