import json

import brief_units as BU
import media as M
from bundle import Bundle

BRIEF = """# Trail notes

## Overview

Every trail page opens with a hero photograph of the trail at dusk.
Each difficulty level carries an icon beside its name.
The app starts from the environment image with no manual steps.
There is no hero imagery inside the signed-in pages.
"""


def _bundle(reference, design: str = "") -> Bundle:
    (reference / "instruction.md").write_text(BRIEF)
    if design:
        (reference / "solution" / "DESIGN.md").write_text(design)
    return Bundle.load(reference)


def _ids(b):
    by = {u.text: u.id for u in BU.units(b)}
    hero = next(i for t, i in by.items() if "hero photograph" in t)
    icon = next(i for t, i in by.items() if "icon beside" in t)
    none = next(i for t, i in by.items() if "no hero imagery" in t)
    return hero, icon, none


def _design(hero, icon, none, hero_how="fetch", hero_files="trail dusk"):
    return f"""# DESIGN

## Media

| Need | Brief units | Produced by | Search / files | Shown at (px) | Alt |
|---|---|---|---|---|---|
| trail hero | {hero} | {hero_how} | {hero_files} | 1440 | A trail at dusk |
| difficulty icons | {icon} | svg-css | | | |

## Not media

| Brief units | Why it is not a media need |
|---|---|
| {none} | it forbids imagery on the signed-in pages; nothing to produce |
"""


def test_media_units_skip_container_images(reference):
    b = _bundle(reference)
    texts = [u.text for u in M.media_units(b)]
    assert any("hero photograph" in t for t in texts)
    assert not any("environment image" in t for t in texts)


def test_plan_lint_wants_a_media_section_and_every_media_unit(reference):
    b = _bundle(reference, "# DESIGN\n\n## Palette\n")
    assert any("## Media is missing" in p for p in M.media_plan_lint(b))
    hero, icon, none = _ids(b)
    b = _bundle(reference, _design(hero, icon, none).replace(f"| {none} |", "| |"))
    problems = M.media_plan_lint(b)
    assert any(none in p and "neither" in p for p in problems)


def test_fetch_row_needs_candidates_a_choice_and_a_current_sheet(reference):
    b = _bundle(reference)
    hero, icon, none = _ids(b)
    b = _bundle(reference, _design(hero, icon, none))
    assert any("no candidates fetched" in p for p in M.media_plan_lint(b))
    data = {"rows": {"trail-hero": {"candidates": [{"id": "ov-1", "file": "media/candidates/x.jpg"}], "chosen": []}}}
    M.save_manifest(b, data)
    assert any("no candidate chosen" in p for p in M.media_plan_lint(b))
    assert M.choose(b, ["trail-hero=ov-1"]) == []
    assert any("contact sheet is missing" in p for p in M.media_plan_lint(b))
    (b.golden_dir / "media" / "sheet.json").write_text(json.dumps({"fingerprint": M.fingerprint(b)}))
    assert M.media_plan_lint(b) == []
    assert M.choose(b, ["trail-hero=nope"])            # an unknown id is refused


def test_member_supplied_waits_for_the_file(reference):
    b = _bundle(reference)
    hero, icon, none = _ids(b)
    b = _bundle(reference, _design(hero, icon, none, "member-supplied", "hero.jpg"))
    assert any("waiting for member media: hero.jpg" in p for p in M.media_plan_lint(b))
    (b.golden_dir / "inputs" / "media").mkdir(parents=True)
    (b.golden_dir / "inputs" / "media" / "hero.jpg").write_bytes(b"\xff\xd8")
    assert not any("waiting" in p for p in M.media_plan_lint(b))


def test_unknown_produced_by_and_unasked_media_are_refused(reference):
    b = _bundle(reference)
    hero, icon, none = _ids(b)
    design = _design(hero, icon, none, "ai-art") + ""
    design = design.replace("| difficulty icons | " + icon, "| difficulty icons | ")
    problems = M.media_plan_lint(_bundle(reference, design))
    assert any("Produced by must be one of" in p for p in problems)
    assert any("names no brief unit" in p for p in problems)


def test_assets_lint_needs_an_origin_and_a_shippable_licence(reference):
    b = _bundle(reference)
    static = b.app_dir / "static" / "img"
    static.mkdir(parents=True, exist_ok=True)
    (static / "trail.webp").write_bytes(b"RIFF")
    assert any("trail.webp has no row" in p for p in M.assets_lint(b))
    sources = b.golden_dir / "sources.md"
    sources.parent.mkdir(parents=True, exist_ok=True)
    row = "| static/img/trail.webp | Wikimedia Commons | {lic} | Ana Ruiz | / |\n"
    head = "## Assets\n\n| File | Origin | Licence | Creator | Used on |\n|---|---|---|---|---|\n"
    sources.write_text(head + row.format(lic="CC BY-SA 4.0"))
    assert any("is not one golden ships" in p for p in M.assets_lint(b))
    sources.write_text(head + row.format(lic="CC BY 4.0"))
    assert any("must credit 'Ana Ruiz'" in p for p in M.assets_lint(b))
    sources.write_text(head + row.format(lic="CC0"))
    assert M.assets_lint(b) == []


def test_placeholder_media_is_a_finding(reference):
    b = _bundle(reference)
    (b.app_dir / "templates" / "hero.html").write_text('<img src="https://picsum.photos/1200/600" alt="">')
    found = M.placeholder_lint(b)
    assert found and found[0]["check"] == "placeholder-media" and found[0]["blocking"]


def test_render_problems_from_the_page_probe():
    pages = [
        {"path": "/", "viewport": "phone-390", "media": [
            {"kind": "img", "src": "/a.webp", "broken": True, "natural": [0, 0], "shown": [300, 200]},
            {"kind": "img", "src": "/b.webp", "blank": "flat", "natural": [600, 400], "shown": [300, 200]},
            {"kind": "img", "src": "/hero.jpg", "natural": [4000, 2000], "shown": [390, 200], "bytes": 90000},
            {"kind": "img", "src": "/logo.svg", "svg": True, "natural": [2000, 2000], "shown": [40, 40]},
            {"kind": "video", "src": "/reel.mp4", "error": 4, "preload": "metadata"}]},
        {"path": "/", "viewport": "desktop-1440", "media": [
            {"kind": "img", "src": "/a.webp", "broken": True, "natural": [0, 0], "shown": [600, 400]},
            {"kind": "img", "src": "/hero.jpg", "natural": [4000, 2000], "shown": [1440, 720], "bytes": 90000},
            {"kind": "img", "src": "/heavy.jpg", "natural": [800, 600], "shown": [400, 300], "bytes": 900000}]},
    ]
    out = M.problems(pages, {})
    assert sum("/a.webp" in p for p in out) == 1                 # one finding per picture, not per viewport
    assert any("flat field" in p for p in out)
    assert any("4000px wide but never shown wider than 1440px" in p for p in out)
    assert not any("logo.svg" in p for p in out)                 # vectors have no natural size to waste
    assert any("MediaError 4" in p for p in out)
    assert any("heavy.jpg" in p and "KB" in p for p in out)


def test_icon_lists_resolve_to_licensed_svgs():
    found = M.icon_candidates("lucide: timer, route")
    assert [c["id"] for c in found] == ["lucide-timer", "lucide-route"]
    assert found[0]["licence"] == "ISC" and found[0]["url"].endswith("/timer.svg")
    assert M.icon_candidates("runner at dusk") is None
