"""Fixtures for solution/golden_tests/ -- the agent-written golden suites.

Installed as /golden/suite/conftest.py in the runner; the bundle's
solution/golden_tests/ tree is copied beside it before each run.

A walkthrough test drives ONE browser substep of tests/workflows.yaml and says
which one:

    @pytest.mark.substep("guest_rsvp_yes_sends_email", 2)   # 2nd browser substep
    def test_guest_confirms_attendance(page, base_url):
        page.goto(base_url + "/events/spring-gala")
        page.get_by_role("button", name="Attend").click()
        expect(page.get_by_text("You're on the list")).to_be_visible()

Every page a test opens is watched: a console error, an uncaught exception or a
same-origin request that fails FAILS the test, so authenticated surfaces the
anonymous crawl (G5) cannot reach are still held to "devtools shows nothing".
A frame is saved after every substep test, pass or fail.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

FRAMES = Path(os.environ.get("GOLDEN_FRAMES_DIR", "/logs/golden/frames"))


def pytest_configure(config):
    config.addinivalue_line("markers", "substep(workflow_id, index): the browser substep this test drives")


# Chrome writes "Failed to load resource: the server responded with a status of N"
# to the console for EVERY 4xx/5xx response -- including the ones a brief requires
# (a 404 not-found page, a 400 refusal of bad input). That line is a symptom; the
# response itself is judged by network_defect() instead.
NETWORK_LINE = re.compile(r"^Failed to load resource: the server responded with a status of \d{3}")
ASSET_TYPES = {"script", "stylesheet", "image", "font", "media", "manifest", "texttrack"}


def network_defect(status: int, resource_type: str) -> bool:
    """A 5xx is always a defect; a 4xx only on an asset (a missing file).

    A 4xx on a document the test opened, or on an API call (fetch / xhr), is the
    app's own HTTP semantics -- the brief's refusals and its not-found page.
    """
    return status >= 500 or (400 <= status < 500 and resource_type in ASSET_TYPES)


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.environ.get("APP_PUBLIC_URL", "http://main:4173").rstrip("/")


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser, base_url, request):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    origin = re.match(r"https?://[^/]+", base_url).group(0)
    problems: list[str] = []
    pg.on("console", lambda m: problems.append(f"console {m.type}: {m.text[:200]}")
          if m.type == "error" and not NETWORK_LINE.match(m.text) else None)
    pg.on("pageerror", lambda e: problems.append(f"uncaught: {str(e)[:200]}"))
    pg.on("requestfailed", lambda r: problems.append(f"request failed: {r.url}")
          if r.url.startswith(origin) and "ERR_ABORTED" not in (r.failure or "") else None)
    pg.on("response", lambda r: problems.append(f"HTTP {r.status} on a {r.request.resource_type}: {r.url}")
          if r.url.startswith(origin) and network_defect(r.status, r.request.resource_type) else None)
    yield pg
    marker = request.node.get_closest_marker("substep")
    if marker is not None:
        FRAMES.mkdir(parents=True, exist_ok=True)
        wf, idx = marker.args[0], marker.args[1]
        try:
            pg.screenshot(path=str(FRAMES / f"{wf}__{idx:02d}.png"), full_page=True)
        except Exception:
            pass
    ctx.close()
    if problems and os.environ.get("GOLDEN_STRICT_CONSOLE", "1") == "1":
        pytest.fail("devtools was not clean during this test:\n  " + "\n  ".join(problems[:10]))
