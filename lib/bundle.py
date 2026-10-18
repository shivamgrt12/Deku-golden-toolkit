"""One task bundle, read once: its task.toml, workflows and the golden app.

The bundle is the contract. Nothing here interprets it beyond what the harness
itself reads, so a fact this module reports is a fact the grader will act on.
"""
from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import yaml


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "bundle"


@dataclass
class Bundle:
    root: Path
    toml: dict = field(default_factory=dict)
    workflows: list[dict] = field(default_factory=list)
    workflows_error: str | None = None   # workflows.yaml present but unparseable

    @classmethod
    def load(cls, root: Path) -> "Bundle":
        root = Path(root).resolve()
        if not (root / "task.toml").is_file():
            raise SystemExit(f"golden: {root} is not a task bundle (no task.toml)")
        toml = tomllib.loads((root / "task.toml").read_text())
        workflows: list[dict] = []
        error = None
        wf = root / "tests" / "workflows.yaml"
        if wf.is_file():
            # The harness's score.py does yaml.safe_load on this same file; if it
            # cannot parse, every run crashes at scoring. Recorded, not raised, so
            # triage can say so instead of the gauntlet dying on it.
            try:
                raw = yaml.safe_load(wf.read_text()) or []
                workflows = raw.get("workflows", []) if isinstance(raw, dict) else raw
            except yaml.YAMLError as exc:
                error = " ".join(str(exc).split())[:300]
        return cls(root=root, toml=toml, workflows=workflows or [], workflows_error=error)

    # ------------------------------------------------------------ identity
    @property
    def metadata(self) -> dict:
        return self.toml.get("metadata") or {}

    @property
    def name(self) -> str:
        return (self.toml.get("task") or {}).get("name") or self.root.name

    @property
    def project(self) -> str:
        """The docker compose project name: unique per bundle COPY, lowercase.

        The path hash keeps two copies of one task (a calibration copy and a
        member's working copy) from tearing down each other's containers.
        """
        import hashlib  # noqa: PLC0415
        code = self.metadata.get("task_code") or self.root.name
        tag = hashlib.sha256(str(self.root).encode()).hexdigest()[:6]
        return f"golden-{_slug(str(code))[:32]}-{tag}"

    # ------------------------------------------------------------ layout
    @property
    def app_dir(self) -> Path:
        return self.root / "solution" / "app"

    @property
    def solve_sh(self) -> Path:
        return self.root / "solution" / "solve.sh"

    @property
    def env_dir(self) -> Path:
        return self.root / "environment"

    @property
    def compose_file(self) -> Path:
        return self.env_dir / "docker-compose.yaml"

    @property
    def golden_dir(self) -> Path:
        return self.root / "_handoff" / "golden"

    @property
    def evidence_dir(self) -> Path:
        return self.golden_dir / "evidence"

    # ------------------------------------------------------------ contract
    @property
    def port(self) -> str:
        env = (self.toml.get("environment") or {}).get("env") or {}
        raw = str(env.get("APP_PUBLIC_PORT") or "4173")
        m = re.match(r"^\$\{[A-Za-z_]+:-(\d+)\}$", raw)
        return m.group(1) if m else (raw if raw.isdigit() else "4173")

    @property
    def browser_substeps(self) -> int:
        return sum(1 for w in self.workflows for s in (w.get("substeps") or [])
                   if s.get("kind") == "browser")

    @property
    def pytest_substeps(self) -> int:
        return sum(1 for w in self.workflows for s in (w.get("substeps") or [])
                   if s.get("kind") == "pytest")

    def run_manifest(self) -> dict | None:
        """solution/app/run.json when it is a valid run-manifest-v1, else None."""
        path = self.app_dir / "run.json"
        try:
            raw = json.loads(path.read_text())
        except (OSError, ValueError):
            return None
        if not isinstance(raw, dict):
            return None
        if not all(isinstance(raw.get(k, ""), str) for k in ("install", "build", "serve")):
            return None
        return raw if str(raw.get("serve", "")).strip() else None
