"""Terac — the human labour layer.

Terac operates a verified expert panel and sells on-demand access to it. Bookit
uses it for every judgement an agent cannot make: which cover a reader would
pick up, whether a translated sentence sounds native, whether a blurb lands.

The lifecycle is a quote, then a launch, then a wait:

    POST /quotes                  → quoteId, totalCost, costPerParticipant
    POST /quotes/{id}/launch      → opportunityId
    GET  /opportunities/{id}      → status: draft|active|fulfilled|…
    GET  /opportunities/{id}/submissions

Pricing is a round trip, not a constant: you describe the task and the panel,
and Terac prices it. Nothing is charged until launch, which is why the
orchestrator always puts the author's approval between the two.

One hard constraint shapes everything downstream: ``timelineHours`` has a
minimum of **72**. Human work cannot come back inside a demo, so the pipeline
treats "launched and recruiting" as a legitimate resting state rather than an
unfinished one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

BASE_URL = "https://terac.com/api/external/v2"

MIN_TIMELINE_HOURS, MAX_TIMELINE_HOURS = 72, 720
MIN_SUBMISSIONS, MAX_SUBMISSIONS = 1, 999

# Terac's own vocabulary, kept verbatim so status checks read like the API docs.
LIVE_STATUSES = ("active", "draft")
DONE_STATUSES = ("fulfilled", "completed")
STOPPED_STATUSES = ("stopped", "paused")


class TeracError(RuntimeError):
    """Terac refused a request, or could not be reached."""


def api_key(explicit: str | None = None) -> str:
    """Explicit, then environment, then .streamlit/secrets.toml."""
    from bookit.secrets import MissingKey, require_secret

    try:
        return require_secret("TERAC_API_KEY", explicit)
    except MissingKey as exc:
        raise TeracError(str(exc)) from exc


@dataclass(frozen=True)
class Quote:
    """What Terac says a job will cost, before anything is charged."""

    quote_id: str
    total_cost: float
    cost_per_participant: float
    timeline_hours: int
    submission_count: int
    expires_at: str = ""
    reasoning: str = ""

    @property
    def label(self) -> str:
        return (
            f"${self.total_cost:.2f} for {self.submission_count} "
            f"({'expert' if self.submission_count == 1 else 'experts'}) "
            f"@ ${self.cost_per_participant:.2f}, {self.timeline_hours}h"
        )

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> Quote:
        return cls(
            quote_id=str(raw.get("quoteId") or raw.get("id") or ""),
            total_cost=_number(raw.get("totalCost") or raw.get("price")),
            cost_per_participant=_number(raw.get("costPerParticipant")),
            timeline_hours=int(_number(raw.get("timelineHours"))),
            submission_count=int(_number(raw.get("submissionCount"))),
            expires_at=str(raw.get("expiresAt") or ""),
            reasoning=str(raw.get("reasoning") or ""),
        )


@dataclass(frozen=True)
class Opportunity:
    """A launched job, live on the Terac panel."""

    opportunity_id: str
    status: str = ""
    participants: int = 0
    dashboard_url: str = ""

    @property
    def is_live(self) -> bool:
        return self.status in LIVE_STATUSES

    @property
    def is_done(self) -> bool:
        return self.status in DONE_STATUSES


@dataclass(frozen=True)
class Submission:
    """One expert's response."""

    submission_id: str
    status: str = ""
    participant_id: str = ""
    screening_outcome: str | None = None
    answers: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return self.status in ("awaiting_review", "approved")


