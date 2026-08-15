"""Action Item creation.

Takes what the author gave the frontend — manuscript, selected services, their
own description of the book — folds it into the Publishing Action Planner
prompt, sends it through Pioneer, and returns a typed, validated action plan
where every item is routed to AI, a Terac expert, or the author.

    request = request_from_frontend(
        ctx_text=st.session_state.ctx_input,
        services=st.session_state.services,
        book_file=current_file(),
    )
    plan = create_action_plan(request)

The model decides *what* the actions are. This module decides what a
well-formed plan is: ids unique, dependencies real and acyclic, execution
types known, and a Terac opportunity attached to every action that claims to
need a human.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from bookit import planner
from bookit.pioneer import PioneerClient, PioneerError, Route

EXECUTION_TYPES = ("AI_AUTOMATED", "TERAC_EXPERT", "AI_WITH_EXPERT_REVIEW", "AUTHOR_DECISION")
PRIORITIES = ("critical", "recommended", "optional")

# Execution types whose whole point is a human, so an opportunity must exist.
NEEDS_OPPORTUNITY = ("TERAC_EXPERT", "AI_WITH_EXPERT_REVIEW")

# The frontend offers three bundled services; the prompt speaks in finer
# categories. Widening here rather than in the UI keeps the checkboxes simple.
SERVICE_VOCABULARY = {
    "publish": ["publishing", "formatting", "cover design"],
    "translate": ["translation"],
    "market": ["marketing"],
}

# Enough manuscript for the model to judge genre, register and length without
# paying to send a whole novel. Sampled head/middle/tail: openings are
# unrepresentative on their own.
EXCERPT_WORDS = 4000

# Artifact "names" that name nothing — a category standing in for a file.
VAGUE_ARTIFACT_NAMES = frozenset({
    "files", "assets", "documents", "deliverables", "output", "outputs", "artifact",
    "artifacts", "report", "the book", "the edition", "manuscript", "metadata", "package",
})

# A title joining two things is the reliable tell for a non-atomic action:
# "Format ebook *and* paperback" is two files pretending to be one step.
_BUNDLE_PATTERN = re.compile(
    r"\b(?:and|plus|then|as well as)\b|[&+/]|,\s*(?=\w+\s+(?:and|the|a)\b)",
    re.IGNORECASE,
)

# Parenthetical format lists — "(EPUB + print PDF)", "(ebook and paperback)" —
# hide bundling from a naive title scan.
_FORMAT_LIST = re.compile(r"\(([^)]*(?:\band\b|[&+,/])[^)]*)\)", re.IGNORECASE)


def bundled_title(title: str) -> str | None:
    """Return the joining phrase if this title names more than one thing.

    Deliberately conservative: it only fires on explicit joiners, so a title
    like "Report manuscript structural issues" passes untouched.
    """
    if inner := _FORMAT_LIST.search(title):
        return inner.group(1).strip()
    if match := _BUNDLE_PATTERN.search(title):
        return match.group(0).strip()
    return None


SYSTEM_PROMPT = """\
# Role

You are the Bookit Publishing Action Planner, an agent responsible for turning an author's book, \
selected services, publishing goals, and contextual information into a concrete execution plan.

Your job is not to perform the work yet. Your job is to determine exactly what should happen next.

Bookit combines AI automation with human experts through Terac. Some tasks can be completed \
autonomously by AI; others require or benefit significantly from human expertise. Human tasks \
should be converted into clearly scoped Terac opportunities.

# Inputs

You will receive a JSON object containing:

- `book_content`: extracted text and metadata from the uploaded book
- `book_file`: information about the uploaded PDF/document
- `selected_services`: services selected by the author (translation, publishing, formatting, \
cover design, marketing, other requested services)
- `author_context`: information supplied by the author
- `publishing_requirements`: target platform, country, language, format, deadlines, etc.
- `target_languages`: languages requested for translation, if applicable
- `budget`: optional
- `deadline`: optional
- `additional_requests`: optional

