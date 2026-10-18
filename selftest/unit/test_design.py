import json
import re
import tomllib

import design_preview as DP
import phaselints as L
from bundle import Bundle

UI = """## UI/UX notes

The ground is `#060403` and the ink is `#e9eae4`; the accent `#455e53` appears once per screen.
Do not ship `#00dc82`: it belongs to a framework's not-found page.
The display face is "Cirrus Display", a serif, at `18px`. Entrances fade over `0.8s` on
`cubic-bezier(.2,.65,.47,.96)`.

"""


def _brief(reference):
    """Swap the reference brief's (very long) UI sections for a small, known one."""
    path = reference / "instruction.md"
    text = path.read_text()
    text = re.sub(r"^## UI/UX notes\n.*?(?=^## )", UI, text, count=1, flags=re.M | re.S)
    text = re.sub(r"^## Front-end specification\n.*?(?=^## |\Z)", "", text, count=1, flags=re.M | re.S)
    path.write_text(text)
    return Bundle.load(reference)


def _visual_ids(reference):
    doc = tomllib.loads((reference / "tests" / "judge.toml").read_text())
    return [c["id"] for c in doc["criterion"] if c["annotations"].get("dimension") in
            ("ui_visual", "motion", "accessibility", "responsiveness")]


def _design(reference, palette_extra="", drop_accent=False):
    accent = "" if drop_accent else "| accent | `#455e53` | once per screen | accent on ink: 5.83:1 | brief: UI/UX notes |\n"
    mapping = "\n".join(f"| {cid} | the palette and type above |" for cid in _visual_ids(reference))
    return f"""# DESIGN — talent roster

design_direction: editorial-serif

## Palette

| Role | Hex | Used for | AA pair | Source |
|---|---|---|---|---|
| ground | `#060403` | page ground | | brief: UI/UX notes |
| ink | `#e9eae4` | text | ink on ground: 16.91:1 | brief: UI/UX notes |
{accent}| muted | `#9a9a94` | captions | 7.1:1 | decided: a dimmed ink for secondary text, warm like the ground |
| focus | `#e9eae4` | focus ring | | decided: the ink, so the ring reads on every surface |
| danger | `#ff8a7a` | errors | 8.93:1 | decided: brief names no error colour; warm, AA on the ground |
{palette_extra}
## Typography

| Token | Family (with fallback stack) | Weight | Size / line height | Used for | Source |
|---|---|---|---|---|---|
| display | "Cirrus Display", Georgia, serif | 300 | 18px / 1.5 | body and headings | brief: UI/UX notes |

Prose measure: 66 characters.

## Space, shape, depth

| Token | Value | Source |
|---|---|---|
| spacing unit | 8px | decided: an 8px grid suits the spacious density of the direction |
| radius | 0px | decided: print-like, square corners |
| border width | 1px | decided: hairline rules |
| elevation | none | decided: a flat, editorial page |

## Motion

| Token | Duration (ms) | Easing | What animates (named properties) | Source |
|---|---|---|---|---|
| entrance | 800ms | cubic-bezier(.2,.65,.47,.96) | opacity | brief: UI/UX notes |

Reduced motion (`prefers-reduced-motion: reduce`): the entrance is removed; content appears at rest.

## Focus

| Property | Value | Source |
|---|---|---|
| ring | 2px solid focus | decided: visible on the dark ground |
| offset | 3px | decided: clears the text |

## Breakpoints

| Width | What changes | Source |
|---|---|---|
| 320 | one column, nav collapses to a menu button | decided: WCAG reflow |
| 1440 | three columns | decided: the index grid |

## States

| State | Treatment | Source |
|---|---|---|
| empty | a sentence in the display face naming what will appear | decided: in the house voice |

## Judged criteria mapping

| Criterion | Satisfied by |
|---|---|
{mapping}

## Brief values not carried

| Value | Why it is not in this design |
|---|---|
| `#00dc82` | the brief forbids it: a framework's not-found colour |
"""


def _write(b, text):
    L.design_path(b).write_text(text)
    return L.design_lint(b)


def test_brief_values_are_extracted_in_every_unit(reference):
    v = L.design_values(L.brief_ui_text(_brief(reference)))
    assert v["colour"] == {"#060403", "#e9eae4", "#455e53", "#00dc82"}
    assert v["ms"] == {"800ms"} and v["px"] == {"18px"} and v["font"] == {"Cirrus Display"}
    assert v["easing"] == {"cubic-bezier(.2,.65,.47,.96)"}


def test_a_faithful_design_passes(reference):
    b = _brief(reference)
    assert _write(b, _design(reference)) == []


def test_a_dropped_brief_value_fails_carriage(reference):
    b = _brief(reference)
    problems = " | ".join(_write(b, _design(reference, drop_accent=True)))
    assert "#455e53" in problems and "neither in the design nor listed" in problems


def test_a_brief_row_cannot_carry_an_invented_value(reference):
    b = _brief(reference)
    extra = "| surface | `#1b1b1b` | cards | | brief: UI/UX notes |\n"
    problems = " | ".join(_write(b, _design(reference, palette_extra=extra)))
    assert "'surface' is marked brief but carries #1b1b1b" in problems


