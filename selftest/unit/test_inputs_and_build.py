import appbuild
import cli
import receipts as R
from bundle import Bundle
from stages import STAGES, Context, g0_inputs, t0_triage


def test_reference_bundle_shape(reference):
    b = Bundle.load(reference)
    assert b.name == "deku/talent-roster-reel"
    assert b.port == "4173"
    assert b.pytest_substeps > 0 and b.browser_substeps == 0
    assert b.project.startswith("golden-s-conte-dire-talent-roster-reel")
    assert appbuild.deploy_mode(b) == "run.json"


def test_g0_passes_on_the_solved_reference(reference):
    verdict, summary, details = g0_inputs(Context(bundle=Bundle.load(reference), bar={}))
    assert verdict == R.PASS, details.get("problems")


def test_g0_fails_on_an_unsolved_bundle(unsolved):
    verdict, _, details = g0_inputs(Context(bundle=Bundle.load(unsolved), bar={}))
    assert verdict == R.FAIL
    problems = " | ".join(details["problems"])
    assert "solution/app/ is missing or empty" in problems
    assert "NO-SOLUTION stub" in problems


def test_g0_catches_an_undeclared_slot(reference):
    toml = reference / "task.toml"
    toml.write_text(toml.read_text().replace('\n[metadata.services]\nbackend = "postgres"\n', "\n"))
    verdict, _, details = t0_triage(Context(bundle=Bundle.load(reference), bar={}))
    assert verdict == R.FAIL
    assert any("make_backend() but task.toml declares no [metadata.services].backend" in p
               for p in details["problems"])


def test_manifest_must_serve_in_the_foreground():
    ok = {"install": "", "build": "", "serve": "gunicorn app:app"}
    assert appbuild.manifest_problems(ok) == []
    assert appbuild.manifest_problems(dict(ok, serve="setsid gunicorn app:app"))
    assert appbuild.manifest_problems(dict(ok, serve="gunicorn app:app &"))
    assert appbuild.manifest_problems(None)


def test_rendered_dockerfile_builds_from_the_manifest(reference, tmp_path):
    b = Bundle.load(reference)
    (b.app_dir / "node_modules").mkdir()
    (b.app_dir / "node_modules" / "stale.js").write_text("x")
    ctx, mode = appbuild.stage(b, "env:latest", tmp_path)
    text = (ctx / "Dockerfile").read_text()
    assert mode == "run.json"
    assert text.startswith("FROM env:latest")
    assert '"pip install --no-cache-dir -r requirements.txt"' in text.replace("set -e; cd /app; ", "")
    assert "exec python -m gunicorn --bind 0.0.0.0:${APP_PUBLIC_PORT} app:app" in text
    assert not (ctx / "node_modules").exists()
    assert (b.app_dir / "node_modules").exists()  # the bundle itself is untouched


def test_gauntlet_g0_exit_code(reference):
    assert cli.main(["gauntlet", str(reference), "--only", "G0"]) == 0
    rows = R.read(Bundle.load(reference))
    assert rows[-1]["stage"] == "G0" and rows[-1]["verdict"] == R.PASS


def test_g10_never_runs_without_official(reference):
    assert cli.main(["gauntlet", str(reference), "--only", "G10"]) == 2
    assert R.read(Bundle.load(reference))[-1]["verdict"] == R.BLOCKED
