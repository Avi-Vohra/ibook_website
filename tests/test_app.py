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


# A canned plan, injected via the `_offline_plan` seam so the wizard tests never
# call Pioneer or Terac. Shaped exactly like real planner output.
OFFLINE_PLAN = {
    "book_summary": {"title": "The Salt Road", "genre": "YA fantasy",
                     "current_language": "English", "target_audience": "young adult"},
    "plan_summary": "Translate and publish a German edition.",
    "actions": [
        {"id": "A1", "title": "Confirm the German tone",
         "execution_type": "AUTHOR_DECISION",
         "description": "Should the German edition use du or Sie?",
         "product": {"name": "Decision record"},
         "steps": [{"step": "Answer the question", "owner": "author"},
                   {"step": "Record the answer", "owner": "ai"}]},
        {"id": "A2", "title": "Translate the book into German",
         "execution_type": "AI_AUTOMATED", "depends_on": ["A1"],
         "product": {"name": "German edition of the manuscript"},
         "steps": [{"step": "Lock names into a glossary", "owner": "ai"},
                   {"step": "Translate the manuscript", "owner": "ai"}]},
        {"id": "A3", "title": "Native German editorial review",
         "execution_type": "TERAC_EXPERT", "depends_on": ["A2"],
         "product": {"name": "Reviewed German manuscript"},
         "steps": [{"step": "A native editor revises the draft", "owner": "expert"},
                   {"step": "Corrections are applied", "owner": "ai"}],
         "terac_opportunity": {"expert_role": "Native German literary editor",
                               "panel_description": "Native German literary editors",
                               "opportunity_description": "Review the translation.",
                               "expert_count": 1, "timeline_hours": 120}},
    ],
}


def _wizard_at_plan(**services: bool) -> "AppTest":
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["nav"] = "Try it"
    at.session_state["sample_file"] = True
    at.session_state["ctx_input"] = content.SAMPLE_CTX
    at.session_state["_offline_plan"] = OFFLINE_PLAN
    for key, value in (services or {"svc_publish": True, "svc_translate": True}).items():
        at.session_state[key] = value
    at.run()
    assert not at.exception
    build = [b for b in at.button if "publishing plan" in b.label][0]
    assert not build.disabled, "sample manuscript + services should unlock the build"
    build.click().run()  # thinking animation, then the plan
    assert not at.exception, at.exception
    return at


def test_plan_step_shows_actions_with_their_steps() -> None:
    at = _wizard_at_plan()
    assert at.session_state["step"] == "plan"
    plan = at.session_state["plan"]
    assert [a.id for a in plan.actions] == ["A1", "A2", "A3"]

    body = " ".join(str(m.value) for m in at.markdown)
    assert "Translate the book into German" in body
    assert "German edition of the manuscript" in body      # the product line
    assert "Human via Terac" in body                        # the badge on A3
    assert "Needs your decision" in body                    # the badge on A1
    # every action gets a collapsible step list
    assert len(at.expander) >= 3


def test_run_stops_at_the_terac_approval_instead_of_spending() -> None:
    at = _wizard_at_plan()
    [b for b in at.button if b.label.startswith("Run it")][0].click().run()
    assert not at.exception, at.exception
    assert at.session_state["step"] == "results"

    run = at.session_state["run"]
    # A1 needs the author, so nothing behind it may have started
    assert run.tasks["A1"].status == "awaiting_author"
    assert run.tasks["A2"].status == "pending"
    assert run.spent_usd == 0.0

    body = " ".join(str(m.value) for m in at.markdown)
    assert "Your call" in body, "the author's decision must be surfaced"
    assert "simulated" in body.lower(), "the demo must say Terac was not real"


def test_answering_the_author_question_advances_the_run() -> None:
    at = _wizard_at_plan()
    [b for b in at.button if b.label.startswith("Run it")][0].click().run()

    at.text_input[0].set_value("Use informal du.").run()
    [b for b in at.button if b.label == "Submit"][0].click().run()
    assert not at.exception, at.exception

    run = at.session_state["run"]
    assert run.tasks["A1"].status == "done"
    assert run.tasks["A2"].status == "done", "answering unblocks the AI work"
    assert run.tasks["A3"].status == "quoted", "and the Terac task gets priced"
    assert run.spent_usd == 0.0, "quoting must not spend"

    body = " ".join(str(m.value) for m in at.markdown)
    assert "needs your approval" in body.lower()

    invoice = [b for b in at.button if "invoice" in b.label][0]
    invoice.click().run()
    assert not at.exception
    assert at.session_state["step"] == "invoice"
    body = " ".join(str(m.value) for m in at.markdown)
    assert "$215" in body                      # 75 + 4×10 + 100 (publish + translate)
    assert "Stripe is not configured" in body or "Opens Stripe's hosted checkout" in body


def test_deselecting_every_item_blocks_the_run() -> None:
    at = _wizard_at_plan()
    for checkbox in at.checkbox:
        if checkbox.key and checkbox.key.startswith("act_"):
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
