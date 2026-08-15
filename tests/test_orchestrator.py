"""The execution agent: state machine, spend gate, durability.

Everything here runs offline against stubs — no Pioneer call, no Terac call, no
money. The point of these tests is that the spend gate cannot be bypassed.

    python tests/test_orchestrator.py        (or: pytest tests)
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bookit import orchestrator as orch  # noqa: E402
from bookit.action_planner import parse_plan  # noqa: E402
from bookit.terac import StubTeracClient  # noqa: E402

PLAN = {
    "book_summary": {"title": "The Salt Road", "genre": "fantasy"},
    "plan_summary": "Translate and publish a German edition.",
    "actions": [
        {
            "id": "A1", "title": "Confirm pricing and pen name",
            "execution_type": "AUTHOR_DECISION",
            "description": "Should the German edition use du or Sie?",
            "product": {"name": "Decision record"},
            "steps": [{"step": "Answer three questions", "owner": "author"},
                      {"step": "Record the answers", "owner": "ai"}],
        },
        {
            "id": "A2", "title": "Translate the book into German",
            "execution_type": "AI_AUTOMATED", "depends_on": ["A1"],
            "product": {"name": "German edition of the manuscript"},
            "steps": [{"step": "Lock the glossary", "owner": "ai"},
                      {"step": "Translate it", "owner": "ai"}],
        },
        {
            "id": "A3", "title": "Native German editorial review",
            "execution_type": "TERAC_EXPERT", "depends_on": ["A2"],
            "product": {"name": "Reviewed German manuscript"},
            "steps": [{"step": "A native editor revises", "owner": "expert"},
                      {"step": "Apply corrections", "owner": "ai"}],
            "terac_opportunity": {
                "expert_role": "Native German literary editor",
                "panel_description": "Native German literary editors",
                "opportunity_description": "Review the translation.",
                "expert_count": 2, "timeline_hours": 120,
            },
        },
    ],
}


class FakePioneer:
    """Returns canned text instead of calling the model."""

    def __init__(self) -> None:
        self.model = "fake-model"
        self.calls: list[str] = []


def _fake_text(self, system, user):  # noqa: ANN001, ARG001
    from bookit.pioneer import Route
    self.pioneer.calls.append(user)
    return "Generated content for this action.", Route(model="fake-model")


def build(tmp: Path, **kwargs):  # noqa: ANN001, ANN201
    plan = parse_plan(PLAN)
    store = orch.RunStore(tmp)
    o = orch.Orchestrator(store, pioneer=FakePioneer(), terac=StubTeracClient(), **kwargs)
    o._pioneer_text = _fake_text.__get__(o)  # noqa: SLF001
    return o, plan, store


def test_author_decision_blocks_everything_behind_it() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        o, plan, _ = build(tmp)
        run = o.tick(o.start(plan), plan)

        assert run.tasks["A1"].status == orch.AWAITING_AUTHOR
        assert "du or Sie" in run.tasks["A1"].question
        # A2 depends on A1, A3 on A2 — neither may start
        assert run.tasks["A2"].status == orch.PENDING
        assert run.tasks["A3"].status == orch.PENDING
        assert not run.is_finished

        o.answer(run, "A1", "Use informal du.")
        run = o.tick(run, plan)
        assert run.tasks["A1"].status == orch.DONE
        assert run.tasks["A2"].status == orch.DONE, "answering must unblock the chain"
        assert run.tasks["A3"].status == orch.QUOTED
    finally:
        shutil.rmtree(tmp)


def test_terac_work_is_quoted_but_never_launched_without_approval() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        o, plan, _ = build(tmp)
        run = o.start(plan)
        o.answer(run, "A1", "du")
        run = o.tick(run, plan)

        task = run.tasks["A3"]
        assert task.status == orch.QUOTED
        assert task.quote_id and task.quote_cost > 0
        assert run.spent_usd == 0.0, "quoting must be free"
        assert not task.opportunity_id, "nothing may be launched yet"
        assert [c[0] for c in o.terac.calls] == ["quote"], "launch must not have been called"
        assert run.quoted_total == task.quote_cost

        # ticking again must not sneak a launch through
        run = o.tick(run, plan)
        assert run.spent_usd == 0.0
        assert [c[0] for c in o.terac.calls] == ["quote"]
    finally:
        shutil.rmtree(tmp)


def test_approval_launches_and_records_the_spend() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        o, plan, _ = build(tmp)
        run = o.start(plan)
        o.answer(run, "A1", "du")
        run = o.tick(run, plan)
        cost = run.tasks["A3"].quote_cost

        o.approve(run, "A3")
        assert run.tasks["A3"].status == orch.LAUNCHED
        assert run.tasks["A3"].opportunity_id
        assert run.spent_usd == cost
        assert [c[0] for c in o.terac.calls] == ["quote", "launch"]
    finally:
        shutil.rmtree(tmp)


def test_an_expired_quote_is_re_priced_instead_of_failing() -> None:
    # Terac quotes last one hour; an author is under no obligation to decide
    # inside one. Launching a dead quote would just error.
    from bookit.action_planner import parse_plan as _pp

    tmp = Path(tempfile.mkdtemp())
    try:
        o, plan, _ = build(tmp)
        run = o.start(plan)
        o.answer(run, "A1", "du")
        run = o.tick(run, plan)

        task = run.tasks["A3"]
        first_quote = task.quote_id
        task.quote_expires_at = "2020-01-01T00:00:00Z"      # long gone

        spec = next(a for a in _pp(PLAN).actions if a.id == "A3").terac_opportunity
        o.approve(run, "A3", spec)

        assert task.quote_id != first_quote, "a stale quote must be refreshed"
        assert task.status == orch.LAUNCHED
        assert [c[0] for c in o.terac.calls] == ["quote", "quote", "launch"]
        assert any("re-quoted" in line for line in run.log)
    finally:
        shutil.rmtree(tmp)


def test_a_fresh_quote_is_not_re_priced() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        o, plan, _ = build(tmp)
        run = o.start(plan)
        o.answer(run, "A1", "du")
        run = o.tick(run, plan)
        first_quote = run.tasks["A3"].quote_id

        o.approve(run, "A3", None)
        assert run.tasks["A3"].quote_id == first_quote
        assert [c[0] for c in o.terac.calls] == ["quote", "launch"], "no wasted re-quote"
    finally:
        shutil.rmtree(tmp)


def test_approving_something_not_quoted_is_refused() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        o, plan, _ = build(tmp)
        run = o.tick(o.start(plan), plan)
        try:
            o.approve(run, "A1")  # an author decision, never quoted
        except ValueError:
            assert run.spent_usd == 0.0
            return
        raise AssertionError("approving an unquoted task should raise")
    finally:
        shutil.rmtree(tmp)


def test_declining_drops_the_task_without_spending() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        o, plan, _ = build(tmp)
        run = o.start(plan)
        o.answer(run, "A1", "du")
        run = o.tick(run, plan)
        o.decline(run, "A3")
        assert run.tasks["A3"].status == orch.FAILED
        assert run.spent_usd == 0.0
        assert "launch" not in [c[0] for c in o.terac.calls]
    finally:
        shutil.rmtree(tmp)


def test_auto_approve_only_fires_under_the_ceiling() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        # stub prices 2 experts at 4.25 each = 8.50
        o, plan, _ = build(tmp, auto_approve_under=100.0)
        run = o.start(plan)
        o.answer(run, "A1", "du")
        run = o.tick(run, plan)
        assert run.tasks["A3"].status == orch.LAUNCHED
        assert run.spent_usd == 8.50
    finally:
        shutil.rmtree(tmp)

    tmp = Path(tempfile.mkdtemp())
    try:
        o, plan, _ = build(tmp, auto_approve_under=5.0)  # below the quote
        run = o.start(plan)
        o.answer(run, "A1", "du")
        run = o.tick(run, plan)
        assert run.tasks["A3"].status == orch.QUOTED, "over the ceiling must still ask"
        assert run.spent_usd == 0.0
    finally:
        shutil.rmtree(tmp)


def test_a_run_survives_a_restart() -> None:
    # Terac needs >= 72h, so a run must outlive the process that started it.
    tmp = Path(tempfile.mkdtemp())
    try:
        o, plan, store = build(tmp)
        run = o.start(plan)
        o.answer(run, "A1", "Use informal du.")
        run = o.tick(run, plan)
        o.approve(run, "A3")
        run_id = run.run_id

        reloaded = orch.RunStore(tmp).load(run_id)
        assert reloaded.tasks["A1"].answer == "Use informal du."
        assert reloaded.tasks["A2"].output
        assert reloaded.tasks["A3"].status == orch.LAUNCHED
        assert reloaded.tasks["A3"].opportunity_id
        assert reloaded.spent_usd == run.spent_usd
        # and the plan round-trips, so the orchestrator can keep going
        assert len(parse_plan(reloaded.plan).actions) == 3
    finally:
        shutil.rmtree(tmp)


def test_an_empty_ai_result_fails_instead_of_reporting_success() -> None:
    # Observed live: a reasoning model spent its whole budget thinking and
    # returned "". The task was marked done and released everything behind it.
    from bookit.pioneer import Route

    tmp = Path(tempfile.mkdtemp())
    try:
        o, plan, _ = build(tmp)
        o._pioneer_text = lambda s, u: ("   ", Route(model="fake-model"))  # noqa: SLF001
        run = o.start(plan)
        o.answer(run, "A1", "du")
        run = o.tick(run, plan)

        assert run.tasks["A2"].status == orch.FAILED
        assert "empty" in run.tasks["A2"].error.lower()
        assert run.tasks["A3"].status == orch.PENDING, "must not release dependents"
        assert run.spent_usd == 0.0, "and must not reach Terac"
    finally:
        shutil.rmtree(tmp)


def test_a_completing_terac_task_releases_its_dependents_in_the_same_tick() -> None:
    # Regression: _collect() used to run after the ready-loop, so a Terac task
    # finishing during polling left everything behind it pending until the
    # *next* tick — a run could look stalled while it was actually done.
    tmp = Path(tempfile.mkdtemp())
    try:
        plan = parse_plan({
            "actions": [
                {"id": "A1", "title": "Cover test with readers",
                 "execution_type": "TERAC_EXPERT",
                 "product": {"name": "Chosen cover"},
                 "steps": [{"step": "Readers rank the covers", "owner": "expert"},
                           {"step": "Ship the winner", "owner": "ai"}],
                 "terac_opportunity": {"expert_role": "reader", "panel_description": "readers",
                                       "expert_count": 3, "timeline_hours": 72}},
                {"id": "A2", "title": "Publish the edition", "depends_on": ["A1"],
                 "product": {"name": "Live listing"},
                 "steps": [{"step": "Upload", "owner": "ai"},
                           {"step": "Verify", "owner": "ai"}]},
            ]
        })
        store = orch.RunStore(tmp)
        o = orch.Orchestrator(
            store, pioneer=FakePioneer(),
            terac=StubTeracClient(complete_after_polls=1),
            auto_approve_under=100.0,
        )
        o._pioneer_text = _fake_text.__get__(o)  # noqa: SLF001

        run = o.tick(o.start(plan), plan)
        assert run.tasks["A1"].status == orch.DONE
        assert run.tasks["A1"].submissions_in == 3
        assert run.tasks["A2"].status == orch.DONE, "dependent must run in the same tick"
        assert run.is_finished
    finally:
        shutil.rmtree(tmp)


def test_failed_dependency_does_not_release_dependents() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        o, plan, _ = build(tmp)
        run = o.start(plan)
        run.tasks["A1"].status = orch.FAILED
        run = o.tick(run, plan)
        assert run.tasks["A2"].status == orch.PENDING, "must not run behind a failure"
    finally:
        shutil.rmtree(tmp)


def test_tick_is_idempotent_when_nothing_can_move() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        o, plan, _ = build(tmp)
        run = o.tick(o.start(plan), plan)
        before = {k: (t.status, t.updated_at) for k, t in run.tasks.items()}
        run = o.tick(run, plan)
        after = {k: (t.status, t.updated_at) for k, t in run.tasks.items()}
        assert before == after, "a no-op tick must not churn state"
        assert len(o.pioneer.calls) == 0
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\n{len(tests)} passed")
