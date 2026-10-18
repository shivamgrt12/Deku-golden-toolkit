"""Bring a bundle up the way grading does: cold, isolated, from the bundle alone.

Three parts on one docker network, under one compose project per bundle:

  sidecars   the bundle's environment/docker-compose.yaml minus `main`, started
             from empty volumes (eval_fresh.sidecars_only_compose / start_sidecars)
  app        solution/app/ built FROM the environment image via its run.json,
             reachable as `main` -- the host every task.toml default already names
  runner     the HARNESS's own verifier image plus this bundle's tests/, with the
             harness grader files overlaid exactly as eval_fresh stages them

The app and the graders never share a container, which is the `separate`
verifier mode every genkit bundle declares. Nothing the agent's machine holds
(a warm cache, a hand-started process, a row inserted by hand) reaches it.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import appbuild
from paths import HARNESS_LIB, RUNNER, harness_sha, import_harness, load_harness_env

CACHE_DIRS = ("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache")   # eval_fresh's


def env_tools(env_tag: str) -> dict[str, str]:
    """The Node version and psql the environment image carries ('' when absent).

    Official grading runs the bundle's tests on the environment image itself, so a
    test that shells out to psql or starts the app with node finds them there.
    """
    probe = run(["docker", "run", "--rm", "--entrypoint", "sh", env_tag, "-c",
                 "node -p process.versions.node 2>/dev/null || true; echo '|'; "
                 "command -v psql >/dev/null && echo psql || true"])
    node, _, rest = (probe.stdout or "").partition("|")
    return {"node": node.strip(), "psql": "psql" if "psql" in rest else ""}


def runner_dockerfile(env_tag: str) -> str:
    """golden/runner/Dockerfile plus the environment image's Node and psql."""
    base = (RUNNER / "Dockerfile").read_text()
    tools = env_tools(env_tag)
    head, tail = [], []
    if tools["node"]:
        head.append(f"FROM node:{tools['node']}-bookworm-slim AS node_runtime")
        tail += ["COPY --from=node_runtime /usr/local/bin/node /usr/local/bin/node",
                 "COPY --from=node_runtime /usr/local/lib/node_modules /usr/local/lib/node_modules",
                 "RUN ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm"
                 " && ln -sf /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx"
                 " && node -v"]
    if tools["psql"]:
        tail.append("RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client"
                    " && rm -rf /var/lib/apt/lists/*")
    if not head and not tail:
        return base
    args, _, body = base.partition("\n")              # ARG BASE must precede every FROM
    return "\n".join([args] + head + [body.rstrip("\n")] + tail) + "\n"


class StackError(RuntimeError):
    """The stack could not be brought up. Says nothing about the app's quality."""


def log(msg: str) -> None:
    print(f"  {msg}", file=sys.stderr, flush=True)


def run(cmd: list[str], *, timeout: float | None = None, log_to: Path | None = None,
        check: bool = False, what: str = "") -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if log_to is not None:
        log_to.parent.mkdir(parents=True, exist_ok=True)
        log_to.write_text(f"$ {' '.join(cmd)}\n\n--- stdout ---\n{proc.stdout}\n"
                          f"--- stderr ---\n{proc.stderr}\n--- exit {proc.returncode} ---\n")
    if check and proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-1500:]
        raise StackError(f"{what or cmd[0]} failed (exit {proc.returncode}):\n{tail}")
    return proc


def docker_problem() -> str | None:
    """None when the docker daemon answers, else why not."""
    if not shutil.which("docker"):
        return "docker is not installed"
    try:
        proc = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"],
                              capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        return "the docker daemon is not responding (start Docker Desktop)"
    if proc.returncode != 0:
        return "the docker daemon is not running (start Docker Desktop)"
    return None


