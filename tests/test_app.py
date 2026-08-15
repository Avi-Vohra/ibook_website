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
PAGES = ["Home", "How it works", "Try it", "Human results", "The stack"]


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
    assert r.budget == 200
    assert r.title == "The Salt Road"
    assert r.debut and r.deadline

    plan = planner.make_plan(r, {"publish", "translate", "market"})
    assert len(plan) == 9
    assert sum(i.cost for i in plan) == 145
    assert sum(1 for i in plan if i.is_human) == 3
    assert [i.phase for i in plan] == sorted(i.phase for i in plan)


def test_plan_respects_a_smaller_budget() -> None:
    r = planner.read_context(content.SAMPLE_CTX)
    r.budget = 100
    plan = planner.make_plan(r, {"publish", "translate", "market"})
    assert sum(i.cost for i in plan) <= 100
    assert any(i.is_human for i in plan), "the human step is the point of Bookit"


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
    assert len(at.session_state["plan"]) == 9

    run = [b for b in at.button if b.label.startswith("Run it")][0]
    run.click().run()  # run animation, then the results
    assert not at.exception
    assert at.session_state["step"] == "results"

    body = " ".join(str(m.value) for m in at.markdown)
    assert "Cover directions" in body
    assert "Translation glossary" in body      # translation was selected
    assert "Launch assets" in body             # marketing was selected
    assert "interior-print.pdf" in body        # publishing was selected


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
