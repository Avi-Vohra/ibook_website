"""The execution agent.

Takes an approved ActionPlan and runs it: AI work goes to Pioneer, human work
goes to Terac, and anything only the author can answer stops and waits.

The design constraint that shapes all of this is that **Terac takes at least 72
hours**. There is no version of this that runs to completion inside a request,
so the orchestrator is not a loop — it is durable state plus a ``tick()`` that
advances whatever is ready and returns. Call it from a button, a cron, or a
poll; it is safe to call repeatedly and never blocks on human work.

Each action moves through its own small state machine:

    AI_AUTOMATED     PENDING → RUNNING → DONE
    TERAC_EXPERT     PENDING → QUOTED → (author approves) → LAUNCHED
                             → COLLECTING → DONE
    AUTHOR_DECISION  PENDING → AWAITING_AUTHOR → DONE

The gap between QUOTED and LAUNCHED is deliberate: Terac prices a job for free
but charges on launch, so the author's approval sits exactly there. Nothing in
this module spends money without passing through ``approve()``.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
from pathlib import Path
from typing import Any, Callable

from bookit.action_planner import Action, ActionPlan, TeracOpportunity
from bookit.pioneer import PioneerClient, PioneerError, Route
from bookit.terac import Quote, StubTeracClient, TeracError

# ── task states ───────────────────────────────────────────────────────
PENDING = "pending"
RUNNING = "running"
QUOTED = "quoted"                    # priced by Terac, waiting on the author
LAUNCHED = "launched"                # live on the panel, costing money
COLLECTING = "collecting"            # responses arriving
AWAITING_AUTHOR = "awaiting_author"  # blocked on a decision only the author makes
DONE = "done"
FAILED = "failed"

TERMINAL = (DONE, FAILED)
# States where the orchestrator is waiting on someone else and has no work to do.
WAITING = (QUOTED, LAUNCHED, COLLECTING, AWAITING_AUTHOR)


@dataclass
class TaskState:
    """One action's execution record. Serialisable, because it outlives the process."""

    action_id: str
    title: str
    execution_type: str
    status: str = PENDING
    depends_on: list[str] = field(default_factory=list)

    # AI work
    output: str = ""
    model: str = ""

    # Terac work
    quote_id: str = ""
    quote_cost: float = 0.0
    quote_label: str = ""
    quote_expires_at: str = ""
    opportunity_id: str = ""
    dashboard_url: str = ""
    submissions_in: int = 0

    # Author work
    question: str = ""
    answer: str = ""

    error: str = ""
    updated_at: float = field(default_factory=time.time)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL

    @property
    def awaits_approval(self) -> bool:
        return self.status == QUOTED


@dataclass
class Run:
    """A whole plan, mid-execution."""

    run_id: str
    plan: dict[str, Any]                       # the ActionPlan as JSON
    tasks: dict[str, TaskState] = field(default_factory=dict)
    spent_usd: float = 0.0
    log: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    @property
    def quoted_total(self) -> float:
        """Everything Terac has priced but not yet been paid for."""
        return round(sum(t.quote_cost for t in self.tasks.values() if t.awaits_approval), 2)

    @property
    def is_finished(self) -> bool:
        return all(t.is_terminal for t in self.tasks.values())

    def pending_approvals(self) -> list[TaskState]:
        return [t for t in self.tasks.values() if t.awaits_approval]

    def open_questions(self) -> list[TaskState]:
        return [t for t in self.tasks.values() if t.status == AWAITING_AUTHOR]

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "plan": self.plan,
            "tasks": {k: asdict(v) for k, v in self.tasks.items()},
            "spent_usd": self.spent_usd,
            "log": self.log,
            "created_at": self.created_at,
        }

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> Run:
        return cls(
            run_id=raw["run_id"],
            plan=raw.get("plan") or {},
            tasks={k: TaskState(**v) for k, v in (raw.get("tasks") or {}).items()},
            spent_usd=float(raw.get("spent_usd") or 0.0),
            log=list(raw.get("log") or []),
            created_at=float(raw.get("created_at") or time.time()),
        )


