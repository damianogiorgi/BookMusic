"""Tests for the Strudel static validator.

The key invariant: every style example embedded in prompt.txt must pass the
validator. The prompt teaches by example, so if an example drifts out of line
with the rules (or the validator gets stricter than the prompt), these tests
catch the mismatch before the model starts producing rejected code.
"""

import re
from pathlib import Path

import pytest

from bookmusic.validator import is_valid, repair, validate

PROMPT = (Path(__file__).parent.parent / "bookmusic" / "prompt.txt").read_text()

# Each example sits between "CODE:" and the following blank line.
PROMPT_EXAMPLES = re.findall(r"CODE:\n(setcpm.*?)\n\n", PROMPT, re.S)


def test_prompt_has_all_style_examples():
    assert len(PROMPT_EXAMPLES) == 9


@pytest.mark.parametrize(
    "example", PROMPT_EXAMPLES, ids=lambda e: e.splitlines()[0]
)
def test_prompt_examples_pass(example):
    assert validate(example) == []


GOOD = """setcpm(30)
stack(
  note("<[c3,e3,g3,b3] [a2,c3,e3] [f2,a2,c3] [g2,b2,d3]>").sound("piano").attack(.1).release(1.2).gain(.5).room(.5).lpf(sine.range(900,1600).slow(16)),
  note("<c2 a1 f1 g1>").sound("piano").gain(.35).lpf(500),
  n("<~ 4 ~ 2>").scale("C5:major").sound("gm_flute").gain(.3).room(.6).pan(sine.range(.35,.65).slow(12))
)"""


def test_good_piece_passes():
    assert validate(GOOD) == []
    assert is_valid(GOOD)


def test_repair_appends_dropped_trailing_parens():
    for damaged in (GOOD[:-1], GOOD[:-1] + "\n"):  # gemma4-style: final ) dropped
        assert validate(repair(damaged)) == []
    assert repair(GOOD) == GOOD                    # balanced code untouched


def test_repair_leaves_real_damage_alone():
    truncated = GOOD[: GOOD.index("n(\"<~ 4")] + 'n("<~ 4'  # mid-layer cut
    assert repair(truncated) == truncated     # deficit > 2: not our case
    dangling = GOOD[:-1].rstrip() + ","       # ends mid-list: ambiguous
    assert repair(dangling) == dangling


def bad(transform):
    """Return GOOD with one deliberate defect applied."""
    return transform(GOOD)


@pytest.mark.parametrize(
    "defect,expected",
    [
        # shape
        (lambda c: "", "empty"),
        (lambda c: "Here is your music:\n" + c, "setcpm"),
        (lambda c: c.replace("setcpm(30)\n", ""), "setcpm"),
        (lambda c: f"```\n{c}\n```", "markdown"),
        (lambda c: c + "\nThis piece evokes a calm mood.", "non-code line"),
        (lambda c: c.replace("stack(", "stack(("), "unbalanced ()"),
        (lambda c: c.replace("setcpm(30)", "setcpm(90)"), "tempo"),
        (lambda c: c.replace('n("<~ 4 ~ 2>")', 'n("<~ 4 ~ 2>)'), "malformed pattern call"),
        (lambda c: c + "\n" * 0 + "\n".join([',  note("c2").sound("piano").gain(.3)'] * 15), "too long"),
        # vocabulary
        (lambda c: c.replace('sound("piano")', 'sound("gm_super_lead")', 1), "unknown sound"),
        (lambda c: c.replace(".room(.5)", ".reverb(.5)"), "unknown method"),
        (lambda c: c.replace("stack(", "arrange(") , "unknown function"),
        # loudness
        (lambda c: c.replace(".gain(.5)", ".gain(.9)"), "too loud"),
        (lambda c: c.replace(".gain(.35)", ".gain(perlin.range(.3,.9))"), "peaks"),
        (lambda c: c.replace(".gain(.35)", ""), "without .gain"),
        # structure
        (lambda c: re.sub(r",\n  n\(.*\n", "\n", c), "layers"),
        (
            lambda c: c.replace(
                '"<[c3,e3,g3,b3] [a2,c3,e3] [f2,a2,c3] [g2,b2,d3]>"', '"[c3,e3,g3]"'
            ).replace('"<c2 a1 f1 g1>"', '"c2"').replace('"<~ 4 ~ 2>"', '"0 2"'),
            "loop statically",
        ),
        (lambda c: c.replace("sine.range(900,1600).slow(16)", "1200"), "modulation"),
        (lambda c: c.replace(".slow(16)", ".slow(1)"), "too fast"),
        # pleasantness
        (lambda c: c.replace('"<c2 a1 f1 g1>"', '"<c6 a6 f6 g6>"'), "octave"),
        (lambda c: c.replace('scale("C5:major")', 'scale("C7:major")'), "octave"),
        (lambda c: c.replace('"<~ 4 ~ 2>"', '"<~ 14 ~ 2>"'), "degree"),
        (
            lambda c: c.replace(
                'note("<c2 a1 f1 g1>").sound("piano").gain(.35).lpf(500)',
                'note("<c2 a1 f1 g1>").sound("sawtooth").gain(.35)',
            ),
            "sawtooth",
        ),
        (lambda c: c.replace(".lpf(500)", ".lpf(500).lpq(12)"), "lpq"),
        (lambda c: c.replace("sine.range(.35,.65)", "sine.range(-.6,.6)"), "pan"),
        (
            lambda c: c.replace(
                ',\n  n("<~ 4 ~ 2>").scale("C5:major").sound("gm_flute").gain(.3).room(.6).pan(sine.range(.35,.65).slow(12))',
                ',\n  sound("hh*16").gain(.15).pan(sine.range(.35,.65).slow(12))',
            ),
            "hh*16",
        ),
        (
            lambda c: c.replace("setcpm(30)", "setcpm(40)").replace(
                ',\n  n("<~ 4 ~ 2>").scale("C5:major").sound("gm_flute").gain(.3).room(.6).pan(sine.range(.35,.65).slow(12))',
                ',\n  sound("bd ~ sd ~").gain(.4).pan(sine.range(.35,.65).slow(12))',
            ),
            "drum beat",
        ),
    ],
    ids=[
        "empty", "prose-prefix", "missing-setcpm", "markdown-fence", "prose-suffix",
        "unbalanced-parens", "tempo-out-of-range", "missing-quote", "too-many-lines",
        "invented-sound", "invented-method", "invented-function",
        "gain-too-high", "gain-range-too-high", "layer-missing-gain",
        "too-few-layers", "static-loop", "missing-modulation", "modulation-too-fast",
        "note-too-high", "scale-root-too-high", "degree-too-high",
        "sawtooth-no-lpf", "lpq-too-high", "negative-pan", "hats-too-busy",
        "beat-tempo-too-fast",
    ],
)
def test_defects_are_caught(defect, expected):
    code = bad(defect)
    issues = validate(code)
    assert issues, f"expected an issue matching {expected!r}, got none"
    assert any(expected in issue for issue in issues), (
        f"expected an issue matching {expected!r}, got {issues}"
    )
