"""Unit cases for Strudel validity gate (Experiment B follow-up).

Run:  cd backend && PYTHONPATH=. python3 -m bookmusic.test_validate
  or: PYTHONPATH=. python3 -m unittest bookmusic.test_validate
"""

from __future__ import annotations

import unittest
from unittest import mock

from bookmusic import generator as gen
from bookmusic.style_cards import STYLE_CARDS, extract_example, fallback_strudel
from bookmusic.validate import is_valid_strudel, validation_issues


# --- Damiano class A: trailing commentary / junk after stack -----------------
CASE_A_TRAILING = """\
setcpm(24)
stack(
  note("<c2 a1 f1>").sound("gm_acoustic_bass").gain(.5).lpf(800),
  note("<[b2,g3] [d2,b3] [e2,bb2]>").sound("sine").gain(.4).room(.6).lpf(900)
)

# Note sequence (one chord per cycle): ...
# 1. Bass starts low...
<c2 a1 f1> <b2 g3> <e2 bb2> </><a e o>
</
"""

# --- Damiano class B: <…] mismatch + PARAGRAPH -------------------------------
CASE_B_FIREPLACE = """\
setcpm(30)
stack(
  note("<c1 b1 a1 f1 d1 g1 e1]").sound("gm_synth_strings_1").gain(.4).room(.7)
)
PARAGRAPH: Alice stand by the fireplace...
"""

CASE_B_WINDOW = """\
setcpm(40)
stack(
  note("<g2 e3 b3 c3]").sound("triangle").gain(.35).room(.6)
)
PARAGRAPH: Alice stood by the window...
"""

CASE_GOOD = """\
setcpm(34)
stack(
  note("<[g2,bb2,d3] [eb3,g3,bb3] [f2,ab2,c3]>").sound("gm_pad_warm").attack(.8).release(2).gain(.4).room(.75).lpf(sine.range(350,900).slow(24)),
  note("<g1 ~ eb1>").sound("sine").gain(.28).lpf(400).pan(sine.range(.25,.75).slow(18))
)
"""


class ValidateABTests(unittest.TestCase):
    def test_case_a_trailing_junk(self):
        issues = validation_issues(CASE_A_TRAILING)
        self.assertTrue(issues, "expected rejection")
        joined = " ".join(issues)
        self.assertTrue(
            "trailing" in joined or "#" in joined or "</" in joined,
            issues,
        )
        self.assertFalse(is_valid_strudel(CASE_A_TRAILING))

    def test_case_b_mismatch_and_paragraph_fireplace(self):
        issues = validation_issues(CASE_B_FIREPLACE)
        self.assertTrue(any("PARAGRAPH" in i for i in issues), issues)
        self.assertTrue(
            any("mismatch" in i or "missing >" in i or "unbalanced" in i for i in issues),
            issues,
        )
        self.assertFalse(is_valid_strudel(CASE_B_FIREPLACE))

    def test_case_b_mismatch_and_paragraph_window(self):
        issues = validation_issues(CASE_B_WINDOW)
        self.assertTrue(any("PARAGRAPH" in i for i in issues), issues)
        self.assertTrue(
            any("mismatch" in i or "missing >" in i or "unbalanced" in i for i in issues),
            issues,
        )
        self.assertFalse(is_valid_strudel(CASE_B_WINDOW))

    def test_good_still_valid(self):
        self.assertEqual(validation_issues(CASE_GOOD), [])
        self.assertTrue(is_valid_strudel(CASE_GOOD))

    def test_hash_comment_alone_after_stack(self):
        code = CASE_GOOD + "\n# commentary\n"
        self.assertTrue(any("comment" in i or "trailing" in i for i in validation_issues(code)))

    def test_bare_slash_angle_trailing(self):
        code = CASE_GOOD + "\n</\n"
        self.assertTrue(validation_issues(code))


class FallbackTests(unittest.TestCase):
    def test_every_style_card_example_valid(self):
        for style in STYLE_CARDS:
            example = extract_example(style)
            issues = validation_issues(example)
            self.assertEqual(issues, [], f"{style}: {issues}\n{example}")

    def test_fallback_adapts_cpm_and_validates(self):
        code = fallback_strudel("DREAMY", "F lydian", energy=4)
        self.assertIn("setcpm(", code)
        self.assertIn('.scale("F4:lydian")', code)
        self.assertEqual(validation_issues(code), [])

    def test_generate_returns_fallback_not_invalid(self):
        """If the LLM only returns class-A junk, generate must not serve it."""
        with mock.patch.object(gen, "call_llm", return_value=CASE_A_TRAILING):
            out = gen.generate("alone at dusk quiet calm", previous_code="")
        self.assertNotIn("PARAGRAPH", out)
        self.assertNotIn("# Note sequence", out)
        self.assertEqual(validation_issues(out), [], out)
        self.assertTrue(out.strip().startswith("setcpm("))

    def test_generate_fallback_on_paragraph_echo(self):
        with mock.patch.object(gen, "call_llm", return_value=CASE_B_FIREPLACE):
            out = gen.generate("tender grief photograph", previous_code="")
        self.assertNotIn("PARAGRAPH", out)
        self.assertEqual(validation_issues(out), [], out)


if __name__ == "__main__":
    unittest.main()