class RunStore:
    """One JSON file per run.

    A database would be tidier, but a run is a single small document that is
    read and written whole, and files survive a Streamlit restart without any
    setup at all.
    """

    def __init__(self, directory: str | Path = ".bookit_runs") -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def path(self, run_id: str) -> Path:
        return self.directory / f"{run_id}.json"

    def save(self, run: Run) -> None:
        # Write-then-rename: a crash mid-write leaves the old run intact.
        temporary = self.path(run.run_id).with_suffix(".tmp")
        temporary.write_text(json.dumps(run.to_json(), indent=2), encoding="utf-8")
        temporary.replace(self.path(run.run_id))

    def load(self, run_id: str) -> Run:
        return Run.from_json(json.loads(self.path(run_id).read_text(encoding="utf-8")))

    def exists(self, run_id: str) -> bool:
        return self.path(run_id).exists()

    def list_runs(self) -> list[str]:
        return sorted(p.stem for p in self.directory.glob("*.json"))


# The AI worker. Real production agents (typesetting, EPUB, covers) will
# replace this; for now the model writes what it would have produced so the
# pipeline is exercisable end to end.
AI_WORKER_SYSTEM = """\
You are a Bookit production agent. You have been given one action from an approved publishing \
plan and you are executing it now.

Do the work you can actually do in text: write the copy, draft the metadata, build the glossary, \
outline the structure. Where the real deliverable is a binary file you cannot emit — an EPUB, a \
print PDF, a cover image — produce the exact content that would go into it, plus a one-line note \
naming the file that would be written.

Be concrete and specific to this book. No preamble, no restating the task, no offers to help \
further. Under 400 words."""


