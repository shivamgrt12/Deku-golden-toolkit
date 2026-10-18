"""Render solution/DESIGN.md as a page a member can approve by eye.

Hex codes cannot be judged for taste. This builds one self-contained HTML page
from DESIGN.md's own tables -- nothing else -- and screenshots it at a phone and
a desktop width, so the P1 approval is of what the design LOOKS like:

  palette     swatches with computed WCAG contrast against ground and ink
  type        one specimen line per typography row, at its size and weight
  space       spacing, radius, border and elevation samples
  components  buttons, a labelled input with an error, a card, every state row
  focus       the ring, drawn on a focused control
  motion      each motion token running, and stopped under reduced motion

Every value carries a badge: `brief` (verbatim from instruction.md) or `decided`
(the agent's call, with its reason on hover) -- the member reviews the decided ones.

Written to _handoff/golden/design/: preview.html, preview@390.png,
preview@1440.png, preview.json (the DESIGN.md hash it was built from).
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import subprocess
from pathlib import Path

import phaselints as L

ROLES_DEFAULT = {"ground": "#ffffff", "ink": "#111111", "muted": "#666666", "accent": "#2f5bd3",
                 "focus": "#2f5bd3", "danger": "#b42318"}


def _rows(text: str, section: str) -> list[dict]:
    out = []
    for sec, header, cells in L._tables(text):
        if sec.lower().startswith(section.lower()):
            out.append({header[i] if i < len(header) else f"c{i}": c for i, c in enumerate(cells)})
    return out


def _hex(s: str) -> str | None:
    m = L.HEX.search(s or "")
    return m.group(0) if m else None


def _hexes(s: str) -> list[str]:
    return L.HEX.findall(s or "")


def _var(role: str) -> str:
    """A role name as a CSS custom property name: `code panel` -> `code-panel`."""
    return re.sub(r"[^a-z0-9]+", "-", role.lower()).strip("-") or "role"


SURFACE = re.compile(r"\b(ground|background|surface|panel|sidebar|card|canvas|backdrop|sheet|well|bg|tint)s?\b", re.I)
TEXTY = re.compile(r"\b(text|ink|label|link|heading|body|caption|copy|figure|number|title|prose)s?\b", re.I)
NON_TEXT = re.compile(r"\b(large|border|ring|outline|icon|divider|ui|rule|stroke)s?\b", re.I)
ON_ACCENT = re.compile(r"^(on[- ]?accent|text on accent|accent text|on[- ]?primary|accent ink)$", re.I)


def palette(text: str) -> tuple[dict[str, dict], dict[str, str]]:
    """(role -> row, role -> first hex), every role that names a hex."""
    rows = {r.get("role", "").strip().lower(): r for r in _rows(text, "Palette") if _hex(r.get("hex", ""))}
    return rows, {role: _hex(r["hex"]) for role, r in rows.items()}


def surfaces_and_text(rows: dict[str, dict]) -> tuple[list[str], dict[str, float]]:
    """Surface roles, and text roles with the contrast each needs (4.5 text, 3 large / UI)."""
    surfaces, texts = [], {}
    for role, r in rows.items():
        used = r.get("used for", "")
        if SURFACE.search(role) or (SURFACE.search(used) and not TEXTY.search(used)):
            surfaces.append(role)
        elif TEXTY.search(used) or role in ("ink", "muted"):
            texts[role] = 3.0 if NON_TEXT.search(used) and not TEXTY.search(used) else 4.5
        elif NON_TEXT.search(used):
            texts[role] = 3.0
    return surfaces, texts


def _scope(row: dict, surfaces: list[str]) -> list[str]:
    """`only on panel, card` in Used for limits which surfaces a text role is checked on."""
    m = re.search(r"\bonly on ([^.;)]+)", row.get("used for", ""), re.I)
    if not m:
        return surfaces
    named = [s for s in surfaces if re.search(rf"\b{re.escape(s)}\b", m.group(1), re.I)]
    return named or surfaces


def _lum(hexv: str) -> float:
    h = hexv.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    def chan(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def contrast(a: str, b: str) -> float:
    la, lb = _lum(a), _lum(b)
    return round((max(la, lb) + 0.05) / (min(la, lb) + 0.05), 2)


def _source(row: dict) -> tuple[str, str]:
    src = row.get("source", "")
    kind = "brief" if src.lower().startswith("brief") else ("decided" if src.lower().startswith("decided") else "?")
    return kind, src.split(":", 1)[1].strip() if ":" in src else src


def _badge(row: dict) -> str:
    kind, why = _source(row)
    return f'<span class="badge {kind}" title="{html.escape(why)}">{kind}</span>'


def _px(value: str, default: str) -> str:
    m = re.search(r"(\d+(?:\.\d+)?)\s*px", value or "")
    return f"{m.group(1)}px" if m else default


def _ms_value(value: str) -> str:
    vals = L.design_values(value or "")["ms"]
    return sorted(vals)[0] if vals else "200ms"


def render(b) -> tuple[str, dict]:
    text = L.design_path(b).read_text()
    palette_rows, colours = palette(text)
    c = {**ROLES_DEFAULT, **{_var(k): v for k, v in colours.items()}}
    typo, space = _rows(text, "Typography"), {r.get("token", "").strip().lower(): r for r in _rows(text, "Space")}
    motion, focus = _rows(text, "Motion"), {r.get("property", "").lower(): r for r in _rows(text, "Focus")}
    states = _rows(text, "States")
    # Tokens are matched by prefix: `radius`, `radius small`, `radius pill` are all radii.
    radii = [(k, _px(v.get("value", ""), "")) for k, v in space.items() if k.startswith("radius")]
    radii = [(k, r) for k, r in radii if r]
    shadows = [(k, v.get("value", "").strip().strip("`")) for k, v in space.items()
               if k.startswith(("elevation", "shadow")) and v.get("value", "").strip()]
    unit = _px(space.get("spacing unit", {}).get("value", ""), "8px")
    radius = radii[0][1] if radii else "4px"
    border = _px(space.get("border width", {}).get("value", ""), "1px")
    shadow = shadows[0][1] if shadows else "0 1px 3px rgba(0,0,0,.2)"
    ring = focus.get("ring", {}).get("value", "")
    ring_w, ring_off = _px(ring, "2px"), _px(focus.get("offset", {}).get("value", ""), "2px")
    # The ring's colour as the Focus table states it: a hex, or a palette role it names.
    named = next((role for role in sorted(colours, key=len, reverse=True)
                  if re.search(rf"\b{re.escape(role)}\b", ring, re.I)), None)
    c["focus"] = _hex(ring) or (colours[named] if named else c["focus"])
    # Text on the accent: the role DESIGN.md names for it, else whichever of ground / ink reads.
    stated = next((colours[r] for r in colours if ON_ACCENT.match(r)), None)
    c["on-accent"] = stated or max((c["ground"], c["ink"]), key=lambda t: contrast(t, c["accent"]))
    families = [r.get("family (with fallback stack)", r.get("family", "")) for r in typo]
    body_font = families[-1] if families else "system-ui, sans-serif"

    swatches = []
    for role, r in palette_rows.items():
        for hx in _hexes(r["hex"]):           # a row may carry several colours (a tag set)
            swatches.append(
                f'<div class="sw"><div class="chip" style="background:{hx}"></div>'
                f'<div><b>{html.escape(role)}</b> <code>{hx}</code> {_badge(r)}<br>'
                f'<small>on ground {contrast(hx, c["ground"])}:1 · on ink {contrast(hx, c["ink"])}:1</small><br>'
                f'<small>{html.escape(r.get("used for", ""))}</small></div></div>')
    surfaces, texts = surfaces_and_text(palette_rows)
    matrix = ""
    if surfaces and texts:
        head = "".join(f"<th>{html.escape(s)}</th>" for s in surfaces)
        body = ""
        for role, need in texts.items():
            cells = ""
            for srf in surfaces:
                if srf not in _scope(palette_rows[role], surfaces):
                    cells += "<td>–</td>"
                    continue
                ratio = min(contrast(hx, colours[srf]) for hx in _hexes(palette_rows[role]["hex"]))
                cells += f'<td class="{"ok" if ratio >= need else "bad"}">{ratio}:1</td>'
            body += f"<tr><th>{html.escape(role)} <small>(needs {need}:1)</small></th>{cells}</tr>"
        matrix = (f'<section><h2>Text on every surface</h2><table class="mx"><tr><th></th>{head}</tr>{body}'
                  f'</table></section>')
    shape = "".join(f'<div class="shape" style="border-radius:{r}">{html.escape(k)} · {r}</div>' for k, r in radii)
    shape += "".join(f'<div class="card" style="box-shadow:{html.escape(v)}"><b>{html.escape(k)}</b><br>'
                     f'<code>{html.escape(v)}</code></div>' for k, v in shadows)
    specimens = []
    for r in typo:
        fam = r.get("family (with fallback stack)", r.get("family", "")) or body_font
        size = _px(r.get("size / line height", ""), "16px")
        weight = re.search(r"\d{3}", r.get("weight", "")) or None
        specimens.append(
            f'<div class="spec"><div style="font-family:{html.escape(fam)};font-size:{size};'
            f'font-weight:{weight.group(0) if weight else 400}">The quick brown fox jumps over the lazy dog</div>'
            f'<small><b>{html.escape(r.get("token", ""))}</b> · {html.escape(fam)} · '
            f'{html.escape(r.get("weight", ""))} · {html.escape(r.get("size / line height", ""))} {_badge(r)}</small></div>')
    motions = []
    for i, r in enumerate(motion):
        dur = _ms_value(r.get("duration (ms)", ""))
        ease = r.get("easing", "") or "ease"
        motions.append(
            f'<div class="mo"><div class="dot" style="animation-duration:calc({dur} * 4);'
            f'animation-timing-function:{html.escape(ease)}"></div><small><b>{html.escape(r.get("token", ""))}</b> '
            f'{dur} {html.escape(ease)} · {html.escape(r.get("what animates (named properties)", ""))} {_badge(r)}</small></div>')
    state_cards = "".join(
        f'<div class="card"><b>{html.escape(r.get("state", ""))}</b> {_badge(r)}<p>{html.escape(r.get("treatment", ""))}</p></div>'
        for r in states)
    space_rows = "".join(
        f'<li>{html.escape(k)}: <code>{html.escape(v.get("value", ""))}</code> {_badge(v)}</li>' for k, v in space.items())
    decided = sum(1 for _, h, cells in L._tables(text) if "source" in h
                  and cells[h.index("source")].lower().startswith("decided"))
    briefed = sum(1 for _, h, cells in L._tables(text) if "source" in h
                  and cells[h.index("source")].lower().startswith("brief"))
    page = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>DESIGN preview — {html.escape(b.name)}</title><style>
:root {{ {"".join(f"--{k}:{v};" for k, v in c.items())} --u:{unit}; --r:{radius}; --bw:{border}; }}
* {{ box-sizing:border-box }} body {{ margin:0; background:var(--ground); color:var(--ink); font-family:{body_font}; }}
main {{ max-width:1100px; margin:0 auto; padding:calc(var(--u)*4) calc(var(--u)*2); display:grid; gap:calc(var(--u)*4) }}
h1 {{ margin:0; font-size:1.4rem }} h2 {{ margin:0 0 var(--u); font-size:1rem; text-transform:uppercase; letter-spacing:.06em; color:var(--muted) }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:calc(var(--u)*2) }}
.sw {{ display:flex; gap:var(--u); align-items:flex-start }} .chip {{ width:56px; height:56px; flex:none; border-radius:var(--r); border:var(--bw) solid var(--muted) }}
.spec {{ display:grid; gap:4px; overflow-wrap:anywhere }} code {{ font-size:.85em }}
.badge {{ font:600 10px/1 system-ui; padding:2px 6px; border-radius:999px; vertical-align:middle }}
.badge.brief {{ background:#e7f5ec; color:#11713a }} .badge.decided {{ background:#fff4e0; color:#8a4b00 }} .badge.\\? {{ background:#fdecea; color:#b42318 }}
.btn {{ font:inherit; padding:var(--u) calc(var(--u)*2); border-radius:var(--r); border:var(--bw) solid var(--ink); background:var(--accent); color:var(--on-accent); cursor:pointer }}
.btn.secondary {{ background:transparent; color:var(--ink) }}
.btn:focus-visible, .btn.focused, input:focus-visible {{ outline:{ring_w} solid var(--focus); outline-offset:{ring_off} }}
label {{ display:grid; gap:4px; max-width:320px }} input {{ font:inherit; padding:var(--u); border:var(--bw) solid var(--danger); border-radius:var(--r); background:var(--ground); color:var(--ink) }}
.err {{ color:var(--danger); font-size:.85em }}
.card {{ padding:calc(var(--u)*2); border-radius:var(--r); box-shadow:{html.escape(shadow)}; border:var(--bw) solid color-mix(in srgb, var(--ink) 15%, transparent) }}
.shape {{ padding:calc(var(--u)*2); background:color-mix(in srgb, var(--accent) 20%, var(--ground)) }}
.mx {{ border-collapse:collapse }} .mx th, .mx td {{ padding:4px 10px; border:1px solid color-mix(in srgb, var(--ink) 20%, transparent); text-align:left }}
.mx .ok {{ color:inherit }} .mx .bad {{ background:#fdecea; color:#b42318; font-weight:700 }}
.mo {{ display:grid; gap:4px }} .dot {{ width:24px; height:24px; border-radius:50%; background:var(--accent); animation:slide infinite alternate }}
@keyframes slide {{ from {{ transform:translateX(0) }} to {{ transform:translateX(160px) }} }}
@media (prefers-reduced-motion: reduce) {{ .dot {{ animation:none }} }}
</style></head><body><main>
<header><h1>DESIGN preview — {html.escape(b.name)}</h1>
<p>design_direction <code>{html.escape(str(b.metadata.get("design_direction", "")))}</code> ·
{briefed} value(s) from the brief, <b>{decided} decided by the agent</b> (hover a badge for the reason).
Faces show in their fallback until the app vendors the font files.</p></header>
<section><h2>Palette</h2><div class="grid">{"".join(swatches)}</div></section>
<section><h2>Type</h2><div class="grid" style="grid-template-columns:1fr">{"".join(specimens)}</div></section>
{matrix}
<section><h2>Space, shape, depth</h2><ul>{space_rows}</ul><div class="grid">{shape}</div></section>
<section><h2>Components</h2><div class="grid">
<div style="display:flex;gap:var(--u);flex-wrap:wrap"><button class="btn">Primary action</button>
<button class="btn secondary">Secondary</button><button class="btn focused">Focused</button></div>
<label>Email<input value="not-an-email" aria-invalid="true"><span class="err">Enter an email like name@example.com</span></label>
<div class="card"><b>A card</b><p>Running text at the body face, to judge measure, rhythm and contrast together.</p></div>
</div></section>
<section><h2>States</h2><div class="grid">{state_cards}</div></section>
<section><h2>Motion</h2><div class="grid">{"".join(motions)}</div></section>
</main></body></html>"""
    meta = {"design_sha": hashlib.sha256(text.encode()).hexdigest(), "decided": decided, "brief": briefed,
            "contrast": {role: {"on_ground": contrast(hx, c["ground"]), "on_ink": contrast(hx, c["ink"])}
                         for role, hx in colours.items()}}
    return page, meta