class Stack:
    def __init__(self, bundle, evidence: Path):
        self.bundle = bundle
        self.evidence = evidence
        self.project = bundle.project
        self.net = f"{self.project}_default"
        self.app_name = f"{self.project}-app"
        self.runner_name = f"{self.project}-runner"
        self.staging = Path(tempfile.mkdtemp(prefix=f"{self.project}-"))
        self.eval_fresh, _ = import_harness()
        self.sidecar_compose: Path | None = None
        self.sidecars: list[str] = []
        self.owned_network = False
        self.images: dict[str, str] = {}

    # ------------------------------------------------------------------ images
    def build_images(self, logs: Path) -> dict[str, str]:
        """env, app, grader base and runner. Each failure names its own log."""
        b = self.bundle
        env_tag = f"{self.project}-env:latest"
        run(["docker", "build", "-t", env_tag, str(b.env_dir)], log_to=logs / "env-build.log",
            check=True, what="environment image build (see env-build.log)")

        ctx, mode = appbuild.stage(b, env_tag, self.staging)
        if mode == "none":
            raise StackError("solution/app has neither run.json nor a Dockerfile")
        app_tag = f"{self.project}-app:latest"
        run(["docker", "build", "--no-cache", "-t", app_tag, str(ctx)],
            log_to=logs / "app-build.log", check=True, what="app image build (see app-build.log)")

        base_tag = f"golden-grader:{harness_sha()}"
        if run(["docker", "image", "inspect", base_tag]).returncode != 0:
            log(f"building the harness verifier image {base_tag} (first run only) ...")
            run(["docker", "build", "-t", base_tag, "-f", str(HARNESS_LIB / "verifier" / "Dockerfile"),
                 str(HARNESS_LIB)], log_to=logs / "grader-base-build.log", check=True,
                what="harness verifier image build (see grader-base-build.log)")

        runner_ctx = self._stage_tests()
        runner_tag = f"{self.project}-runner:latest"
        (runner_ctx / "Dockerfile").write_text(runner_dockerfile(env_tag))
        run(["docker", "build", "--build-arg", f"BASE={base_tag}", "-t", runner_tag, str(runner_ctx)],
            log_to=logs / "runner-build.log", check=True, what="runner image build (see runner-build.log)")
        self.images = {"env": env_tag, "app": app_tag, "grader": base_tag,
                       "runner": runner_tag, "deploy_mode": mode}
        return self.images

    def _stage_tests(self) -> Path:
        """The bundle's tests/ with the harness grader files laid over the top.

        Harness wins for every grader file, as in eval_fresh.stage_tests: a
        bundle's stale test.sh or score.py must not grade with old code.
        """
        stage = self.staging / "runner-build"
        shutil.rmtree(stage, ignore_errors=True)
        shutil.copytree(self.bundle.root / "tests", stage / "tests",
                        ignore=shutil.ignore_patterns("Dockerfile", ".dockerignore", "__pycache__"))
        for src in self.eval_fresh.grader_files(self.bundle.root):
            if src.is_file():
                shutil.copy2(src, stage / "tests" / src.name)
        # The golden probes live OUTSIDE /tests: test.sh runs `pytest /tests`, and
        # a golden suite collected there would change the bundle's own pytest pass.
        for sub in ("probes", "vendor"):
            shutil.copytree(RUNNER / sub, stage / "golden" / sub,
                            ignore=shutil.ignore_patterns("__pycache__"))
        return stage

    # ------------------------------------------------------------------ env
    def app_env(self) -> dict[str, str]:
        """[environment.env] with defaults only -- the host's own DATABASE_URL
        must never leak into a golden deploy."""
        spec = (self.bundle.toml.get("environment") or {}).get("env") or {}
        env = self.eval_fresh.resolve_env(spec, {})
        env.setdefault("APP_PUBLIC_PORT", self.bundle.port)
        return env

    def grader_env(self) -> dict[str, str]:
        host = load_harness_env()
        env = self.eval_fresh.grader_env_for(self.bundle.toml, host)
        env.update(self.eval_fresh.forwarded_grader_env(host))
        env["APP_PUBLIC_URL"] = f"http://main:{self.bundle.port}"
        env["APP_PUBLIC_PORT"] = self.bundle.port
        return env

    def missing_grader_credentials(self) -> list[str]:
        verifier_spec = (self.bundle.toml.get("verifier") or {}).get("env") or {}
        return self.eval_fresh.missing_required(verifier_spec, load_harness_env())

    # ------------------------------------------------------------------ lifecycle
    def down(self) -> None:
        run(["docker", "rm", "-f", self.app_name, self.runner_name])
        if self.sidecar_compose is not None:
            self.eval_fresh.stop_sidecars(self.sidecar_compose, self.project, self.bundle.env_dir)
        else:
            compose = self.bundle.compose_file
            if compose.is_file():
                filtered = self.eval_fresh.sidecars_only_compose(compose, self.staging / "sidecars.yaml")
                self.eval_fresh.stop_sidecars(filtered, self.project, self.bundle.env_dir)
        if self.owned_network:
            run(["docker", "network", "rm", self.net])
            self.owned_network = False

    def up(self) -> None:
        """Cold start: tear down whatever a previous run left, then start fresh."""
        if not self.images:
            raise StackError("build_images() must run before up()")
        self.down()
        ef, b = self.eval_fresh, self.bundle
        if b.compose_file.is_file():
            self.sidecar_compose = ef.sidecars_only_compose(b.compose_file, self.staging / "sidecars.yaml")
            self.sidecars = ef.sidecar_services(b.compose_file)
        if self.sidecars:
            try:
                ef.start_sidecars(self.sidecar_compose, self.project, self.sidecars, b.env_dir)
            except SystemExit as exc:  # eval_fresh exits on failure; we report instead
                raise StackError(str(exc)) from None
        if run(["docker", "network", "inspect", self.net]).returncode != 0:
            run(["docker", "network", "create", self.net], check=True, what="network create")
            self.owned_network = True

        def env_flags(env: dict[str, str]) -> list[str]:
            return [arg for k, v in env.items() for arg in ("-e", f"{k}={v}")]

        run(["docker", "run", "-d", "--name", self.app_name, "--network", self.net,
             "--network-alias", "main", "--network-alias", "app",
             *env_flags(self.app_env()), self.images["app"]], check=True, what="start app container")
        run(["docker", "run", "-d", "--name", self.runner_name, "--network", self.net,
             "--add-host", "host.docker.internal:host-gateway",
             *env_flags(self.grader_env()), "--entrypoint", "sleep", self.images["runner"],
             "infinity"], check=True, what="start runner container")
        run(["docker", "exec", self.runner_name, "mkdir", "-p", "/app", "/logs/verifier"])
        # The judge's source-target criteria read /app (source_list / source_read),
        # exactly as they do under the harness, where the collected app sits there.
        # Without it every code-quality criterion comes back unresolved.
        # The harness copies the agent's whole /app, build output and installed
        # dependencies included: a test that launches the app a second time runs it
        # from there. Take /app from the app IMAGE (a created, never-started
        # container), so nothing the app writes at boot is carried over.
        src = self.staging / "app-src"
        shutil.rmtree(src, ignore_errors=True)
        src.mkdir(parents=True)
        frozen = f"{self.app_name}-files"
        run(["docker", "rm", "-f", frozen])
        run(["docker", "create", "--name", frozen, self.images["app"]], check=True,
            what="create a stopped copy of the app image")
        try:
            copied = run(["docker", "cp", f"{frozen}:/app/.", str(src)]).returncode == 0
        finally:
            run(["docker", "rm", "-f", frozen])
        if not copied:                    # an app Dockerfile that does not live in /app
            shutil.rmtree(src, ignore_errors=True)
            shutil.copytree(b.app_dir, src, ignore=shutil.ignore_patterns(*CACHE_DIRS, ".DS_Store"))
        run(["docker", "cp", f"{src}/.", f"{self.runner_name}:/app"], check=True,
            what="copy the built app into the runner")
        run(["docker", "exec", self.runner_name, "mkdir", "-p",
             "/app/.browser_screenshots", "/app/.downloads"])
        readme = next((p for p in (b.app_dir / "USER_README.md",
                                   b.root / "solution" / "USER_README.md") if p.is_file()), None)
        if readme is not None:
            run(["docker", "cp", str(readme), f"{self.runner_name}:/app/USER_README.md"])

    def app_running(self) -> bool:
        proc = run(["docker", "inspect", "-f", "{{.State.Running}}", self.app_name])
        return proc.stdout.strip() == "true"

    def wait_healthy(self, path: str, timeout: float) -> tuple[bool, str, float]:
        """(healthy, last status seen, seconds taken), probed from the runner."""
        url = f"http://main:{self.bundle.port}{path}"
        started, code = time.monotonic(), ""
        while time.monotonic() - started < timeout:
            if not self.app_running():
                return False, f"app container exited (last status {code or 'none'})", \
                    time.monotonic() - started
            proc = run(["docker", "exec", self.runner_name, "curl", "-s", "-o", "/dev/null",
                        "-w", "%{http_code}", "--max-time", "5", url])
            code = proc.stdout.strip()
            if code == "200":
                return True, code, time.monotonic() - started
            time.sleep(2)
        return False, code or "no response", time.monotonic() - started

    def app_logs(self) -> str:
        proc = run(["docker", "logs", self.app_name])
        return (proc.stdout or "") + (proc.stderr or "")

    def exec_runner(self, args: list[str], *, env: dict[str, str] | None = None,
                    timeout: float | None = None, log_to: Path | None = None,
                    workdir: str | None = None):
        flags = [arg for k, v in (env or {}).items() for arg in ("-e", f"{k}={v}")]
        if workdir:
            flags += ["-w", workdir]
        return run(["docker", "exec", *flags, self.runner_name, *args],
                   timeout=timeout, log_to=log_to)

    def push_golden_tests(self) -> None:
        """Copy the bundle's current solution/golden_tests/ beside the golden conftest.

        Copied at run time rather than baked into the image: these are the
        agent's own suites and change between every fix.
        """
        self.exec_runner(["sh", "-c", "find /golden/suite -mindepth 1 -maxdepth 1 "
                                      "! -name conftest.py -exec rm -rf {} +"])
        src = self.bundle.root / "solution" / "golden_tests"
        if src.is_dir():
            run(["docker", "cp", f"{src}/.", f"{self.runner_name}:/golden/suite/"], check=True,
                what="copy solution/golden_tests into the runner")

    def run_probe(self, name: str, cfg: dict, log_to: Path):
        """Run /golden/probes/<name>.py in the runner with a JSON config."""
        tmp = self.staging / f"{name}-config.json"
        tmp.write_text(json.dumps(cfg))
        self.run_cp_in(tmp, f"/tmp/{name}-config.json")
        self.exec_runner(["mkdir", "-p", cfg.get("out_dir", "/logs/golden")])
        return self.exec_runner(["python3", f"/golden/probes/{name}.py", f"/tmp/{name}-config.json"],
                                timeout=3600, log_to=log_to)

    def run_adapter(self, lang: str, log_to: Path):
        """A language adapter in a throwaway container from the APP image."""
        return run(["docker", "run", "--rm", "--entrypoint", "sh",
                    "-v", f"{RUNNER / 'adapters'}:/golden-adapters:ro",
                    self.images["app"], f"/golden-adapters/{lang}.sh"],
                   timeout=1800, log_to=log_to)

    def run_cp_in(self, src: Path, container_path: str) -> None:
        run(["docker", "cp", str(src), f"{self.runner_name}:{container_path}"], check=True,
            what=f"copy {src.name} into the runner")

    def exec_runner_watched(self, args: list[str], *, env: dict[str, str], timeout: float,
                            log_to: Path, every: float, tick) -> int:
        """exec_runner for long passes: calls tick() every `every` seconds while it runs."""
        flags = [arg for k, v in env.items() for arg in ("-e", f"{k}={v}")]
        log_to.parent.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        with log_to.open("w", encoding="utf-8") as fh:
            proc = subprocess.Popen(["docker", "exec", *flags, self.runner_name, *args],
                                    stdout=fh, stderr=subprocess.STDOUT, text=True)
            while True:
                try:
                    return proc.wait(timeout=every)
                except subprocess.TimeoutExpired:
                    if time.monotonic() - started > timeout:
                        proc.kill()
                        fh.write(f"\n--- golden: killed after {timeout:.0f}s ---\n")
                        return 124
                    tick(time.monotonic() - started)

    def copy_out(self, container_path: str, dest: Path) -> bool:
        dest.parent.mkdir(parents=True, exist_ok=True)
        return run(["docker", "cp", f"{self.runner_name}:{container_path}", str(dest)]).returncode == 0

    def describe(self) -> dict:
        return {"project": self.project, "network": self.net, "sidecars": self.sidecars,
                "images": self.images}

    def cleanup(self) -> None:
        self.down()
        shutil.rmtree(self.staging, ignore_errors=True)


def read_json(path: Path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None