class Orchestrator:
    """Drives one run forward. Never blocks, never spends without approval."""

    def __init__(
        self,
        store: RunStore | None = None,
        pioneer: PioneerClient | None = None,
        terac: Any | None = None,
        *,
        auto_approve_under: float = 0.0,
    ) -> None:
        self.store = store or RunStore()
        self._pioneer = pioneer
        # Stub by default: nothing in a dev loop should be able to spend money
        # by accident. Pass a real TeracClient explicitly to go live.
        self.terac = terac if terac is not None else StubTeracClient()
        self.auto_approve_under = auto_approve_under

    @property
    def pioneer(self) -> PioneerClient:
        if self._pioneer is None:  # deferred so a stub run needs no API key
            self._pioneer = PioneerClient()
        return self._pioneer

    # ── lifecycle ─────────────────────────────────────────────────────
    def start(self, plan: ActionPlan, run_id: str | None = None) -> Run:
        """Turn an approved plan into a run of pending tasks."""
        run = Run(
            run_id=run_id or f"run-{int(time.time())}",
            plan=plan.to_json(),
            tasks={
                action.id: TaskState(
                    action_id=action.id,
                    title=action.title,
                    execution_type=action.execution_type,
                    depends_on=list(action.depends_on),
                )
                for action in plan.actions
            },
        )
        run.log.append(f"Run created with {len(run.tasks)} actions.")
        self.store.save(run)
        return run

    def tick(self, run: Run, plan: ActionPlan, *, limit: int = 25) -> Run:
        """Advance every task that can move right now, then return.

        Ready means: not terminal, not waiting on a human, and every dependency
        already done. Anything waiting on Terac or the author is simply skipped
        — that is the normal resting state of a run, not an error.
        """
        actions = {a.id: a for a in plan.actions}
        for _ in range(limit):
            ready = [
                task for task in run.tasks.values()
                if task.status == PENDING and self._dependencies_met(run, task)
            ]
            for task in ready:
                self._advance(run, task, actions.get(task.action_id))

            # Polling can finish a Terac task, which releases whatever was
            # waiting behind it — so collect inside the loop, not after it, or
            # those dependents sit pending until the next tick.
            collected = self._collect(run)
            self.store.save(run)
            if not ready and not collected:
                break
        return run

    @staticmethod
    def _dependencies_met(run: Run, task: TaskState) -> bool:
        return all(run.tasks[d].status == DONE for d in task.depends_on if d in run.tasks)

    def _advance(self, run: Run, task: TaskState, action: Action | None) -> None:
        if action is None:
            task.status, task.error = FAILED, "Action missing from plan."
            return
        try:
            if action.execution_type == "AUTHOR_DECISION":
                self._ask_author(run, task, action)
            elif action.terac_opportunity is not None:
                self._quote_terac(run, task, action.terac_opportunity)
            else:
                self._run_ai(run, task, action)
        except (PioneerError, TeracError) as exc:
            task.status, task.error = FAILED, str(exc)
            run.log.append(f"{task.action_id} failed: {exc}")
        task.updated_at = time.time()

    # ── the three kinds of work ───────────────────────────────────────
    def _run_ai(self, run: Run, task: TaskState, action: Action) -> None:
        task.status = RUNNING
        brief = {
            "action": action.title,
            "description": action.description,
            "product": action.product.name,
            "steps": [s.step for s in action.steps],
            "book": run.plan.get("book_summary", {}),
        }
        text, route = self._pioneer_text(
            AI_WORKER_SYSTEM,
            json.dumps(brief, indent=2, ensure_ascii=False),
        )
        task.model = route.model
        if not text.strip():
            # Done-with-nothing is the worst outcome: it looks like success and
            # releases every dependent task behind it.
            raise PioneerError("Production agent returned an empty deliverable.")
        task.output, task.status = text, DONE
        run.log.append(f"{task.action_id} done by {route.model} ({len(text)} chars).")

    def _ask_author(self, run: Run, task: TaskState, action: Action) -> None:
        task.status = AWAITING_AUTHOR
        task.question = action.description or action.title
        run.log.append(f"{task.action_id} waiting on the author.")

    def _quote_terac(self, run: Run, task: TaskState, opportunity: TeracOpportunity) -> None:
        """Price the job. Free — the money moves in approve()."""
        quote: Quote = self.terac.quote(
            task_description=opportunity.task_brief(),
            panel_description=opportunity.panel_brief(),
            submission_count=opportunity.expert_count,
            timeline_hours=opportunity.timeline_hours,
        )
        task.quote_id = quote.quote_id
        task.quote_cost = quote.total_cost
        task.quote_label = quote.label
        task.quote_expires_at = quote.expires_at
        task.status = QUOTED
        run.log.append(f"{task.action_id} quoted by Terac: {quote.label}.")

        if self.auto_approve_under and quote.total_cost <= self.auto_approve_under:
            run.log.append(
                f"{task.action_id} auto-approved (under ${self.auto_approve_under:.2f})."
            )
            self.approve(run, task.action_id, opportunity)

    def approve(
        self, run: Run, action_id: str, spec: TeracOpportunity | None = None
    ) -> Run:
        """**Spends money.** Launch a quoted opportunity onto the Terac panel.

        Terac quotes expire an hour after they are issued, and the author is
        under no obligation to decide inside an hour. Pass ``spec`` and a stale
        quote is refreshed at the current price instead of failing — the author
        sees the new number in the log if it moved.
        """
        task = run.tasks[action_id]
        if task.status != QUOTED:
            raise ValueError(f"{action_id} is {task.status}, not awaiting approval.")

        if spec is not None and _quote_expired(task.quote_expires_at):
            fresh = self.terac.quote(
                task_description=spec.task_brief(),
                panel_description=spec.panel_brief(),
                submission_count=spec.expert_count,
                timeline_hours=spec.timeline_hours,
            )
            was = task.quote_cost
            task.quote_id, task.quote_cost = fresh.quote_id, fresh.total_cost
            task.quote_label, task.quote_expires_at = fresh.label, fresh.expires_at
            run.log.append(
                f"{action_id}: quote had expired; re-quoted at ${fresh.total_cost:.2f}"
                + (f" (was ${was:.2f})." if abs(fresh.total_cost - was) > 0.005 else ".")
            )

        opportunity = self.terac.launch(task.quote_id, task.title)
        task.opportunity_id = opportunity.opportunity_id
        task.dashboard_url = opportunity.dashboard_url
        task.status = LAUNCHED
        run.spent_usd = round(run.spent_usd + task.quote_cost, 2)
        run.log.append(f"{task.action_id} launched on Terac (${task.quote_cost:.2f}).")
        task.updated_at = time.time()
        self.store.save(run)
        return run

    def decline(self, run: Run, action_id: str) -> Run:
        """Drop a quoted human task the author does not want to pay for."""
        task = run.tasks[action_id]
        task.status, task.error = FAILED, "Declined by the author."
        run.log.append(f"{task.action_id} declined.")
        self.store.save(run)
        return run

    def answer(self, run: Run, action_id: str, answer: str) -> Run:
        """Record the author's decision and unblock whatever depended on it."""
        task = run.tasks[action_id]
        task.answer, task.status = answer, DONE
        task.updated_at = time.time()
        run.log.append(f"{task.action_id} answered by the author.")
        self.store.save(run)
        return run

    def _collect(self, run: Run) -> bool:
        """Poll launched opportunities. Returns True if any task changed state."""
        changed = False
        for task in run.tasks.values():
            if task.status not in (LAUNCHED, COLLECTING) or not task.opportunity_id:
                continue
            try:
                submissions, dashboard = self.terac.submissions(task.opportunity_id)
            except TeracError as exc:
                run.log.append(f"{task.action_id} poll failed: {exc}")
                continue
            task.dashboard_url = dashboard or task.dashboard_url
            complete = [s for s in submissions if s.is_complete]
            before = task.status
            task.submissions_in = len(complete)
            if complete:
                task.status = COLLECTING
            state = self.terac.get_opportunity(task.opportunity_id)
            if state.is_done:
                task.status = DONE
                run.log.append(
                    f"{task.action_id} complete: {len(complete)} expert responses."
                )
            if task.status != before:
                changed = True
                task.updated_at = time.time()
        return changed

    # ── Pioneer plumbing ──────────────────────────────────────────────
    def _pioneer_text(self, system: str, user: str) -> tuple[str, Route]:
        """A plain-text completion. Raises rather than returning nothing.

        Kept as its own seam so tests can swap the model out entirely.
        """
        return self.pioneer.complete_text(system, user, temperature=0.4)