SHOT = """
import sys
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch()
    for w, h in ((390, 844), (1440, 900)):
        p = b.new_page(viewport={"width": w, "height": h}, reduced_motion="reduce")
        p.goto("file:///design/preview.html")
        p.screenshot(path=f"/design/preview@{w}.png", full_page=True)
    b.close()
"""


def build(b) -> tuple[Path, dict, str | None]:
    """Write preview.html + preview.json; screenshots when Docker is up. Returns the note on screenshots."""
    out = b.golden_dir / "design"
    out.mkdir(parents=True, exist_ok=True)
    page, meta = render(b)
    (out / "preview.html").write_text(page)
    (out / "preview.json").write_text(json.dumps(meta, indent=2) + "\n")
    from stack import docker_problem  # noqa: PLC0415
    problem = docker_problem()
    if problem:
        return out, meta, f"screenshots skipped: {problem} -- open preview.html in a browser instead"
    import capture  # noqa: PLC0415
    image = capture.grader_image(out / "grader-build.log")
    proc = subprocess.run(["docker", "run", "--rm", "--entrypoint", "python3", "-v", f"{out}:/design",
                           image, "-c", SHOT], capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        return out, meta, f"screenshots failed: {(proc.stderr or proc.stdout).strip()[-300:]}"
    return out, meta, None


RATIO = re.compile(r"(?:\d+(?:\.\d+)?\s*:\s*1\b|[≥>]=?\s*\d+(?:\.\d+)?)")


def contrast_claims_lint(b) -> list[str]:
    """Contrast in DESIGN.md is computed, never taken on trust.

    A member cannot check a ratio by eye, so a wrong one passes review:
      - every claim in the Palette's AA pair column is recomputed. It is
        `<role> on <role>: N:1` (role names may contain spaces), or a bare `N:1`
        meaning this row's role on ground. It must match within 0.15 and never be
        below 3:1. A ratio written any other way ("each on its tint >= 4.5") cannot
        be checked, so it fails;
      - every text role is measured on every surface role (by name or Used for),
        and must reach 4.5:1 (3:1 for large text and UI). `only on <surfaces>` in
        a role's Used for limits where it is measured.
    """
    path = L.design_path(b)
    if not path.is_file():
        return []
    text = path.read_text()
    rows, colours = palette(text)
    names = "|".join(re.escape(r) for r in sorted(colours, key=len, reverse=True)) or "(?!)"
    pair = re.compile(rf"\b({names})\s+on\s+({names})\s*:\s*(\d+(?:\.\d+)?)\s*:\s*1", re.I)
    problems = []
    for role, row in rows.items():
        cell = row.get("aa pair", "")
        claims = [(a.lower(), b2.lower(), stated) for a, b2, stated in pair.findall(cell)]
        rest = pair.sub(" ", cell)
        bare = re.fullmatch(r"\s*`?(\d+(?:\.\d+)?)\s*:\s*1`?\s*", rest) if not claims else None
        if bare and "ground" in colours:
            claims.append((role, "ground", bare.group(1)))
        elif RATIO.search(rest):
            problems.append(f"## Palette '{role}': the contrast claim {rest.strip()[:60]!r} cannot be checked -- "
                            "write each as `<role> on <role>: N:1` using this table's Role names")
        for a, b2, stated in claims:
            actual = min(contrast(hx, colours[b2]) for hx in _hexes(rows[a]["hex"]))
            if abs(actual - float(stated)) > 0.15:
                problems.append(f"## Palette '{role}': {a} on {b2} is stated as {stated}:1 "
                                f"but computes to {actual}:1")
            elif actual < 3:
                problems.append(f"## Palette '{role}': {a} on {b2} is {actual}:1, below AA "
                                f"for any use (3:1 large text and UI, 4.5:1 text)")
    surfaces, texts = surfaces_and_text(rows)
    for role, need in texts.items():
        for srf in _scope(rows[role], surfaces):
            for hx in _hexes(rows[role]["hex"]):
                ratio = contrast(hx, colours[srf])
                if ratio < need:
                    problems.append(f"## Palette '{role}' {hx} on '{srf}' is {ratio}:1, below the {need}:1 it needs "
                                    f"as {'text' if need == 4.5 else 'large text / UI'} -- change a colour, or write "
                                    f"`only on <surfaces>` in its Used for if it never appears there")
    return problems


def preview_lint(b) -> list[str]:
    """The approved preview must be of the CURRENT DESIGN.md."""
    meta_path = b.golden_dir / "design" / "preview.json"
    if not meta_path.is_file():
        return ["no design preview yet -- run golden/bin/golden-design-preview <bundle>"]
    try:
        meta = json.loads(meta_path.read_text())
    except ValueError:
        return ["design/preview.json is unreadable -- re-run golden-design-preview"]
    if not L.design_path(b).is_file():
        return []
    if meta.get("design_sha") != hashlib.sha256(L.design_path(b).read_text().encode()).hexdigest():
        return ["the design preview is STALE: DESIGN.md changed after it was built -- re-run golden-design-preview"]
    return []