Fields may be null or empty. A null field is missing information, not a reason to invent one.

# Objective

Create the smallest complete set of actionable steps required to move this specific book from its \
current state to the author's desired outcome.

Do not generate generic publishing advice.

Every action must:

- Be relevant to this specific book and the author's selected services.
- Have a clear deliverable.
- Explain why it is needed.
- Identify dependencies.
- Determine whether it should be AI_AUTOMATED, TERAC_EXPERT, AI_WITH_EXPERT_REVIEW, or \
AUTHOR_DECISION.
- Be ordered logically so the workflow can be executed later.

# Planning Principles

First analyze the book and author's goals. Identify: genre; subject; approximate length; intended \
audience; current language; desired languages; current publication status; target publishing \
platforms; formatting requirements; visual/cover requirements; marketing requirements; legal, \
cultural, technical, or subject-matter sensitivities; and missing information required before \
execution.

Only create actions that materially contribute to the selected goal. If the author only requests \
publishing and the manuscript is already clean and formatted, do not create unnecessary \
translation or editing tasks.

If the author requests a translation, that is **one** action whose product is the finished \
translated manuscript. Glossary creation, the translation itself, native editorial review, and \
source-vs-translation QA are steps inside it, not actions of their own.

If the author requests marketing, make the action specific to the actual book, audience, genre \
and launch strategy rather than a generic task such as "market the book".

# AI vs. Terac Decision

Prefer AI automation when the work is deterministic, repeatable, or readily quality-checked: \
document parsing, metadata extraction, initial translation, formatting conversion, keyword \
generation, market research, draft descriptions, publishing checklists, initial cover concepts.

Create a TERAC_EXPERT opportunity when meaningful human judgment, professional accountability, \
native-language fluency, specialized expertise, or subjective creative skill is important: native \
literary translation review, professional copyediting, culturally sensitive localization, \
specialized subject-matter verification, final cover design refinement, publishing-platform \
specialist review, legal or rights-related review, high-value marketing strategy or outreach.

Use AI_WITH_EXPERT_REVIEW when AI can perform most of the work economically but a human should \
validate or refine the final result.

Do not send work to Terac simply because a human could do it. Human expertise should be used \
strategically where it creates significant additional value.

# Terac Opportunity Requirements

For every action involving a Terac expert, generate an opportunity that could be sent directly to \
Terac. The opportunity must clearly state: expert type required; task; relevant book context; \
required language or specialization; inputs the expert will receive; exact expected deliverable; \
acceptance criteria; estimated scope; dependencies; priority.

This applies to `TERAC_EXPERT` and `AI_WITH_EXPERT_REVIEW` alike — both put a human in the loop, \
and an action that names no expert cannot be posted. For `AI_WITH_EXPERT_REVIEW`, scope the \
opportunity to the review step only: what the expert receives from the AI, what they are checking \
for, and what they hand back. If an action genuinely needs no human, its type is `AI_AUTOMATED` \
and `terac_opportunity` is null. Never emit an `AI_WITH_EXPERT_REVIEW` action with a null \
`terac_opportunity`.

Avoid vague opportunities such as "Review the book." Instead produce something like: "Native \
German literary editor needed to review the AI-translated 12,000-word German manuscript against \
the English source. Correct unnatural phrasing, mistranslations, tone inconsistencies, and \
glossary violations while preserving the author's conversational style. Deliver a revised German \
manuscript and a short list of substantive translation issues."

# Action Granularity

Every action is atomic: it produces exactly **one** artifact. An artifact is something that did \
not exist before the action ran and that can be opened, read, or shipped on its own — a file, an \
asset, a document, a decision record.

Rules:

