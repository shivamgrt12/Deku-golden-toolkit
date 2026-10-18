#!/usr/bin/env python3
"""Visit every page at three viewports and measure what devtools would show.

    python3 /golden/probes/pages.py <config.json>

config: {"base_url", "routes": [...], "max_pages", "viewports": {name: [w, h]},
         "out_dir"}

Writes <out_dir>/pages.json and full-page screenshots under <out_dir>/screens/.
It MEASURES and never judges: thresholds live host-side in acceptance.yaml, so
one probe run serves both G5 (inspect) and G6 (aesthetic).
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright

WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]
AXE = Path(__file__).resolve().parent.parent / "vendor" / "axe.min.js"
SKIP_LINK = re.compile(r"(logout|log-out|signout|sign-out|/api/)|\.(pdf|zip|csv|png|jpe?g|webp|svg|mp4)$", re.I)

# Chrome logs a console error for every 4xx/5xx response; the response is judged
# host-side by its status and resource type, so that console line is not counted twice.
NETWORK_LINE = re.compile(r"^Failed to load resource: the server responded with a status of \d{3}")

CLS_INIT = """
window.__golden_cls = 0;
try {
  new PerformanceObserver(list => {
    for (const e of list.getEntries()) if (!e.hadRecentInput) window.__golden_cls += e.value;
  }).observe({type: 'layout-shift', buffered: true});
} catch (e) {}
"""

OVERFLOW_JS = """() => Math.max(
  document.documentElement.scrollWidth - document.documentElement.clientWidth,
  document.body ? document.body.scrollWidth - document.documentElement.clientWidth : 0)"""

LINKS_JS = "() => Array.from(document.querySelectorAll('a[href]')).map(a => a.getAttribute('href'))"

# Every mechanically-checkable visual claim, in one pass. Anything it cannot
# settle (text over an image, a gradient) is COUNTED as unsettled rather than
# guessed, so the host can send those to a human or the visual critic.
STYLE_JS = r"""() => {
  const parse = c => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null;
    const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number);
    return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1}; };
  const lum = c => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const blend = (fg, bg) => ({r: fg.r * fg.a + bg.r * (1 - fg.a), g: fg.g * fg.a + bg.g * (1 - fg.a),
    b: fg.b * fg.a + bg.b * (1 - fg.a), a: 1});
  const background = el => {
    for (let n = el; n; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if (cs.backgroundImage && cs.backgroundImage !== 'none') return null;
      const c = parse(cs.backgroundColor);
      if (c && c.a > 0) return c.a >= 1 ? c : blend(c, {r: 255, g: 255, b: 255, a: 1});
    }
    return {r: 255, g: 255, b: 255, a: 1};
  };
  // Visible to a reader: laid out, and not hidden by ANY ancestor -- a closed
  // dialog, an aria-hidden or inert subtree, an opacity-0 wrapper. Measuring the
  // contrast of text nobody can see reports defects that do not exist.
  const visible = el => {
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    if (el.closest('[aria-hidden="true"],[inert],[hidden],dialog:not([open])')) return false;
    for (let n = el; n && n !== document.documentElement; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if (cs.visibility === 'hidden' || cs.display === 'none' || parseFloat(cs.opacity) === 0) return false;
    }
    return true;
  };
  const texts = [];
  const walker = document.createTreeWalker(document.body || document.documentElement, NodeFilter.SHOW_TEXT);
  const seen = new Set();
  while (walker.nextNode() && texts.length < 400) {
    const t = walker.currentNode; const el = t.parentElement;
    if (!el || seen.has(el) || !t.textContent.trim()) continue;
    if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE'].includes(el.tagName)) continue;
    seen.add(el); if (visible(el)) texts.push(el);
  }
  const weights = new Set(), families = new Set();
  let small = [], lowContrast = [], unsettled = 0, minSize = 999; const smallSizes = {};
  for (const el of texts) {
    const cs = getComputedStyle(el);
    const size = parseFloat(cs.fontSize), weight = parseInt(cs.fontWeight, 10);
    weights.add(weight); families.add(cs.fontFamily.split(',')[0].trim().replace(/["']/g, ''));
    minSize = Math.min(minSize, size);
    const label = (el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') +
      (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/)[0] : ''));
    if (size < 12) { small.push({el: label, size, text: el.textContent.trim().slice(0, 40)});
                     smallSizes[size] = (smallSizes[size] || 0) + 1; }
    const fg = parse(cs.color), bg = background(el);
    if (!fg || !bg || cs.mixBlendMode !== 'normal') { unsettled++; continue; }
    const f = fg.a < 1 ? blend(fg, bg) : fg;
    const L1 = lum(f), L2 = lum(bg);
    const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    // Text that is legible on screen cannot really sit at ~1:1 on its background;
    // a ratio that low means the real backdrop is not an ancestor (an image, a
    // positioned sibling, a canvas) -- unmeasurable, not a defect.
    if (ratio < 1.1) { unsettled++; continue; }
    const large = size >= 24 || (size >= 18.66 && weight >= 700);
    if (ratio < (large ? 3 : 4.5)) lowContrast.push({el: label, ratio: Math.round(ratio * 100) / 100,
      text: el.textContent.trim().slice(0, 40)});
  }
  const transitionAll = [];
  for (const sheet of Array.from(document.styleSheets)) {
    let rules; try { rules = sheet.cssRules; } catch (e) { continue; }
    const walk = list => { for (const r of Array.from(list || [])) {
      if (r.cssRules) walk(r.cssRules);
      if (!r.style) continue;
      const prop = (r.style.transitionProperty || '') + ' ' + (r.style.transition || '');
      if (/(^|[\s,])all([\s,]|$)/.test(prop.trim())) transitionAll.push(r.selectorText || '(rule)');
    } };
    walk(rules);
  }
  const measures = [];
  for (const p of Array.from(document.querySelectorAll('p, li'))) {
    const text = p.textContent.trim(); if (text.length < 160 || !visible(p)) continue;
    const cs = getComputedStyle(p); const lh = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.4;
    const lines = Math.max(1, Math.round(p.getBoundingClientRect().height / lh));
    if (lines >= 2) measures.push(Math.round(text.length / lines));
  }
  measures.sort((a, b) => a - b);
  return {sampled: texts.length, font_weights: Array.from(weights).sort(), font_families: Array.from(families),
          min_font_px: minSize === 999 ? null : minSize, small_text: small.slice(0, 20), small_text_count: small.length, small_sizes: smallSizes,
          low_contrast: lowContrast.slice(0, 20), low_contrast_count: lowContrast.length,
          contrast_unsettled: unsettled, transition_all: transitionAll.slice(0, 20),
          transition_all_count: transitionAll.length,
          measure_median: measures.length ? measures[Math.floor(measures.length / 2)] : null};
}"""


def slug(path: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", path).strip("_") or "root"


def same_origin_path(base: str, href: str | None) -> str | None:
    if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
        return None
    url = urlparse(urljoin(base + "/", href))
    if url.netloc and url.netloc != urlparse(base).netloc:
        return None
    path = url.path or "/"
    return None if SKIP_LINK.search(path) else path


def audit(page, base: str, path: str, shots: Path, label: str) -> dict:
    console, errors, failed, bad, external = [], [], [], [], []
    origin = urlparse(base).netloc
    page.on("request", lambda r: external.append(r.url)
            if urlparse(r.url).netloc not in ("", origin) and r.url.startswith("http") else None)
    page.on("console", lambda m: console.append({"type": m.type, "text": m.text[:300]})
            if m.type in ("error", "warning") and not NETWORK_LINE.match(m.text) else None)
    page.on("pageerror", lambda e: errors.append(str(e)[:300]))
    page.on("requestfailed", lambda r: failed.append({"url": r.url, "error": (r.failure or "")[:120]}))
    page.on("response", lambda r: bad.append({"url": r.url, "status": r.status,
                                              "type": r.request.resource_type}) if r.status >= 400 else None)
    record = {"path": path, "viewport": label}
    try:
        resp = page.goto(base + path, wait_until="networkidle", timeout=45000)
        record["status"] = resp.status if resp else None
        page.wait_for_timeout(800)
        record["overflow_px"] = page.evaluate(OVERFLOW_JS)
        record["cls"] = round(page.evaluate("() => window.__golden_cls || 0"), 4)
        record["style"] = page.evaluate(STYLE_JS)
        page.add_script_tag(content=AXE.read_text())
        record["axe"] = page.evaluate(
            """tags => axe.run(document, {runOnly: {type: 'tag', values: tags}}).then(r =>
                 r.violations.map(v => ({id: v.id, impact: v.impact, help: v.help,
                   nodes: v.nodes.slice(0, 3).map(n => n.target.join(' '))})))""", WCAG_TAGS)
        shots.mkdir(parents=True, exist_ok=True)
        shot = shots / f"{slug(path)}@{label}.png"
        page.screenshot(path=str(shot), full_page=True)
        record["screenshot"] = str(shot)
        record["media"] = page.evaluate(MEDIA_JS)
    except Exception as exc:  # recorded, never raised: one page must not end the sweep
        record["probe_error"] = f"{exc.__class__.__name__}: {str(exc)[:300]}"
    record.update(console=console, page_errors=errors, failed_requests=failed, bad_responses=bad,
                  external_requests=sorted(set(external))[:20])
    return record


# Every picture and video on the page, after a slow scroll has woken lazy loading.
# Measured in the page, so it sees what a visitor sees: an <img> that answered 200
# but decodes to nothing, one that decodes to a flat field of one colour, a raster
# far larger than the box it is shown in, a video that never yields a duration.
MEDIA_JS = r"""async () => {
  const step = Math.max(200, innerHeight * 0.8);
  for (let y = 0; y < document.documentElement.scrollHeight; y += step) {
    scrollTo(0, y); await new Promise(r => setTimeout(r, 120));
  }
  scrollTo(0, 0);
  const pending = [...document.images].filter(i => !i.complete);
  await Promise.race([Promise.all(pending.map(i => new Promise(r => { i.onload = i.onerror = r; }))),
                      new Promise(r => setTimeout(r, 4000))]);
  const shown = el => { const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const bytes = src => { const e = performance.getEntriesByName(src)[0]; return e ? (e.encodedBodySize || e.transferSize || 0) : 0; };
  const flat = img => {
    try {
      const c = document.createElement('canvas'); c.width = c.height = 24;
      const g = c.getContext('2d'); g.drawImage(img, 0, 0, 24, 24);
      const d = g.getImageData(0, 0, 24, 24).data; let lo = [255,255,255,255], hi = [0,0,0,0];
      for (let i = 0; i < d.length; i += 4) for (let k = 0; k < 4; k++) { lo[k] = Math.min(lo[k], d[i+k]); hi[k] = Math.max(hi[k], d[i+k]); }
      return hi[3] === 0 ? 'transparent' : (Math.max(...hi.map((h, k) => h - lo[k])) < 6 ? 'flat' : null);
    } catch (e) { return null; }      // a cross-origin picture cannot be read; G5 flags the hotlink itself
  };
  const out = [];
  for (const img of document.images) {
    if (!shown(img)) continue;
    const r = img.getBoundingClientRect(), src = img.currentSrc || img.src;
    const svg = /\.svg(\?|#|$)/i.test(src) || src.startsWith('data:image/svg');
    out.push({kind: 'img', src: src.slice(0, 300), alt: img.getAttribute('alt'),
              broken: img.complete && img.naturalWidth === 0,
              blank: img.naturalWidth ? flat(img) : null, svg,
              natural: [img.naturalWidth, img.naturalHeight], shown: [Math.round(r.width), Math.round(r.height)],
              bytes: bytes(src)});
  }
  for (const v of document.querySelectorAll('video')) {
    if (!shown(v)) continue;
    if (v.preload !== 'none' && v.readyState === 0) await new Promise(r => { v.onloadedmetadata = v.onerror = r; setTimeout(r, 4000); });
    out.push({kind: 'video', src: (v.currentSrc || v.src || '').slice(0, 300), preload: v.preload,
              error: v.error ? v.error.code : null, ready: v.readyState,
              duration: isFinite(v.duration) ? v.duration : null, poster: v.poster || null});
  }
  return out;
}"""

PASSWORD_JS = "() => !!document.querySelector('input[type=password]')"
SIGN_IN_PATH = re.compile(r"/(log-?in|sign-?in|sign-?up|register|auth)(/|$)", re.I)


def crawl(browser, base: str, start: list[str], limit: int, state=None) -> tuple[list[str], bool]:
    """Same-origin pages reachable from `start`, and whether any shows a password field."""
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, storage_state=state)
    page = ctx.new_page()
    queue, found, saw_password = deque(start), [], False
    while queue and len(found) < limit:
        path = queue.popleft()
        if path in found:
            continue
        found.append(path)
        try:
            page.goto(base + path, wait_until="domcontentloaded", timeout=30000)
            saw_password = saw_password or page.evaluate(PASSWORD_JS)
            for href in page.evaluate(LINKS_JS):
                nxt = same_origin_path(base, href)
                if nxt and nxt not in found and nxt not in queue:
                    queue.append(nxt)
        except Exception:
            continue
    ctx.close()
    return found, saw_password


def load_sessions(base: str, browser) -> tuple[dict, dict, list[str]]:
    """solution/golden_tests/audit.py: SESSIONS {name: login(page, base_url)}, ROUTES {name: [paths]}.

    Each login runs once in a real browser, exactly as a user signs in; the signed-in
    storage state is then reused for every page and viewport of that session.
    """
    states, routes, errors = {}, {}, []
    if not Path("/golden/suite/audit.py").is_file():
        return states, routes, errors
    sys.path.insert(0, "/golden/suite")
    try:
        import audit as declared  # noqa: PLC0415
    except Exception as exc:
        return states, routes, [f"audit.py does not import: {exc.__class__.__name__}: {exc}"]
    for name, login in (getattr(declared, "SESSIONS", {}) or {}).items():
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        try:
            login(ctx.new_page(), base)
            states[name] = ctx.storage_state()
            routes[name] = list((getattr(declared, "ROUTES", {}) or {}).get(name) or ["/"])
        except Exception as exc:
            errors.append(f"session {name!r}: sign-in failed: {exc.__class__.__name__}: {str(exc)[:200]}")
        finally:
            ctx.close()
    return states, routes, errors


def main() -> int:
    cfg = json.loads(Path(sys.argv[1]).read_text())
    base, out = cfg["base_url"].rstrip("/"), Path(cfg["out_dir"])
    out.mkdir(parents=True, exist_ok=True)
    started, limit = time.monotonic(), int(cfg.get("max_pages", 25))
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        anon, saw_password = crawl(browser, base, cfg.get("routes") or ["/"], limit)
        states, session_routes, session_errors = load_sessions(base, browser)
        plan = [("", None, anon)]
        for name, state in states.items():
            found, _ = crawl(browser, base, session_routes[name], limit, state)
            plan.append((name, state, found))
        pages = []
        for session, state, found in plan:
            for path in found:
                for label, (w, h) in cfg["viewports"].items():
                    ctx = browser.new_context(viewport={"width": w, "height": h}, storage_state=state)
                    ctx.add_init_script(CLS_INIT)
                    shot_label = f"{session}-{label}" if session else label
                    record = audit(ctx.new_page(), base, path, out / "screens", shot_label)
                    record["viewport"], record["session"] = label, session or None
                    pages.append(record)
                    ctx.close()
        browser.close()
    auth_detected = saw_password or any(SIGN_IN_PATH.search(p) for p in anon)
    (out / "pages.json").write_text(json.dumps({
        "routes": anon, "pages": pages, "auth_detected": auth_detected,
        "sessions": {name: found for name, _, found in plan if name},
        "session_errors": session_errors,
        "seconds": round(time.monotonic() - started, 1)}, indent=2))
    print(f"pages.py: {len(anon)} public route(s), {sum(len(f) for n, _, f in plan if n)} signed-in "
          f"route(s) across {len(states)} session(s) x {len(cfg['viewports'])} viewport(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
