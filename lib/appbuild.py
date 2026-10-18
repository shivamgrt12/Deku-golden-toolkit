"""Turn solution/app/ into an image the way grading does: from its own manifest.

A golden app declares how it is built and served in `solution/app/run.json`
(run-manifest-v1, the contract solve.sh and the harness already share), or
ships its own `Dockerfile`. Nothing is read from the working tree around it:
the build context is a fresh copy with installed trees excluded, so an app that
only worked because node_modules was already there fails here.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from receipts import IGNORE_DIRS

FOREGROUND_BANNED = ("setsid", "nohup", "disown")


def manifest_problems(manifest: dict | None) -> list[str]:
    if manifest is None:
        return ["solution/app/run.json is missing or not a valid run-manifest-v1 "
                "(string install/build/serve, non-empty serve)"]
    serve = manifest["serve"].strip()
    problems = [f"run.json serve must run in the foreground, found {word!r}"
                for word in FOREGROUND_BANNED if word in serve]
    if serve.endswith("&"):
        problems.append("run.json serve must run in the foreground, found a trailing '&'")
    return problems


def deploy_mode(bundle) -> str:
    if (bundle.app_dir / "Dockerfile").is_file():
        return "dockerfile"
    if bundle.run_manifest() is not None:
        return "run.json"
    return "none"


def _sh(cmd: str) -> str:
    """A JSON-form CMD/RUN argument for `sh -c`, so ${VAR} expands at run time."""
    import json  # noqa: PLC0415
    return json.dumps(["sh", "-c", cmd])


def render_dockerfile(env_image: str, manifest: dict, port: str) -> str:
    lines = [f"FROM {env_image}", "WORKDIR /app", "COPY . /app",
             "RUN mkdir -p /app/.browser_screenshots /app/.downloads"]
    for step in ("install", "build"):
        cmd = str(manifest.get(step) or "").strip()
        if cmd:
            lines.append(f"RUN {_sh('set -e; cd /app; ' + cmd)}")
    lines += [f"ENV APP_PUBLIC_PORT={port} PORT={port} HOST=0.0.0.0",
              f"EXPOSE {port}",
              f"CMD {_sh('cd /app && exec ' + manifest['serve'].strip())}", ""]
    return "\n".join(lines)


def stage(bundle, env_image: str, staging: Path) -> tuple[Path, str]:
    """Copy the app into a clean build context and write its Dockerfile.

    Returns (context_dir, mode). The bundle's own solution/app/ is never written to.
    """
    ctx = staging / "app-build"
    shutil.rmtree(ctx, ignore_errors=True)
    shutil.copytree(bundle.app_dir, ctx,
                    ignore=shutil.ignore_patterns(*IGNORE_DIRS, "*.pyc", ".DS_Store"))
    (ctx / ".dockerignore").write_text("\n".join(f"**/{d}" for d in sorted(IGNORE_DIRS)) + "\n")
    mode = deploy_mode(bundle)
    if mode == "run.json":
        (ctx / "Dockerfile").write_text(render_dockerfile(env_image, bundle.run_manifest(), bundle.port))
    return ctx, mode