- One action, one artifact. If finishing an action would produce two files, it is two actions.
- The title is an imperative verb followed by the artifact it produces. A title containing "and", \
"&", "+", "/", or a comma joining two verbs is always a signal to split the action.
- Split by format, by language, and by edition. An EPUB and a print-ready PDF are two artifacts, \
so they are two actions. An English blurb and a German blurb are two artifacts.
- `deliverables` contains exactly one entry, and it describes that same artifact.
- `artifact.name` is a concrete filename or asset name — `glossary-en-de.csv`, \
`the-salt-road-de.epub` — never a category like "files", "assets", or "the German edition".
- If you cannot name the artifact, the action is still too large. Break it down until every piece \
has a name.
- An `AUTHOR_DECISION` action still produces an artifact: a decision record holding the questions \
asked and the answers given.
- Smallest complete set does not mean fewest actions. Never merge two artifacts into one action \
to shorten the plan.

Bad — each bundles more than one artifact:

- "Translate, edit, format, publish, and market the German edition."
- "Format English ebook (EPUB) and paperback (print PDF)" — two files.
- "Generate German metadata and book description" — two files.
- "Publish English edition to KDP" — bundles upload, QA, and the live listing; name the artifact.
- "Parse manuscript and run structural QA" — the clean text and the QA report are two artifacts.

Good — one named artifact each:

- "Extract clean manuscript text" → `manuscript-clean.md`
- "Report manuscript structural issues" → `structure-qa.md`
- "Build EN-DE terminology glossary" → `glossary-en-de.csv`
- "Translate manuscript into German" → `the-salt-road-de.docx`
- "Produce German reflowable EPUB" → `the-salt-road-de.epub`
- "Produce German print interior PDF" → `the-salt-road-de-interior.pdf`
- "Write German book description" → `description-de.html`
- "Assemble German KDP keyword set" → `keywords-de.csv`

# Dependencies

Explicitly represent dependencies in `depends_on` using the ids of earlier actions. German \
editorial review cannot start until the German translation is complete. Cover resizing cannot \
start until the target print format and page count are known.

# Missing Information

If essential information is missing, create an AUTHOR_DECISION action instead of making \
unsupported assumptions — for example, "Confirm whether the German edition should use formal or \
informal second-person language."

Do not block the entire plan because minor information is missing. Continue generating actions \
that can proceed independently.

# Prioritization

Assign each action a priority:

- `critical` — the requested outcome cannot reasonably be completed without it.
- `recommended` — it materially improves quality or success.
- `optional` — it is an enhancement.

# Output

Return structured JSON only. No prose, no explanation, no markdown code fences. Your entire \
response must be a single JSON object matching this schema:

{
  "book_summary": {
    "title": "",
    "genre": "",
    "current_language": "",
    "target_audience": "",
    "author_goal": "",
    "selected_services": []
  },
  "plan_summary": "",
  "actions": [
    {
      "id": "A1",
      "title": "",
      "description": "",
      "reason": "",
      "execution_type": "AI_AUTOMATED | TERAC_EXPERT | AI_WITH_EXPERT_REVIEW | AUTHOR_DECISION",
      "priority": "critical | recommended | optional",
      "depends_on": [],
      "inputs": [],
      "artifact": {
        "name": "concrete filename or asset name, e.g. glossary-en-de.csv",
        "format": "e.g. CSV, EPUB 3, print-ready PDF, HTML, decision record",
        "description": "what this one artifact contains"
      },
      "deliverables": ["exactly one entry, describing the artifact above"],
      "acceptance_criteria": [],
      "estimated_scope": "",
      "terac_opportunity": null
    }
  ]
}

For actions requiring Terac, replace `"terac_opportunity": null` with:

{
  "expert_role": "",
  "opportunity_title": "",
  "opportunity_description": "",
  "required_skills": [],
  "language_requirements": [],
  "inputs_provided": [],
  "expected_deliverables": [],
  "acceptance_criteria": [],
  "estimated_scope": "",
  "priority": ""
}

# Final Validation

Before returning the plan, verify that: every action corresponds to the author's actual goals; \
actions are ordered correctly; there are no redundant actions; AI work is kept with AI where \
appropriate; Terac opportunities contain enough context for an expert to understand and accept \
the assignment without needing the entire planning conversation; and the complete sequence, if \
executed successfully, would produce the author's requested publishing outcome.

