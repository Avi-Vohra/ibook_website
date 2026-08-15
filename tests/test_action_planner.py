"""Action-item creation: payload building, parsing, and plan validation.

These run offline against a stub client. The live Pioneer call is exercised
separately by `scripts/plan_demo.py`, which costs money and needs a key.

    python tests/test_action_planner.py        (or: pytest tests)
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bookit import action_planner as ap  # noqa: E402
from bookit import content  # noqa: E402
from bookit.pioneer import (  # noqa: E402
    PioneerClient,
    PioneerError,
    Route,
    parse_json_response,
)

VALID_PLAN = {
    "book_summary": {
        "title": "The Salt Road",
        "genre": "fantasy",
        "current_language": "English",
        "target_audience": "young adult",
        "author_goal": "German edition on Amazon KDP",
        "selected_services": ["translation", "publishing"],
    },
    "plan_summary": "Translate, review, typeset and publish a German edition.",
    "actions": [
        {
            "id": "A1",
            "title": "Build German terminology glossary",
            "description": "Extract named entities and lock one German rendering each.",
            "reason": "Keeps chapter 40 consistent with chapter 1.",
            "execution_type": "AI_AUTOMATED",
            "priority": "critical",
            "depends_on": [],
            "inputs": ["manuscript"],
            "product": {
                "name": "EN-DE terminology glossary",
                "format": "glossary",
                "description": "Named entities with one locked German rendering each",
            },
            "steps": [
                {"step": "Extract every character, place and invented term", "owner": "ai"},
                {"step": "Lock one German rendering for each", "owner": "ai"},
            ],
            "acceptance_criteria": ["Every named entity has one German rendering"],
            "estimated_scope": "30 minutes",
            "terac_opportunity": None,
        },
        {
            "id": "A3",
            "title": "Native German editorial review",
            "description": "A native editor reviews the translation against the source.",
            "reason": "Machine translation does not survive a native reader.",
            "execution_type": "TERAC_EXPERT",
            "priority": "critical",
            "depends_on": ["A2"],
            "inputs": ["German manuscript", "English source"],
            "product": {
                "name": "Natively reviewed German manuscript",
                "format": "manuscript",
                "description": "German text revised by a native literary editor",
            },
            "steps": [
                {"step": "A native German editor reads against the source", "owner": "expert"},
                {"step": "Corrections are applied to the manuscript", "owner": "ai"},
            ],
            "acceptance_criteria": ["No glossary violations"],
            "estimated_scope": "8 hours",
            "terac_opportunity": {
                "expert_role": "Native German literary editor",
                "panel_description": "Native German speakers who edit literary fiction",
                "expert_count": 1,
                "timeline_hours": 120,
                "opportunity_title": "Review AI-translated German fantasy manuscript",
                "opportunity_description": "Review 62,000 words against the English source.",
                "required_skills": ["literary editing", "fantasy genre"],
                "language_requirements": ["German (native)", "English (fluent)"],
                "inputs_provided": ["German manuscript", "English source", "glossary"],
                "expected_deliverables": ["Revised manuscript", "Issue list"],
                "acceptance_criteria": ["Tone preserved"],
                "estimated_scope": "8 hours",
                "priority": "critical",
            },
        },
        {
            "id": "A2",
            "title": "Translate manuscript into German",
            "description": "Glossary-locked translation of the full manuscript.",
            "reason": "The author asked for a German edition.",
            "execution_type": "AI_AUTOMATED",
            "priority": "critical",
            "depends_on": ["A1"],
            "inputs": ["manuscript", "glossary-en-de.csv"],
            "product": {
                "name": "German translation of the manuscript",
                "format": "manuscript",
                "description": "Glossary-locked German translation",
            },
            "steps": [
                {"step": "Translate the full manuscript against the glossary", "owner": "ai"},
                {"step": "Check names stayed consistent throughout", "owner": "ai"},
            ],
            "acceptance_criteria": ["All chapters translated"],
            "estimated_scope": "2 hours",
            "terac_opportunity": None,
        },
    ],
}


class StubClient:
    """Stands in for PioneerClient without touching the network."""

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.system: str | None = None
        self.user: str | None = None

    def complete_json(self, system, user, **kwargs):  # noqa: ANN001, ANN003
        self.system, self.user = system, user
        return self.payload, Route(model="stub-model")


# ── request building ──────────────────────────────────────────────────
def test_frontend_state_becomes_a_prompt_payload() -> None:
    request = ap.request_from_frontend(
        ctx_text=content.SAMPLE_CTX,
        services={"publish", "translate"},
        book_file={"name": "the-salt-road.pdf", "size": 1_240_000, "meta": "62,000 words"},
    )
    payload = request.to_payload()

    assert payload["target_languages"] == ["German"]
    assert payload["budget"] == 200
    assert payload["deadline"] is not None
    assert payload["publishing_requirements"]["target_platform"] == "Amazon KDP"
    assert payload["publishing_requirements"]["genre"] == "fantasy"
    assert payload["publishing_requirements"]["author_status"].startswith("debut")
    assert payload["book_file"]["filename"] == "the-salt-road.pdf"
    assert payload["book_file"]["format"] == "pdf"
    # the three UI checkboxes widen into the prompt's finer vocabulary, in a
    # fixed order — the same selection must always build the same prompt
    assert payload["selected_services"] == [
        "publishing", "formatting", "cover design", "translation"
    ]
    again = ap.request_from_frontend(
        ctx_text=content.SAMPLE_CTX, services={"translate", "publish"}
    )
    assert again.to_payload()["selected_services"] == payload["selected_services"]


def test_missing_fields_are_sent_as_null_not_omitted() -> None:
    # The prompt turns nulls into AUTHOR_DECISION actions, so they must survive.
    request = ap.request_from_frontend(ctx_text="I wrote a book.", services={"publish"})
    payload = request.to_payload()
    for key in ("book_content", "book_file", "budget", "deadline", "additional_requests"):
        assert key in payload and payload[key] is None, key


def test_long_manuscripts_are_sampled_head_middle_and_tail() -> None:
    text = " ".join(f"w{i}" for i in range(10_000))
    out = ap.excerpt(text, max_words=300)
    assert len(out.split()) < 400
    assert "w0" in out and "w9999" in out, "head and tail must both survive"
    assert "words omitted" in out
    short = "just a few words"
    assert ap.excerpt(short) == short


# ── parsing and validation ────────────────────────────────────────────
def test_parses_a_well_formed_plan() -> None:
    plan = ap.parse_plan(VALID_PLAN)
    assert plan.book_summary.title == "The Salt Road"
    assert len(plan.actions) == 3
    assert not plan.warnings
    assert [a.id for a in plan.ai_actions] == ["A1", "A2"]
    assert [a.id for a in plan.human_actions] == ["A3"]
    assert len(plan.opportunities) == 1
    assert plan.opportunities[0].expert_role == "Native German literary editor"
    assert plan.actions[0].owner == "agent"
    assert plan.human_actions[0].owner == "human"


def test_actions_are_reordered_to_respect_dependencies() -> None:
    # A3 arrives before A2 in the payload but depends on it.
    plan = ap.parse_plan(VALID_PLAN)
    order = [a.id for a in plan.actions]
    assert order.index("A1") < order.index("A2") < order.index("A3")


def test_dependency_cycles_do_not_lose_actions() -> None:
    payload = {
        "actions": [
            {"id": "A1", "title": "one", "depends_on": ["A2"], "deliverables": ["x"]},
            {"id": "A2", "title": "two", "depends_on": ["A1"], "deliverables": ["y"]},
        ]
    }
    plan = ap.parse_plan(payload)
    assert {a.id for a in plan.actions} == {"A1", "A2"}, "a cycle must not drop work"


def test_bad_fields_are_repaired_and_reported() -> None:
    payload = {
        "actions": [
            {
                "id": "A1",
                "title": "Ghost dependency",
                "execution_type": "MAGIC",          # unknown → falls back to AI
                "priority": "urgent",               # unknown → falls back
                "depends_on": ["A1", "A99"],        # self + nonexistent
                "product": {"name": "Something"},
                "steps": [{"step": "a", "owner": "ai"}, {"step": "b", "owner": "ai"}],
            },
            {"id": "A1", "title": "Duplicate id", "product": {"name": "Other"},
             "steps": [{"step": "a", "owner": "ai"}, {"step": "b", "owner": "ai"}]},
        ]
    }
    plan = ap.parse_plan(payload)
    first = plan.actions[0]
    assert first.execution_type == "AI_AUTOMATED"
    assert first.priority == "recommended"
    assert first.depends_on == []
    assert len({a.id for a in plan.actions}) == 2, "duplicate ids must be made unique"
    joined = " ".join(plan.warnings)
    assert "A99" in joined and "self-dependency" in joined


# ── author-facing shape: coarse actions with a step preview ───────────
def test_a_well_shaped_action_produces_no_warnings() -> None:
    payload = {
        "actions": [{
            "id": "A1",
            "title": "Translate the book into German",
            "execution_type": "AI_WITH_EXPERT_REVIEW",
            "priority": "critical",
            "product": {"name": "German edition of the manuscript", "format": "manuscript"},
            "steps": [
                {"step": "Lock character names into a glossary", "owner": "ai"},
                {"step": "Translate the full manuscript", "owner": "ai"},
                {"step": "A native German editor revises the draft", "owner": "expert"},
            ],
            "terac_opportunity": {
                "expert_role": "Native German literary editor",
                "panel_description": "Native German literary editors",
                "expert_count": 1, "timeline_hours": 120,
            },
        }, {
            "id": "A2", "title": "Publish the German edition on Amazon KDP",
            "product": {"name": "Live German listing", "format": "KDP listing"},
            "steps": [{"step": "Build the files", "owner": "ai"},
                      {"step": "Upload to KDP", "owner": "ai"}],
        }, {
            "id": "A3", "title": "Design the cover",
            "product": {"name": "Final cover", "format": "cover artwork"},
            "steps": [{"step": "Generate four directions", "owner": "ai"},
                      {"step": "Readers pick the winner", "owner": "expert"}],
        }]
    }
    plan = ap.parse_plan(payload)
    assert not plan.warnings, plan.warnings
    assert not plan.malformed_actions
    assert plan.products[0].name == "German edition of the manuscript"
    assert [s.owner for s in plan.actions[0].steps] == ["ai", "ai", "expert"]
    assert len(plan.actions[0].expert_steps) == 1


def test_a_plan_with_no_humans_is_flagged() -> None:
    # Observed live with a cheap model: "4 actions · 0 involve real people".
    # Mechanically fine, but it deletes the product's central claim.
    payload = {"actions": [
        {"id": f"A{i}", "title": f"Do thing {i}",
         "execution_type": "AI_AUTOMATED",
         "product": {"name": f"Product {i}"},
         "steps": [{"step": "a", "owner": "ai"}, {"step": "b", "owner": "ai"}]}
        for i in range(1, 5)
    ]}
    plan = ap.parse_plan(payload)
    assert any("does not do" in w for w in plan.warnings)
    assert not plan.human_actions


def test_an_engineering_backlog_is_flagged() -> None:
    # The failure mode the coarse rewrite exists to prevent: 23 micro-actions.
    payload = {"actions": [
        {"id": f"A{i}", "title": f"Step {i}",
         "product": {"name": f"Thing {i}"},
         "steps": [{"step": "do it", "owner": "ai"}, {"step": "check it", "owner": "ai"}]}
        for i in range(1, 13)
    ]}
    plan = ap.parse_plan(payload)
    assert any("engineering backlog" in w for w in plan.warnings)


def test_too_many_steps_is_flagged_as_too_detailed() -> None:
    payload = {"actions": [{
        "id": "A1", "title": "Translate the book into German",
        "product": {"name": "German edition"},
        "steps": [{"step": f"micro step {i}", "owner": "ai"} for i in range(9)],
    }]}
    plan = ap.parse_plan(payload)
    assert any("too detailed" in w for w in plan.warnings)
    assert plan.malformed_actions == plan.actions


def test_missing_product_and_steps_are_reported() -> None:
    plan = ap.parse_plan({"actions": [{"id": "A1", "title": "Do a thing"}]})
    joined = " ".join(plan.warnings)
    assert "no product named" in joined
    assert "no steps" in joined


def test_category_product_names_are_rejected() -> None:
    plan = ap.parse_plan({"actions": [{
        "id": "A1", "title": "Make things", "product": {"name": "files"},
        "steps": [{"step": "a", "owner": "ai"}, {"step": "b", "owner": "ai"}],
    }]})
    assert any("category, not a deliverable" in w for w in plan.warnings)


def test_product_collapsed_to_a_bare_string_still_parses() -> None:
    plan = ap.parse_plan({"actions": [{
        "id": "A1", "title": "Translate the book",
        "product": "German edition of the manuscript",
        "steps": ["Translate it", "Have it reviewed"],
    }]})
    action = plan.actions[0]
    assert action.product.name == "German edition of the manuscript"
    assert [s.step for s in action.steps] == ["Translate it", "Have it reviewed"]
    assert action.steps[0].owner == "ai", "owner defaults to ai when unstated"


def test_terac_counts_and_timelines_are_clamped_to_what_terac_accepts() -> None:
    # Terac rejects timelineHours outside 72..720 and counts outside 1..999,
    # so a plan promising "24 hours" must never reach the API.
    opportunity = ap.TeracOpportunity.from_json({
        "expert_role": "editor", "expert_count": 5000, "timeline_hours": 24,
    })
    assert opportunity.expert_count == ap.MAX_EXPERTS
    assert opportunity.timeline_hours == ap.MIN_TIMELINE_HOURS

    loose = ap.TeracOpportunity.from_json({"expert_count": "40", "timeline_hours": 120.0})
    assert loose.expert_count == 40 and loose.timeline_hours == 120

    missing = ap.TeracOpportunity.from_json({})
    assert missing.expert_count == 1 and missing.timeline_hours == ap.MIN_TIMELINE_HOURS


def test_opportunity_briefs_are_complete_enough_to_post() -> None:
    opportunity = ap.TeracOpportunity.from_json({
        "expert_role": "Native German literary editor",
        "opportunity_description": "Review the translated manuscript.",
        "inputs_provided": ["German manuscript", "English source"],
        "expected_deliverables": ["Revised manuscript"],
        "acceptance_criteria": ["Tone preserved"],
        "language_requirements": ["German (native)"],
    })
    task = opportunity.task_brief()
    assert "Review the translated manuscript." in task
    assert "You will receive: German manuscript, English source." in task
    assert "Deliver: Revised manuscript." in task
    assert "Accepted when: Tone preserved." in task
    # no panel_description given, so it is synthesised from role + languages
    assert "Native German literary editor" in opportunity.panel_brief()
    assert "German (native)" in opportunity.panel_brief()


def test_a_panel_sized_review_step_is_flagged_as_costly() -> None:
    plan = ap.parse_plan({"actions": [{
        "id": "A1", "title": "Review the translation",
        "execution_type": "AI_WITH_EXPERT_REVIEW",
        "product": {"name": "Reviewed manuscript"},
        "steps": [{"step": "a", "owner": "expert"}, {"step": "b", "owner": "ai"}],
        "terac_opportunity": {"expert_role": "editor", "panel_description": "editors",
                              "expert_count": 40, "timeline_hours": 120},
    }]})
    assert any("multiplies cost" in w for w in plan.warnings)


def test_human_action_without_an_opportunity_is_flagged() -> None:
    payload = {
        "actions": [{
            "id": "A1", "title": "Vague human task", "execution_type": "TERAC_EXPERT",
            "deliverables": ["something"], "terac_opportunity": None,
        }]
    }
    plan = ap.parse_plan(payload)
    assert any("cannot be posted" in w for w in plan.warnings)


def test_scalar_where_a_list_belongs_is_accepted() -> None:
    payload = {"actions": [{"id": "A1", "title": "t", "product": {"name": "A thing"},
                            "steps": [{"step": "a", "owner": "ai"},
                                      {"step": "b", "owner": "ai"}],
                            "depends_on": [], "inputs": "manuscript",
                            "acceptance_criteria": "it works"}]}
    plan = ap.parse_plan(payload)
    assert plan.actions[0].inputs == ["manuscript"]
    assert plan.actions[0].acceptance_criteria == ["it works"]


def test_empty_plan_is_an_error() -> None:
    for payload in ({"actions": []}, {"actions": "nope"}, {}):
        try:
            ap.parse_plan(payload)
        except PioneerError:
            continue
        raise AssertionError(f"{payload} should have raised")


# ── JSON recovery (Pioneer has no structured-output mode) ─────────────
def test_json_survives_fences_and_surrounding_prose() -> None:
    obj = '{"actions": [{"id": "A1", "title": "x"}]}'
    for text in (
        obj,
        f"```json\n{obj}\n```",
        f"Here is your plan:\n\n{obj}\n\nLet me know if you need changes.",
        f"```\n{obj}\n```",
    ):
        assert parse_json_response(text)["actions"][0]["id"] == "A1"


def test_braces_inside_strings_do_not_break_extraction() -> None:
    text = 'Plan: {"actions": [{"id": "A1", "title": "Use {curly} braces \\" here"}]}  done'
    assert parse_json_response(text)["actions"][0]["title"] == 'Use {curly} braces " here'


def test_unparseable_output_raises() -> None:
    for text in ("", "   ", "I cannot help with that."):
        try:
            parse_json_response(text)
        except PioneerError:
            continue
        raise AssertionError(f"{text!r} should have raised")


# ── end to end, against the stub ──────────────────────────────────────
def test_create_action_plan_sends_the_prompt_and_returns_a_plan() -> None:
    stub = StubClient(VALID_PLAN)
    request = ap.request_from_frontend(
        ctx_text=content.SAMPLE_CTX, services={"translate", "publish"}
    )
    plan = ap.create_action_plan(request, client=stub)  # type: ignore[arg-type]

    assert "Bookit Publishing Action Planner" in stub.system
    assert "AI_WITH_EXPERT_REVIEW" in stub.system
    assert '"target_languages"' in stub.user and "German" in stub.user
    assert plan.route.model == "stub-model"
    assert len(plan.actions) == 3


def test_no_services_selected_is_rejected_before_spending_a_call() -> None:
    request = ap.PlanRequest(author_context="hello", selected_services=[])
    try:
        ap.create_action_plan(request, client=StubClient(VALID_PLAN))  # type: ignore[arg-type]
    except ValueError:
        return
    raise AssertionError("empty service selection should raise")


# ── retry behaviour ───────────────────────────────────────────────────
class FakeAPI:
    """Minimal stand-in for the OpenAI client, scripted response by response."""

    def __init__(self, script: list[tuple[str, str]]) -> None:
        self.script = script
        self.calls: list[dict] = []
        self.chat = type("chat", (), {"completions": self})()

    def create(self, **kwargs):  # noqa: ANN003, ANN201
        self.calls.append(kwargs)
        content_text, finish_reason = self.script[len(self.calls) - 1]
        usage = type("u", (), {"prompt_tokens": 100, "completion_tokens": 200})()
        message = type("m", (), {"content": content_text})()
        choice = type("c", (), {"message": message, "finish_reason": finish_reason})()
        return type("r", (), {
            "choices": [choice], "usage": usage, "model": "fake", "model_extra": {},
        })()


def _client_with(script: list[tuple[str, str]]) -> tuple[PioneerClient, FakeAPI]:
    client = PioneerClient(api_key="test-key")
    fake = FakeAPI(script)
    client._client = fake  # noqa: SLF001 - deliberate injection for the test
    return client, fake


def test_truncated_json_retries_with_a_doubled_budget() -> None:
    # Re-asking a truncated model to "fix its JSON" truncates again at the same
    # place; only a bigger budget helps.
    good = '{"actions": [{"id": "A1", "title": "ok"}]}'
    client, fake = _client_with([('{"actions": [{"id": "A1"', "length"), (good, "stop")])
    payload, route = client.complete_json("sys", "usr", max_tokens=1000)

    assert payload["actions"][0]["id"] == "A1"
    assert [c["max_tokens"] for c in fake.calls] == [1000, 2000], "budget must double"
    assert route.attempts == 2
    # the retry re-sends the original request, it does not append a repair turn
    assert len(fake.calls[1]["messages"]) == 2


def test_malformed_json_retries_with_a_repair_turn_at_the_same_budget() -> None:
    good = '{"actions": [{"id": "A1", "title": "ok"}]}'
    client, fake = _client_with([("Sure! Here you go: not json", "stop"), (good, "stop")])
    payload, _ = client.complete_json("sys", "usr", max_tokens=1000)

    assert payload["actions"][0]["id"] == "A1"
    assert [c["max_tokens"] for c in fake.calls] == [1000, 1000], "budget must not grow"
    assert len(fake.calls[1]["messages"]) == 4, "repair turn appended"


def test_persistent_truncation_reports_the_token_limit_not_bad_json() -> None:
    client, _ = _client_with([('{"actions": [', "length")] * 3)
    try:
        client.complete_json("sys", "usr", max_tokens=1000, attempts=3)
    except PioneerError as exc:
        assert "token limit" in str(exc), f"unhelpful error: {exc}"
        return
    raise AssertionError("should have raised")


def test_route_reports_savings_against_the_baseline() -> None:
    route = Route(
        model="zai-org/GLM-5.1",
        baseline_model="gpt-5.5",
        rate_diff_per_mtok={"input": 3.7, "output": 25.7},
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
    )
    assert route.saved_usd == 29.4
    assert "routed from gpt-5.5" in route.label


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\n{len(tests)} passed")
