"""Static checks that need no Docker: bundle triage, leak, scope, coverage.

Each finding is a dict {id, check, text}. The id is a stable hash of the text,
so a member can waive one specific finding with a written reason
(`golden-status <bundle> --waive <id> --note "..."`) without silencing the check.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import tomllib
from pathlib import Path

ENDPOINT = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE)\s+`?(/api/[^\s`\"')\],;]+)")
PARAM = re.compile(r"\{[^}/]+\}|:[A-Za-z_][A-Za-z0-9_]*|<[^>/]+>")
SUBSTEP_MARK = re.compile(r"mark\.substep\(\s*[\"']([\w-]+)[\"']\s*,\s*(\d+)\s*\)")


# Advisory checks are reported but never block: their signal is real, but a
# correct app can still reach golden with them present.
ADVISORY = {"criterion-points-at-brief"}


def finding(check: str, text: str) -> dict:
    return {"id": hashlib.sha1(f"{check}:{text}".encode()).hexdigest()[:8], "check": check,
            "text": text, "blocking": check not in ADVISORY}


def brief(b) -> str:
    path = b.root / "instruction.md"
    return path.read_text() if path.is_file() else ""


def endpoints(b) -> list[dict]:
    seen, out = set(), []
    for method, path in ENDPOINT.findall(brief(b)):
        path = path.rstrip(".")
        if (method, path) not in seen:
            seen.add((method, path))
            out.append({"method": method, "path": path})
    return out


# ---------------------------------------------------------------- triage (P-1)
SLOT_FACTORIES = {"make_backend": "backend", "make_inbox": "email",
                  "make_payments": "payments", "make_store": "storage"}

# Browser substeps the grader cannot perform (genkit reference/N, gate G7): one
# context, one tab, one session at a time, inside the workflow budget.
UNPASSABLE = [
    (re.compile(r"\b(new|second|another|other)\s+(tab|window|browser)\b", re.I), "a second tab or window"),
    (re.compile(r"\bincognito|private window\b", re.I), "a private window"),
    (re.compile(r"\bdownload(s|ed)?\b.*\b(open|read|inspect|verify)\b|\bopen the downloaded\b", re.I),
     "inspecting a downloaded file"),
    (re.compile(r"\b(wait|after)\s+\d+\s*(minutes?|hours?|days?)\b", re.I), "a wait beyond the workflow budget"),
    (re.compile(r"\b(simultaneous(ly)?|at the same time|two users at once)\b", re.I), "simultaneous actors"),
    (re.compile(r"\b(check|open|read) (the|your|their) (email|inbox|mailbox)\b", re.I),
     "reading an inbox (the browser grader has no mail client)"),
]
BRIEF_POINTERS = re.compile(r"\b(the brief|as stated|as specified|the stated|per the spec|instruction\.md)\b", re.I)


def _test_sources(b) -> str:
    tests = b.root / "tests"
    return "\n".join(p.read_text() for p in sorted(tests.glob("*.py"))
                     if p.name == "conftest.py" or p.name.startswith("test_")) if tests.is_dir() else ""


def _string_constants(source: str) -> list[str]:
    """Every string constant; an f-string becomes its template with {} holes."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            out.append("".join(v.value if isinstance(v, ast.Constant) else "{}" for v in node.values))
    return out


def _route_known(path: str, brief_text: str, templates: list[re.Pattern]) -> bool:
    path = path.split("?", 1)[0].rstrip("/") or "/"
    if path in brief_text:
        return True
    return any(t.fullmatch(path) for t in templates)


