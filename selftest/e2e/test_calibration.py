"""Calibrate the gauntlet against the one bundle known to be solved.

The reference task's app scored oracle 1.0 on 3/3 stock harbor 0.24 runs, so
G0-G3 MUST go green on it -- a red here is a gauntlet defect, not an app one.
The two planted defects MUST go red, or the gauntlet is passing things it should not.
Needs Docker; run with: golden/bin/gauntlet --self-test --e2e
"""
import cli
import receipts as R
from bundle import Bundle

API = "solution/app/cirrus/api_public.py"


def _plant(bundle_root, old, new):
    path = bundle_root / API
    text = path.read_text()
    assert old in text, "planted-defect anchor moved; update the calibration"
    path.write_text(text.replace(old, new, 1))


def _verdicts(bundle_root):
    return {sid: row["verdict"] for sid, row in R.latest(R.read(Bundle.load(bundle_root))).items()}


def test_known_good_app_goes_green(reference):
    assert cli.main(["gauntlet", str(reference), "--only", "G0,G1,G2,G3"]) == 0
    assert _verdicts(reference) == {"G0": "PASS", "G1": "PASS", "G2": "PASS", "G3": "PASS"}


def test_failing_health_route_is_caught_at_deploy(reference):
    _plant(reference, 'def health() -> tuple[Response, int]:\n',
           'def health() -> tuple[Response, int]:\n'
           '    return jsonify({"status": "broken"}), 503\n')
    assert cli.main(["gauntlet", str(reference), "--only", "G0,G1,G2"]) == 2
    assert _verdicts(reference)["G2"] == "FAIL"


def test_api_regression_is_caught_by_pytest(reference):
    _plant(reference, 'return jsonify({"error": "not_found", "reason": reason}), 404',
           'return jsonify({"error": "not_found", "reason": reason}), 500')
    assert cli.main(["gauntlet", str(reference), "--only", "G0,G1,G2,G3"]) == 2
    assert _verdicts(reference)["G3"] == "FAIL"
