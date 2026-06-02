"""Generate ambient Strudel code for a paragraph of prose.

Provider-agnostic: it assembles the system + user messages exactly as the spike
did and hands them to `llm.call_llm`. The `previous_code` argument feeds the
prompt's CONTINUITY mechanism so consecutive paragraphs evolve rather than jump.
"""

from pathlib import Path

from .llm import call_llm

# Load the system prompt relative to this file so cwd doesn't matter.
SYSTEM_PROMPT = (Path(__file__).parent / "prompt.txt").read_text()


def generate(paragraph: str, previous_code: str = "") -> str:
    """Return Strudel code for the mood of `paragraph`.

    If `previous_code` is given, the model keeps the same timbre/style and evolves it.
    """
    user = (f"PREVIOUS CODE:\n{previous_code}\n\n" if previous_code else "") + \
           f"PARAGRAPH: {paragraph}"
    return call_llm(SYSTEM_PROMPT, user)


if __name__ == "__main__":
    print(generate("Una cosa era certa: che il micino bianco non c'entrava affatto..."))
