import receipts as R
import state as S
from bundle import Bundle


def test_tree_sha_ignores_installed_trees(tmp_path):
    (tmp_path / "app.py").write_text("print(1)\n")
    before = R.tree_sha(tmp_path)
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "node_modules" / "x" / "index.js").write_text("junk")
    (tmp_path / "server.log").write_text("noise")
    assert R.tree_sha(tmp_path) == before
    (tmp_path / "app.py").write_text("print(2)\n")
    assert R.tree_sha(tmp_path) != before


def test_receipt_goes_stale_when_the_app_changes(reference):
    b = Bundle.load(reference)
    row = R.append(b, "G3", R.PASS, "pytest 57/57")
    assert not R.is_stale(row, R.input_hashes(b), ("app", "bundle"))
    (b.app_dir / "app.py").write_text((b.app_dir / "app.py").read_text() + "\n# edited\n")
    assert R.is_stale(row, R.input_hashes(b), ("app", "bundle"))
    assert not R.is_stale(row, R.input_hashes(b), ("bundle",))


def test_latest_receipt_wins(reference):
    b = Bundle.load(reference)
    R.append(b, "G1", R.FAIL, "first")
    R.append(b, "G1", R.PASS, "second")
    assert R.latest(R.read(b))["G1"]["summary"] == "second"


def test_state_machine_and_approvals(reference):
    b = Bundle.load(reference)
    st = S.init(b)
    assert st["phase"] == "P-1" and st["status"] == "IN_PROGRESS"
    st = S.advance(b, st, "P2", "design approved")
    assert S.load(b)["phase"] == "P2"
    st = S.approve(b, st, "P7", "reviewer")
    assert S.load(b)["status"] == "GOLDEN"
    assert S.init(b)["phase"] == "P2"  # init never resets existing state


def test_rubric_resume_only_over_identical_bytes(reference, tmp_path):
    from stages import Context, resumable_rubric
    b = Bundle.load(reference)
    ev = tmp_path / "g9run"
    (ev / "verifier").mkdir(parents=True)
    (ev / "verifier" / "evidence_bundle.json").write_text('{"verdicts": []}')
    R.append(b, "G9", R.FAIL, "rubric short", {"evidence": str(ev)})
    ctx = Context(bundle=b, bar={})
    assert resumable_rubric(ctx) == ev / "verifier" / "evidence_bundle.json"
    (b.app_dir / "app.py").write_text((b.app_dir / "app.py").read_text() + "\n# fixed\n")
    assert resumable_rubric(ctx) is None
