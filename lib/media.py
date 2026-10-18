"""Media: every picture, icon and video the brief asks for -- planned, sourced, licensed, rendered.

The brief decides whether there is media at all. DESIGN.md ## Media turns each
media need into one row that says how it is produced:

  svg-css           drawn by the agent as SVG or CSS -- the default
  seeded-renderer   drawn by the app at request time from stored data (a seed)
  rendered-video    frames drawn by code, encoded with ffmpeg at authoring time
  fetch             a CC0 / public-domain file found by golden-media (Openverse
                    without Flickr, Wikimedia Commons without personality or
                    trademark restrictions; Lucide / Heroicons for icons) --
                    licence and creator come from the source's own API, never
                    from the model. CC BY only with --allow-cc-by.
  member-supplied   a file the member provides in _handoff/golden/inputs/media/

and DESIGN.md ## Not media accounts for every brief sentence that mentions media
without asking for any ("no hero imagery inside the signed-in pages").

  P1   media_plan_lint   every media sentence is planned; fetched files chosen and
                         on the contact sheet the member reviews; member files present
  P3   assets_lint       every media or font file in the app has an origin and licence
  G5   problems()        every picture renders, is not a flat field, is not far larger
                         than it is shown; every video loads
  G8   placeholder_lint  no picsum, placehold.co, grey boxes or lorem imagery
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

import brief_units as BU
import phaselints as L

PRODUCED = ("svg-css", "seeded-renderer", "rendered-video", "fetch", "member-supplied")
MEDIA_WORDS = re.compile(
    r"\b(images?|imagery|photo(?:graph)?s?|pictures?|illustrat\w*|icons?|logos?|avatars?|portraits?|"
    r"thumbnails?|posters?|videos?|reels?|footage|galler(?:y|ies)|artwork|"
    r"hero (?:art|shot)|svgs?|mp4|webm|lottie|favicon)\b", re.I)
# "the environment image", "the verifier image": containers, not pictures.
NOT_PICTURES = re.compile(r"\b(?:environment|docker|container|base|verifier|runner|app|oci)\s+images?\b|"
                          r"\bimages?\s+(?:build|tag|digest|registry)\b", re.I)
VIDEO_WORDS = re.compile(r"\b(videos?|reels?|footage|mp4|webm|film)\b", re.I)
BUNIT = re.compile(r"B-\d{3}")
MEDIA_EXT = {".png", ".jpg", ".jpeg", ".webp", ".avif", ".gif", ".svg", ".ico", ".bmp", ".mp4", ".webm",
             ".mov", ".m4v", ".mp3", ".ogg", ".wav", ".woff", ".woff2", ".ttf", ".otf"}
LICENCE_OK = re.compile(
    r"^\s*(original|cc0|pdm|public[- ]domain|cc[- ]?by(?![- ]?(?:sa|nc|nd))(?:[- ]?\d(?:\.\d)?)?|"
    r"unsplash|pexels|(?:sil[- ])?ofl|mit|isc|apache|bsd|member-supplied)\b", re.I)
ATTRIBUTION = re.compile(r"^\s*cc[- ]?by\b", re.I)
PLACEHOLDER = re.compile(
    r"(picsum\.photos|placehold\.co|placeholder\.com|via\.placeholder|dummyimage\.com|placekitten|"
    r"placebear|loremflickr|source\.unsplash\.com|fakeimg\.pl|placeimg|lorempixel|"
    r"\bplaceholder\.(?:png|jpe?g|webp|svg|gif)\b|\blorem[-_]?image)", re.I)
UA = "golden-media/1.0 (deku golden toolkit; https://github.com/)"
ICON_SETS = {
    "lucide": ("https://unpkg.com/lucide-static@0.460.0/icons/{name}.svg", "ISC",
               "https://lucide.dev/license", "Lucide contributors", "https://lucide.dev/icons/{name}"),
    "heroicons": ("https://unpkg.com/heroicons@2.1.5/24/outline/{name}.svg", "MIT",
                  "https://github.com/tailwindlabs/heroicons/blob/master/LICENSE", "Tailwind Labs",
                  "https://heroicons.com"),
}


# ------------------------------------------------------------------ the plan
def media_units(b) -> list:
    """Brief units that mention a picture, icon or video (container images aside)."""
    return [u for u in BU.units(b) if MEDIA_WORDS.search(NOT_PICTURES.sub(" ", u.text))]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "media"


def rows(b) -> tuple[list[dict], list[dict], str]:
    """(## Media rows, ## Not media rows, the ## Media section text)."""
    path = L.design_path(b)
    text = path.read_text() if path.is_file() else ""
    media, not_media = [], []
    for section, header, cells in L._tables(text):
        if not any(cells):
            continue
        row = {h: (cells[i] if i < len(cells) else "") for i, h in enumerate(header)}
        if section.lower() == "media":
            row["slug"] = slug(row.get("need", ""))
            media.append(row)
        elif section.lower() == "not media":
            not_media.append(row)
    return media, not_media, L._section(text, "Media")


def manifest_path(b) -> Path:
    return b.golden_dir / "media" / "media.json"


def manifest(b) -> dict:
    try:
        return json.loads(manifest_path(b).read_text())
    except (OSError, ValueError):
        return {"rows": {}}


def save_manifest(b, data: dict) -> None:
    manifest_path(b).parent.mkdir(parents=True, exist_ok=True)
    manifest_path(b).write_text(json.dumps(data, indent=2) + "\n")


def fingerprint(b) -> str:
    """What the contact sheet showed: the plan rows and the chosen files."""
    media, _, _ = rows(b)
    chosen = {k: v.get("chosen") for k, v in manifest(b).get("rows", {}).items()}
    blob = json.dumps([[r.get(k, "") for k in sorted(r)] for r in media], sort_keys=True) + json.dumps(chosen, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def member_files(row: dict) -> list[str]:
    return [f.strip() for f in re.split(r"[,;]", row.get("search / files", "")) if f.strip()]


def media_plan_lint(b) -> list[str]:
    """P1: every media sentence of the brief is planned, and every planned file is in hand."""
    if not L.design_path(b).is_file():
        return []
    media, not_media, section = rows(b)
    problems = []
    if not section.strip():
        return ["## Media is missing -- list every media need of the brief (golden/templates/DESIGN.md), "
                "or write `none` under it when the brief asks for no media"]
    known = {u.id: u for u in BU.units(b)}
    covered = set()
    for r in media:
        covered.update(BUNIT.findall(r.get("brief units", "")))
    for r in not_media:
        covered.update(BUNIT.findall(r.get("brief units", "")))
        if not r.get("why it is not a media need", "").strip():
            problems.append(f"## Not media row {r.get('brief units', '')!r} gives no reason")
    for u in media_units(b):
        if u.id not in covered:
            problems.append(f"{u.id} mentions media but is in neither ## Media nor ## Not media: "
                            f"«{u.text[:110]}»")
    for uid in sorted(covered - set(known)):
        problems.append(f"{uid} is not a unit of _handoff/golden/brief-units.md")
    data, inputs = manifest(b).get("rows", {}), b.golden_dir / "inputs" / "media"
    needs_sheet = False
    for r in media:
        need, how = r.get("need", "") or "(row)", r.get("produced by", "").strip().lower()
        if how not in PRODUCED:
            problems.append(f"## Media '{need}': Produced by must be one of {', '.join(PRODUCED)} (got {how!r})")
            continue
        if not BUNIT.search(r.get("brief units", "")):
            problems.append(f"## Media '{need}' names no brief unit -- media the brief does not ask for is "
                            "unasked scope")
        raster = how in ("fetch", "member-supplied")
        if raster and not re.search(r"\d", r.get("shown at (px)", "")):
            problems.append(f"## Media '{need}': give the largest width it is shown at, in px (it is resized to it)")
        if raster and not r.get("alt", "").strip():
            problems.append(f"## Media '{need}': write the alt text, or `decorative`")
        if how == "fetch":
            needs_sheet = True
            got = data.get(r["slug"]) or {}
            if not got.get("candidates"):
                problems.append(f"## Media '{need}': no candidates fetched yet -- run golden/bin/golden-media <bundle>")
            elif not got.get("chosen"):
                problems.append(f"## Media '{need}': no candidate chosen -- look at the contact sheet, then "
                                f"golden-media <bundle> --choose {r['slug']}=<id>")
        elif how == "member-supplied":
            needs_sheet = True
            want = member_files(r)
            missing = [f for f in want if not (inputs / f).is_file()]
            if not want:
                problems.append(f"## Media '{need}': list the files the member supplies under Search / files")
            elif missing:
                problems.append(f"waiting for member media: {', '.join(missing)} -- the member puts them in "
                                f"_handoff/golden/inputs/media/ (never a placeholder in the meantime)")
        elif how == "rendered-video" and not ffmpeg():
            problems.append(f"## Media '{need}' is rendered-video but ffmpeg is not installed on this machine "
                            "(macOS: brew install ffmpeg)")
    if needs_sheet:
        sheet = b.golden_dir / "media" / "sheet.json"
        try:
            shown = json.loads(sheet.read_text()).get("fingerprint")
        except (OSError, ValueError):
            shown = None
        if shown != fingerprint(b):
            problems.append("the media contact sheet is missing or older than ## Media and the chosen files -- "
                            "re-run golden/bin/golden-media <bundle> so the member reviews what will ship")
    return problems


# ------------------------------------------------------------------ licences
def _sources_rows(b) -> list[dict]:
    path = b.golden_dir / "sources.md"
    if not path.is_file():
        return []
    out = []
    for section, header, cells in L._tables(path.read_text()):
        if section.lower() == "assets" and any(cells):
            out.append({h: (cells[i] if i < len(cells) else "") for i, h in enumerate(header)})
    return out


def app_media_files(b) -> list[Path]:
    from receipts import IGNORE_DIRS  # noqa: PLC0415
    out = []
    if not b.app_dir.is_dir():
        return out
    for path in b.app_dir.rglob("*"):
        rel = path.relative_to(b.app_dir)
        if path.is_file() and path.suffix.lower() in MEDIA_EXT and not any(p in IGNORE_DIRS for p in rel.parts):
            out.append(path)
    return sorted(out)


def _matches(spec: str, rel: str) -> bool:
    spec = spec.strip().strip("`").removeprefix("solution/app/")
    return bool(spec) and (spec == rel or Path(rel).match(spec) or spec == Path(rel).name)


def assets_lint(b) -> list[str]:
    """Every media or font file in the app says where it came from and under what licence."""
    files = app_media_files(b)
    if not files:
        return []
    vendored = {}
    for row in manifest(b).get("rows", {}).values():
        for v in row.get("vendored") or []:
            vendored[v["path"]] = v
    table = _sources_rows(b)
    app_text = None
    problems = []
    for f in files:
        rel = str(f.relative_to(b.app_dir))
        entry = vendored.get(rel)
        if entry is None:
            row = next((r for r in table if _matches(r.get("file", ""), rel)), None)
            if row is None:
                problems.append(f"{rel} has no row in _handoff/golden/sources.md ## Assets (origin + licence)")
                continue
            entry = {"licence": row.get("licence", ""), "origin": row.get("origin", ""), "creator": row.get("creator", "")}
            if not entry["origin"].strip():
                problems.append(f"{rel}: ## Assets row gives no origin")
        if not LICENCE_OK.match(entry.get("licence", "")):
            problems.append(f"{rel}: licence {entry.get('licence', '')!r} is not one golden ships "
                            "(original, CC0, public domain, CC BY, Unsplash, Pexels, OFL, MIT/ISC/Apache, member-supplied)")
        elif ATTRIBUTION.match(entry.get("licence", "")) and entry.get("creator"):
            if app_text is None:
                import checks  # noqa: PLC0415
                app_text = "\n".join(p.read_text(errors="ignore") for p in checks._app_files(b))
            if entry["creator"] not in app_text:
                problems.append(f"{rel} is {entry['licence']}: the app must credit {entry['creator']!r} "
                                "(a credits line or page)")
    return problems


def placeholder_lint(b) -> list[dict]:
    import checks  # noqa: PLC0415
    out = []
    for path in checks._app_files(b):
        m = PLACEHOLDER.search(path.read_text(errors="ignore"))
        if m:
            out.append(checks.finding("placeholder-media",
                f"{path.relative_to(b.app_dir)} uses placeholder media ({m.group(0)}) -- ship the real asset "
                "or a member-supplied one; never a stand-in"))
    return out


# ------------------------------------------------------------------ G5
def problems(pages: list[dict], rules: dict) -> list[str]:
    """Render findings from the page probe's `media` records, one per picture or video."""
    ratio = float(rules.get("oversize_ratio", 2.5))
    bpp = float(rules.get("max_bytes_per_px", 0.6))
    floor = int(rules.get("min_bytes_budget", 150_000))
    out, seen, size = [], set(), {}
    for p in pages:
        where = f"{p['path']} @{p['viewport']}" + (f" [signed in: {p['session']}]" if p.get("session") else "")
        for m in p.get("media") or []:
            src = m.get("src") or "(no src)"
            if m["kind"] == "img":
                if m.get("broken"):
                    key, text = ("broken", src), f"{where}: image answered but does not render (corrupt or wrong format): {src[:120]}"
                elif m.get("blank"):
                    key, text = ("blank", src), f"{where}: image renders as a {m['blank']} field -- nothing to see: {src[:120]}"
                else:
                    key = None
                if key and key not in seen:
                    seen.add(key)
                    out.append(text)
                if not m.get("svg") and not m.get("broken") and m.get("natural", [0])[0]:
                    s = size.setdefault(src, {"natural": m["natural"], "shown": [0, 0], "bytes": 0, "where": where})
                    s["shown"] = [max(s["shown"][0], m["shown"][0]), max(s["shown"][1], m["shown"][1])]
                    s["bytes"] = max(s["bytes"], m.get("bytes") or 0)
            elif m["kind"] == "video":
                key = ("video", src)
                if key in seen:
                    continue
                if m.get("error"):
                    seen.add(key)
                    out.append(f"{where}: video failed to load (MediaError {m['error']}): {src[:120]}")
                elif m.get("preload") != "none" and not m.get("duration"):
                    seen.add(key)
                    out.append(f"{where}: video never reported a duration (not playable): {src[:120]}")
    for src, s in size.items():
        nw, (sw, sh) = s["natural"][0], s["shown"]
        if sw and nw > ratio * sw:
            out.append(f"{s['where']}: image is {nw}px wide but never shown wider than {sw}px "
                       f"(resize it, or serve a srcset): {src[:110]}")
        elif sw and s["bytes"] > max(floor, bpp * sw * sh * 4):
            out.append(f"{s['where']}: image weighs {s['bytes'] // 1024} KB for a {sw}x{sh} box "
                       f"(compress it): {src[:110]}")
    return out


# ------------------------------------------------------------------ fetch
def _get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _clean_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


# The lowest-risk policy by default: CC0 and public domain only (no conditions, no
# credit to forget); never Flickr, where most mislabelled uploads live; never a
# Commons file tagged with personality (an identifiable person) or trademark
# restrictions, which a copyright licence does not clear.
def search_openverse(query: str, n: int, allow_by: bool = False) -> list[dict]:
    q = urllib.parse.urlencode({"q": query, "license": "cc0,pdm" + (",by" if allow_by else ""),
                                "excluded_source": "flickr", "page_size": n, "mature": "false"})
    data = json.loads(_get(f"https://api.openverse.org/v1/images/?{q}"))
    out = []
    for r in data.get("results") or []:
        lic = {"cc0": "CC0", "pdm": "Public domain"}.get(r.get("license"), f"CC BY {r.get('license_version') or ''}".strip())
        out.append({"id": f"ov-{r['id'][:8]}", "source": f"Openverse ({r.get('source') or '?'})",
                    "title": r.get("title") or "",
                    "url": r["url"], "landing": r.get("foreign_landing_url") or "", "creator": r.get("creator") or "",
                    "licence": lic, "licence_url": r.get("license_url") or "",
                    "width": r.get("width"), "height": r.get("height")})
    return out


def search_commons(query: str, n: int, allow_by: bool = False) -> list[dict]:
    q = urllib.parse.urlencode({
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
        "gsrsearch": f"{query} filetype:bitmap", "gsrlimit": n * 2, "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 2400,
        "iiextmetadatafilter": "LicenseShortName|Artist|LicenseUrl|ObjectName|Restrictions"})
    data = json.loads(_get(f"https://commons.wikimedia.org/w/api.php?{q}"))
    out = []
    for page in (data.get("query") or {}).get("pages", {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        lic = _clean_html((meta.get("LicenseShortName") or {}).get("value", ""))
        ok = r"^(cc0|public domain|pd\b|cc by \d)" if allow_by else r"^(cc0|public domain|pd\b)"
        if not re.match(ok, lic, re.I) or re.search(r"\b(sa|nc|nd)\b", lic, re.I):
            continue                     # share-alike / non-commercial / no-derivatives are never shipped
        if _clean_html((meta.get("Restrictions") or {}).get("value", "")):
            continue                     # personality / trademark / insignia rights a licence does not clear
        out.append({"id": f"wm-{page['pageid']}", "source": "Wikimedia Commons",
                    "title": _clean_html((meta.get("ObjectName") or {}).get("value", "")) or page.get("title", ""),
                    "url": info.get("thumburl") or info.get("url"), "landing": info.get("descriptionurl", ""),
                    "creator": _clean_html((meta.get("Artist") or {}).get("value", ""))[:120], "licence": lic,
                    "licence_url": _clean_html((meta.get("LicenseUrl") or {}).get("value", "")),
                    "width": info.get("thumbwidth") or info.get("width"),
                    "height": info.get("thumbheight") or info.get("height")})
    return out[:n]


def icon_candidates(spec: str) -> list[dict] | None:
    m = re.match(r"^\s*(lucide|heroicons)\s*:\s*(.+)$", spec, re.I)
    if not m:
        return None
    url, lic, lic_url, creator, landing = ICON_SETS[m.group(1).lower()]
    return [{"id": f"{m.group(1).lower()}-{name}", "source": m.group(1).title(), "title": name,
             "url": url.format(name=name), "landing": landing.format(name=name), "creator": creator,
             "licence": lic, "licence_url": lic_url, "icon": True}
            for name in [n.strip() for n in m.group(2).split(",") if n.strip()]]


def fetch(b, n: int = 8, refresh: bool = False, allow_by: bool = False, log=print) -> dict:
    """Candidates for every `fetch` row; icons are chosen as named, photos by the agent."""
    media, _, _ = rows(b)
    data = manifest(b)
    store = b.golden_dir / "media" / "candidates"
    for r in media:
        if r.get("produced by", "").strip().lower() != "fetch":
            continue
        key, query = r["slug"], r.get("search / files", "").strip()
        row = data["rows"].setdefault(key, {})
        row.update(need=r.get("need", ""), query=query)
        if row.get("candidates") and not refresh and row.get("query_fetched") == query:
            continue
        icons = icon_candidates(query)
        if icons is not None:
            found = icons
        else:
            found, errors = [], []
            for search in (search_openverse, search_commons):
                try:
                    found += search(query, n, allow_by)
                except Exception as exc:  # one source down must not stop the other
                    errors.append(f"{search.__name__}: {exc.__class__.__name__}")
            if errors:
                log(f"  {key}: {'; '.join(errors)}")
        kept = []
        for c in found:
            ext = ".svg" if c.get("icon") else (Path(urllib.parse.urlparse(c["url"]).path).suffix.lower() or ".jpg")
            dest = store / key / f"{c['id']}{ext if ext in MEDIA_EXT else '.jpg'}"
            try:
                if not dest.is_file():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(_get(c["url"], timeout=60))
                kept.append({**c, "file": str(dest.relative_to(b.golden_dir))})
            except Exception as exc:
                log(f"  {key}: could not download {c['id']} ({exc.__class__.__name__})")
        row.update(candidates=kept, query_fetched=query)
        row["chosen"] = [c["id"] for c in kept] if icons is not None else [
            c for c in (row.get("chosen") or []) if any(k["id"] == c for k in kept)]
        log(f"  {key}: {len(kept)} candidate(s) from "
            + ("the icon set (MIT / ISC)" if icons is not None else "Openverse + Wikimedia Commons ("
               + ("CC0 / public domain / CC BY" if allow_by else "CC0 / public domain only") + ")"))
    save_manifest(b, data)
    return data


def choose(b, picks: list[str]) -> list[str]:
    data, problems = manifest(b), []
    for pick in picks:
        key, _, ids = pick.partition("=")
        row = data["rows"].get(key.strip())
        if row is None:
            problems.append(f"no fetched row {key!r} (rows: {', '.join(data['rows']) or 'none'})")
            continue
        want = [i.strip() for i in ids.split(",") if i.strip()]
        unknown = [i for i in want if not any(c["id"] == i for c in row.get("candidates") or [])]
        if unknown:
            problems.append(f"{key}: no candidate {', '.join(unknown)}")
            continue
        row["chosen"] = want
    save_manifest(b, data)
    return problems


# ------------------------------------------------------------------ contact sheet
def sheet(b) -> tuple[Path, str | None]:
    """sheet.html (+ sheet.png when Docker is up): each need beside its brief words and its files."""
    import html  # noqa: PLC0415
    media, _, _ = rows(b)
    data, units = manifest(b).get("rows", {}), {u.id: u.text for u in BU.units(b)}
    out = b.golden_dir / "media"
    out.mkdir(parents=True, exist_ok=True)
    parts = ["<!doctype html><meta charset=utf-8><title>Media contact sheet</title><style>"
             "body{font:14px/1.45 system-ui,sans-serif;margin:24px;color:#1b1b1b;background:#fafaf8}"
             "h2{margin:28px 0 4px;font-size:18px}.brief{color:#555;margin:0 0 10px;max-width:90ch}"
             ".grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:12px}"
             "figure{margin:0;padding:8px;background:#fff;border:1px solid #ddd;border-radius:6px}"
             "figure.chosen{border:3px solid #0a7d3e}img{width:100%;height:130px;object-fit:contain;background:#eee}"
             "figcaption{font-size:12px;color:#333;margin-top:6px;word-break:break-word}"
             ".tag{display:inline-block;padding:1px 6px;border-radius:4px;background:#eee;font-size:12px}</style>",
             "<h1>Media contact sheet</h1><p>Every media need in DESIGN.md, the brief sentences behind it, and the "
             "files that will ship. A green border marks the chosen file.</p>"]
    for r in media:
        how = r.get("produced by", "").strip().lower()
        said = " / ".join(units.get(u, u) for u in BUNIT.findall(r.get("brief units", "")))
        parts.append(f"<h2>{html.escape(r.get('need', ''))} <span class=tag>{html.escape(how)}</span></h2>"
                     f"<p class=brief>«{html.escape(said[:600])}»</p>")
        figs = []
        if how == "fetch":
            row = data.get(r["slug"]) or {}
            for c in row.get("candidates") or []:
                cls = " class=chosen" if c["id"] in (row.get("chosen") or []) else ""
                figs.append(f"<figure{cls}><img src=\"{html.escape(c['file'])}\" alt=\"\"><figcaption><b>{c['id']}</b> "
                            f"· {html.escape(c['licence'])} · {html.escape(c['creator'][:60])}<br>"
                            f"{html.escape(c['title'][:80])}</figcaption></figure>")
        elif how == "member-supplied":
            for f in member_files(r):
                figs.append(f"<figure class=chosen><img src=\"inputs/media/{html.escape(f)}\" alt=\"\">"
                            f"<figcaption><b>{html.escape(f)}</b> · member-supplied</figcaption></figure>")
        else:
            figs.append(f"<p>Made in code ({html.escape(how)}): seen in the design preview and the app, not here.</p>")
        parts.append("<div class=grid>" + "".join(figs) + "</div>")
    # Served from _handoff/golden/ so candidate and member paths resolve as written.
    page = b.golden_dir / "media-sheet.html"
    page.write_text("".join(parts))
    (out / "sheet.json").write_text(json.dumps({"fingerprint": fingerprint(b)}) + "\n")
    from stack import docker_problem  # noqa: PLC0415
    problem = docker_problem()
    if problem:
        return page, f"screenshot skipped: {problem} -- open {page} in a browser"
    import capture  # noqa: PLC0415
    image = capture.grader_image(out / "grader-build.log")
    shot = ("from playwright.sync_api import sync_playwright\n"
            "with sync_playwright() as pw:\n"
            " b = pw.chromium.launch(); p = b.new_page(viewport={'width': 1280, 'height': 900})\n"
            " p.goto('file:///g/media-sheet.html'); p.wait_for_timeout(800)\n"
            " p.screenshot(path='/g/media/sheet.png', full_page=True); b.close()\n")
    proc = subprocess.run(["docker", "run", "--rm", "--entrypoint", "python3", "-v", f"{b.golden_dir}:/g",
                           image, "-c", shot], capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        return page, f"screenshot failed: {(proc.stderr or proc.stdout).strip()[-300:]}"
    return page, None


# ------------------------------------------------------------------ vendor (P3)
ENCODE = """
import base64, json, sys
from playwright.sync_api import sync_playwright
jobs = json.load(open('/w/jobs.json'))
with sync_playwright() as pw:
    b = pw.chromium.launch(); p = b.new_page()
    for j in jobs:
        data = base64.b64encode(open(j['src'], 'rb').read()).decode()
        out = p.evaluate('''async ([data, mime, width, q]) => {
            const img = new Image(); img.src = `data:${mime};base64,${data}`; await img.decode();
            const w = Math.min(img.naturalWidth, width), h = Math.round(img.naturalHeight * w / img.naturalWidth);
            const c = document.createElement('canvas'); c.width = w; c.height = h;
            c.getContext('2d').drawImage(img, 0, 0, w, h);
            return [c.toDataURL('image/webp', q).split(',')[1], w, h];
        }''', [data, j['mime'], j['width'], j['quality']])
        open(j['dest'], 'wb').write(base64.b64decode(out[0])); j['size'] = out[1:]
    b.close()
json.dump(jobs, open('/w/jobs.json', 'w'))
"""


def vendor(b, into: str, quality: float = 0.8, log=print) -> list[str]:
    """Copy every chosen file into the app, resized to 2x its shown width, as WebP (SVG as-is)."""
    media, _, _ = rows(b)
    data = manifest(b)
    dest_dir = b.app_dir / into
    dest_dir.mkdir(parents=True, exist_ok=True)
    work = b.golden_dir / "media" / "encode"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    jobs, problems, records = [], [], {}
    for r in media:
        how = r.get("produced by", "").strip().lower()
        if how not in ("fetch", "member-supplied"):
            continue
        # Twice the shown width covers retina screens; past 2400px the bytes buy nothing visible.
        width = min(2400, int((re.findall(r"\d+", r.get("shown at (px)", "")) or ["1200"])[0]) * 2)
        if how == "fetch":
            row = data["rows"].get(r["slug"]) or {}
            picks = [c for c in row.get("candidates") or [] if c["id"] in (row.get("chosen") or [])]
            items = [(b.golden_dir / c["file"], c["id"], c) for c in picks]
        else:
            items = [(b.golden_dir / "inputs" / "media" / f, Path(f).stem,
                      {"source": "member", "licence": "member-supplied", "creator": "", "landing": "", "title": f})
                     for f in member_files(r)]
        if not items:
            problems.append(f"{r['slug']}: nothing chosen or supplied")
        for src, ident, meta in items:
            if not src.is_file():
                problems.append(f"{r['slug']}: {src} is missing")
                continue
            name = f"{r['slug']}-{slug(ident)}"
            rec = {"source": meta.get("source"), "licence": meta.get("licence"), "creator": meta.get("creator", ""),
                   "landing": meta.get("landing", ""), "title": meta.get("title", "")}
            if src.suffix.lower() == ".svg":
                shutil.copy2(src, dest_dir / f"{name}.svg")
                records.setdefault(r["slug"], []).append({**rec, "path": str((dest_dir / f"{name}.svg").relative_to(b.app_dir))})
                continue
            staged = work / f"{name}{src.suffix.lower()}"
            shutil.copy2(src, staged)
            mime = {".png": "image/png", ".gif": "image/gif", ".webp": "image/webp", ".avif": "image/avif"}.get(
                src.suffix.lower(), "image/jpeg")
            jobs.append({"src": f"/w/{staged.name}", "dest": f"/w/{name}.webp", "mime": mime, "width": width,
                         "quality": quality, "slug": r["slug"], "name": name, "rec": rec})
    if jobs:
        (work / "jobs.json").write_text(json.dumps(jobs))
        import capture  # noqa: PLC0415
        image = capture.grader_image(work / "grader-build.log")
        proc = subprocess.run(["docker", "run", "--rm", "--entrypoint", "python3", "-v", f"{work}:/w",
                               image, "-c", ENCODE], capture_output=True, text=True, timeout=900)
        if proc.returncode != 0:
            return problems + [f"encoding failed: {(proc.stderr or proc.stdout).strip()[-300:]}"]
        for j in json.loads((work / "jobs.json").read_text()):
            target = dest_dir / f"{j['name']}.webp"
            shutil.copy2(work / f"{j['name']}.webp", target)
            records.setdefault(j["slug"], []).append({**j["rec"], "path": str(target.relative_to(b.app_dir)),
                                                     "size": j.get("size")})
            log(f"  {target.relative_to(b.root)}  {j.get('size', ['?', '?'])[0]}x{j.get('size', ['?', '?'])[1]}  "
                f"{target.stat().st_size // 1024} KB  {j['rec']['licence']}")
    for key, recs in records.items():
        data["rows"].setdefault(key, {})["vendored"] = recs
    save_manifest(b, data)
    shutil.rmtree(work, ignore_errors=True)
    return problems


def credits(b) -> list[str]:
    """The credit lines CC BY files require, ready to place on a credits line or page."""
    out = []
    for row in manifest(b).get("rows", {}).values():
        for v in row.get("vendored") or []:
            if ATTRIBUTION.match(v.get("licence") or "") and v.get("creator"):
                out.append(f"“{v.get('title') or Path(v['path']).name}” by {v['creator']}, "
                           f"{v['licence']} ({v.get('landing', '')})")
    return out
