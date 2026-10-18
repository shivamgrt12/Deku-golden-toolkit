import noise


def _run(w1_sub2, rubric_r2, combined):
    return {
        "final": {"combined_score": combined},
        "workflows": {"workflows": [
            {"id": "w1", "passed": w1_sub2, "substeps": [
                {"kind": "browser", "ref": "Sign in", "passed": True},
                {"kind": "browser", "ref": "Verify the badge", "passed": w1_sub2}]},
        ]},
        "judge": {"dimensions": {"R1_ui_visual": {"passed": True},
                                 "R2_ux_flow": {"passed": rubric_r2}}},
    }


def test_flapping_and_stable_items_are_separated():
    report = noise.summarize([_run(True, False, 0.9), _run(False, False, 0.7), _run(True, False, 0.9)])
    flapping = {r["item"] for r in report["flapping"]}
    red = {r["item"] for r in report["stable_red"]}
    green = {r["item"] for r in report["stable_green"]}
    assert any("Verify the badge" in i for i in flapping)
    assert any(i.startswith("workflow  w1") for i in flapping)
    assert "rubric    R2_ux_flow" in red
    assert "rubric    R1_ui_visual" in green
    assert report["combined_scores"] == [0.9, 0.7, 0.9]


def test_unobserved_is_its_own_class():
    a, b = _run(True, True, 1.0), _run(True, True, 1.0)
    for r in (a, b):
        r["workflows"]["workflows"][0]["substeps"][0]["passed"] = None
    report = noise.summarize([a, b])
    assert any("Sign in" in r["item"] for r in report["unobserved"])
    assert "Stable red" not in noise.render(report)