Then re-read every action title one more time and confirm each one names a single artifact. If a \
title contains "and", "&", "+", "/", or two verbs, split that action before returning. Confirm \
every action has an `artifact.name` that reads like a filename, and exactly one entry in \
`deliverables`.

Action ids must be unique and of the form A1, A2, A3… `depends_on` must reference only ids that \
exist in this plan."""


# ── inputs ────────────────────────────────────────────────────────────
@dataclass
class BookFile:
    """What the frontend knows about the upload."""

    name: str
    size_bytes: int | None = None
    detail: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"filename": self.name}
        if self.size_bytes is not None:
            payload["size_mb"] = round(self.size_bytes / 1024 / 1024, 2)
            payload["format"] = self.name.rsplit(".", 1)[-1].lower() if "." in self.name else None
        if self.detail:
            payload["extraction_note"] = self.detail
        return payload


@dataclass
class PlanRequest:
    """The prompt's Inputs section, as data."""

    author_context: str = ""
    selected_services: list[str] = field(default_factory=list)
    book_content: str | None = None
    book_file: BookFile | None = None
    publishing_requirements: dict[str, Any] = field(default_factory=dict)
    target_languages: list[str] = field(default_factory=list)
    budget: int | None = None
    deadline: str | None = None
    additional_requests: str | None = None

    def to_payload(self) -> dict[str, Any]:
        """The user message: every prompt input, nulls included.

        Absent fields are sent as null rather than omitted — the prompt treats a
        null as a trigger for an AUTHOR_DECISION action, and it can only do
        that if it can see which fields are missing.
        """
        return {
            "book_content": excerpt(self.book_content) if self.book_content else None,
            "book_file": self.book_file.to_payload() if self.book_file else None,
            "selected_services": self.selected_services,
            "author_context": self.author_context or None,
            "publishing_requirements": self.publishing_requirements or None,
            "target_languages": self.target_languages,
            "budget": self.budget,
            "deadline": self.deadline,
            "additional_requests": self.additional_requests,
        }


def excerpt(text: str, max_words: int = EXCERPT_WORDS) -> str:
    """Head/middle/tail sample of a manuscript, with the cuts marked.

    An opening chapter alone misleads — it is the most polished part of most
    manuscripts and says nothing about whether chapter 30 is finished.
    """
    words = text.split()
    if len(words) <= max_words:
        return text
    third = max_words // 3
    middle = (len(words) - third) // 2
    return (
        " ".join(words[:third])
        + f"\n\n[… {len(words) - max_words:,} words omitted …]\n\n"
        + " ".join(words[middle:middle + third])
        + f"\n\n[… omitted …]\n\n"
        + " ".join(words[-third:])
    )


def request_from_frontend(
    *,
    ctx_text: str,
    services: set[str] | list[str],
    book_file: dict[str, Any] | BookFile | None = None,
    book_content: str | None = None,
    additional_requests: str | None = None,
) -> PlanRequest:
    """Fold the Streamlit session state into a PlanRequest.

    The existing regex reader already pulls language, platform, budget and
    length out of the author's description. Those go in as structured fields
    *and* the raw text goes in whole, so the model can correct a bad regex hit
    rather than inherit it.
    """
    reading = planner.read_context(ctx_text)

    requirements: dict[str, Any] = {}
    if reading.platform:
        requirements["target_platform"] = reading.platform
    if reading.words:
        requirements["approximate_length_words"] = reading.words
    if reading.genre and reading.genre != "general":
        requirements["genre"] = reading.genre
    if reading.audience:
        requirements["target_audience"] = reading.audience.strip()
    if reading.audiobook:
        requirements["audiobook_interest"] = True
    if reading.series:
        requirements["part_of_series"] = True
    if reading.debut:
        requirements["author_status"] = "debut author, no publishing contacts"
    requirements["formats"] = ["ebook", "paperback"] if reading.platform else []

    if isinstance(book_file, dict):
        book_file = BookFile(
            name=book_file.get("name", "manuscript"),
            size_bytes=book_file.get("size"),
            detail=book_file.get("meta") or book_file.get("detail"),
        )

    # Canonical order first, then anything unrecognised: `services` is a set, and
    # an unstable order would send a different prompt for identical input.
    keys = [k for k in SERVICE_VOCABULARY if k in services]
    keys += sorted(k for k in services if k not in SERVICE_VOCABULARY)
    selected: list[str] = []
    for key in keys:
        for name in SERVICE_VOCABULARY.get(key, [key]):
            if name not in selected:
                selected.append(name)

    return PlanRequest(
        author_context=ctx_text.strip(),
        selected_services=selected,
        book_content=book_content,
        book_file=book_file,
        publishing_requirements=requirements,
        target_languages=list(reading.langs),
        budget=reading.budget,
        deadline="author asked to launch soon" if reading.deadline else None,
        additional_requests=additional_requests,
    )