def _quote_expired(expires_at: str, *, margin_seconds: int = 120) -> bool:
    """Has this quote lapsed, or is it about to?

    The margin covers the round trip: a quote with ten seconds left will be
    dead by the time the launch request lands.
    """
    if not expires_at:
        return False  # the stub issues no expiry; nothing to refresh
    try:
        deadline = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    return datetime.now(UTC) >= deadline - timedelta(seconds=margin_seconds)


def summarise(run: Run) -> str:
    """A one-glance status line per task, for CLI and logs."""
    icon = {
        DONE: "✓", FAILED: "✗", QUOTED: "$", LAUNCHED: "→",
        COLLECTING: "◐", AWAITING_AUTHOR: "?", PENDING: "·", RUNNING: "◐",
    }
    lines = []
    for task in run.tasks.values():
        detail = ""
        if task.status == QUOTED:
            detail = f"  {task.quote_label} — needs approval"
        elif task.status in (LAUNCHED, COLLECTING):
            detail = f"  live on Terac, {task.submissions_in} responses in"
        elif task.status == AWAITING_AUTHOR:
            detail = f"  {task.question[:60]}"
        elif task.status == FAILED:
            detail = f"  {task.error[:70]}"
        lines.append(f"  {icon.get(task.status, '·')} {task.action_id:4} {task.title[:52]}{detail}")
    return "\n".join(lines)
