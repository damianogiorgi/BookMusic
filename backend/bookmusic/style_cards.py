"""One structure-only style card per STYLE (Experiment B).

Injected into the user message after mood pick so the system prompt stays slim
and the tiny model only sees the recipe it should follow.
"""

from __future__ import annotations

# Diversified shapes from try-first A (not the old homogeneous 4×C-chord skeleton).
STYLE_CARDS: dict[str, str] = {
    "AMBIENT": """\
STYLE: AMBIENT
Use exactly this layer recipe (instruments + roles), new harmony in KEY from the slots:
1) pads: gm_pad_warm, long attack/release, big room, very slow lpf
2) low sine drone with rests + gentle pan — DRUMLESS

EXAMPLE (structure only — do not copy these notes):
setcpm(34)
stack(
  note("<[g2,bb2,d3] [eb3,g3,bb3] [f2,ab2,c3]>").sound("gm_pad_warm").attack(.8).release(2).gain(.4).room(.75).lpf(sine.range(350,900).slow(24)),
  note("<g1 ~ eb1>").sound("sine").gain(.28).lpf(400).pan(sine.range(.25,.75).slow(18))
)
""",
    "LOFI": """\
STYLE: LOFI
Use exactly this layer recipe (instruments + roles), new harmony in KEY from the slots:
1) chords: gm_epiano1, soft attack/release, light room, slow lpf
2) bass: gm_acoustic_bass, low notes, lpf ~600
3) drums: sound("bd ~ sd ~").gain(.3)  (optional quiet hh*4)

EXAMPLE (structure only — do not copy these notes):
setcpm(20)
stack(
  note("<[d3,f3,a3] [g2,bb2,d3] [c3,eb3,g3] [a2,c3,e3] [f2,a2,c3]>").sound("gm_epiano1").attack(.02).release(.65).gain(.4).room(.35).lpf(sine.range(650,1300).slow(9)),
  note("<d2 g1 c2 a1 f1>").sound("gm_acoustic_bass").gain(.45).lpf(580),
  sound("bd ~ sd ~").gain(.3)
)
""",
    "CHILLHOP": """\
STYLE: CHILLHOP
Use exactly this layer recipe (instruments + roles), new harmony in KEY from the slots:
1) chords: gm_electric_guitar_jazz, soft attack, light room
2) bass: gm_acoustic_bass
3) drums: soft sound("bd ~ sd ~").gain(.3)

EXAMPLE (structure only — do not copy these notes):
setcpm(20)
stack(
  note("<[d3,f3,a3] [g2,b2,d3] [c3,e3,g3] [a2,c3,e3]>").sound("gm_electric_guitar_jazz").attack(.01).release(.5).gain(.4).room(.4).lpf(1800),
  note("<d2 g1 c2 a1>").sound("gm_acoustic_bass").gain(.45).lpf(700),
  sound("bd ~ sd ~").gain(.3)
)
""",
    "WARM_PIANO": """\
STYLE: WARM_PIANO
Use exactly this layer recipe (instruments + roles), new harmony in KEY from the slots:
1) broken / lyrical piano line with rests
2) soft low piano bass — DRUMLESS

EXAMPLE (structure only — do not copy these notes):
setcpm(28)
stack(
  note("<a3 e3 c3 e3 ~ g3 e3>").sound("piano").gain(.4).room(.45).attack(.01).release(1.1).lpf(sine.range(1000,1600).slow(14)),
  note("<a1 f1 e1>").sound("piano").gain(.3).lpf(500)
)
""",
    "DREAMY": """\
STYLE: DREAMY
Use exactly this layer recipe (instruments + roles), new harmony in KEY from the slots:
1) bells/vibraphone via n(...).scale(... lydian)
2) soft triangle pad — DRUMLESS, lots of room

EXAMPLE (structure only — do not copy these notes):
setcpm(45)
stack(
  n("<0 2 4 6 4 2>").scale("C4:lydian").sound("gm_vibraphone").gain(.4).room(.8).lpf(sine.range(700,1500).slow(16)),
  note("<c2 g2>").sound("triangle").gain(.3).room(.6).lpf(600)
)
""",
    "TENSE": """\
STYLE: TENSE
Use exactly this layer recipe (instruments + roles), new harmony in KEY from the slots:
1) dark sawtooth pad, phrygian, slow lpf + mild lpq, soft attack
2) low sine
3) sparse quiet rim only (no upbeat drums)

EXAMPLE (structure only — do not copy these notes):
setcpm(36)
stack(
  n("<0 1 2 1>").scale("C3:phrygian").sound("sawtooth").gain(.35).lpf(sine.range(300,800).slow(18)).lpq(6).room(.6).attack(.4).release(1.2),
  note("<c2 ab1>").sound("sine").gain(.35).lpf(300),
  sound("~ ~ rim ~").gain(.18).room(.5)
)
""",
    "HAPPY": """\
STYLE: HAPPY
Use exactly this layer recipe (instruments + roles), new harmony in KEY from the slots:
1) bright major gm_epiano1 line
2) acoustic bass
3) light sound("bd ~ sd ~").gain(.3)

EXAMPLE (structure only — do not copy these notes):
setcpm(26)
stack(
  n("<0 2 4 6 4 2 0 2>").scale("C4:major").sound("gm_epiano1").attack(.02).release(.4).gain(.4).room(.35).lpf(sine.range(900,1900).slow(8)),
  note("<c2 g1 a1 f1>").sound("gm_acoustic_bass").gain(.45).lpf(800),
  sound("bd ~ sd ~").gain(.3)
)
""",
    "EPIC": """\
STYLE: EPIC
Use exactly this layer recipe (instruments + roles), new harmony in KEY from the slots:
1) gm_string_ensemble_1 swell, big room, slow lpf
2) soft gm_brass_section
3) low bass — DRUMLESS

EXAMPLE (structure only — do not copy these notes):
setcpm(30)
stack(
  note("<[c3,e3,g3] [g2,b2,d3] [a2,c3,e3] [f2,a2,c3]>").sound("gm_string_ensemble_1").attack(.6).release(1.6).gain(.45).room(.8).lpf(sine.range(500,1500).slow(16)),
  note("<c4 b3 a3 c4>").sound("gm_brass_section").gain(.28).room(.7).lpf(1500).attack(.2).release(1),
  note("<c2 g1 a1 f1>").sound("gm_acoustic_bass").gain(.35).lpf(400)
)
""",
    "ANGER": """\
STYLE: ANGER
Use exactly this layer recipe (instruments + roles), new harmony in KEY from the slots:
1) gritty low sawtooth, phrygian
2) dark string chords, kept quiet
3) insistent kick sound("bd ~ bd ~").gain(.3) — still background, never harsh

EXAMPLE (structure only — do not copy these notes):
setcpm(26)
stack(
  n("<0 1 0 -1>").scale("C2:phrygian").sound("sawtooth").gain(.35).lpf(sine.range(250,700).slow(6)).lpq(8).room(.4).attack(.05).release(.5),
  note("<[c3,db3,g3] [c3,eb3,ab3] [bb2,d3,g3]>").sound("gm_synth_strings_1").gain(.28).lpf(800).room(.5).attack(.2).release(.8),
  sound("bd ~ bd ~").gain(.3)
)
""",
}


def style_card(style: str) -> str:
    """Return the card for `style`, falling back to AMBIENT."""
    return STYLE_CARDS.get(style, STYLE_CARDS["AMBIENT"]).strip()