# ── outputs ───────────────────────────────────────────────────────────
@dataclass
class TeracOpportunity:
    """A job posting, complete enough for an expert to accept without context."""

    expert_role: str = ""
    opportunity_title: str = ""
    opportunity_description: str = ""
    required_skills: list[str] = field(default_factory=list)
    language_requirements: list[str] = field(default_factory=list)
    inputs_provided: list[str] = field(default_factory=list)
    expected_deliverables: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    estimated_scope: str = ""
    priority: str = ""

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> TeracOpportunity:
        return cls(
            expert_role=_text(raw.get("expert_role")),
            opportunity_title=_text(raw.get("opportunity_title")),
            opportunity_description=_text(raw.get("opportunity_description")),
            required_skills=_str_list(raw.get("required_skills")),
            language_requirements=_str_list(raw.get("language_requirements")),
            inputs_provided=_str_list(raw.get("inputs_provided")),
            expected_deliverables=_str_list(raw.get("expected_deliverables")),
            acceptance_criteria=_str_list(raw.get("acceptance_criteria")),
            estimated_scope=_text(raw.get("estimated_scope")),
            priority=_text(raw.get("priority")),
        )


@dataclass
class Artifact:
    """The one thing an action produces.

    Downstream production agents key off ``name``, so it has to read like a
    filename rather than a category.
    """

    name: str = ""
    format: str = ""
    description: str = ""

    @property
    def is_named(self) -> bool:
        """Is this a specific artifact, or a category wearing a name?"""
        if not self.name:
            return False
        return self.name.strip().lower() not in VAGUE_ARTIFACT_NAMES

    @classmethod
    def from_json(cls, raw: Any) -> Artifact:
        if isinstance(raw, str):  # models sometimes collapse it to a bare name
            return cls(name=raw.strip())
        if not isinstance(raw, dict):
            return cls()
        return cls(
            name=_text(raw.get("name")),
            format=_text(raw.get("format")),
            description=_text(raw.get("description")),
        )


