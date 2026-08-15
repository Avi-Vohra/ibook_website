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
            "artifact": {
                "name": "glossary-en-de.csv",
                "format": "CSV",
                "description": "Named entities with one locked German rendering each",
            },
            "deliverables": ["glossary-en-de.csv"],
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
            "artifact": {
                "name": "the-salt-road-de-edited.docx",
                "format": "DOCX",
                "description": "Native-edited German manuscript",
            },
            "deliverables": ["the-salt-road-de-edited.docx"],
            "acceptance_criteria": ["No glossary violations"],
            "estimated_scope": "8 hours",
            "terac_opportunity": {
                "expert_role": "Native German literary editor",
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
            "artifact": {
                "name": "the-salt-road-de.docx",
                "format": "DOCX",
                "description": "Glossary-locked German translation",
            },
            "deliverables": ["the-salt-road-de.docx"],
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
                "deliverables": [],                 # missing deliverable
            },
            {"id": "A1", "title": "Duplicate id", "deliverables": ["x"]},
        ]
    }
    plan = ap.parse_plan(payload)
    first = plan.actions[0]
    assert first.execution_type == "AI_AUTOMATED"
    assert first.priority == "recommended"
    assert first.depends_on == []
    assert len({a.id for a in plan.actions}) == 2, "duplicate ids must be made unique"
    joined = " ".join(plan.warnings)
    assert "A99" in joined and "self-dependency" in joined and "no deliverable" in joined


# ── atomicity: one action, one product ────────────────────────────────
def test_bundled_titles_are_detected() -> None:
    bundled = [
        "Format English ebook (EPUB) and paperback (print PDF)",
        "Generate German metadata and book description",
        "Parse manuscript and run structural QA",
        "Publish English edition (ebook + paperback) to KDP",
        "Translate, edit, and format the German edition",
        "Produce cover JPG & paperback wrap PDF",
        "Build glossary then translate manuscript",
        "Create EPUB/PDF bundle",
    ]
    for title in bundled:
        assert ap.bundled_title(title), f"should have been flagged: {title}"

    atomic = [
        "Extract clean manuscript text",
        "Build EN-DE terminology glossary",
        "Produce German reflowable EPUB",
        "Write German book description",
        "Report manuscript structural issues",
        "Assemble German KDP keyword set",
    ]
    for title in atomic:
        assert not ap.bundled_title(title), f"false positive: {title}"


def test_author_decisions_may_batch_questions_onto_one_record() -> None:
    # Four questions on one decision sheet is one artifact — and four separate
    # interruptions of the author would be worse, not more atomic.
    payload = {
        "actions": [{
            "id": "A1",
            "title": "Confirm pricing, pen name and German tone decisions",
            "execution_type": "AUTHOR_DECISION",
            "artifact": {"name": "author-decisions.md", "format": "decision record"},
            "deliverables": ["author-decisions.md with all four answers"],
        }]
    }
    plan = ap.parse_plan(payload)
    assert not plan.warnings, plan.warnings
    assert plan.actions[0].is_atomic
    # the same title on a production action is still flagged
    payload["actions"][0]["execution_type"] = "AI_AUTOMATED"
    assert any("bundles" in w for w in ap.parse_plan(payload).warnings)


def test_non_atomic_actions_are_flagged_with_the_offending_join() -> None:
    payload = {
        "actions": [{
            "id": "A1",
            "title": "Format English ebook (EPUB) and paperback (print PDF)",
            "artifact": {"name": "files", "format": "mixed"},
            "deliverables": ["EPUB file", "Print interior PDF", "Page count"],
        }]
    }
    plan = ap.parse_plan(payload)
    joined = " ".join(plan.warnings)
    assert "bundles more than one artifact" in joined
    assert "3 deliverables" in joined
    assert "is a category, not a file" in joined
    assert plan.non_atomic_actions == plan.actions
    assert not plan.actions[0].is_atomic


def test_an_atomic_action_produces_no_warnings() -> None:
    payload = {
        "actions": [{
            "id": "A1",
            "title": "Build EN-DE terminology glossary",
            "execution_type": "AI_AUTOMATED",
            "priority": "critical",
            "artifact": {
                "name": "glossary-en-de.csv",
                "format": "CSV",
                "description": "Every proper noun with its locked German rendering",
            },
            "deliverables": ["glossary-en-de.csv with one German rendering per term"],
        }]
    }
    plan = ap.parse_plan(payload)
    assert not plan.warnings, plan.warnings
    assert plan.actions[0].is_atomic
    assert plan.artifacts[0].name == "glossary-en-de.csv"
    assert not plan.non_atomic_actions


def test_artifact_collapsed_to_a_bare_string_still_parses() -> None:
    payload = {"actions": [{"id": "A1", "title": "Produce German EPUB",
                            "artifact": "the-salt-road-de.epub",
                            "deliverables": ["the German EPUB"]}]}
    plan = ap.parse_plan(payload)
    assert plan.actions[0].artifact.name == "the-salt-road-de.epub"
    assert plan.actions[0].is_atomic


def test_missing_artifact_is_reported() -> None:
    payload = {"actions": [{"id": "A1", "title": "Do a thing", "deliverables": ["something"]}]}
    plan = ap.parse_plan(payload)
    assert any("no artifact named" in w for w in plan.warnings)


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
    payload = {"actions": [{"id": "A1", "title": "t", "deliverables": "one file",
                            "depends_on": [], "inputs": "manuscript"}]}
    plan = ap.parse_plan(payload)
    assert plan.actions[0].deliverables == ["one file"]
    assert plan.actions[0].inputs == ["manuscript"]


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
