"""Capture a reference website as a frozen, advisory input for P0/P1.

Reuses prd-generator's own capture (prdgen.py) rather than a second scraper. It
runs inside the harness verifier image, which already carries Playwright and
Chromium, so the member's machine needs no browser install. The capture is
evidence of rhythm, hierarchy and density -- never a source of brand, copy or
images (OVERRIDES.md, prompts/source-reconcile.md).
"""
from __future__ import annotations

import os
from pathlib import Path

from paths import HARNESS_LIB, KIT_ROOT, harness_sha
from stack import run

PRDGEN = Path(os.environ.get("DEKU_PRDGEN_DIR") or KIT_ROOT.parent / "prd-generator")


def grader_image(log_to: Path) -> str:
    tag = f"golden-grader:{harness_sha()}"
    if run(["docker", "image", "inspect", tag]).returncode != 0:
        run(["docker", "build", "-t", tag, "-f", str(HARNESS_LIB / "verifier" / "Dockerfile"),
             str(HARNESS_LIB)], log_to=log_to, check=True, what="harness verifier image build")
    return tag


def capture_site(url: str, dest: Path) -> int:
    if not (PRDGEN / "prdgen.py").is_file():
        print(f"golden: prd-generator not found at {PRDGEN} (set DEKU_PRDGEN_DIR)")
        return 2
    dest.mkdir(parents=True, exist_ok=True)
    image = grader_image(dest / "grader-build.log")
    proc = run(["docker", "run", "--rm", "--entrypoint", "python3",
                "-v", f"{PRDGEN}:/prdgen:ro", "-v", f"{dest}:/out", "-w", "/prdgen",
                image, "/prdgen/prdgen.py", url, "--out", "/out", "--no-handoff",
                "--output-root", "/tmp/prdgen", "--profile", "/tmp/prdgen-profile"],
               timeout=3600, log_to=dest / "capture.log")
    return proc.returncode