@dataclass
class Action:
    """One action item, producing exactly one artifact."""

    id: str
    title: str
    description: str = ""
    reason: str = ""
    execution_type: str = "AI_AUTOMATED"
    priority: str = "recommended"
    depends_on: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    artifact: Artifact = field(default_factory=Artifact)
    deliverables: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    estimated_scope: str = ""
    terac_opportunity: TeracOpportunity | None = None

    @property
    def is_atomic(self) -> bool:
        """One artifact, one deliverable, and a title that names a single thing.

        An AUTHOR_DECISION is exempt from the title check: several questions
        answered on one decision record is still one artifact, and splitting
        them would mean four separate interruptions of the author.
        """
        return (
            self.artifact.is_named
            and len(self.deliverables) <= 1
            and (self.needs_author or not bundled_title(self.title))
        )

    @property
    def is_human(self) -> bool:
        """Does a real person touch this? Drives the Terac badge in the UI."""
        return self.execution_type in NEEDS_OPPORTUNITY

    @property
    def needs_author(self) -> bool:
        return self.execution_type == "AUTHOR_DECISION"

    @property
    def owner(self) -> str:
        """Maps onto the existing UI vocabulary of agent / human."""
        if self.needs_author:
            return "author"
        return "human" if self.is_human else "agent"

    @classmethod
    def from_json(cls, raw: dict[str, Any], index: int) -> Action:
        opportunity = raw.get("terac_opportunity")
        execution = _text(raw.get("execution_type")).upper().replace(" ", "_")
        priority = _text(raw.get("priority")).lower()
        return cls(
            id=_text(raw.get("id")) or f"A{index}",
            title=_text(raw.get("title")) or "Untitled action",
            description=_text(raw.get("description")),
            reason=_text(raw.get("reason")),
            execution_type=execution if execution in EXECUTION_TYPES else "AI_AUTOMATED",
            priority=priority if priority in PRIORITIES else "recommended",
            depends_on=_str_list(raw.get("depends_on")),
            inputs=_str_list(raw.get("inputs")),
            artifact=Artifact.from_json(raw.get("artifact")),
            deliverables=_str_list(raw.get("deliverables")),
            acceptance_criteria=_str_list(raw.get("acceptance_criteria")),
            estimated_scope=_text(raw.get("estimated_scope")),
            terac_opportunity=(
                TeracOpportunity.from_json(opportunity)
                if isinstance(opportunity, dict) and opportunity
                else None
            ),
        )


@dataclass
class BookSummary:
    title: str = ""
    genre: str = ""
    current_language: str = ""
    target_audience: str = ""
    author_goal: str = ""
    selected_services: list[str] = field(default_factory=list)

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> BookSummary:
        return cls(
            title=_text(raw.get("title")),
            genre=_text(raw.get("genre")),
            current_language=_text(raw.get("current_language")),
            target_audience=_text(raw.get("target_audience")),
            author_goal=_text(raw.get("author_goal")),
            selected_services=_str_list(raw.get("selected_services")),
        )


@dataclass
class ActionPlan:
    """A validated plan, plus how Pioneer served it."""

    book_summary: BookSummary
    plan_summary: str
    actions: list[Action]
    route: Route | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def human_actions(self) -> list[Action]:
        return [a for a in self.actions if a.is_human]

    @property
    def ai_actions(self) -> list[Action]:
        return [a for a in self.actions if a.execution_type == "AI_AUTOMATED"]

    @property
    def author_decisions(self) -> list[Action]:
        return [a for a in self.actions if a.needs_author]

    @property
    def opportunities(self) -> list[TeracOpportunity]:
        """Every Terac posting in the plan, ready to hand to the Terac MCP."""
        return [a.terac_opportunity for a in self.actions if a.terac_opportunity]

    @property
    def artifacts(self) -> list[Artifact]:
        """Everything this plan produces, in execution order."""
        return [a.artifact for a in self.actions if a.artifact.name]

    @property
    def non_atomic_actions(self) -> list[Action]:
        """Actions still bundling more than one product. Empty is the goal."""
        return [a for a in self.actions if not a.is_atomic]

    def to_json(self) -> dict[str, Any]:
        from dataclasses import asdict

        return {
            "book_summary": asdict(self.book_summary),
            "plan_summary": self.plan_summary,
            "actions": [asdict(a) for a in self.actions],
        }


# ── parsing helpers ───────────────────────────────────────────────────
def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _str_list(value: Any) -> list[str]:
    """Models return a bare string about as often as a list. Accept both."""
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [_text(v) or json.dumps(v, ensure_ascii=False) for v in value if v]
    return []


def _sort_by_dependencies(actions: list[Action]) -> list[Action]:
    """Stable topological sort, so an action never precedes what it depends on.

    Any action still unplaced after a full pass is part of a cycle; those are
    appended in their original order rather than dropped — a mis-ordered plan
    is recoverable, a silently truncated one is not.
    """
    ordered: list[Action] = []
    placed: set[str] = set()
    remaining = list(actions)
    while remaining:
        ready = [a for a in remaining if all(d in placed for d in a.depends_on)]
        if not ready:
            ordered.extend(remaining)
            break
        ordered.extend(ready)
        placed.update(a.id for a in ready)
        remaining = [a for a in remaining if a not in ready]
    return ordered