def test_every_row_needs_a_source(reference):
    b = _brief(reference)
    extra = "| surface | `#1b1b1b` | cards | | |\n"
    problems = " | ".join(_write(b, _design(reference, palette_extra=extra)))
    assert "'surface': Source must be" in problems


def test_a_forbidden_brief_colour_may_not_ship(reference):
    b = _brief(reference)
    extra = "| success | `#00dc82` | confirmations | | decided: a bright green |\n"
    problems = " | ".join(_write(b, _design(reference, palette_extra=extra)))
    assert "#00dc82 is listed as forbidden by the brief yet appears in the design" in problems


def test_preview_renders_the_tokens_and_goes_stale(reference):
    b = _brief(reference)
    _write(b, _design(reference))
    page, meta = DP.render(b)
    assert "#455e53" in page and 'class="badge decided"' in page and 'class="badge brief"' in page
    assert meta["decided"] > 0 and meta["brief"] >= 4
    assert meta["contrast"]["ink"]["on_ground"] > 15
    out = b.golden_dir / "design"
    out.mkdir(parents=True)
    (out / "preview.json").write_text(json.dumps(meta))
    assert DP.preview_lint(b) == []
    L.design_path(b).write_text(L.design_path(b).read_text() + "\n")
    assert "STALE" in DP.preview_lint(b)[0]


def test_contrast_matches_wcag():
    assert DP.contrast("#000000", "#ffffff") == 21.0
    assert DP.contrast("#777777", "#ffffff") == 4.48


def test_a_wrong_contrast_claim_fails(reference):
    b = _brief(reference)
    _write(b, _design(reference))
    assert DP.contrast_claims_lint(b) == []
    L.design_path(b).write_text(L.design_path(b).read_text().replace("accent on ink: 5.83:1", "accent on ground: 3.1:1"))
    problems = " | ".join(DP.contrast_claims_lint(b))
    assert "accent on ground is stated as 3.1:1 but computes to 2.9:1" in problems


def test_preview_puts_readable_text_on_the_accent(reference):
    b = _brief(reference)
    _write(b, _design(reference))
    page, _ = DP.render(b)
    assert "--on-accent:#e9eae4;" in page


def _with_palette(reference, rows: str, space: str = "", focus: str = "2px solid focus"):
    b = _brief(reference)
    text = _design(reference)
    text = text.replace("{palette_extra}", "")
    text = re.sub(r"(## Palette\n\n\|.*\n\|.*\n)", lambda m: m.group(1) + rows, text, count=1)
    if space:
        text = re.sub(r"(## Space, shape, depth\n\n\|.*\n\|.*\n)", lambda m: m.group(1) + space, text, count=1)
    text = re.sub(r"\| ring \|[^\n]*", f"| ring | {focus} | decided: the brief names none |", text, count=1)
    _write(b, text)
    return b


def test_preview_reads_every_colour_spaced_roles_focus_on_accent_and_shapes(reference):
    rows = ("| tag colours | `#ff0000` `#00ff00` | tags | | decided: one per tag |\n"
            "| code panel | `#1a1a1a` | code panel background | | decided: a quiet surface |\n"
            "| cyan | `#22d3ee` | focus ring | | decided: the ring |\n"
            "| on accent | `#ffffff` | text on the accent | | decided: white on the accent |\n")
    space = ("| radius small | 6px | decided: inputs |\n| radius pill | 999px | decided: tags |\n"
             "| elevation card | `0 2px 8px rgba(0,0,0,.3)` | decided: cards |\n")
    b = _with_palette(reference, rows, space, focus="2px solid cyan")
    page, _ = DP.render(b)
    assert "#ff0000" in page and "#00ff00" in page                     # 1: every hex in a row
    assert "--code-panel:#1a1a1a;" in page and "--code panel" not in page   # 2: CSS-safe names
    assert "--focus:#22d3ee;" in page                                 # 3: the Focus table's colour
    assert "--on-accent:#ffffff;" in page                             # 4: the stated on-accent
    assert "--r:6px" in page and "999px" in page and "0 2px 8px rgba(0,0,0,.3)" in page   # 5: shapes


def test_contrast_lint_rejects_claims_it_cannot_check_and_text_too_faint_on_a_surface(reference):
    rows = ("| tint | `#2a2a2a` | tag background tint | each on its tint ≥ 4.5:1 | decided: tags |\n"
            "| faint | `#5a5a5a` | caption text | | decided: captions |\n")
    problems = " | ".join(DP.contrast_claims_lint(_with_palette(reference, rows)))
    assert "cannot be checked" in problems                            # 6a: free-form claim
    assert "'faint' #5a5a5a on 'ground'" in problems                  # 6b: text measured on every surface
    rows = rows.replace("caption text |", "caption text, only on tint |").replace("each on its tint ≥ 4.5:1", "")
    problems = " | ".join(DP.contrast_claims_lint(_with_palette(reference, rows)))
    assert "on 'ground'" not in problems                              # `only on` limits where it is measured