def triage(b) -> list[dict]:
    out: list[dict] = []
    text, sources = brief(b), _test_sources(b)

    if b.workflows_error:
        out.append(finding("workflows-unparseable",
            f"tests/workflows.yaml does not parse, so the harness's score.py crashes on every "
            f"run (scorer_crashed, reward 0): {b.workflows_error}"))

    declared = b.metadata.get("services") or {}
    for factory, slot in SLOT_FACTORIES.items():
        if re.search(rf"\b{factory}\s*\(", sources) and not declared.get(slot):
            out.append(finding("undeclared-slot",
                f"tests call {factory}() but task.toml declares no [metadata.services].{slot}: the "
                f"harness refuses the adapter (DEKU_SERVICE_{slot.upper()} unset) and every test "
                f"using it fails on a correct app"))

    for wf in b.workflows:
        browser_steps = [s for s in wf.get("substeps") or [] if s.get("kind") == "browser"]
        for i, step in enumerate(browser_steps, 1):
            for pattern, why in UNPASSABLE:
                if pattern.search(step.get("do") or ""):
                    out.append(finding("unpassable-substep",
                        f"{wf.get('id')} browser substep {i} needs {why}, which the browser "
                        f"grader cannot do: {step.get('do', '')[:120]}"))

    names = set(re.findall(r"^def (test_\w+)", sources, re.M))
    for wf in b.workflows:
        for step in wf.get("substeps") or []:
            ref = str(step.get("test") or "")
            if step.get("kind") == "pytest" and ref and ref.split("::")[-1] not in names:
                out.append(finding("dangling-test", f"{wf.get('id')} cites {ref}, which no test file defines"))

    templates = [re.compile(PARAM.sub("[^/]+", p["path"]).replace(".", r"\.")) for p in endpoints(b)]
    for literal in sorted(set(_string_constants(sources))):
        if literal.startswith("/api/") and " " not in literal:
            probe = literal.replace("{}", "x")
            if not _route_known(probe, text, templates):
                out.append(finding("route-not-in-brief",
                    f"a test requests {literal}, which instruction.md never names -- the agent "
                    f"cannot know to build it (INV2)"))

    judge = b.root / "tests" / "judge.toml"
    if judge.is_file():
        try:
            criteria = tomllib.loads(judge.read_text()).get("criterion") or []
        except tomllib.TOMLDecodeError:
            criteria = []
        for c in criteria:
            words = f"{c.get('description', '')} {(c.get('annotations') or {}).get('rule', '')}"
            if BRIEF_POINTERS.search(words):
                out.append(finding("criterion-points-at-brief",
                    f"{c.get('id')} points at the brief instead of carrying the fact; the judge "
                    f"never reads the brief, so it cannot decide it"))
    return out


# ---------------------------------------------------------------- G4 coverage
def walkthrough_dir(b) -> Path:
    return b.root / "solution" / "golden_tests" / "walkthrough"


def walkthrough_coverage(b) -> tuple[list[str], list[str]]:
    """(uncovered browser substeps, markers pointing at no browser substep)."""
    declared = {(wf.get("id"), i) for wf in b.workflows
                for i, _ in enumerate([s for s in wf.get("substeps") or [] if s.get("kind") == "browser"], 1)}
    marked = set()
    folder = walkthrough_dir(b)
    if folder.is_dir():
        for path in folder.rglob("*.py"):
            for wf, idx in SUBSTEP_MARK.findall(path.read_text()):
                marked.add((wf, int(idx)))
    uncovered = [f"{wf} #{i}" for wf, i in sorted(declared - marked)]
    stray = [f"{wf} #{i}" for wf, i in sorted(marked - declared)]
    return uncovered, stray


# ---------------------------------------------------------------- G8 lints
APP_TEXT = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".html", ".jinja", ".j2", ".css",
            ".vue", ".svelte", ".sql", ".json", ".yaml", ".yml", ".toml"}
COMMON_LITERALS = re.compile(
    r"^(application/|text/|multipart/|utf-?8|content-type|authorization|bearer|http|https?://|"
    r"localhost|[A-Z_]+_URL|[A-Z_]+_PORT|APP_PUBLIC|DATABASE|DB_|DEKU_|true|false|null|none)", re.I)


def _app_files(b):
    from receipts import IGNORE_DIRS  # noqa: PLC0415
    for path in b.app_dir.rglob("*"):
        rel = path.relative_to(b.app_dir)
        if path.is_file() and path.suffix in APP_TEXT and not any(p in IGNORE_DIRS for p in rel.parts) \
                and "vendor" not in rel.parts and not path.name.endswith(".min.js"):
            yield path


IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _expected_values(source: str) -> list[str]:
    """String constants a test COMPARES against -- the values it expects.

    Assertion messages, field names passed to a lookup and env var names are
    shared vocabulary, not answers, so only operands of a comparison count.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        for operand in [node.left, *node.comparators]:
            for sub in ast.walk(operand):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    out.append(sub.value)
    return out


def spelled_out(lit: str, text: str) -> bool:
    """A hyphenated keyword the brief states in words: `tabular-nums` for "tabular
    numerals", `line-through` for "a line through". Each part must begin a
    consecutive word of the brief (a trailing plural `s` aside), so a value only the
    tests know still never matches by accident.
    """
    parts = lit.lower().split("-")
    if len(parts) < 2 or not all(re.fullmatch(r"[a-z]{3,}", p) for p in parts):
        return False
    words = r"\W+(?:a\W+|an\W+|the\W+)?".join(rf"{re.escape(p.rstrip('s'))}\w*" for p in parts)
    return re.search(rf"\b{words}", text, re.I) is not None


def leak_lint(b, allow: list[str] | None = None) -> list[dict]:
    """App source carrying a value only the TESTS expect -- teaching to the test.

    A correct app needs only what the brief states. A value a test compares
    against, found in the app but nowhere in instruction.md, is the signature of
    an app built to the answer key rather than to the spec.
    """
    text = brief(b)
    allow_re = [re.compile(a) for a in (allow or [])]
    candidates = set()
    for literal in _expected_values(_test_sources(b)):
        lit = literal.strip()
        if len(lit) < 6 or "\n" in lit or IDENTIFIER.match(lit) or COMMON_LITERALS.search(lit):
            continue
        if lit in text or spelled_out(lit, text) or any(a.search(lit) for a in allow_re):
            continue
        candidates.add(lit)
    if not candidates:
        return []
    hits: dict[str, list[str]] = {}
    for path in _app_files(b):
        try:
            body = path.read_text(errors="ignore")
        except OSError:
            continue
        for lit in candidates:
            if lit in body:
                hits.setdefault(lit, []).append(str(path.relative_to(b.app_dir)))
    return [finding("test-only-literal",
                    f"app source carries {lit!r}, which appears in tests/ but nowhere in "
                    f"instruction.md ({', '.join(files[:3])})")
            for lit, files in sorted(hits.items())]


UNASKED = {
    "analytics": ["posthog", "mixpanel", "segment", "amplitude", "@vercel/analytics", "react-ga",
                  "plausible", "google-analytics", "gtag"],
    "error tracking": ["sentry", "@sentry/", "bugsnag", "rollbar"],
    "cache or queue": ["redis", "ioredis", "celery", "rq", "bull", "bullmq", "kafka", "pika", "amqplib"],
    "second datastore": ["pymongo", "mongoose", "mongodb", "elasticsearch", "@elastic/", "dynamodb"],
    "external mail vendor": ["sendgrid", "@sendgrid/", "mailgun", "postmark", "resend"],
    "external payments vendor": ["stripe", "braintree", "paypal"],
    "consent tooling": ["cookieconsent", "onetrust", "cookiebot"],
}


def dependencies(b) -> list[str]:
    deps, app = [], b.app_dir
    for req in app.rglob("requirements*.txt"):
        if "node_modules" in req.parts:
            continue
        for line in req.read_text().splitlines():
            name = re.split(r"[\s<>=!~\[;]", line.strip(), maxsplit=1)[0]
            if name and not name.startswith(("#", "-")):
                deps.append(name.lower())
    for pkg in app.rglob("package.json"):
        if "node_modules" in pkg.parts:
            continue
        try:
            data = json.loads(pkg.read_text())
        except ValueError:
            continue
        deps += [d.lower() for d in (data.get("dependencies") or {})]
    py = app / "pyproject.toml"
    if py.is_file():
        try:
            project = tomllib.loads(py.read_text()).get("project") or {}
            deps += [re.split(r"[\s<>=!~\[;]", d, maxsplit=1)[0].lower() for d in project.get("dependencies") or []]
        except tomllib.TOMLDecodeError:
            pass
    return sorted(set(deps))


def scope_lint(b) -> list[dict]:
    text, out = brief(b).lower(), []
    for dep in dependencies(b):
        for category, names in UNASKED.items():
            for name in names:
                if dep == name or (name.endswith("/") and dep.startswith(name)):
                    vendor = name.strip("@/")
                    if vendor not in text:
                        out.append(finding("unasked-dependency",
                            f"runtime dependency {dep!r} ({category}) is not asked for by the brief"))
    return out
