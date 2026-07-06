"""LLM eval for prompt.txt — a scorecard, not a pass/fail test.

Runs one fresh paragraph per style (deliberately NOT the paragraphs embedded in
the prompt) through the RAW model — single-shot call_llm, bypassing generate()'s
retry loop — so the numbers measure prompt quality, not the guardrail. Each
reply is scored on:

  * RULES — the static validator (same checks the guardrail uses)
  * STYLE — loose per-mood heuristics: expected instrument family, whether a
    beat belongs, expected scale flavor

Run it before and after a prompt tweak and compare:

    uv run python evals/eval_prompt.py             # 1 run per mood (~5 min)
    uv run python evals/eval_prompt.py --runs 3    # steadier numbers
    uv run python evals/eval_prompt.py --mood lofi anger
"""

import argparse
import re
import time
from collections import Counter
from dataclasses import dataclass, field

from bookmusic.generator import SYSTEM_PROMPT
from bookmusic.llm import call_llm
from bookmusic.validator import validate

BEAT_MARKERS = {"bd", "sd"}  # rim/cp/hh alone are texture, not a beat


@dataclass
class Case:
    paragraph: str
    any_sounds: set[str]        # at least one must appear
    beat: bool                  # True: needs bd; False: bd/sd forbidden
    scale_any: tuple[str, ...] = field(default_factory=tuple)  # substring match


CASES = {
    "ambient": Case(
        "The ship drifted alone on a flat grey ocean, no wind, no birds, only "
        "the slow breathing of the water against the hull.",
        {"gm_synth_strings_1", "gm_pad_warm", "sine", "triangle",
         "gm_choir_aahs", "gm_reed_organ"},
        beat=False,
    ),
    "lofi": Case(
        "She spread her notes across the kitchen table, tea going cold beside "
        "her, the radiator ticking softly while snow gathered on the sill.",
        {"gm_epiano1"},
        beat=True,
    ),
    "chillhop": Case(
        "After midnight the diner emptied out; he lingered over the last of "
        "his coffee, watching taxi lights slide across the wet avenue.",
        {"gm_electric_guitar_jazz", "gm_acoustic_guitar_nylon"},
        beat=True,
    ),
    "piano": Case(
        "He found her handwriting inside the old book's cover and sat down "
        "slowly on the stairs, holding the page like something alive.",
        {"piano"},
        beat=False,
    ),
    "dreamy": Case(
        "The lake at the center of the forest reflected a sky that wasn't "
        "there — two moons, silver reeds, and fish made of light.",
        {"gm_vibraphone", "gm_celesta", "gm_music_box", "gm_pad_warm",
         "triangle"},
        beat=False,
        scale_any=("lydian",),
    ),
    "tense": Case(
        "The footsteps behind her stopped when she stopped. She stood in the "
        "dark hallway, hand on the cold railing, not daring to breathe.",
        {"sawtooth"},
        beat=False,
        scale_any=("phrygian", "minor", "dorian"),
    ),
    "happy": Case(
        "The kite finally caught the wind and the whole beach seemed to "
        "cheer; they ran laughing down the sand, string singing in their hands.",
        {"gm_epiano1"},
        beat=True,
        scale_any=("major",),
    ),
    "epic": Case(
        "Ten thousand lanterns rose over the harbor as the fleet set sail at "
        "dawn, horns sounding from every tower on the cliffs.",
        {"gm_string_ensemble_1", "gm_brass_section", "gm_french_horn",
         "gm_timpani"},
        beat=False,
    ),
    "anger": Case(
        "He read the letter twice, then his fist came down on the desk; "
        "papers scattered and something old and furious woke in his chest.",
        {"sawtooth"},
        beat=True,
        scale_any=("phrygian", "minor"),
    ),
}


def _used_sounds(code: str) -> set[str]:
    tokens: set[str] = set()
    for arg in re.findall(r'sound\("([^"]*)"\)', code):
        tokens |= set(re.findall(r"[a-z_][a-z0-9_]*", arg))
    return tokens


def style_issues(code: str, case: Case) -> list[str]:
    sounds = _used_sounds(code)
    issues = []
    if not sounds & case.any_sounds:
        issues.append(f"expected one of {sorted(case.any_sounds)}")
    if case.beat and "bd" not in sounds:
        issues.append("expected a beat (bd)")
    if not case.beat and sounds & BEAT_MARKERS:
        issues.append("beat where the style should be drumless")
    if case.scale_any and not any(s in code for s in case.scale_any):
        issues.append(f"expected a {'/'.join(case.scale_any)} scale")
    return issues


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", type=int, default=1, help="generations per mood")
    ap.add_argument("--mood", nargs="*", choices=sorted(CASES),
                    help="only these moods (default: all)")
    ap.add_argument("--show-code", action="store_true",
                    help="print every generated piece")
    args = ap.parse_args()

    moods = args.mood or list(CASES)
    results = {}          # mood -> (rules_ok, style_ok, seconds)
    issue_counts = Counter()

    for mood in moods:
        case = CASES[mood]
        rules_ok = style_ok = 0
        elapsed = []
        for run in range(1, args.runs + 1):
            t0 = time.monotonic()
            code = call_llm(SYSTEM_PROMPT, f"PARAGRAPH: {case.paragraph}")
            elapsed.append(time.monotonic() - t0)
            rules = validate(code)
            style = style_issues(code, case)
            rules_ok += not rules
            style_ok += not style
            issue_counts.update(re.sub(r"[\d.]+", "N", i) for i in rules)
            flags = (f"rules: {'OK' if not rules else rules}  "
                     f"style: {'OK' if not style else style}")
            print(f"[{mood} {run}/{args.runs}] {elapsed[-1]:5.1f}s  {flags}")
            if args.show_code:
                print(code, "\n")
        results[mood] = (rules_ok, style_ok, sum(elapsed) / len(elapsed))

    print(f"\n{'mood':<10} {'rules':>7} {'style':>7} {'avg s':>7}")
    for mood, (r, s, secs) in results.items():
        print(f"{mood:<10} {r}/{args.runs:<5} {s}/{args.runs:<5} {secs:7.1f}")
    total = len(moods) * args.runs
    print(f"{'TOTAL':<10} {sum(r for r, _, _ in results.values())}/{total:<5} "
          f"{sum(s for _, s, _ in results.values())}/{total}")

    if issue_counts:
        print("\nmost common rule issues (numbers normalized to N):")
        for issue, n in issue_counts.most_common(8):
            print(f"  {n}x  {issue}")


if __name__ == "__main__":
    main()
