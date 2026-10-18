"""Where the kit, the harness and the harness interpreter live.

Every path is resolved from this file's own location, never from the working
directory, so `golden/bin/*` runs from anywhere -- the same rule genkit's tools
follow (00-RUN.md, "never cd").
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

GOLDEN = Path(__file__).resolve().parent.parent
KIT_ROOT = GOLDEN.parent
GENKIT = KIT_ROOT / "genkit"
HARNESS = Path(os.environ.get("DEKU_HARNESS_DIR") or KIT_ROOT / "deku-harness")
HARNESS_LIB = HARNESS / "harness"
RUNNER = GOLDEN / "runner"


def harness_ready() -> str | None:
    """None when the harness checkout is usable, else the reason it is not."""
    if not (HARNESS_LIB / "eval_fresh.py").is_file():
        return (f"deku-harness is not checked out at {HARNESS} "
                f"-- run ./scripts/setup.sh first")
    return None


def import_harness():
    """Import the harness modules golden reuses rather than re-implements.

    eval_fresh owns env resolution, sidecar filtering and the grader file
    manifest; app_image owns stack detection. Re-implementing either would make
    the gauntlet grade a different deployment than the harness does.
    """
    reason = harness_ready()
    if reason:
        raise SystemExit(f"golden: {reason}")
    if str(HARNESS_LIB) not in sys.path:
        sys.path.insert(0, str(HARNESS_LIB))
    import app_image  # noqa: PLC0415
    import eval_fresh  # noqa: PLC0415
    return eval_fresh, app_image


def harness_sha() -> str:
    """The harness commit, so a receipt records which grader produced it."""
    head = HARNESS / ".git"
    try:
        if head.is_file():  # submodule: .git is a pointer file
            gitdir = Path(head.read_text().split(":", 1)[1].strip())
            if not gitdir.is_absolute():
                gitdir = (HARNESS / gitdir).resolve()
        else:
            gitdir = head
        ref = (gitdir / "HEAD").read_text().strip()
        if ref.startswith("ref:"):
            ref_path = gitdir / ref.split(" ", 1)[1]
            if ref_path.is_file():
                return ref_path.read_text().strip()[:12]
            packed = gitdir / "packed-refs"
            for line in packed.read_text().splitlines():
                if line.endswith(ref.split(" ", 1)[1]):
                    return line.split(" ", 1)[0][:12]
            return "unknown"
        return ref[:12]
    except (OSError, IndexError):
        return "unknown"


def load_harness_env() -> dict[str, str]:
    """deku-harness/.env as a dict, for forwarding grader credentials.

    Values are never printed. A variable already set in the real environment
    wins, matching deku-run's `set -a; source .env` behaviour.
    """
    out: dict[str, str] = {}
    path = HARNESS / ".env"
    if path.is_file():
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            key, value = line.split("=", 1)
            value = value.strip().strip('"').strip("'")
            if value:
                out[key.strip()] = value
    out.update({k: v for k, v in os.environ.items() if v})
    # Bridge mode (the harness default): a Claude Max subscription behind
    # bridge/claude_code, where ANTHROPIC_API_KEY is the bridge secret rather
    # than a real key -- deku-harness/README.md, Setup.
    secret = HARNESS / ".bridge_secret"
    if bridge_mode(out) and not out.get("ANTHROPIC_API_KEY") and secret.is_file():
        out["ANTHROPIC_API_KEY"] = secret.read_text().strip()
    return out


def bridge_mode(env: dict[str, str]) -> bool:
    return str(env.get("DEKU_BRIDGE_ENABLED", "1")).strip().lower() not in ("0", "false", "no", "off")


def bridge_problem() -> str | None:
    """None when the OAuth bridge answers on the host, else how to start it."""
    import urllib.request  # noqa: PLC0415
    port = os.environ.get("DEKU_BRIDGE_PORT", "8765")
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=5) as resp:
            if b'"ok":true' in resp.read().replace(b" ", b""):
                return None
    except OSError:
        pass
    return ("the Claude OAuth bridge is not running or not healthy -- run "
            "golden/bin/golden-bridge start (it restarts an unhealthy one)")