def _number(value: Any) -> float:
    """Terac returns prices as strings on some endpoints and numbers on others."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


class TeracClient:
    """The real API. Every call that spends money is named so you can see it."""

    def __init__(
        self,
        key: str | None = None,
        *,
        base_url: str = BASE_URL,
        timeout: float = 60.0,
        project_id: str | None = None,
    ) -> None:
        import requests  # late import: keeps the module importable without it

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._project_id = project_id
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {api_key(key)}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

    # ── plumbing ──────────────────────────────────────────────────────
    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._session.request(
                method, f"{self.base_url}{path}", timeout=self.timeout, **kwargs
            )
        except Exception as exc:  # noqa: BLE001 - network layer
            raise TeracError(f"Terac {method} {path} failed: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text[:400]
            try:
                body = response.json()
                detail = body.get("message") or detail
                if issues := body.get("issues"):
                    detail += " — " + "; ".join(i.get("message", "") for i in issues)
            except Exception:  # noqa: BLE001 - non-JSON error body
                pass
            raise TeracError(f"Terac {method} {path} → {response.status_code}: {detail}")

        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise TeracError(f"Terac {method} {path} returned non-JSON.") from exc

    # ── reads ─────────────────────────────────────────────────────────
    def project_id(self) -> str:
        """The project new opportunities land in. Cached after first lookup."""
        if self._project_id:
            return self._project_id
        projects = self._request("GET", "/projects").get("data") or []
        if not projects:
            raise TeracError("No Terac project available to launch into.")
        self._project_id = str(projects[0]["id"])
        return self._project_id

    def get_quote(self, quote_id: str) -> Quote:
        return Quote.from_json(self._request("GET", f"/quotes/{quote_id}"))

    def get_opportunity(self, opportunity_id: str) -> Opportunity:
        raw = self._request("GET", f"/opportunities/{opportunity_id}")
        return Opportunity(
            opportunity_id=str(raw.get("id") or opportunity_id),
            status=str(raw.get("status") or ""),
            participants=int(_number(raw.get("num_participants"))),
        )

    def submissions(self, opportunity_id: str) -> tuple[list[Submission], str]:
        """Every response so far, plus the dashboard link for the demo."""
        raw = self._request("GET", f"/opportunities/{opportunity_id}/submissions")
        rows = [
            Submission(
                submission_id=str(s.get("id") or ""),
                status=str(s.get("status") or ""),
                participant_id=str(s.get("participant_id") or ""),
                screening_outcome=s.get("screening_outcome"),
                answers=list(s.get("screening_answers") or []),
            )
            for s in (raw.get("data") or [])
        ]
        return rows, str(raw.get("dashboard_url") or "")

    # ── writes ────────────────────────────────────────────────────────
    def quote(
        self,
        *,
        task_description: str,
        panel_description: str,
        submission_count: int,
        timeline_hours: int,
    ) -> Quote:
        """Price a job. Free — nothing is charged until launch()."""
        payload = {
            "taskDescription": task_description,
            "panelDescription": panel_description,
            "submissionCount": max(MIN_SUBMISSIONS, min(MAX_SUBMISSIONS, submission_count)),
            "timelineHours": max(MIN_TIMELINE_HOURS, min(MAX_TIMELINE_HOURS, timeline_hours)),
        }
        return Quote.from_json(self._request("POST", "/quotes", json=payload))

    def launch(self, quote_id: str, name: str, project_id: str | None = None) -> Opportunity:
        """**Spends money.** Turns a quote into a live opportunity."""
        raw = self._request(
            "POST",
            f"/quotes/{quote_id}/launch",
            json={"name": name[:200], "projectId": project_id or self.project_id()},
        )
        return Opportunity(
            opportunity_id=str(raw.get("opportunityId") or ""),
            status=str(raw.get("status") or "active"),
        )

    def stop(self, opportunity_id: str) -> None:
        self._request("POST", f"/opportunities/{opportunity_id}/stop")


class StubTeracClient:
    """Offline stand-in with the same surface. Spends nothing.

    Prices are invented but proportional, so budget logic can be exercised
    without a network or a bill. The default pipeline uses this.

    Real quotes measured against the live API for calibration: a simple
    four-cover ranking task priced at **$5.82 per reader** (40 readers =
    $232.80), while a 72-hour native-German literary review priced at **$29.71
    per expert**. Cost tracks task complexity far more than headcount, so treat
    the flat rate below as a placeholder and quote for real before promising
    an author a number.

    ``complete_after_polls`` exists purely so the pipeline is walkable end to
    end during development: real experts take 72 hours minimum, so without it
    a launched task never finishes and the run has no reachable end state. The
    submissions it returns are **simulated** and labelled as such — never show
    them as real panel results.
    """

    def __init__(
        self,
        *,
        cost_per_participant: float = 4.25,
        complete_after_polls: int | None = None,
    ) -> None:
        self.cost_per_participant = cost_per_participant
        self.complete_after_polls = complete_after_polls
        self.quotes: dict[str, Quote] = {}
        self.launched: dict[str, Opportunity] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.polls: dict[str, int] = {}
        self._n = 0

    def project_id(self) -> str:
        return "stub-project"

    def quote(self, *, task_description, panel_description, submission_count, timeline_hours):  # noqa: ANN001
        self._n += 1
        self.calls.append(("quote", {
            "task": task_description, "panel": panel_description,
            "count": submission_count, "hours": timeline_hours,
        }))
        count = max(MIN_SUBMISSIONS, min(MAX_SUBMISSIONS, submission_count))
        hours = max(MIN_TIMELINE_HOURS, min(MAX_TIMELINE_HOURS, timeline_hours))
        quote = Quote(
            quote_id=f"stub-quote-{self._n}",
            total_cost=round(count * self.cost_per_participant, 2),
            cost_per_participant=self.cost_per_participant,
            timeline_hours=hours,
            submission_count=count,
            reasoning="Stub pricing — no Terac call was made.",
        )
        self.quotes[quote.quote_id] = quote
        return quote

    def launch(self, quote_id, name, project_id=None):  # noqa: ANN001
        self.calls.append(("launch", {"quote_id": quote_id, "name": name}))
        opportunity = Opportunity(
            opportunity_id=f"stub-opp-{quote_id}", status="active",
            dashboard_url="https://terac.com/(stub)",
        )
        self.launched[opportunity.opportunity_id] = opportunity
        return opportunity

    def get_quote(self, quote_id):  # noqa: ANN001
        return self.quotes[quote_id]

    def get_opportunity(self, opportunity_id):  # noqa: ANN001
        base = self.launched.get(opportunity_id, Opportunity(opportunity_id, "active"))
        if self._is_simulated_complete(opportunity_id):
            return Opportunity(opportunity_id, "fulfilled", base.participants, base.dashboard_url)
        return base

    def submissions(self, opportunity_id):  # noqa: ANN001
        # Real panels take >= 72h, so "launched, nothing back yet" is the
        # honest default rather than fabricated expert responses. Simulation is
        # opt-in via complete_after_polls, for walking the pipeline end to end.
        self.polls[opportunity_id] = self.polls.get(opportunity_id, 0) + 1
        if not self._is_simulated_complete(opportunity_id):
            return [], "https://terac.com/(stub)"
        quote_id = opportunity_id.removeprefix("stub-opp-")
        count = self.quotes[quote_id].submission_count if quote_id in self.quotes else 1
        rows = [
            Submission(
                submission_id=f"{opportunity_id}-sub-{i}",
                status="awaiting_review",
                participant_id=f"simulated-participant-{i}",
                screening_outcome="passed",
                answers=[{"key": "simulated", "question": "(stub)",
                          "answer": "SIMULATED — not a real Terac response"}],
            )
            for i in range(1, count + 1)
        ]
        return rows, "https://terac.com/(stub)"

    def _is_simulated_complete(self, opportunity_id: str) -> bool:
        if self.complete_after_polls is None:
            return False
        return self.polls.get(opportunity_id, 0) >= self.complete_after_polls

    def stop(self, opportunity_id):  # noqa: ANN001
        self.calls.append(("stop", {"opportunity_id": opportunity_id}))
