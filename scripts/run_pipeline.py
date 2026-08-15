"""Bookit end to end: plan → execute → report.

    # cheap models, stubbed Terac, spends nothing on the panel
    BOOKIT_BUDGET=1 python scripts/run_pipeline.py

    # same, and auto-approve human tasks under $50 so the run advances
    BOOKIT_BUDGET=1 python scripts/run_pipeline.py --auto-approve 50

    # real Terac: prices for free, then STOPS and asks before spending
    BOOKIT_BUDGET=1 python scripts/run_pipeline.py --live-terac

    # resume a run later (Terac work takes >= 72h, so this is the normal case)
    python scripts/run_pipeline.py --resume run-1234567890

Pioneer costs a few cents per run in budget mode. Terac only costs money after
an explicit approval, and never in the default stub mode.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bookit import content  # noqa: E402
from bookit.action_planner import create_action_plan, parse_plan, request_from_frontend  # noqa: E402
from bookit.orchestrator import Orchestrator, RunStore, summarise  # noqa: E402
from bookit.pioneer import PioneerClient, PioneerError, default_model  # noqa: E402
from bookit.terac import TeracClient, TeracError  # noqa: E402

OWNER_TAG = {"ai": "AI", "expert": "TERAC", "author": "YOU"}


def build_plan(args) -> tuple:  # noqa: ANN001
    request = request_from_frontend(
        ctx_text=args.context,
        services={s.strip() for s in args.services.split(",") if s.strip()},
        book_file={"name": content.SAMPLE_FILE["name"],
                   "size": content.SAMPLE_FILE["size"],
                   "meta": content.SAMPLE_FILE["detail"]},
    )
    print(f"Planning with {default_model()} …")
    plan = create_action_plan(request, PioneerClient())
    route = plan.route
    print(f"  routed to {route.model} · {route.completion_tokens} out · {route.latency_s}s")
    if route.baseline_model:
        print(f"  saved ${route.saved_usd:.4f} vs {route.baseline_model}")
    return plan, request


def show_plan(plan) -> None:  # noqa: ANN001
    summary = plan.book_summary
    print(f"\n{'='*72}\n{summary.title} — {summary.genre}\n{plan.plan_summary}\n")
    print(f"{len(plan.actions)} actions · {len(plan.human_actions)} involve real people\n")
    for action in plan.actions:
        deps = f"  (after {', '.join(action.depends_on)})" if action.depends_on else ""
        print(f"  {action.id}  {action.title}{deps}")
        print(f"        → {action.product.name}  [{action.priority}]")
        for step in action.steps:                      # the collapsed detail view
            print(f"          {OWNER_TAG.get(step.owner, 'AI'):5} {step.step}")
        if opportunity := action.terac_opportunity:
            print(f"          TERAC {opportunity.expert_count} × {opportunity.expert_role} "
                  f"· {opportunity.timeline_hours}h")
        print()
    if plan.warnings:
        print("Plan warnings:")
        for warning in plan.warnings:
            print(f"  ! {warning}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--services", default="publish,translate,market")
    parser.add_argument("--context", default=content.SAMPLE_CTX)
    parser.add_argument("--auto-approve", type=float, default=0.0,
                        help="auto-approve Terac quotes at or under this many dollars")
    parser.add_argument("--live-terac", action="store_true",
                        help="use the real Terac API instead of the stub")
    parser.add_argument("--simulate-experts", action="store_true",
                        help="stub only: let launched Terac jobs return SIMULATED responses "
                             "so the pipeline can be walked to completion")
    parser.add_argument("--resume", metavar="RUN_ID", help="continue an existing run")
    parser.add_argument("--answer", nargs=2, metavar=("ACTION_ID", "TEXT"),
                        help="answer an author decision on a resumed run")
    parser.add_argument("--approve", metavar="ACTION_ID", help="approve one quoted Terac task")
    args = parser.parse_args()

    store = RunStore(ROOT / ".bookit_runs")
    terac = None
    if args.live_terac:
        try:
            terac = TeracClient()
            print(f"Terac: live (project {terac.project_id()})")
        except TeracError as exc:
            print(f"Terac unavailable: {exc}", file=sys.stderr)
            return 1
    else:
        from bookit.terac import StubTeracClient

        terac = StubTeracClient(complete_after_polls=1 if args.simulate_experts else None)
        note = " · expert responses SIMULATED" if args.simulate_experts else ""
        print(f"Terac: stubbed (no money can move){note}")

    orchestrator = Orchestrator(store, terac=terac, auto_approve_under=args.auto_approve)

    if args.resume:
        run = store.load(args.resume)
        plan = parse_plan(run.plan)
        print(f"Resumed {run.run_id}\n")
    else:
        try:
            plan, _ = build_plan(args)
        except PioneerError as exc:
            print(f"Planning failed: {exc}", file=sys.stderr)
            return 1
        show_plan(plan)
        run = orchestrator.start(plan)
        print(f"Run {run.run_id} started\n")

    if args.answer:
        orchestrator.answer(run, args.answer[0], args.answer[1])
    if args.approve:
        try:
            orchestrator.approve(run, args.approve)
        except (ValueError, TeracError) as exc:
            print(f"Approve failed: {exc}", file=sys.stderr)
            return 1

    run = orchestrator.tick(run, plan)

    print("Execution state:")
    print(summarise(run))

    approvals = run.pending_approvals()
    questions = run.open_questions()
    print(f"\nSpent so far : ${run.spent_usd:.2f}")
    if approvals:
        print(f"Awaiting you : ${run.quoted_total:.2f} across "
              f"{len(approvals)} Terac task(s) — nothing charged yet")
        for task in approvals:
            print(f"    --approve {task.action_id}    {task.quote_label}")
    for task in questions:
        print(f"    --answer {task.action_id} \"…\"    {task.question[:60]}")

    if run.is_finished:
        print("\nRun complete.")
    else:
        print(f"\nResume with:  python scripts/run_pipeline.py --resume {run.run_id}")
        print("Terac needs at least 72h, so human tasks stay open across sessions.")

    for task in run.tasks.values():
        if task.output:
            print(f"\n── {task.action_id} {task.title} ({task.model}) "
                  f"{'─' * max(0, 30 - len(task.title))}")
            print(task.output[:700])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
