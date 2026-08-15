"""Generate a real action plan through Pioneer and print it.

    PIONEER_API_KEY=... python scripts/plan_demo.py
    PIONEER_API_KEY=... python scripts/plan_demo.py --services publish,translate,market
    PIONEER_API_KEY=... python scripts/plan_demo.py --json > plan.json

Costs one API call. Use it to see what the planner actually produces before
wiring it into the app.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bookit import content  # noqa: E402
from bookit.action_planner import create_action_plan, request_from_frontend  # noqa: E402
from bookit.pioneer import PioneerClient, PioneerError  # noqa: E402

BADGE = {"agent": "AI", "human": "TERAC", "author": "AUTHOR"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--services", default="publish,translate,market",
                        help="comma-separated: publish, translate, market")
    parser.add_argument("--context", default=content.SAMPLE_CTX,
                        help="the author's description of their book")
    parser.add_argument("--model", default=None,
                        help="pin a model instead of routing (default: pioneer/auto)")
    parser.add_argument("--json", action="store_true", help="print raw JSON only")
    args = parser.parse_args()

    request = request_from_frontend(
        ctx_text=args.context,
        services={s.strip() for s in args.services.split(",") if s.strip()},
        book_file={"name": content.SAMPLE_FILE["name"],
                   "size": content.SAMPLE_FILE["size"],
                   "meta": content.SAMPLE_FILE["detail"]},
    )

    try:
        plan = create_action_plan(request, PioneerClient(model=args.model))
    except PioneerError as exc:
        print(f"Pioneer failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(plan.to_json(), indent=2, ensure_ascii=False))
        return 0

    route = plan.route
    print(f"\nRouted to : {route.model}")
    if route.baseline_model:
        print(f"Baseline  : {route.baseline_model}  →  saved ${route.saved_usd:.4f} on this call")
    print(f"Tokens    : {route.prompt_tokens} in / {route.completion_tokens} out "
          f"in {route.latency_s}s ({route.attempts} attempt(s))")

    summary = plan.book_summary
    print(f"\n{summary.title} — {summary.genre}, {summary.current_language}")
    print(f"Audience  : {summary.target_audience}")
    print(f"Goal      : {summary.author_goal}")
    print(f"\n{plan.plan_summary}\n")
    print(f"{len(plan.actions)} actions: {len(plan.ai_actions)} AI, "
          f"{len(plan.human_actions)} human, {len(plan.author_decisions)} author\n")

    for action in plan.actions:
        deps = f"  (after {', '.join(action.depends_on)})" if action.depends_on else ""
        flag = "" if action.is_atomic else "  ⚠ not atomic"
        print(f"[{BADGE[action.owner]:6}] {action.id}  {action.title}{deps}{flag}")
        print(f"          {action.priority} · {action.estimated_scope}")
        artifact = action.artifact
        if artifact.name:
            fmt = f" ({artifact.format})" if artifact.format else ""
            print(f"          → {artifact.name}{fmt}")
        elif action.deliverables:
            print(f"          → {'; '.join(action.deliverables)}")
        if opp := action.terac_opportunity:
            print(f"          TERAC: {opp.opportunity_title}")
            print(f"                 {opp.expert_role} · {', '.join(opp.language_requirements)}")
        print()

    atomic = len(plan.actions) - len(plan.non_atomic_actions)
    print(f"Atomicity : {atomic}/{len(plan.actions)} actions produce exactly one named artifact")
    print(f"Artifacts : {len(plan.artifacts)} products\n")

    if plan.warnings:
        print("Warnings:")
        for warning in plan.warnings:
            print(f"  ! {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
