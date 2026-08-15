"""Smoke tests — every page renders, and the wizard runs end to end.

    python tests/test_app.py        (or: pytest tests)
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

from bookit import content, planner  # noqa: E402

APP = str(ROOT / "app.py")
PAGES = ["Home", "How it works", "Pricing", "Try it", "Human results", "The stack"]


def test_every_page_renders() -> None:
    for page in PAGES:
        at = AppTest.from_file(APP, default_timeout=30)
        at.session_state["nav"] = page
        at.run()
        assert not at.exception, f"{page} raised: {at.exception}"


def test_planner_reads_the_sample_author() -> None:
    r = planner.read_context(content.SAMPLE_CTX)
    assert r.genre == "fantasy"
    assert r.langs == ["German"]
    assert r.platform == "Amazon KDP"
    assert r.budget is None
    assert r.title == "The Salt Road"
    assert r.debut and r.deadline

    plan = planner.make_plan(r, {"publish", "translate", "market"})
    assert len(plan) == planner.CAP
    assert sum(1 for i in plan if i.is_human) == 4
    assert [i.phase for i in plan] == sorted(i.phase for i in plan)


def test_pricing_adds_up() -> None:
    services = {"publish", "translate", "market"}
    lines, total = planner.price_order(services, covers=4, langs=1, lang_names=["German"])
    assert total == 75 + 40 + 100 + 50
    assert sum(x["v"] for x in lines) == total
    assert any("German" in x["d"] for x in lines)


def test_trim_fits_the_budget_and_says_what_it_dropped() -> None:
    services = {"publish", "translate", "market"}
    trimmed, cov, lng, dropped = planner.trim_order(120, services, covers=4, langs=2)
    _, total = planner.price_order(trimmed, cov, lng)
    assert total <= 120
    assert "publish" in trimmed, "publishing is the last thing to go"
    assert "Marketing" in dropped and "Translation" in dropped

    # an impossible budget trims as far as it goes, but never drops publishing
    trimmed, cov, lng, _ = planner.trim_order(20, {"publish"}, covers=4, langs=1)
    assert trimmed == {"publish"} and cov == 1
    assert planner.price_order(trimmed, cov, lng)[1] > 20


def test_wizard_runs_end_to_end() -> None:
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["nav"] = "Try it"
    at.session_state["sample_file"] = True
    at.session_state["svc_publish"] = True
    at.session_state["svc_translate"] = True
    at.session_state["svc_market"] = True
    at.session_state["ctx_input"] = content.SAMPLE_CTX
    at.run()
    assert not at.exception

    build = [b for b in at.button if "publishing plan" in b.label][0]
    assert not build.disabled, "sample manuscript + services should unlock the build"
    build.click().run()  # thinking animation, then the plan
    assert not at.exception
    assert at.session_state["step"] == "plan"
    assert len(at.session_state["plan"]) == planner.CAP

    run = [b for b in at.button if b.label.startswith("Run it")][0]
    run.click().run()  # run animation, then the results
    assert not at.exception
    assert at.session_state["step"] == "results"

    body = " ".join(str(m.value) for m in at.markdown)
    assert "Cover directions" in body
    assert "Translation glossary" in body      # translation was selected
    assert "Launch assets" in body             # marketing was selected
    assert "interior-print.pdf" in body        # publishing was selected

    invoice = [b for b in at.button if "invoice" in b.label][0]
    invoice.click().run()
    assert not at.exception
    assert at.session_state["step"] == "invoice"
    body = " ".join(str(m.value) for m in at.markdown)
    assert "$265" in body                      # 75 + 4×10 + 100 + 50
    assert "Stripe is not configured" in body or "Opens Stripe's hosted checkout" in body


def test_deselecting_every_item_blocks_the_run() -> None:
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["nav"] = "Try it"
    at.session_state["sample_file"] = True
    at.session_state["svc_publish"] = True
    at.session_state["ctx_input"] = content.SAMPLE_CTX
    at.run()
    [b for b in at.button if "publishing plan" in b.label][0].click().run()

    for checkbox in at.checkbox:
        if checkbox.key and checkbox.key.startswith("item_"):
            checkbox.uncheck()
    at.run()
    run = [b for b in at.button if b.label.startswith("Run it")][0]
    assert run.disabled, "nothing selected should disable the run"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\n{len(tests)} passed")