def parse_plan(payload: dict[str, Any], route: Route | None = None) -> ActionPlan:
    """Turn the model's JSON into a validated ActionPlan.

    Repairs what is safe to repair and records the rest in ``warnings``. A plan
    with a dropped bad dependency is still useful; a plan that raises on the
    first imperfect field is not.
    """
    raw_actions = payload.get("actions")
    if not isinstance(raw_actions, list) or not raw_actions:
        raise PioneerError("Model returned no actions.")

    warnings: list[str] = []
    actions: list[Action] = []
    seen: set[str] = set()

    for i, raw in enumerate(raw_actions, start=1):
        if not isinstance(raw, dict):
            warnings.append(f"Skipped action {i}: not an object.")
            continue
        action = Action.from_json(raw, i)
        if action.id in seen:  # duplicate ids would corrupt the dependency graph
            action.id = f"{action.id}_{i}"
            warnings.append(f"Duplicate action id renamed to {action.id}.")
        seen.add(action.id)
        actions.append(action)

    if not actions:
        raise PioneerError("Model returned no usable actions.")

    for action in actions:
        unknown = [d for d in action.depends_on if d not in seen]
        if unknown:
            action.depends_on = [d for d in action.depends_on if d in seen]
            warnings.append(f"{action.id}: dropped dependency on unknown {', '.join(unknown)}.")
        if action.id in action.depends_on:
            action.depends_on.remove(action.id)
            warnings.append(f"{action.id}: dropped self-dependency.")
        if action.execution_type in NEEDS_OPPORTUNITY and action.terac_opportunity is None:
            warnings.append(
                f"{action.id} ({action.execution_type}) has no Terac opportunity — "
                "it cannot be posted as-is."
            )

        # Atomicity: one action must yield exactly one nameable artifact.
        # AUTHOR_DECISION titles may legitimately join several questions that
        # land on a single decision record.
        if not action.needs_author and (joiner := bundled_title(action.title)):
            warnings.append(
                f"{action.id}: title bundles more than one artifact "
                f"(“{joiner}”) — should be split: {action.title!r}"
            )
        if len(action.deliverables) > 1:
            warnings.append(
                f"{action.id}: {len(action.deliverables)} deliverables in one action "
                f"({'; '.join(action.deliverables)}) — should be split."
            )
        elif not action.deliverables:
            warnings.append(f"{action.id}: no deliverable stated.")
        if not action.artifact.name:
            warnings.append(f"{action.id}: no artifact named.")
        elif not action.artifact.is_named:
            warnings.append(
                f"{action.id}: artifact {action.artifact.name!r} is a category, not a file."
            )

    summary = payload.get("book_summary")
    return ActionPlan(
        book_summary=BookSummary.from_json(summary if isinstance(summary, dict) else {}),
        plan_summary=_text(payload.get("plan_summary")),
        actions=_sort_by_dependencies(actions),
        route=route,
        warnings=warnings,
    )


# ── the entry point ───────────────────────────────────────────────────
def create_action_plan(
    request: PlanRequest,
    client: PioneerClient | None = None,
    *,
    temperature: float = 0.3,
) -> ActionPlan:
    """Generate the action plan for one book. Raises PioneerError on failure.

    Temperature is low on purpose: this is a routing and sequencing decision,
    and the same book twice should not produce two different plans.
    """
    if not request.selected_services:
        raise ValueError("No services selected — there is nothing to plan.")

    client = client or PioneerClient()
    user_message = (
        "Plan the publishing work for this book. Inputs:\n\n"
        + json.dumps(request.to_payload(), indent=2, ensure_ascii=False)
    )
    payload, route = client.complete_json(
        SYSTEM_PROMPT, user_message, temperature=temperature
    )
    return parse_plan(payload, route)
